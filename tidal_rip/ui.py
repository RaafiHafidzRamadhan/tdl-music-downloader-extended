"""Main application window: navigation shell, login, previews, and session state."""

import asyncio
import glob
import io
import json
import os
import subprocess
import threading
import time
import urllib.parse
from tkinter import messagebox

import aiohttp
import customtkinter as CTk
import imageio_ffmpeg
from PIL import Image

from .components import (
    chip_label,
    format_specs,
    ghost_button,
    open_browser,
    open_in_file_manager,
    primary_button,
    soft_button,
)
from .downloader import DownloadManager
from .player_views import PlayerViewMixin
from .queue_views import QueueViewMixin
from .search_views import SearchViewMixin
from .settings_views import SettingsViewMixin
from .theme import COLORS, SOURCE_META, setup_theme, source_meta, ui_font
from .widgets import rounded_image, truncate_middle
from .youtube_service import YouTubeService

try:
    import winsound
except ImportError:  # pragma: no cover - Windows is the primary target
    winsound = None


setup_theme()

SOURCE_ORDER = ("tidal", "youtube")
SOURCE_ICONS = {"tidal": "≈", "youtube": "▶"}
NAV_ITEMS = {
    "search": ("⌕", "Search"),
    "queue": ("↓", "Downloads"),
    "player": ("♫", "Player"),
    "settings": ("⚙", "Settings"),
}


class AppUI(SearchViewMixin, QueueViewMixin, PlayerViewMixin, SettingsViewMixin, CTk.CTk):
    """Main window: top source selector, sidebar library controls, and shared queue."""

    def __init__(self, api, config, async_loop):
        super().__init__()
        self.api = api
        self.config = config
        self.async_loop = async_loop
        self.downloader = DownloadManager(self.api, self.config)
        self.youtube_service = YouTubeService(self.api, self.config)

        self.source = "tidal"
        self.active_view = "search"
        self._search_gen = 0
        self._search_busy = False
        self._shutdown = False
        self._closing = False
        self.login_in_progress = False

        self.queue_items = {}
        self.queue_order = []
        self.pending_downloads = []

        self._image_refs = []
        self._image_cache = {}
        self._specs_cache = {}

        self.preview_proc = None
        self.preview_tid = None
        self.active_pbtn = None
        self._preview_gen = 0

        self.init_player_state()

        self.title("TDL Music — Tidal · YouTube")
        self._fit_window()
        self.configure(fg_color=COLORS["bg"])
        self.protocol("WM_DELETE_WINDOW", self.on_closing)

        self.setup_layout()
        self.run_async(self.download_worker())
        self.check_login_status()
        self.after(500, self.load_session)

    # ------------------------------------------------------------------ async

    def run_async(self, coro):
        """Schedules a coroutine on the shared background event loop."""
        try:
            return asyncio.run_coroutine_threadsafe(coro, self.async_loop)
        except RuntimeError:
            return None

    def _focus_search(self):
        self.switch_view("search")
        if hasattr(self, "search_entry"):
            self.search_entry.focus_set()

    # ----------------------------------------------------------------- layout

    def _fit_window(self):
        work_width, work_height = self._work_area()
        width = max(980, min(1240, work_width - 60))
        height = max(600, min(760, work_height - 90))
        x = max(0, (work_width - width) // 2)
        y = max(0, (work_height - height) // 2)
        self.geometry(f"{width}x{height}+{x}+{y}")
        self.minsize(980, 600)

    def _work_area(self):
        """Returns the usable screen size in Tk units, excluding the Windows taskbar."""
        try:
            import ctypes
            from ctypes import wintypes

            rect = wintypes.RECT()
            if ctypes.windll.user32.SystemParametersInfoW(
                0x0030, 0, ctypes.byref(rect), 0
            ):
                scale = float(self._get_window_scaling() or 1.0)
                width = int(round((rect.right - rect.left) / scale))
                height = int(round((rect.bottom - rect.top) / scale))
                if width > 0 and height > 0:
                    return width, height
        except Exception:
            pass
        return self.winfo_screenwidth(), self.winfo_screenheight()

    def setup_layout(self):
        self.grid_rowconfigure(2, weight=1)
        self.grid_columnconfigure(2, weight=1)

        self._build_navbar()
        CTk.CTkFrame(self, fg_color=COLORS["border"], height=1).grid(
            row=1, column=0, columnspan=3, sticky="ew"
        )
        self._build_sidebar()
        CTk.CTkFrame(self, fg_color=COLORS["border"], width=1).grid(
            row=2, column=1, sticky="ns"
        )

        self.main_container = CTk.CTkFrame(self, fg_color="transparent")
        self.main_container.grid(
            row=2, column=2, sticky="nsew", padx=26, pady=(18, 22)
        )
        self.main_container.grid_rowconfigure(0, weight=1)
        self.main_container.grid_columnconfigure(0, weight=1)

        self.create_search_view()
        self.create_queue_view()
        self.create_player_view()
        self.create_settings_view()

        self.bind("<Control-f>", lambda _event: self._focus_search())
        self.bind("<Control-Key-1>", lambda _event: self.switch_view("search"))
        self.bind("<Control-Key-2>", lambda _event: self.switch_view("queue"))
        self.bind("<Control-Key-3>", lambda _event: self.switch_view("player"))
        self.bind("<Control-Key-4>", lambda _event: self.switch_view("settings"))

        self.switch_view("search")
        self.switch_source("tidal", initial=True)
        self._display_folder()

    def _build_navbar(self):
        navbar = CTk.CTkFrame(
            self, fg_color=COLORS["surface"], corner_radius=0, height=74
        )
        navbar.grid(row=0, column=0, columnspan=3, sticky="ew")
        navbar.grid_propagate(False)
        navbar.grid_columnconfigure(1, weight=1)

        brand = CTk.CTkFrame(navbar, fg_color="transparent")
        brand.grid(row=0, column=0, sticky="w", padx=(24, 0), pady=14)
        CTk.CTkLabel(
            brand,
            text="♪",
            width=42,
            height=42,
            corner_radius=13,
            fg_color=COLORS["accent"],
            text_color="#FFFFFF",
            font=ui_font(19, "bold"),
        ).pack(side="left", padx=(0, 12))
        brand_text = CTk.CTkFrame(brand, fg_color="transparent")
        brand_text.pack(side="left")
        CTk.CTkLabel(
            brand_text,
            text="TDL Music",
            font=ui_font(17, "bold"),
            text_color=COLORS["text"],
            anchor="w",
        ).pack(anchor="w")
        CTk.CTkLabel(
            brand_text,
            text="TIDAL · YOUTUBE",
            font=ui_font(8, "bold"),
            text_color=COLORS["muted"],
            anchor="w",
        ).pack(anchor="w", pady=(1, 0))

        self.source_buttons = {}
        selector = CTk.CTkFrame(
            navbar, fg_color=COLORS["surface_muted"], corner_radius=12
        )
        selector.grid(row=0, column=1, padx=24, pady=16)
        for key in SOURCE_ORDER:
            meta = source_meta(key)
            button = CTk.CTkButton(
                selector,
                text=f"{SOURCE_ICONS[key]}  {meta['label']}",
                width=102,
                height=34,
                corner_radius=9,
                fg_color="transparent",
                hover_color=COLORS["surface_hover"],
                text_color=COLORS["text_secondary"],
                font=ui_font(11, "bold"),
                command=lambda source=key: self.switch_source(source),
            )
            button.pack(side="left", padx=3, pady=3)
            self.source_buttons[key] = button

        right = CTk.CTkFrame(navbar, fg_color="transparent")
        right.grid(row=0, column=2, sticky="e", padx=(0, 24))
        CTk.CTkLabel(
            right,
            text="OUTPUT",
            font=ui_font(9, "bold"),
            text_color=COLORS["muted"],
        ).pack(side="left", padx=(0, 8))
        self.format_chip = chip_label(right, "Hi-Res FLAC", height=26)
        self.format_chip.pack(side="left")

    def _build_sidebar(self):
        sidebar = CTk.CTkFrame(
            self, width=248, fg_color=COLORS["surface"], corner_radius=0
        )
        sidebar.grid(row=2, column=0, sticky="nsew")
        sidebar.grid_propagate(False)

        CTk.CTkLabel(
            sidebar,
            text="WORKSPACE",
            font=ui_font(9, "bold"),
            text_color=COLORS["muted"],
            anchor="w",
        ).pack(fill="x", padx=22, pady=(20, 8))

        self.nav_buttons = {}
        for name, (icon, label) in NAV_ITEMS.items():
            button = CTk.CTkButton(
                sidebar,
                text=f"{icon}   {label}",
                anchor="w",
                height=38,
                corner_radius=10,
                fg_color="transparent",
                hover_color=COLORS["surface_hover"],
                text_color=COLORS["text_secondary"],
                font=ui_font(12),
                command=lambda target=name: self.switch_view(target),
            )
            button.pack(fill="x", padx=12, pady=2)
            self.nav_buttons[name] = button

        CTk.CTkFrame(sidebar, fg_color="transparent", height=1).pack(
            fill="both", expand=True
        )

        folder_card = CTk.CTkFrame(
            sidebar,
            fg_color=COLORS["surface_muted"],
            corner_radius=14,
            border_width=1,
            border_color=COLORS["border"],
        )
        folder_card.pack(fill="x", padx=14, pady=(0, 10))
        folder_body = CTk.CTkFrame(folder_card, fg_color="transparent")
        folder_body.pack(fill="x", padx=14, pady=12)

        CTk.CTkLabel(
            folder_body,
            text="DOWNLOAD FOLDER",
            font=ui_font(9, "bold"),
            text_color=COLORS["muted"],
            anchor="w",
        ).pack(fill="x", anchor="w")
        self.folder_name_lbl = CTk.CTkLabel(
            folder_body,
            text="",
            font=ui_font(13, "bold"),
            text_color=COLORS["text"],
            anchor="w",
        )
        self.folder_name_lbl.pack(fill="x", anchor="w", pady=(4, 0))
        self.folder_path_lbl = CTk.CTkLabel(
            folder_body,
            text="",
            font=ui_font(9),
            text_color=COLORS["text_secondary"],
            anchor="w",
            justify="left",
            wraplength=192,
        )
        self.folder_path_lbl.pack(fill="x", anchor="w", pady=(1, 8))

        folder_actions = CTk.CTkFrame(folder_body, fg_color="transparent")
        folder_actions.pack(fill="x")
        soft_button(
            folder_actions,
            "Change",
            command=self.browse_download_folder,
            width=84,
            height=30,
        ).pack(side="left")
        ghost_button(
            folder_actions,
            "Open",
            command=lambda: open_in_file_manager(self.config.download_directory),
            width=72,
            height=30,
        ).pack(side="left", padx=(8, 0))

        account_card = CTk.CTkFrame(
            sidebar,
            fg_color=COLORS["surface"],
            corner_radius=14,
            border_width=1,
            border_color=COLORS["border"],
        )
        account_card.pack(fill="x", padx=14, pady=(0, 12))
        account_body = CTk.CTkFrame(account_card, fg_color="transparent")
        account_body.pack(fill="x", padx=14, pady=12)

        account_head = CTk.CTkFrame(account_body, fg_color="transparent")
        account_head.pack(fill="x")
        self.account_dot = CTk.CTkLabel(
            account_head,
            text="●",
            width=14,
            font=ui_font(9, "bold"),
            text_color=COLORS["muted"],
        )
        self.account_dot.pack(side="left")
        CTk.CTkLabel(
            account_head,
            text="TIDAL ACCOUNT",
            font=ui_font(9, "bold"),
            text_color=COLORS["muted"],
        ).pack(side="left", padx=(4, 0))

        self.login_status_lbl = CTk.CTkLabel(
            account_body,
            text="Not connected",
            font=ui_font(11, "bold"),
            text_color=COLORS["text_secondary"],
            anchor="w",
            justify="left",
            wraplength=190,
        )
        self.login_status_lbl.pack(fill="x", anchor="w", pady=(6, 8))

        self.login_btn = primary_button(
            account_body,
            "Log in",
            command=self.handle_login_click,
            width=190,
            height=32,
        )
        self.login_btn.pack(fill="x")

        CTk.CTkLabel(
            sidebar,
            text="TDL Music · Tidal & YouTube",
            font=ui_font(9),
            text_color=COLORS["muted"],
            anchor="w",
        ).pack(fill="x", padx=22, pady=(0, 16))

    # ------------------------------------------------------------------ views

    def switch_view(self, view_name):
        if not hasattr(self, "search_view"):
            return
        self.active_view = view_name
        for name, view in (
            ("search", self.search_view),
            ("queue", self.queue_view),
            ("player", self.player_view),
            ("settings", self.settings_view),
        ):
            try:
                view.grid_forget()
            except Exception:
                pass
            self._style_nav_button(name, name == view_name)

        view = {
            "search": self.search_view,
            "queue": self.queue_view,
            "player": self.player_view,
            "settings": self.settings_view,
        }.get(view_name, self.search_view)
        view.grid(row=0, column=0, sticky="nsew")

        if view_name == "queue":
            self.update_queue_summary()
        elif view_name == "player":
            self.player_on_view_opened()
        elif view_name == "settings":
            self._refresh_settings_account()
            self._sync_settings_folder()
        elif view_name == "search":
            self._update_search_hint()
            self.after(80, self._focus_search_entry)

    def _focus_search_entry(self):
        try:
            self.search_entry.focus_set()
        except Exception:
            pass

    def _style_nav_button(self, name, active):
        button = getattr(self, "nav_buttons", {}).get(name)
        if button is None:
            return
        icon, label = NAV_ITEMS[name]
        if active:
            button.configure(
                fg_color=COLORS["accent_soft"],
                text_color=COLORS["accent_text"],
                font=ui_font(12, "bold"),
            )
        else:
            button.configure(
                fg_color="transparent",
                text_color=COLORS["text_secondary"],
                font=ui_font(12),
            )
            if name == "queue":
                button.configure(text=f"{icon}   {label}")

    def switch_source(self, source, initial=False):
        if source not in SOURCE_META:
            return
        changed = source != self.source
        self.source = source

        for key, button in getattr(self, "source_buttons", {}).items():
            meta = source_meta(key)
            if key == source:
                button.configure(
                    fg_color=COLORS["surface"],
                    hover_color=COLORS["surface"],
                    text_color=meta["color"],
                    border_width=1,
                    border_color=COLORS["border"],
                    font=ui_font(11, "bold"),
                )
            else:
                button.configure(
                    fg_color="transparent",
                    hover_color=COLORS["surface_hover"],
                    text_color=COLORS["text_secondary"],
                    border_width=0,
                    font=ui_font(11),
                )

        if hasattr(self, "format_chip"):
            meta = source_meta(source)
            self.format_chip.configure(
                text=meta["format"], fg_color=meta["soft"], text_color=meta["color"]
            )
        if hasattr(self, "search_btn"):
            self._update_search_copy()

        if initial:
            self._show_source_intro()
            return
        self.switch_view("search")
        if changed:
            self._show_source_intro()

    def _display_folder(self):
        path = getattr(self.config, "download_directory", "") or ""
        if hasattr(self, "folder_name_lbl"):
            name = os.path.basename(os.path.normpath(path)) or path or "Not set"
            self.folder_name_lbl.configure(text=truncate_middle(name, 26))
        if hasattr(self, "folder_path_lbl"):
            self.folder_path_lbl.configure(text=truncate_middle(path, 34))
        if hasattr(self, "open_folder_btn") and self.open_folder_btn.winfo_exists():
            self.open_folder_btn.configure(
                command=lambda: open_in_file_manager(self.config.download_directory)
            )
        entry = getattr(self, "settings_folder_entry", None)
        if entry is not None and entry.winfo_exists():
            entry.delete(0, "end")
            entry.insert(0, path)

    def _sync_settings_folder(self):
        entry = getattr(self, "settings_folder_entry", None)
        if entry is not None and entry.winfo_exists():
            entry.delete(0, "end")
            entry.insert(0, self.config.download_directory)

    # ------------------------------------------------------------------ login

    def check_login_status(self):
        if self.config.access_token:
            if self.config.token_expiry - time.time() < 3600:
                self.run_async(self.refresh_token_on_load())
            else:
                self.run_async(self.verify_session_on_load())
        else:
            self.update_login_display(False)

    async def verify_session_on_load(self):
        try:
            await self.api.fetch_session_info()
            self.after(0, self.update_login_display, True)
        except Exception as exc:
            print(f"Session verification failed on startup: {exc}")
            self.config.clear_session()
            self.after(0, self.update_login_display, False)

    async def refresh_token_on_load(self):
        try:
            await self.api.refresh_token()
            self.after(0, self.update_login_display, True)
        except Exception as exc:
            print(f"Token refresh failed on startup: {exc}")
            self.config.clear_session()
            self.after(0, self.update_login_display, False)

    def update_login_display(self, logged_in):
        logged_in = bool(logged_in and self.config.access_token)
        if hasattr(self, "login_status_lbl"):
            if logged_in:
                user = self.config.user_name or f"User {self.config.user_id}"
                self.login_status_lbl.configure(
                    text=user, text_color=COLORS["text"]
                )
            else:
                self.login_status_lbl.configure(
                    text="Not connected", text_color=COLORS["text_secondary"]
                )
        if hasattr(self, "account_dot"):
            self.account_dot.configure(
                text_color=COLORS["success"] if logged_in else COLORS["muted"]
            )
        if hasattr(self, "login_btn"):
            self.login_btn.configure(state="normal")
            if logged_in:
                self.login_btn.configure(
                    text="Log out",
                    fg_color=COLORS["accent_soft"],
                    hover_color=COLORS["surface_hover"],
                    text_color=COLORS["accent_text"],
                    border_width=0,
                )
            else:
                self.login_btn.configure(
                    text="Log in",
                    fg_color=COLORS["accent"],
                    hover_color=COLORS["accent_hover"],
                    text_color="#FFFFFF",
                    border_width=0,
                )
        if hasattr(self, "settings_account_btn"):
            self._refresh_settings_account()
        if hasattr(self, "search_hint_lbl"):
            self._update_search_hint()

    def handle_login_click(self):
        if self.config.access_token:
            if messagebox.askyesno("Log out", "Disconnect your Tidal account?"):
                self.config.clear_session()
                self.update_login_display(False)
                messagebox.showinfo("Logged out", "Your Tidal session has been cleared.")
            return
        if self.login_in_progress:
            return
        self.start_pkce_login()

    def start_pkce_login(self):
        self.login_in_progress = True
        if hasattr(self, "login_btn") and self.login_btn.winfo_exists():
            self.login_btn.configure(state="disabled", text="Connecting…")
        try:
            login_url = self.api.get_pkce_login_url()
        except Exception as exc:
            self.login_in_progress = False
            self.update_login_display(False)
            messagebox.showerror("Login failed", f"Could not start Tidal login:\n{exc}")
            return
        open_browser(login_url, self.config.login_browser)
        self.show_pkce_redirect_dialog()

    def show_pkce_redirect_dialog(self):
        dialog = CTk.CTkToplevel(self)
        dialog.title("Tidal login")
        dialog.geometry("620x350")
        dialog.resizable(False, False)
        dialog.configure(fg_color=COLORS["bg"])
        dialog.transient(self)
        dialog.grab_set()
        dialog.update_idletasks()
        try:
            x = self.winfo_x() + (self.winfo_width() - 620) // 2
            y = self.winfo_y() + (self.winfo_height() - 350) // 2
            dialog.geometry(f"+{max(0, x)}+{max(0, y)}")
        except Exception:
            pass

        def close_dialog():
            self.login_in_progress = False
            if hasattr(self, "login_btn") and self.login_btn.winfo_exists():
                self.login_btn.configure(state="normal")
            self.update_login_display(bool(self.config.access_token))
            try:
                dialog.destroy()
            except Exception:
                pass

        dialog.protocol("WM_DELETE_WINDOW", close_dialog)
        dialog.bind("<Escape>", lambda _event: close_dialog())
        dialog.after(80, dialog.focus_force)

        body = CTk.CTkFrame(
            dialog,
            fg_color=COLORS["surface"],
            corner_radius=18,
            border_width=1,
            border_color=COLORS["border"],
        )
        body.pack(fill="both", expand=True, padx=18, pady=18)
        inner = CTk.CTkFrame(body, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=22, pady=20)

        chip_label(
            inner,
            "TIDAL LOGIN",
            fg_color=source_meta("tidal")["soft"],
            text_color=source_meta("tidal")["color"],
        ).pack(anchor="w")
        CTk.CTkLabel(
            inner,
            text="Complete sign-in in your browser",
            font=ui_font(17, "bold"),
            text_color=COLORS["text"],
            anchor="w",
        ).pack(fill="x", anchor="w", pady=(8, 4))
        CTk.CTkLabel(
            inner,
            text=(
                "After signing in, your browser lands on an error page. Copy the full URL "
                "from the address bar and paste it below."
            ),
            font=ui_font(10),
            text_color=COLORS["text_secondary"],
            anchor="w",
            justify="left",
            wraplength=520,
        ).pack(fill="x", anchor="w")

        url_entry = CTk.CTkEntry(
            inner,
            placeholder_text="https://tidal.com/android/login/auth?code=…",
            height=40,
            corner_radius=9,
            border_width=1,
            border_color=COLORS["border"],
            fg_color=COLORS["surface_muted"],
            text_color=COLORS["text"],
            font=ui_font(11),
        )
        url_entry.pack(fill="x", pady=(14, 6))
        url_entry.bind("<Return>", lambda _event: submit())
        url_entry.focus_set()

        status_lbl = CTk.CTkLabel(
            inner, text="", font=ui_font(10), text_color=COLORS["error"], anchor="w"
        )
        status_lbl.pack(fill="x", anchor="w")

        footer = CTk.CTkFrame(inner, fg_color="transparent")
        footer.pack(fill="x", pady=(12, 0))

        submit_btn = primary_button(
            footer, "Complete login", command=lambda: submit(), width=156, height=38
        )
        submit_btn.pack(side="right")
        ghost_button(
            footer, "Cancel", command=close_dialog, width=92, height=38
        ).pack(side="right", padx=(0, 8))

        def submit():
            pasted = url_entry.get().strip()
            if not pasted:
                status_lbl.configure(text="Paste the redirect URL to continue.")
                return
            auth_code = None
            if "code=" in pasted:
                parsed = urllib.parse.urlparse(pasted)
                auth_code = (urllib.parse.parse_qs(parsed.query).get("code") or [None])[0]
                if not auth_code and parsed.fragment:
                    fragment = urllib.parse.parse_qs(parsed.fragment)
                    auth_code = (fragment.get("code") or [None])[0]
            elif " " not in pasted and "://" not in pasted:
                auth_code = pasted
            if not auth_code:
                status_lbl.configure(
                    text="Could not find a login code in that URL."
                )
                return
            status_lbl.configure(text="Exchanging token…", text_color=COLORS["accent_text"])
            submit_btn.configure(state="disabled", text="Signing in…")
            self.run_async(self.exchange_pkce_code(auth_code, dialog))

    async def exchange_pkce_code(self, auth_code, dialog):
        try:
            await self.api.exchange_pkce_code(auth_code)
            self.after(0, self.login_success, dialog)
        except Exception as exc:
            message = str(exc)
            self.after(0, lambda: self.login_fail(message, dialog))

    def login_success(self, dialog=None):
        self.login_in_progress = False
        if dialog is not None and dialog.winfo_exists():
            dialog.destroy()
        self.update_login_display(True)
        messagebox.showinfo(
            "Login successful",
            f"Connected to Tidal.\nUser ID: {self.config.user_id}\nCountry: {self.api.country_code}",
        )

    def login_fail(self, error, dialog=None):
        self.login_in_progress = False
        if dialog is not None and dialog.winfo_exists():
            dialog.destroy()
        self.update_login_display(False)
        messagebox.showerror("Login failed", f"Tidal authorization failed:\n{error}")

    # ----------------------------------------------------------------- images

    def load_image(self, url, label, size=64):
        if not url or label is None:
            return
        key = (url, size)
        cached = self._image_cache.get(key)
        if cached is not None:
            self._apply_image(label, cached)
            return
        self.run_async(self._fetch_image(url, label, size, key))

    def _apply_image(self, label, image):
        try:
            if label.winfo_exists():
                label.configure(image=image, text="")
        except Exception:
            pass

    async def _fetch_image(self, url, label, size, key):
        session = None
        owns_session = False
        try:
            if self.api:
                session = await self.api.get_session()
            else:
                session = aiohttp.ClientSession()
                owns_session = True
            async with session.get(
                url, timeout=aiohttp.ClientTimeout(total=20)
            ) as response:
                if response.status != 200:
                    return
                data = await response.read()
            image = Image.open(io.BytesIO(data))
            rounded = rounded_image(image, size=size, radius=max(8, size // 5))
            ctk_image = CTk.CTkImage(
                light_image=rounded, dark_image=rounded, size=(size, size)
            )
            self._image_cache[key] = ctk_image
            self._image_refs.append(ctk_image)
            self.after(0, self._apply_image, label, ctk_image)
        except Exception as exc:
            print(f"Failed to load image {url}: {exc}")
        finally:
            if owns_session and session is not None:
                await session.close()

    async def load_and_set_specs(self, track_id, badge_label):
        if not track_id or badge_label is None:
            return
        if track_id in self._specs_cache:
            text, background, foreground = self._specs_cache[track_id]
            self.after(0, self._apply_badge, badge_label, text, background, foreground)
            return
        try:
            specs = await self.api.get_track_specs(track_id)
            if specs and specs.get("bit_depth"):
                triple = format_specs(
                    specs["bit_depth"],
                    specs["sample_rate"],
                    specs.get("audio_quality", ""),
                    specs.get("audio_mode", "STEREO"),
                )
                self._specs_cache[track_id] = triple
                self.after(0, self._apply_badge, badge_label, *triple)
        except Exception:
            pass

    def _apply_badge(self, label, text, background, foreground):
        try:
            if label.winfo_exists():
                label.configure(text=text, fg_color=background, text_color=foreground)
        except Exception:
            pass

    # ---------------------------------------------------------------- preview

    def stop_preview(self):
        self._preview_gen = getattr(self, "_preview_gen", 0) + 1
        if winsound is not None:
            try:
                winsound.PlaySound(None, winsound.SND_PURGE)
            except Exception:
                pass
        proc = getattr(self, "preview_proc", None)
        if proc is not None:
            try:
                if proc.poll() is None:
                    proc.terminate()
                    proc.wait(timeout=2)
            except Exception:
                pass
        self.preview_proc = None
        button = getattr(self, "active_pbtn", None)
        if button is not None:
            try:
                if button.winfo_exists():
                    button.configure(text="▶")
            except Exception:
                pass
        self.active_pbtn = None
        self.preview_tid = None

    def toggle_preview(self, track_id, button):
        if winsound is None:
            messagebox.showinfo("Preview", "Audio preview is only available on Windows.")
            return
        self._preview_gen = getattr(self, "_preview_gen", 0) + 1
        gen = self._preview_gen
        try:
            winsound.PlaySound(None, winsound.SND_PURGE)
        except Exception:
            pass
        proc = getattr(self, "preview_proc", None)
        if proc is not None:
            try:
                if proc.poll() is None:
                    proc.terminate()
                    proc.wait(timeout=2)
            except Exception:
                pass
        self.preview_proc = None
        if self.active_pbtn is not None and self.active_pbtn is not button:
            try:
                if self.active_pbtn.winfo_exists():
                    self.active_pbtn.configure(text="▶")
            except Exception:
                pass

        if self.preview_tid == track_id:
            self.preview_tid = None
            self.active_pbtn = None
            try:
                button.configure(text="▶")
            except Exception:
                pass
            return

        self.preview_tid = track_id
        self.active_pbtn = button
        try:
            button.configure(text="…")
        except Exception:
            pass
        threading.Thread(
            target=self._preview_worker,
            args=(track_id, button, gen),
            daemon=True,
        ).start()

    def _preview_worker(self, track_id, button, gen):
        try:
            preview_dir = os.path.join(self.config.config_dir, "previews")
            os.makedirs(preview_dir, exist_ok=True)
            tmp_m4a = os.path.join(preview_dir, f"preview_{track_id}.m4a")
            tmp_wav = os.path.join(preview_dir, f"preview_{track_id}.wav")

            if not (os.path.exists(tmp_wav) and os.path.getsize(tmp_wav) > 1000):
                async def fetch_audio():
                    info = await self.api.get_stream_info(track_id, "LOW")
                    session = await self.api.get_session()
                    with open(tmp_m4a, "wb") as handle:
                        if info["type"] == "direct":
                            async with session.get(info["url"]) as response:
                                handle.write(await response.content.read(1024 * 500))
                        else:
                            async with session.get(info["init_url"]) as response:
                                handle.write(await response.read())
                            for segment in info.get("segment_urls", [])[:3]:
                                async with session.get(segment) as response:
                                    handle.write(await response.read())

                future = asyncio.run_coroutine_threadsafe(fetch_audio(), self.async_loop)
                future.result(timeout=30)
                if self._preview_gen != gen:
                    return

                ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
                self.preview_proc = subprocess.Popen(
                    [ffmpeg_exe, "-y", "-i", tmp_m4a, "-f", "wav", tmp_wav],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                self.preview_proc.wait()
                try:
                    os.remove(tmp_m4a)
                except OSError:
                    pass

            if self._preview_gen != gen:
                return
            if os.path.exists(tmp_wav) and os.path.getsize(tmp_wav) > 1000:
                self.after(0, self._set_preview_button, button, "⏹")
                winsound.PlaySound(tmp_wav, winsound.SND_FILENAME | winsound.SND_ASYNC)
            else:
                self.after(0, self._set_preview_button, button, "▶")
        except Exception as exc:
            print(f"Preview error: {exc}")
            self.after(0, self._set_preview_button, button, "▶")

    def _set_preview_button(self, button, text):
        try:
            if button.winfo_exists():
                button.configure(text=text)
        except Exception:
            pass

    # ------------------------------------------------------- session lifecycle

    def on_closing_save_session(self):
        self._shutdown = True
        try:
            entries = []
            for key in self.queue_order:
                item = self.queue_items.get(key)
                if not item:
                    continue
                if item.get("status") not in ("queued", "downloading"):
                    continue
                entries.append(
                    {
                        "task": item.get("task"),
                        "title": item.get("title"),
                        "subtitle": item.get("subtitle"),
                    }
                )
            session_file = os.path.join(self.config.config_dir, "session.json")
            os.makedirs(self.config.config_dir, exist_ok=True)
            with open(session_file, "w", encoding="utf-8") as handle:
                json.dump(entries, handle, ensure_ascii=False, indent=2)
        except Exception as exc:
            print(f"Failed to save session: {exc}")

        self.stop_preview()
        self._cleanup_preview_files()
        if hasattr(self, "player_shutdown"):
            self.player_shutdown()

    def _cleanup_preview_files(self):
        preview_dir = os.path.join(self.config.config_dir, "previews")
        for pattern in ("preview_*.m4a", "preview_*.wav"):
            try:
                for path in glob.glob(os.path.join(preview_dir, pattern)):
                    try:
                        os.remove(path)
                    except OSError:
                        pass
            except Exception:
                pass

    def on_closing(self):
        if self._closing:
            return
        self._closing = True
        self.on_closing_save_session()
        self.downloader.is_cancelled = True
        try:
            self.destroy()
        except Exception:
            pass

    def load_session(self):
        session_file = os.path.join(self.config.config_dir, "session.json")
        if not os.path.exists(session_file):
            return
        try:
            with open(session_file, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except Exception as exc:
            print(f"Failed to read session: {exc}")
            try:
                os.remove(session_file)
            except OSError:
                pass
            return

        restored = 0
        try:
            for entry in data or []:
                if not isinstance(entry, dict):
                    continue
                task = entry.get("task")
                if isinstance(task, dict) and task.get("source"):
                    self.queue_task(
                        dict(task),
                        title=entry.get("title"),
                        subtitle=entry.get("subtitle"),
                        switch=False,
                    )
                    restored += 1
                elif entry.get("track_id"):
                    migrated = {
                        "source": "tidal",
                        "track_id": entry["track_id"],
                        "parent_folder": entry.get("parent_folder"),
                        "meta": {
                            "title": entry.get("title") or "Unknown title",
                            "artist": "",
                            "album": "",
                        },
                    }
                    self.queue_task(
                        migrated,
                        title=entry.get("title") or "Unknown title",
                        subtitle="Tidal · restored from last session",
                        switch=False,
                    )
                    restored += 1
        finally:
            try:
                os.remove(session_file)
            except OSError:
                pass

        if restored:
            self.switch_view("queue")
            messagebox.showinfo(
                "Queue restored",
                f"Restored {restored} unfinished download(s) from your last session.",
            )

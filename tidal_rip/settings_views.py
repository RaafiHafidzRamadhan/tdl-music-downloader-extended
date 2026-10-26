"""Settings view for library, audio quality, and Tidal account options."""

import os
from tkinter import filedialog, messagebox

import customtkinter as CTk

from .components import ghost_button, primary_button, soft_button
from .theme import COLORS, ui_font


QUALITY_MAP = {
    "Max · Hi-Res Lossless FLAC": "HI_RES_LOSSLESS",
    "HiFi · CD-Quality Lossless FLAC": "LOSSLESS",
    "High · 320 kbps AAC": "HIGH",
    "Low · 96 kbps AAC": "LOW",
}


class SettingsViewMixin:
    """Builds the settings view and keeps it in sync with the sidebar."""

    def create_settings_view(self):
        self.settings_view = CTk.CTkScrollableFrame(
            self.main_container,
            fg_color="transparent",
            corner_radius=0,
            scrollbar_button_color=COLORS["border"],
            scrollbar_button_hover_color=COLORS["border_strong"],
        )

        header = CTk.CTkFrame(self.settings_view, fg_color="transparent")
        header.pack(fill="x", padx=2, pady=(0, 16))
        CTk.CTkLabel(
            header,
            text="Settings",
            font=ui_font(26, "bold"),
            text_color=COLORS["text"],
            anchor="w",
        ).pack(fill="x", anchor="w")
        CTk.CTkLabel(
            header,
            text="Control where music is saved, how it sounds, and how downloads behave.",
            font=ui_font(12),
            text_color=COLORS["text_secondary"],
            anchor="w",
        ).pack(fill="x", anchor="w", pady=(4, 0))

        # ---------------------------------------------------------- library
        body = self._settings_section(
            self.settings_view,
            "Library",
            "Tidal downloads, YouTube MP3s, and the music player all use this folder.",
        )
        CTk.CTkLabel(
            body,
            text="Download folder",
            font=ui_font(11, "bold"),
            text_color=COLORS["text"],
            anchor="w",
        ).pack(fill="x", anchor="w")

        folder_row = CTk.CTkFrame(body, fg_color="transparent")
        folder_row.pack(fill="x", pady=(6, 8))
        self.settings_folder_entry = CTk.CTkEntry(
            folder_row,
            height=38,
            corner_radius=9,
            border_width=1,
            border_color=COLORS["border"],
            fg_color=COLORS["surface_muted"],
            text_color=COLORS["text"],
            font=ui_font(12),
        )
        self.settings_folder_entry.pack(side="left", fill="x", expand=True)
        self.settings_folder_entry.insert(0, self.config.download_directory)
        ghost_button(
            folder_row,
            "Browse",
            command=self.browse_settings_directory,
            width=88,
            height=38,
        ).pack(side="left", padx=(8, 0))

        folder_actions = CTk.CTkFrame(body, fg_color="transparent")
        folder_actions.pack(fill="x")
        soft_button(
            folder_actions,
            "Open folder",
            command=lambda: self._open_download_folder(),
            width=104,
            height=32,
        ).pack(side="left")
        CTk.CTkLabel(
            folder_actions,
            text="Changing this here takes effect when you save.",
            font=ui_font(10),
            text_color=COLORS["muted"],
        ).pack(side="left", padx=(12, 0))

        # ------------------------------------------------------ audio quality
        body = self._settings_section(
            self.settings_view,
            "Audio quality",
            "Tidal streams stay lossless; YouTube audio is converted to MP3.",
        )
        CTk.CTkLabel(
            body,
            text="Tidal stream quality",
            font=ui_font(11, "bold"),
            text_color=COLORS["text"],
            anchor="w",
        ).pack(fill="x", anchor="w")
        self.quality_menu = self._make_option_menu(body, list(QUALITY_MAP.keys()))
        self.quality_menu.pack(anchor="w", pady=(6, 16))
        reverse = {value: label for label, value in QUALITY_MAP.items()}
        self.quality_menu.set(
            reverse.get(self.config.quality_tier, "HiFi · CD-Quality Lossless FLAC")
        )

        CTk.CTkLabel(
            body,
            text="MP3 bitrate for YouTube",
            font=ui_font(11, "bold"),
            text_color=COLORS["text"],
            anchor="w",
        ).pack(fill="x", anchor="w")
        mp3_options = ["128 kbps", "192 kbps", "256 kbps", "320 kbps"]
        self.mp3_menu = self._make_option_menu(body, mp3_options, width=200)
        self.mp3_menu.pack(anchor="w", pady=(6, 16))
        current_bitrate = str(getattr(self.config, "mp3_bitrate", "320"))
        self.mp3_menu.set(
            f"{current_bitrate} kbps" if current_bitrate in ("128", "192", "256", "320") else "320 kbps"
        )

        self.atmos_switch = CTk.CTkSwitch(
            body,
            text="Allow Dolby Atmos streams when available",
            font=ui_font(11),
            text_color=COLORS["text_secondary"],
            progress_color=COLORS["accent"],
            button_color=COLORS["surface"],
            button_hover_color=COLORS["surface_hover"],
        )
        self.atmos_switch.pack(anchor="w")
        if self.config.allow_dolby_atmos:
            self.atmos_switch.select()
        else:
            self.atmos_switch.deselect()

        # ---------------------------------------------------------- downloads
        body = self._settings_section(
            self.settings_view,
            "Downloads",
            "Tune concurrency, completion alerts, and the Tidal file naming pattern.",
        )
        concurrent_row = CTk.CTkFrame(body, fg_color="transparent")
        concurrent_row.pack(fill="x", pady=(0, 14))
        CTk.CTkLabel(
            concurrent_row,
            text="Concurrent downloads",
            font=ui_font(11, "bold"),
            text_color=COLORS["text"],
            width=180,
            anchor="w",
        ).pack(side="left")
        self.concurrent_slider = CTk.CTkSlider(
            concurrent_row,
            from_=1,
            to=3,
            number_of_steps=2,
            width=220,
            progress_color=COLORS["accent"],
            button_color=COLORS["accent"],
            button_hover_color=COLORS["accent_hover"],
            fg_color=COLORS["border"],
        )
        self.concurrent_slider.pack(side="left")
        self.concurrent_value_lbl = CTk.CTkLabel(
            concurrent_row,
            text=str(int(getattr(self.config, "concurrent_downloads", 3))),
            font=ui_font(12, "bold"),
            text_color=COLORS["accent_text"],
            width=28,
        )
        self.concurrent_value_lbl.pack(side="left", padx=(10, 0))
        self.concurrent_slider.configure(
            command=lambda value: self.concurrent_value_lbl.configure(
                text=str(int(value))
            )
        )
        self.concurrent_slider.set(getattr(self.config, "concurrent_downloads", 3))

        self.sound_switch = CTk.CTkSwitch(
            body,
            text="Play a chime when the whole queue finishes",
            font=ui_font(11),
            text_color=COLORS["text_secondary"],
            progress_color=COLORS["accent"],
            button_color=COLORS["surface"],
            button_hover_color=COLORS["surface_hover"],
        )
        self.sound_switch.pack(anchor="w", pady=(0, 16))
        if getattr(self.config, "play_sound_on_complete", True):
            self.sound_switch.select()
        else:
            self.sound_switch.deselect()

        CTk.CTkLabel(
            body,
            text="Tidal file naming template",
            font=ui_font(11, "bold"),
            text_color=COLORS["text"],
            anchor="w",
        ).pack(fill="x", anchor="w")
        self.template_entry = CTk.CTkEntry(
            body,
            height=38,
            corner_radius=9,
            border_width=1,
            border_color=COLORS["border"],
            fg_color=COLORS["surface_muted"],
            text_color=COLORS["text"],
            font=ui_font(12),
        )
        self.template_entry.pack(fill="x", pady=(6, 4))
        self.template_entry.insert(
            0, getattr(self.config, "file_template", "{album}/{track_num} - {title}.{ext}")
        )
        CTk.CTkLabel(
            body,
            text="Available tokens: {album}, {artist}, {track_num}, {title}, {ext}",
            font=ui_font(10),
            text_color=COLORS["muted"],
            anchor="w",
        ).pack(fill="x", anchor="w")

        # ------------------------------------------------------ Tidal account
        body = self._settings_section(
            self.settings_view,
            "Tidal account",
            "Login is only required for Tidal search and lossless downloads.",
        )
        browser_row = CTk.CTkFrame(body, fg_color="transparent")
        browser_row.pack(fill="x", pady=(0, 12))
        CTk.CTkLabel(
            browser_row,
            text="Browser for login",
            font=ui_font(11, "bold"),
            text_color=COLORS["text"],
            width=180,
            anchor="w",
        ).pack(side="left")
        browser_options = [
            "Default Browser",
            "Google Chrome",
            "Mozilla Firefox",
            "Microsoft Edge",
            "Safari",
            "Opera",
        ]
        self.browser_menu = self._make_option_menu(browser_row, browser_options, width=240)
        self.browser_menu.pack(side="left")
        self.browser_menu.set(self.config.login_browser)

        account_row = CTk.CTkFrame(body, fg_color="transparent")
        account_row.pack(fill="x")
        self.settings_account_btn = soft_button(
            account_row,
            "Log in",
            command=self.handle_login_click,
            width=96,
            height=32,
        )
        self.settings_account_btn.pack(side="left")
        self.settings_account_lbl = CTk.CTkLabel(
            account_row,
            text="",
            font=ui_font(11),
            text_color=COLORS["muted"],
            anchor="w",
        )
        self.settings_account_lbl.pack(side="left", padx=(12, 0))
        self._refresh_settings_account()

        # ----------------------------------------------------------- advanced
        body = self._settings_section(
            self.settings_view,
            "Advanced",
            "Override the built-in Tidal API credentials only if you know what you are doing.",
        )
        self.client_id_entry = CTk.CTkEntry(
            body,
            placeholder_text="Client ID",
            height=38,
            corner_radius=9,
            border_width=1,
            border_color=COLORS["border"],
            fg_color=COLORS["surface_muted"],
            text_color=COLORS["text"],
            font=ui_font(12),
        )
        self.client_id_entry.pack(fill="x", pady=(0, 8))
        self.client_id_entry.insert(0, self.config.client_id)

        self.client_secret_entry = CTk.CTkEntry(
            body,
            placeholder_text="Client secret",
            height=38,
            corner_radius=9,
            border_width=1,
            border_color=COLORS["border"],
            fg_color=COLORS["surface_muted"],
            text_color=COLORS["text"],
            font=ui_font(12),
        )
        self.client_secret_entry.pack(fill="x", pady=(0, 10))
        self.client_secret_entry.insert(0, self.config.client_secret)

        ghost_button(
            body,
            "Reset credentials",
            command=self.reset_keys,
            width=140,
            height=32,
        ).pack(anchor="w")

        # ------------------------------------------------------------ actions
        actions = CTk.CTkFrame(self.settings_view, fg_color="transparent")
        actions.pack(fill="x", padx=2, pady=(0, 20))
        primary_button(
            actions,
            "Save settings",
            command=self.save_settings,
            width=140,
            height=40,
        ).pack(side="left")
        CTk.CTkLabel(
            actions,
            text="Settings are saved to your user profile.",
            font=ui_font(10),
            text_color=COLORS["muted"],
        ).pack(side="left", padx=(12, 0))

    # --------------------------------------------------------------- helpers

    def _settings_section(self, parent, title, subtitle=None):
        card = CTk.CTkFrame(
            parent,
            fg_color=COLORS["surface"],
            corner_radius=16,
            border_width=1,
            border_color=COLORS["border"],
        )
        card.pack(fill="x", padx=2, pady=(0, 14))

        inner = CTk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="x", padx=18, pady=16)

        CTk.CTkLabel(
            inner,
            text=title,
            font=ui_font(14, "bold"),
            text_color=COLORS["text"],
            anchor="w",
        ).pack(fill="x", anchor="w")
        if subtitle:
            CTk.CTkLabel(
                inner,
                text=subtitle,
                font=ui_font(10),
                text_color=COLORS["text_secondary"],
                anchor="w",
                justify="left",
                wraplength=700,
            ).pack(fill="x", anchor="w", pady=(3, 0))

        body = CTk.CTkFrame(inner, fg_color="transparent")
        body.pack(fill="x", pady=(12, 0))
        return body

    def _make_option_menu(self, parent, values, width=280):
        return CTk.CTkOptionMenu(
            parent,
            values=values,
            width=width,
            height=36,
            corner_radius=9,
            fg_color=COLORS["surface_muted"],
            button_color=COLORS["surface_hover"],
            button_hover_color=COLORS["border"],
            text_color=COLORS["text"],
            dropdown_fg_color=COLORS["surface"],
            dropdown_hover_color=COLORS["surface_hover"],
            dropdown_text_color=COLORS["text"],
            font=ui_font(11),
            dropdown_font=ui_font(11),
        )

    def _refresh_settings_account(self):
        if not hasattr(self, "settings_account_btn"):
            return
        if self.config.access_token:
            name = self.config.user_name or f"User {self.config.user_id}"
            self.settings_account_btn.configure(text="Log out")
            self.settings_account_lbl.configure(
                text=f"Connected as {name}", text_color=COLORS["success"]
            )
        else:
            self.settings_account_btn.configure(text="Log in")
            self.settings_account_lbl.configure(
                text="Not connected", text_color=COLORS["muted"]
            )

    def _open_download_folder(self):
        from .components import open_in_file_manager

        open_in_file_manager(self.config.download_directory)

    def apply_download_folder(self, path, show_errors=True):
        path = os.path.abspath(os.path.expanduser((path or "").strip()))
        if not path:
            if show_errors:
                messagebox.showerror("Folder required", "Choose a download folder.")
            return False
        try:
            os.makedirs(path, exist_ok=True)
        except OSError as exc:
            if show_errors:
                messagebox.showerror(
                    "Cannot use this folder", f"This folder cannot be created:\n{exc}"
                )
            return False
        self.config.download_directory = path
        self.config.save()
        self._display_folder()
        if hasattr(self, "player_note_library_changed"):
            self.player_note_library_changed()
        if hasattr(self, "settings_folder_entry") and self.settings_folder_entry.winfo_exists():
            self.settings_folder_entry.delete(0, "end")
            self.settings_folder_entry.insert(0, path)
        return True

    def browse_download_folder(self):
        selected = filedialog.askdirectory(
            initialdir=self.config.download_directory,
            title="Choose download folder",
        )
        if selected:
            self.apply_download_folder(selected)

    def browse_settings_directory(self):
        current = self.settings_folder_entry.get().strip() or self.config.download_directory
        selected = filedialog.askdirectory(initialdir=current, title="Choose download folder")
        if selected:
            self.settings_folder_entry.delete(0, "end")
            self.settings_folder_entry.insert(0, selected)

    def save_settings(self):
        folder = self.settings_folder_entry.get().strip()
        quality = QUALITY_MAP.get(
            self.quality_menu.get(), "HI_RES_LOSSLESS"
        )
        browser = self.browser_menu.get()
        atmos = bool(self.atmos_switch.get())
        concurrent = int(self.concurrent_slider.get())
        template = self.template_entry.get().strip()
        client_id = self.client_id_entry.get().strip()
        client_secret = self.client_secret_entry.get().strip()
        bitrate = self.mp3_menu.get().split(" ")[0]

        if not folder:
            messagebox.showerror("Folder required", "Download folder cannot be empty.")
            return
        if not client_id:
            messagebox.showerror("Client ID required", "Client ID cannot be empty.")
            return

        folder = os.path.abspath(os.path.expanduser(folder))
        try:
            os.makedirs(folder, exist_ok=True)
        except OSError as exc:
            messagebox.showerror(
                "Cannot use this folder", f"This folder cannot be created:\n{exc}"
            )
            return

        keys_changed = (
            self.config.client_id != client_id
            or self.config.client_secret != client_secret
        )

        self.config.download_directory = folder
        self.config.quality_tier = quality
        self.config.login_browser = browser
        self.config.allow_dolby_atmos = atmos
        self.config.play_sound_on_complete = bool(self.sound_switch.get())
        self.config.concurrent_downloads = concurrent
        self.config.file_template = template
        self.config.mp3_bitrate = bitrate
        self.config.client_id = client_id
        self.config.client_secret = client_secret
        self.config.save()

        self._display_folder()
        self._update_search_hint()

        if keys_changed:
            self.config.clear_session()
            self.update_login_display(False)
            messagebox.showinfo(
                "Settings saved",
                "Settings saved. Your Tidal session was cleared because the API credentials changed. Please log in again.",
            )
        else:
            messagebox.showinfo("Settings saved", "Your settings have been saved.")

    def reset_keys(self):
        self.client_id_entry.delete(0, "end")
        self.client_id_entry.insert(0, self.config.DEFAULT_CLIENT_ID)
        self.client_secret_entry.delete(0, "end")
        self.client_secret_entry.insert(0, self.config.DEFAULT_CLIENT_SECRET)

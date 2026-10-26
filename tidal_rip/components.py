"""Shared light-theme widgets, dialogs, and small UI helpers."""

import os
import re
import subprocess
import webbrowser

import customtkinter as CTk

from .theme import COLORS, ui_font


SEARCH_COPY = {
    "tidal": {
        "title": "Search Tidal",
        "subtitle": "Hi-Res lossless catalog with full metadata, album art, and quality selection.",
        "placeholder": "Search Tidal or paste a Tidal / music service link…",
        "button": "Search Tidal",
        "intro_title": "Lossless music, beautifully organized",
        "intro_text": (
            "Search tracks, albums, playlists, or artists on Tidal. "
            "Downloads keep their original FLAC quality, cover art, and tags."
        ),
        "highlights": "Up to 24-bit / 192 kHz FLAC\nDolby Atmos support\nAlbum & playlist selection",
    },
    "youtube": {
        "title": "Search YouTube",
        "subtitle": "Find any song, video, or playlist and save it as a tagged MP3.",
        "placeholder": "Search YouTube or paste a video / playlist link…",
        "button": "Search YouTube",
        "intro_title": "Anything on YouTube, saved as MP3",
        "intro_text": (
            "Search by keyword or paste a YouTube link. Audio is converted to MP3 "
            "with embedded cover art and ID3 tags."
        ),
        "highlights": "MP3 up to 320 kbps\nVideo & playlist support\nCover art + ID3 tags",
    },
}


def primary_button(master, text, command=None, width=112, height=36, **kwargs):
    options = dict(
        text=text,
        command=command,
        width=width,
        height=height,
        fg_color=COLORS["accent"],
        hover_color=COLORS["accent_hover"],
        text_color="#FFFFFF",
        font=ui_font(12, "bold"),
        corner_radius=10,
    )
    options.update(kwargs)
    return CTk.CTkButton(master, **options)


def soft_button(master, text, command=None, width=96, height=32, **kwargs):
    options = dict(
        text=text,
        command=command,
        width=width,
        height=height,
        fg_color=COLORS["accent_soft"],
        hover_color=COLORS["surface_hover"],
        text_color=COLORS["accent_text"],
        font=ui_font(11, "bold"),
        corner_radius=9,
    )
    options.update(kwargs)
    return CTk.CTkButton(master, **options)


def ghost_button(master, text, command=None, width=96, height=32, **kwargs):
    options = dict(
        text=text,
        command=command,
        width=width,
        height=height,
        fg_color=COLORS["surface"],
        hover_color=COLORS["surface_hover"],
        text_color=COLORS["text_secondary"],
        border_width=1,
        border_color=COLORS["border"],
        font=ui_font(11),
        corner_radius=9,
    )
    options.update(kwargs)
    return CTk.CTkButton(master, **options)


def danger_button(master, text, command=None, width=96, height=32, **kwargs):
    options = dict(
        text=text,
        command=command,
        width=width,
        height=height,
        fg_color=COLORS["error_soft"],
        hover_color="#FECACA",
        text_color="#B91C1C",
        font=ui_font(11, "bold"),
        corner_radius=9,
    )
    options.update(kwargs)
    return CTk.CTkButton(master, **options)


def chip_label(master, text, fg_color=None, text_color=None, **kwargs):
    options = dict(
        text=text,
        fg_color=fg_color or COLORS["surface_soft"],
        text_color=text_color or COLORS["accent_text"],
        font=ui_font(10, "bold"),
        corner_radius=7,
        height=22,
        padx=8,
    )
    options.update(kwargs)
    return CTk.CTkLabel(master, **options)


def register_browsers():
    import platform

    if platform.system() != "Windows":
        return

    import winreg

    browser_keys = {
        "chrome": ["chrome", "google-chrome", "google chrome"],
        "firefox": ["firefox", "mozilla firefox"],
        "edge": ["edge", "microsoft edge", "msedge"],
        "opera": ["opera", "opera beta", "opera stable"],
    }
    registered = set()

    for root in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        try:
            key_path = r"SOFTWARE\Clients\StartMenuInternet"
            with winreg.OpenKey(root, key_path) as key:
                num_subkeys = winreg.QueryInfoKey(key)[0]
                for i in range(num_subkeys):
                    subkey_name = winreg.EnumKey(key, i)
                    try:
                        shell_path = f"{key_path}\\{subkey_name}\\shell\\open\\command"
                        with winreg.OpenKey(root, shell_path) as path_key:
                            val = winreg.QueryValue(path_key, None)
                            if not val:
                                continue
                            path = val.strip('"')
                            if path.lower().endswith(" %1"):
                                path = path[:-3].strip('"')
                            if not os.path.exists(path):
                                continue
                            sub_lower = subkey_name.lower()
                            matched = None
                            for name, aliases in browser_keys.items():
                                if any(alias in sub_lower for alias in aliases):
                                    matched = name
                                    break
                            if matched and matched not in registered:
                                webbrowser.register(
                                    matched,
                                    None,
                                    webbrowser.BackgroundBrowser(path),
                                )
                                registered.add(matched)
                    except Exception:
                        pass
        except Exception:
            pass

    local_app_data = os.environ.get("LOCALAPPDATA", "")
    program_files = os.environ.get("ProgramFiles", "C:\\Program Files")
    program_files_x86 = os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)")
    common = {
        "chrome": [
            os.path.join(program_files, "Google\\Chrome\\Application\\chrome.exe"),
            os.path.join(program_files_x86, "Google\\Chrome\\Application\\chrome.exe"),
            os.path.join(local_app_data, "Google\\Chrome\\Application\\chrome.exe"),
        ],
        "firefox": [
            os.path.join(program_files, "Mozilla Firefox\\firefox.exe"),
            os.path.join(program_files_x86, "Mozilla Firefox\\firefox.exe"),
        ],
        "edge": [
            os.path.join(program_files_x86, "Microsoft\\Edge\\Application\\msedge.exe"),
            os.path.join(program_files, "Microsoft\\Edge\\Application\\msedge.exe"),
        ],
        "opera": [
            os.path.join(local_app_data, "Programs\\Opera\\launcher.exe"),
            os.path.join(program_files, "Opera\\launcher.exe"),
            os.path.join(program_files_x86, "Opera\\launcher.exe"),
        ],
    }

    for name, paths in common.items():
        if name in registered:
            continue
        for path in paths:
            if os.path.exists(path):
                try:
                    webbrowser.register(name, None, webbrowser.BackgroundBrowser(path))
                    registered.add(name)
                    break
                except Exception:
                    pass


def open_browser(url, browser_name):
    if not browser_name or browser_name == "Default Browser":
        webbrowser.open(url)
        return

    mapping = {
        "Google Chrome": "chrome",
        "Mozilla Firefox": "firefox",
        "Microsoft Edge": "edge",
        "Safari": "safari",
        "Opera": "opera",
    }
    key = mapping.get(browser_name)
    if key:
        try:
            webbrowser.get(key).open(url)
            return
        except Exception as exc:
            print(f"Failed to open {browser_name}: {exc}. Falling back to default.")
    webbrowser.open(url)


def open_in_file_manager(path, select_file=False):
    """Opens a directory or highlights a file in Explorer / Finder / Linux."""
    if not path:
        return False
    try:
        norm_path = os.path.normpath(str(path))
        if not os.path.exists(norm_path):
            parent = os.path.dirname(norm_path)
            if os.path.exists(parent):
                norm_path = parent
                select_file = False
            else:
                return False

        import platform

        system = platform.system()
        if system == "Windows":
            if select_file and os.path.isfile(norm_path):
                subprocess.Popen(["explorer.exe", f"/select,{norm_path}"])
            else:
                target = norm_path if os.path.isdir(norm_path) else os.path.dirname(norm_path)
                subprocess.Popen(["explorer.exe", target])
        elif system == "Darwin":
            if select_file and os.path.isfile(norm_path):
                subprocess.Popen(["open", "-R", norm_path])
            else:
                target = norm_path if os.path.isdir(norm_path) else os.path.dirname(norm_path)
                subprocess.Popen(["open", target])
        else:
            target = norm_path if os.path.isdir(norm_path) else os.path.dirname(norm_path)
            subprocess.Popen(["xdg-open", target])
        return True
    except Exception as exc:
        print(f"Failed to open file manager: {exc}")
        return False


def parse_tidal_url(query):
    """Parses Tidal track, album, playlist, or artist links (and raw playlist UUIDs)."""
    query = (query or "").strip()

    uuid_match = re.search(
        r"^([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})$",
        query,
    )
    if uuid_match:
        return "playlist", uuid_match.group(1)

    patterns = {
        "track": r"tidal\.com/(?:[a-z]+/)?(?:browse/)?(?:album/\d+/)?track/(\d+)",
        "album": r"tidal\.com/(?:[a-z]+/)?(?:browse/)?album/(\d+)",
        "playlist": r"tidal\.com/(?:[a-z]+/)?(?:browse/)?playlist/([a-zA-Z0-9-]+)",
        "artist": r"tidal\.com/(?:[a-z]+/)?(?:browse/)?artist/(\d+)",
    }
    for item_type, pattern in patterns.items():
        match = re.search(pattern, query)
        if match:
            return item_type, match.group(1)

    if query.isdigit() and len(query) >= 5:
        return "track", query
    return None, None


def format_specs(bit_depth, sample_rate, audio_quality="", audio_mode="STEREO"):
    """Returns (text, background, foreground) for a Tidal quality chip."""
    if audio_mode == "DOLBY_ATMOS" or "ATMOS" in str(audio_mode).upper():
        return "Dolby Atmos", "#EDE9FE", "#6D28D9"

    sr_str = ""
    if sample_rate:
        sr_str = f"{sample_rate / 1000.0:g}kHz"

    if bit_depth and bit_depth >= 24:
        text = f"MAX · {bit_depth}-bit/{sr_str}" if sr_str else f"MAX · {bit_depth}-bit"
        return text, "#FEF3C7", "#92400E"
    if bit_depth == 16:
        text = f"HiFi · 16-bit/{sr_str}" if sr_str else "HiFi · 16-bit/44.1kHz"
        return text, "#DBEAFE", "#1D4ED8"
    if "HIRES" in str(audio_quality).upper() or "HI_RES" in str(audio_quality).upper():
        return "MAX · Hi-Res", "#FEF3C7", "#92400E"
    if "LOSSLESS" in str(audio_quality).upper():
        return "HiFi · Lossless", "#DBEAFE", "#1D4ED8"
    return "AAC", "#F1F5F9", "#475569"


def get_quality_badge(item):
    """Initial (text, background, foreground) quality chip for a Tidal item."""
    media_meta = item.get("mediaMetadata", {})
    tags = media_meta.get("tags", []) if isinstance(media_meta, dict) else []
    audio_quality = item.get("audioQuality", "")
    audio_modes = item.get("audioModes", []) or []

    if "DOLBY_ATMOS" in audio_modes or "DOLBY_ATMOS" in tags:
        return "Dolby Atmos", "#EDE9FE", "#6D28D9"
    if "HIRES_LOSSLESS" in tags or audio_quality == "HI_RES_LOSSLESS":
        return "MAX · Hi-Res", "#FEF3C7", "#92400E"
    if "MQA" in tags:
        return "MQA · Master", "#E0F2FE", "#0369A1"
    if "LOSSLESS" in tags or audio_quality == "LOSSLESS":
        return "HiFi · 16-bit", "#DBEAFE", "#1D4ED8"
    if audio_quality in ("HIGH", "LOW"):
        return "AAC", "#F1F5F9", "#475569"
    return "", COLORS["surface_soft"], COLORS["text_secondary"]


class TrackSelectionModal(CTk.CTkToplevel):
    """Light-theme dialog to choose which tracks to queue."""

    def __init__(
        self,
        parent,
        collection_type,
        collection_title,
        track_list,
        on_confirm_callback,
    ):
        super().__init__(parent)
        self.parent = parent
        self.collection_type = collection_type
        self.collection_title = collection_title
        self.track_list = track_list
        self.on_confirm = on_confirm_callback
        self.check_vars = []

        self.title("Select tracks")
        self.geometry("760x640")
        self.minsize(620, 480)
        self.configure(fg_color=COLORS["bg"])
        self.transient(parent)
        self.grab_set()
        self.bind("<Escape>", lambda _event: self.destroy())
        self.update_idletasks()
        try:
            x = parent.winfo_x() + (parent.winfo_width() - 760) // 2
            y = parent.winfo_y() + (parent.winfo_height() - 640) // 2
            self.geometry(f"+{max(0, x)}+{max(0, y)}")
        except Exception:
            pass
        self.after(50, self.focus_force)
        self._build_ui()

    def _build_ui(self):
        header = CTk.CTkFrame(
            self,
            fg_color=COLORS["surface"],
            corner_radius=16,
            border_width=1,
            border_color=COLORS["border"],
        )
        header.pack(fill="x", padx=20, pady=(20, 12))
        header_body = CTk.CTkFrame(header, fg_color="transparent")
        header_body.pack(fill="x", padx=18, pady=16)

        chip_label(
            header_body,
            str(self.collection_type).upper(),
            fg_color=COLORS["accent_soft"],
            text_color=COLORS["accent_text"],
        ).pack(anchor="w", pady=(0, 6))

        CTk.CTkLabel(
            header_body,
            text=self.collection_title,
            font=ui_font(17, "bold"),
            text_color=COLORS["text"],
            anchor="w",
            justify="left",
            wraplength=660,
        ).pack(fill="x", anchor="w")

        CTk.CTkLabel(
            header_body,
            text=f"{len(self.track_list)} tracks available · choose what to add to the queue",
            font=ui_font(11),
            text_color=COLORS["text_secondary"],
            anchor="w",
        ).pack(fill="x", anchor="w", pady=(4, 0))

        toolbar = CTk.CTkFrame(self, fg_color="transparent")
        toolbar.pack(fill="x", padx=20, pady=(0, 10))

        soft_button(toolbar, "Select all", command=self.select_all, width=92, height=30).pack(
            side="left", padx=(0, 8)
        )
        ghost_button(toolbar, "Deselect all", command=self.deselect_all, width=104, height=30).pack(
            side="left", padx=(0, 8)
        )
        ghost_button(toolbar, "Invert", command=self.invert_selection, width=76, height=30).pack(
            side="left"
        )
        self.count_lbl = CTk.CTkLabel(
            toolbar,
            text="",
            font=ui_font(11, "bold"),
            text_color=COLORS["accent_text"],
        )
        self.count_lbl.pack(side="right")

        list_card = CTk.CTkFrame(
            self,
            fg_color=COLORS["surface"],
            corner_radius=16,
            border_width=1,
            border_color=COLORS["border"],
        )
        list_card.pack(fill="both", expand=True, padx=20, pady=(0, 14))

        scroll = CTk.CTkScrollableFrame(
            list_card,
            fg_color="transparent",
            scrollbar_button_color=COLORS["border"],
            scrollbar_button_hover_color=COLORS["border_strong"],
        )
        scroll.pack(fill="both", expand=True, padx=8, pady=8)

        has_multiple_discs = any(t.get("disc_num", 1) > 1 for t in self.track_list)

        for idx, track in enumerate(self.track_list):
            row = CTk.CTkFrame(scroll, fg_color="transparent", height=44)
            row.pack(fill="x", padx=6, pady=1)
            row.pack_propagate(False)

            var = CTk.BooleanVar(value=True)
            self.check_vars.append((track, var))

            CTk.CTkCheckBox(
                row,
                text="",
                variable=var,
                width=24,
                checkbox_width=20,
                checkbox_height=20,
                border_width=2,
                border_color=COLORS["border_strong"],
                fg_color=COLORS["accent"],
                hover_color=COLORS["accent_hover"],
                checkmark_color="#FFFFFF",
                command=self.update_counter,
            ).pack(side="left", padx=(8, 12))

            if has_multiple_discs and track.get("disc_num"):
                number = f"{track['disc_num']}-{track.get('track_num', idx + 1):02d}"
            else:
                number = f"{track.get('track_num', idx + 1):02d}"
            CTk.CTkLabel(
                row,
                text=number,
                font=ui_font(10),
                text_color=COLORS["muted"],
                width=38,
                anchor="w",
            ).pack(side="left", padx=(0, 6))

            if track.get("duration_str"):
                CTk.CTkLabel(
                    row,
                    text=track["duration_str"],
                    font=ui_font(10),
                    text_color=COLORS["muted"],
                    width=46,
                    anchor="e",
                ).pack(side="right", padx=(6, 12))

            info = CTk.CTkFrame(row, fg_color="transparent")
            info.pack(side="left", fill="both", expand=True)

            title_text = track.get("title", "Unknown title")
            artist_text = track.get("artist", "Unknown artist")
            label = CTk.CTkLabel(
                info,
                text=f"{title_text}  ·  {artist_text}",
                font=ui_font(12),
                text_color=COLORS["text"],
                anchor="w",
                justify="left",
            )
            label.pack(side="left", fill="x", expand=True)
            label.bind("<Button-1>", lambda _event, v=var: self._toggle(v))

            if idx < len(self.track_list) - 1:
                CTk.CTkFrame(scroll, fg_color=COLORS["border"], height=1).pack(
                    fill="x", padx=14
                )

        footer = CTk.CTkFrame(self, fg_color="transparent")
        footer.pack(fill="x", padx=20, pady=(0, 20))

        ghost_button(footer, "Cancel", command=self.destroy, width=96, height=38).pack(
            side="right", padx=(10, 0)
        )
        self.confirm_btn = primary_button(
            footer,
            "Add to queue",
            command=self.confirm_selection,
            width=190,
            height=38,
        )
        self.confirm_btn.pack(side="right")

        self.update_counter()

    def _toggle(self, var):
        var.set(not var.get())
        self.update_counter()

    def select_all(self):
        for _, var in self.check_vars:
            var.set(True)
        self.update_counter()

    def deselect_all(self):
        for _, var in self.check_vars:
            var.set(False)
        self.update_counter()

    def invert_selection(self):
        for _, var in self.check_vars:
            var.set(not var.get())
        self.update_counter()

    def update_counter(self):
        selected = sum(1 for _, var in self.check_vars if var.get())
        total = len(self.check_vars)
        self.count_lbl.configure(text=f"{selected} of {total} selected")
        if selected == 0:
            self.confirm_btn.configure(
                text="Select at least one track",
                state="disabled",
                fg_color=COLORS["surface_muted"],
                text_color=COLORS["muted"],
            )
        else:
            self.confirm_btn.configure(
                text=f"Add {selected} to queue",
                state="normal",
                fg_color=COLORS["accent"],
                text_color="#FFFFFF",
            )

    def confirm_selection(self):
        selected = [track for track, var in self.check_vars if var.get()]
        if not selected:
            return
        self.destroy()
        self.on_confirm(selected)


register_browsers()

"""Music player view for the local downloaded library."""

import asyncio
import io
import os
import time

import customtkinter as CTk
from PIL import Image

from .audio_player import (
    FORMAT_BADGES,
    PlaybackEngine,
    cleanup_playback_cache,
    format_size,
    format_time,
    prepare_playback,
    probe_audio,
    scan_library,
)
from .components import (
    chip_label,
    ghost_button,
    open_in_file_manager,
    primary_button,
)
from .theme import COLORS, ui_font
from .widgets import rounded_image, truncate_middle


class PlayerViewMixin:
    """Builds the player view and manages playback of downloaded files."""

    # ---------------------------------------------------------------- state

    def init_player_state(self):
        self.player_engine = PlaybackEngine()
        self.player_library = []
        self.player_library_root = None
        self.player_index = -1
        self.player_current = None
        self.player_volume = 0.8
        self.player_is_paused = False
        self._player_load_token = 0
        self._player_scan_token = 0
        self._player_seek_dragging = False
        self._player_started_at = 0.0
        self._player_temp_path = None
        self._player_library_stale = True
        self._player_cover_ref = None
        self._player_tick_job = None
        self._player_refresh_job = None

    # ---------------------------------------------------------------- layout

    def create_player_view(self):
        self.player_view = CTk.CTkFrame(self.main_container, fg_color="transparent")
        self.player_view.grid_columnconfigure(0, weight=1)
        self.player_view.grid_rowconfigure(2, weight=1)

        header = CTk.CTkFrame(self.player_view, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", pady=(0, 14))
        titles = CTk.CTkFrame(header, fg_color="transparent")
        titles.pack(side="left", fill="x", expand=True)
        CTk.CTkLabel(
            titles,
            text="Music player",
            font=ui_font(26, "bold"),
            text_color=COLORS["text"],
            anchor="w",
        ).pack(fill="x", anchor="w")
        CTk.CTkLabel(
            titles,
            text="Play your downloads and see the real audio format of every file.",
            font=ui_font(12),
            text_color=COLORS["text_secondary"],
            anchor="w",
        ).pack(fill="x", anchor="w", pady=(4, 0))
        ghost_button(
            header,
            "Rescan library",
            command=lambda: self.player_refresh_library(force=True),
            width=118,
            height=34,
        ).pack(side="right", padx=(12, 0))

        self._build_player_now_card()
        self._build_player_library()

        self._update_player_now(None)
        self._player_update_buttons()
        self._player_tick_job = self.after(450, self._player_tick)

    def _build_player_now_card(self):
        card = CTk.CTkFrame(
            self.player_view,
            fg_color=COLORS["surface"],
            corner_radius=18,
            border_width=1,
            border_color=COLORS["border"],
        )
        card.grid(row=1, column=0, sticky="ew", pady=(0, 14))

        body = CTk.CTkFrame(card, fg_color="transparent")
        body.pack(fill="x", padx=20, pady=16)

        top = CTk.CTkFrame(body, fg_color="transparent")
        top.pack(fill="x")

        self.player_cover_box = CTk.CTkFrame(
            top,
            width=120,
            height=120,
            fg_color=COLORS["surface_soft"],
            corner_radius=16,
        )
        self.player_cover_box.pack(side="left", padx=(0, 18))
        self.player_cover_box.pack_propagate(False)
        self.player_cover_placeholder = CTk.CTkLabel(
            self.player_cover_box,
            text="♫",
            fg_color="transparent",
            text_color=COLORS["accent"],
            font=ui_font(30, "bold"),
        )
        self.player_cover_placeholder.place(relx=0.5, rely=0.5, anchor="center")
        self.player_cover_image_lbl = CTk.CTkLabel(
            self.player_cover_box, text="", fg_color="transparent"
        )

        info = CTk.CTkFrame(top, fg_color="transparent")
        info.pack(side="left", fill="both", expand=True)

        chip_row = CTk.CTkFrame(info, fg_color="transparent")
        chip_row.pack(fill="x")
        chip_label(
            chip_row,
            "NOW PLAYING",
            fg_color=COLORS["accent_soft"],
            text_color=COLORS["accent_text"],
            height=20,
        ).pack(side="left")
        self.player_format_chip = chip_label(
            chip_row,
            "AUDIO",
            fg_color=FORMAT_BADGES["AUDIO"][0],
            text_color=FORMAT_BADGES["AUDIO"][1],
            height=20,
        )
        self.player_format_chip.pack(side="left", padx=(6, 0))

        self.player_title_lbl = CTk.CTkLabel(
            info,
            text="Nothing playing",
            font=ui_font(20, "bold"),
            text_color=COLORS["text"],
            anchor="w",
        )
        self.player_title_lbl.pack(fill="x", anchor="w", pady=(6, 0))
        self.player_artist_lbl = CTk.CTkLabel(
            info,
            text="Pick a track from your library below.",
            font=ui_font(12),
            text_color=COLORS["text_secondary"],
            anchor="w",
        )
        self.player_artist_lbl.pack(fill="x", anchor="w", pady=(1, 0))
        self.player_detail_lbl = CTk.CTkLabel(
            info,
            text="Downloads show up here automatically.",
            font=ui_font(10),
            text_color=COLORS["muted"],
            anchor="w",
        )
        self.player_detail_lbl.pack(fill="x", anchor="w", pady=(1, 4))

        self.player_progress = CTk.CTkSlider(
            info,
            from_=0,
            to=1,
            height=14,
            button_length=16,
            fg_color=COLORS["border"],
            progress_color=COLORS["accent"],
            button_color=COLORS["accent"],
            button_hover_color=COLORS["accent_hover"],
            command=self._player_seek_value_changed,
            state="disabled",
        )
        self.player_progress.pack(fill="x", pady=(2, 0))
        self.player_progress.set(0)
        self.player_progress.bind("<ButtonPress-1>", self._player_seek_started)
        self.player_progress.bind("<ButtonRelease-1>", self._player_seek_released)

        time_row = CTk.CTkFrame(info, fg_color="transparent")
        time_row.pack(fill="x", pady=(1, 0))
        self.player_elapsed_lbl = CTk.CTkLabel(
            time_row,
            text="0:00",
            font=ui_font(9),
            text_color=COLORS["muted"],
        )
        self.player_elapsed_lbl.pack(side="left")
        self.player_total_lbl = CTk.CTkLabel(
            time_row,
            text="0:00",
            font=ui_font(9),
            text_color=COLORS["muted"],
        )
        self.player_total_lbl.pack(side="right")

        controls = CTk.CTkFrame(info, fg_color="transparent")
        controls.pack(fill="x", pady=(4, 0))

        ghost_button(
            controls,
            "⏮",
            command=lambda: self.player_advance(-1),
            width=34,
            height=34,
            font=ui_font(13),
        ).pack(side="left", padx=(0, 6))
        self.player_play_btn = primary_button(
            controls,
            "▶  Play",
            command=self.player_toggle_play,
            width=96,
            height=34,
            font=ui_font(11, "bold"),
        )
        self.player_play_btn.pack(side="left")
        ghost_button(
            controls,
            "⏭",
            command=lambda: self.player_advance(1),
            width=34,
            height=34,
            font=ui_font(13),
        ).pack(side="left", padx=(6, 0))

        self.player_open_btn = ghost_button(
            controls,
            "Show file",
            command=self.player_open_current_file,
            width=88,
            height=34,
            font=ui_font(10),
            state="disabled",
        )
        self.player_open_btn.pack(side="right")

        volume = CTk.CTkFrame(controls, fg_color="transparent")
        volume.pack(side="right", padx=(0, 10))
        CTk.CTkLabel(
            volume,
            text="VOL",
            font=ui_font(9, "bold"),
            text_color=COLORS["muted"],
        ).pack(side="left", padx=(0, 6))
        self.player_volume_slider = CTk.CTkSlider(
            volume,
            from_=0,
            to=1,
            width=104,
            height=14,
            button_length=14,
            fg_color=COLORS["border"],
            progress_color=COLORS["accent"],
            button_color=COLORS["accent"],
            button_hover_color=COLORS["accent_hover"],
            command=self.player_set_volume,
        )
        self.player_volume_slider.pack(side="left")
        self.player_volume_slider.set(self.player_volume)

    def _build_player_library(self):
        card = CTk.CTkFrame(
            self.player_view,
            fg_color=COLORS["surface"],
            corner_radius=18,
            border_width=1,
            border_color=COLORS["border"],
        )
        card.grid(row=2, column=0, sticky="nsew")
        card.grid_columnconfigure(0, weight=1)
        card.grid_rowconfigure(1, weight=1)

        head = CTk.CTkFrame(card, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=16, pady=(12, 8))
        CTk.CTkLabel(
            head,
            text="Library",
            font=ui_font(15, "bold"),
            text_color=COLORS["text"],
        ).pack(side="left")
        self.player_library_count_lbl = CTk.CTkLabel(
            head,
            text="",
            font=ui_font(10),
            text_color=COLORS["muted"],
        )
        self.player_library_count_lbl.pack(side="left", padx=(8, 0))
        self.player_filter_entry = CTk.CTkEntry(
            head,
            placeholder_text="Filter by title, artist, or album…",
            width=228,
            height=30,
            corner_radius=8,
            border_width=1,
            border_color=COLORS["border"],
            fg_color=COLORS["surface_muted"],
            text_color=COLORS["text"],
            placeholder_text_color=COLORS["muted"],
            font=ui_font(10),
        )
        self.player_filter_entry.pack(side="right")
        self.player_filter_entry.bind("<KeyRelease>", self._player_filter_changed)

        self.player_scroll = CTk.CTkScrollableFrame(
            card,
            fg_color="transparent",
            corner_radius=0,
            scrollbar_button_color=COLORS["border"],
            scrollbar_button_hover_color=COLORS["border_strong"],
        )
        self.player_scroll.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))
        self._player_library_rendered = False

    # -------------------------------------------------------------- helpers

    def _player_update_buttons(self):
        if not hasattr(self, "player_play_btn"):
            return
        playing = (
            self.player_engine.state == "playing" and not self.player_is_paused
        )
        if self.player_current is None and not self.player_library:
            self.player_play_btn.configure(text="▶  Play", state="disabled")
        else:
            self.player_play_btn.configure(
                text="❚❚  Pause" if playing else "▶  Play", state="normal"
            )
        has_track = self.player_current is not None
        if hasattr(self, "player_open_btn"):
            self.player_open_btn.configure(state="normal" if has_track else "disabled")
        if hasattr(self, "player_progress"):
            self.player_progress.configure(state="normal" if has_track else "disabled")

    def _player_set_cover(self, cover):
        self._player_cover_ref = None
        if cover:
            try:
                image = Image.open(io.BytesIO(cover))
                rounded = rounded_image(image, size=120, radius=16)
                ctk_image = CTk.CTkImage(
                    light_image=rounded, dark_image=rounded, size=(120, 120)
                )
                self._player_cover_ref = ctk_image
                self.player_cover_image_lbl.configure(image=ctk_image, text="")
                self.player_cover_placeholder.place_forget()
                self.player_cover_image_lbl.place(relx=0.5, rely=0.5, anchor="center")
                return
            except Exception:
                pass
        self.player_cover_image_lbl.place_forget()
        self.player_cover_placeholder.place(relx=0.5, rely=0.5, anchor="center")

    def _update_player_now(self, info):
        if not hasattr(self, "player_title_lbl"):
            return
        if info is None:
            self.player_title_lbl.configure(text="Nothing playing")
            self.player_artist_lbl.configure(
                text="Pick a track from your library below."
            )
            self.player_detail_lbl.configure(
                text="Downloads show up here automatically.",
                text_color=COLORS["muted"],
            )
            self.player_format_chip.configure(
                text="AUDIO",
                fg_color=FORMAT_BADGES["AUDIO"][0],
                text_color=FORMAT_BADGES["AUDIO"][1],
            )
            self.player_elapsed_lbl.configure(text="0:00")
            self.player_total_lbl.configure(text="0:00")
            self.player_progress.set(0)
            self._player_set_cover(None)
            return

        artist = info.get("artist") or "Unknown artist"
        album = info.get("album") or ""
        subtitle = f"{artist} · {album}" if album else artist
        self.player_title_lbl.configure(
            text=truncate_middle(info.get("title") or "Unknown title", 58)
        )
        self.player_artist_lbl.configure(text=truncate_middle(subtitle, 72))
        self.player_detail_lbl.configure(
            text=f"{format_size(info.get('size'))} · {format_time(info.get('duration'))} · {os.path.basename(info.get('path', ''))}",
            text_color=COLORS["muted"],
        )
        background, foreground = FORMAT_BADGES.get(
            info.get("format", "AUDIO"), FORMAT_BADGES["AUDIO"]
        )
        self.player_format_chip.configure(
            text=info.get("badge") or info.get("format", "AUDIO"),
            fg_color=background,
            text_color=foreground,
        )
        self.player_total_lbl.configure(text=format_time(info.get("duration")))
        self.player_elapsed_lbl.configure(text="0:00")
        self.player_progress.set(0)
        self._player_set_cover(info.get("cover"))

    # --------------------------------------------------------------- library

    def player_on_view_opened(self):
        root = os.path.abspath(self.config.download_directory)
        if (
            self._player_library_stale
            or root != self.player_library_root
            or not self._player_library_rendered
        ):
            self.player_refresh_library()

    def player_note_library_changed(self):
        self._player_library_stale = True
        if getattr(self, "active_view", "") != "player":
            return
        if self._player_refresh_job is None:
            self._player_refresh_job = self.after(
                1200, self._player_refresh_after_downloads
            )

    def _player_refresh_after_downloads(self):
        self._player_refresh_job = None
        if getattr(self, "active_view", "") == "player":
            self.player_refresh_library(force=True)

    def player_refresh_library(self, force=False):
        if not hasattr(self, "player_library_count_lbl"):
            return
        root = os.path.abspath(self.config.download_directory)
        if (
            not force
            and not self._player_library_stale
            and root == self.player_library_root
            and self._player_library_rendered
        ):
            self._render_player_library()
            return
        self._player_scan_token += 1
        token = self._player_scan_token
        self.player_library_count_lbl.configure(text="Scanning library…")
        self.run_async(self._scan_player_library(root, token))

    async def _scan_player_library(self, root, token):
        try:
            infos = await asyncio.to_thread(scan_library, root)
            self.after(0, self._apply_player_library, root, infos, token)
        except Exception as exc:
            self.after(0, self._player_scan_failed, str(exc), token)

    def _player_scan_failed(self, error, token):
        if token != self._player_scan_token:
            return
        self.player_library_count_lbl.configure(text="Scan failed")
        print(f"Player library scan failed: {error}")

    def _apply_player_library(self, root, infos, token):
        if token != self._player_scan_token:
            return
        self.player_library = infos
        self.player_library_root = root
        self._player_library_stale = False
        self._player_library_rendered = True

        if self.player_current is not None:
            current_path = os.path.normcase(self.player_current["path"])
            previous_cover = self.player_current.get("cover")
            match = next(
                (
                    index
                    for index, item in enumerate(infos)
                    if os.path.normcase(item["path"]) == current_path
                ),
                None,
            )
            if match is not None:
                if not infos[match].get("cover") and previous_cover:
                    infos[match]["cover"] = previous_cover
                self.player_index = match
                self.player_current = infos[match]
                self._update_player_now(infos[match])
            elif self.player_engine.state == "stopped":
                self.player_current = None
                self.player_index = -1
                self._update_player_now(None)
        self._player_update_buttons()
        self._render_player_library()

    def _player_filter_changed(self, _event=None):
        self._render_player_library()

    def _render_player_library(self):
        if not hasattr(self, "player_scroll"):
            return
        try:
            for child in self.player_scroll.winfo_children():
                child.destroy()
        except Exception:
            pass

        query = ""
        try:
            query = self.player_filter_entry.get().strip().casefold()
        except Exception:
            pass

        visible = []
        for index, info in enumerate(self.player_library):
            if query:
                haystack = " ".join(
                    (
                        info.get("title", ""),
                        info.get("artist", ""),
                        info.get("album", ""),
                        info.get("format", ""),
                    )
                ).casefold()
                if query not in haystack:
                    continue
            visible.append((index, info))

        total = len(self.player_library)
        if query:
            self.player_library_count_lbl.configure(
                text=f"{len(visible)} of {total} tracks"
            )
        else:
            self.player_library_count_lbl.configure(
                text=f"{total} track{'s' if total != 1 else ''}"
            )

        if not total:
            self._render_player_empty(
                "Your library is empty",
                "Download music from Tidal or YouTube. Files appear here with their real format, like FLAC or MP3.",
            )
            return
        if not visible:
            self._render_player_empty(
                "No tracks match your filter",
                "Try a different title, artist, or album name.",
            )
            return

        current_path = (
            os.path.normcase(self.player_current["path"])
            if self.player_current
            else None
        )
        playing = (
            self.player_engine.state == "playing" and not self.player_is_paused
        )

        for index, info in visible:
            is_current = (
                current_path is not None
                and os.path.normcase(info["path"]) == current_path
            )
            row = CTk.CTkFrame(
                self.player_scroll,
                fg_color=COLORS["accent_soft"] if is_current else "transparent",
                corner_radius=10,
            )
            row.pack(fill="x", padx=2, pady=1)
            body = CTk.CTkFrame(row, fg_color="transparent")
            body.pack(fill="x", padx=8, pady=6)

            play_text = "❚❚" if is_current and playing else "▶"
            play_btn = CTk.CTkButton(
                body,
                text=play_text,
                width=30,
                height=30,
                corner_radius=8,
                fg_color="transparent",
                hover_color=COLORS["surface_hover"],
                text_color=COLORS["accent_text"] if is_current else COLORS["muted"],
                font=ui_font(10, "bold"),
                command=lambda i=index: self._player_row_clicked(i),
            )
            play_btn.pack(side="left", padx=(0, 8))

            info_box = CTk.CTkFrame(body, fg_color="transparent")
            info_box.pack(side="left", fill="both", expand=True)
            title_lbl = CTk.CTkLabel(
                info_box,
                text=truncate_middle(info.get("title") or "Unknown title", 52),
                font=ui_font(12, "bold"),
                text_color=COLORS["accent_text"] if is_current else COLORS["text"],
                anchor="w",
            )
            title_lbl.pack(fill="x", anchor="w")
            artist = info.get("artist") or "Unknown artist"
            album = info.get("album") or ""
            subtitle = f"{artist} · {album}" if album else artist
            subtitle_lbl = CTk.CTkLabel(
                info_box,
                text=truncate_middle(subtitle, 52),
                font=ui_font(9),
                text_color=COLORS["text_secondary"],
                anchor="w",
            )
            subtitle_lbl.pack(fill="x", anchor="w")

            background, foreground = FORMAT_BADGES.get(
                info.get("format", "AUDIO"), FORMAT_BADGES["AUDIO"]
            )
            format_chip = chip_label(
                body,
                info.get("badge") or info.get("format", "AUDIO"),
                fg_color=background,
                text_color=foreground,
                height=20,
                font=ui_font(9, "bold"),
            )
            format_chip.pack(side="right", padx=(8, 0))

            duration_lbl = CTk.CTkLabel(
                body,
                text=format_time(info.get("duration")),
                font=ui_font(9),
                text_color=COLORS["muted"],
                width=44,
                anchor="e",
            )
            duration_lbl.pack(side="right", padx=(0, 8))

            for widget in (row, body, info_box, title_lbl, subtitle_lbl):
                widget.bind(
                    "<Button-1>", lambda _event, i=index: self._player_row_clicked(i)
                )

    def _render_player_empty(self, title, text):
        card = CTk.CTkFrame(
            self.player_scroll,
            fg_color=COLORS["surface_muted"],
            corner_radius=14,
            border_width=1,
            border_color=COLORS["border"],
        )
        card.pack(fill="x", padx=2, pady=2)
        body = CTk.CTkFrame(card, fg_color="transparent")
        body.pack(padx=22, pady=18)
        CTk.CTkLabel(
            body,
            text="♫",
            width=38,
            height=38,
            corner_radius=19,
            fg_color=COLORS["accent_soft"],
            text_color=COLORS["accent"],
            font=ui_font(16, "bold"),
        ).pack(pady=(0, 8))
        CTk.CTkLabel(
            body,
            text=title,
            font=ui_font(13, "bold"),
            text_color=COLORS["text"],
        ).pack()
        CTk.CTkLabel(
            body,
            text=text,
            font=ui_font(10),
            text_color=COLORS["text_secondary"],
            wraplength=560,
            justify="center",
        ).pack(pady=(4, 0))

    def _player_row_clicked(self, index):
        current = self.player_current
        info = self.player_library[index] if 0 <= index < len(self.player_library) else None
        if (
            current is not None
            and info is not None
            and os.path.normcase(current["path"]) == os.path.normcase(info["path"])
            and self.player_engine.state in ("playing", "paused")
        ):
            self.player_toggle_play()
            return
        self.player_play_index(index)

    # -------------------------------------------------------------- playback

    def player_play_index(self, index):
        if not self.player_library:
            self.player_refresh_library(force=True)
            return
        index = max(0, min(int(index), len(self.player_library) - 1))
        info = self.player_library[index]
        self._player_load_token += 1
        token = self._player_load_token
        self.player_index = index
        self.player_current = info
        self.player_is_paused = False
        self.player_engine.stop()
        self._update_player_now(info)
        self.player_play_btn.configure(text="…", state="disabled")
        self._render_player_library()

        self.run_async(self._prepare_player_track(info, token))

    async def _prepare_player_track(self, info, token):
        try:
            playable, is_temp = await asyncio.to_thread(
                prepare_playback, info["path"]
            )
            cover = info.get("cover")
            if cover is None:
                fresh = await asyncio.to_thread(probe_audio, info["path"])
                cover = fresh.get("cover")
            if token != self._player_load_token:
                return
            self.after(
                0, self._start_player_playback, info, playable, is_temp, token, cover
            )
        except Exception as exc:
            self.after(0, self._player_playback_error, str(exc), token)

    def _start_player_playback(self, info, playable, is_temp, token, cover=None):
        if token != self._player_load_token:
            return
        try:
            self.player_engine.load(playable)
            self.player_engine.set_volume(self.player_volume)
            self.player_engine.play()
        except Exception as exc:
            self._player_playback_error(str(exc), token)
            return
        if cover:
            info["cover"] = cover
            self._player_set_cover(cover)
        self._player_temp_path = playable if is_temp else None
        self.player_is_paused = False
        self._player_started_at = time.monotonic()
        self._player_update_buttons()
        self._render_player_library()

    def _player_playback_error(self, error, token):
        if token != self._player_load_token:
            return
        self.player_engine.close()
        self.player_is_paused = False
        self.player_detail_lbl.configure(
            text=truncate_middle(f"Playback failed · {error}", 90),
            text_color=COLORS["error"],
        )
        self._player_update_buttons()
        self._render_player_library()

    def player_toggle_play(self):
        if not self.player_library:
            self.player_refresh_library(force=True)
            return
        if self.player_current is None:
            self.player_play_index(self.player_index if self.player_index >= 0 else 0)
            return

        state = self.player_engine.state
        if state == "playing" and not self.player_is_paused:
            self.player_engine.pause()
            self.player_is_paused = True
        else:
            if self.player_engine.length():
                position = self.player_engine.position()
                if position >= self.player_engine.length() - 300:
                    self.player_engine.seek(0)
            self.player_engine.play()
            self.player_is_paused = False
            self._player_started_at = time.monotonic()
        self._player_update_buttons()
        self._render_player_library()

    def player_advance(self, direction):
        if not self.player_library:
            return
        if self.player_index < 0:
            self.player_play_index(0)
            return
        next_index = (self.player_index + int(direction)) % len(self.player_library)
        self.player_play_index(next_index)

    def player_set_volume(self, value):
        self.player_volume = max(0.0, min(1.0, float(value)))
        self.player_engine.set_volume(self.player_volume)

    def player_open_current_file(self):
        if self.player_current:
            open_in_file_manager(self.player_current["path"], select_file=True)

    def player_open_path(self, path):
        """Plays a file from the queue and switches to the player view."""
        if not path or not os.path.exists(path):
            return False
        path = os.path.abspath(path)
        self.switch_view("player")
        target = os.path.normcase(path)
        index = next(
            (
                position
                for position, item in enumerate(self.player_library)
                if os.path.normcase(item["path"]) == target
            ),
            None,
        )
        if index is None:
            try:
                info = probe_audio(path)
            except Exception as exc:
                print(f"Could not read audio file for player: {exc}")
                return False
            self.player_library.append(info)
            index = len(self.player_library) - 1
        self.player_play_index(index)
        return True

    # ------------------------------------------------------------------ tick

    def _player_tick(self):
        try:
            if self.player_current is not None:
                length_ms = self.player_engine.length()
                if length_ms:
                    position_ms = self.player_engine.position()
                    if not self._player_seek_dragging:
                        self.player_progress.set(
                            min(1.0, position_ms / float(length_ms))
                        )
                        self.player_elapsed_lbl.configure(
                            text=format_time(position_ms / 1000)
                        )
                    if (
                        not self.player_is_paused
                        and self.player_engine.state == "playing"
                        and self.player_engine.mode() == "stopped"
                        and time.monotonic() - self._player_started_at > 1.0
                    ):
                        self._player_finished_track()
        except Exception as exc:
            print(f"Player tick error: {exc}")
        finally:
            if self.winfo_exists():
                self._player_tick_job = self.after(450, self._player_tick)

    def _player_finished_track(self):
        if self.player_index >= len(self.player_library) - 1:
            self.player_engine.finish()
            self.player_is_paused = False
            self.player_progress.set(1.0)
            self.player_elapsed_lbl.configure(
                text=format_time(self.player_engine.length() / 1000)
            )
            self.player_play_btn.configure(text="↻  Replay", state="normal")
            self._render_player_library()
            return
        self.player_play_index(self.player_index + 1)

    def _player_seek_started(self, _event=None):
        self._player_seek_dragging = True

    def _player_seek_released(self, _event=None):
        self._player_seek_dragging = False
        if self.player_current is None or not self.player_engine.length():
            return
        self.player_engine.seek(
            int(float(self.player_progress.get()) * self.player_engine.length())
        )
        self._player_started_at = time.monotonic()
        self._player_update_buttons()

    def _player_seek_value_changed(self, value):
        if self.player_current is None or not self.player_engine.length():
            return
        self.player_elapsed_lbl.configure(
            text=format_time(float(value) * self.player_engine.length() / 1000)
        )

    # -------------------------------------------------------------- shutdown

    def player_shutdown(self):
        self._player_load_token += 1
        self._player_scan_token += 1
        if self._player_tick_job is not None:
            try:
                self.after_cancel(self._player_tick_job)
            except Exception:
                pass
            self._player_tick_job = None
        if self._player_refresh_job is not None:
            try:
                self.after_cancel(self._player_refresh_job)
            except Exception:
                pass
            self._player_refresh_job = None
        try:
            self.player_engine.close()
        except Exception:
            pass
        cleanup_playback_cache()

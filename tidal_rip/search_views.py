"""Search and result rendering for Tidal and YouTube."""

from tkinter import messagebox

import customtkinter as CTk

from .components import (
    SEARCH_COPY,
    TrackSelectionModal,
    chip_label,
    format_specs,
    get_quality_badge,
    ghost_button,
    parse_tidal_url,
    primary_button,
)
from .link_resolver import is_external_music_link, resolve_external_link
from .theme import COLORS, source_meta, ui_font
from .widgets import truncate_middle
from .youtube_service import format_duration, is_youtube_url


TIDAL_TYPES = ("tracks", "albums", "playlists", "artists")
TIDAL_TYPE_LABELS = {
    "tracks": "Tracks",
    "albums": "Albums",
    "playlists": "Playlists",
    "artists": "Artists",
}


class SearchViewMixin:
    """Builds the search view and implements the three source-specific flows."""

    # ---------------------------------------------------------------- layout

    def create_search_view(self):
        self.search_view = CTk.CTkFrame(self.main_container, fg_color="transparent")
        self.search_view.grid_columnconfigure(0, weight=1)
        self.search_view.grid_rowconfigure(3, weight=1)

        header = CTk.CTkFrame(self.search_view, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", pady=(0, 16))

        self.search_title_lbl = CTk.CTkLabel(
            header,
            text="Search Tidal",
            font=ui_font(26, "bold"),
            text_color=COLORS["text"],
            anchor="w",
        )
        self.search_title_lbl.pack(fill="x", anchor="w")
        self.search_sub_lbl = CTk.CTkLabel(
            header,
            text="",
            font=ui_font(12),
            text_color=COLORS["text_secondary"],
            anchor="w",
            justify="left",
        )
        self.search_sub_lbl.pack(fill="x", anchor="w", pady=(4, 0))

        search_card = CTk.CTkFrame(
            self.search_view,
            fg_color=COLORS["surface"],
            corner_radius=16,
            border_width=1,
            border_color=COLORS["border"],
        )
        search_card.grid(row=1, column=0, sticky="ew")

        search_inner = CTk.CTkFrame(search_card, fg_color="transparent")
        search_inner.pack(fill="x", padx=12, pady=12)
        search_inner.grid_columnconfigure(0, weight=1)

        self.search_entry = CTk.CTkEntry(
            search_inner,
            placeholder_text=SEARCH_COPY["tidal"]["placeholder"],
            height=42,
            corner_radius=10,
            border_width=1,
            border_color=COLORS["border"],
            fg_color=COLORS["surface_muted"],
            text_color=COLORS["text"],
            placeholder_text_color=COLORS["muted"],
            font=ui_font(13),
        )
        self.search_entry.grid(row=0, column=0, sticky="ew")
        self.search_entry.bind("<Return>", lambda _event: self.trigger_search())

        self.clear_search_btn = CTk.CTkButton(
            search_inner,
            text="✕",
            width=32,
            height=42,
            fg_color="transparent",
            hover_color=COLORS["surface_hover"],
            text_color=COLORS["muted"],
            font=ui_font(12, "bold"),
            corner_radius=8,
            command=self.clear_search_entry,
        )
        self.clear_search_btn.grid(row=0, column=1, padx=(4, 0))

        self.search_type_menu = CTk.CTkOptionMenu(
            search_inner,
            values=[TIDAL_TYPE_LABELS[t] for t in TIDAL_TYPES],
            width=118,
            height=42,
            corner_radius=10,
            fg_color=COLORS["surface_muted"],
            button_color=COLORS["surface_hover"],
            button_hover_color=COLORS["border"],
            text_color=COLORS["text"],
            dropdown_fg_color=COLORS["surface"],
            dropdown_hover_color=COLORS["surface_hover"],
            dropdown_text_color=COLORS["text"],
            font=ui_font(12),
            dropdown_font=ui_font(12),
        )
        self.search_type_menu.grid(row=0, column=2, sticky="w", padx=(8, 0))
        self.search_type_menu.set("Tracks")

        self.search_btn = primary_button(
            search_inner,
            SEARCH_COPY["tidal"]["button"],
            command=self.trigger_search,
            width=142,
            height=42,
        )
        self.search_btn.grid(row=0, column=3, sticky="e", padx=(8, 0))

        hint = CTk.CTkFrame(self.search_view, fg_color="transparent")
        hint.grid(row=2, column=0, sticky="ew", pady=(8, 4))
        self.search_hint_lbl = CTk.CTkLabel(
            hint,
            text="",
            font=ui_font(11),
            text_color=COLORS["muted"],
            anchor="w",
            justify="left",
        )
        self.search_hint_lbl.pack(side="left", fill="x", expand=True)
        self.search_hint_action = ghost_button(
            hint, "Log in", command=self.handle_login_click, width=96, height=28
        )

        self.results_scroll = CTk.CTkScrollableFrame(
            self.search_view,
            fg_color="transparent",
            corner_radius=0,
            scrollbar_button_color=COLORS["border"],
            scrollbar_button_hover_color=COLORS["border_strong"],
        )
        self.results_scroll.grid(row=3, column=0, sticky="nsew", pady=(10, 0))

        self._loading_bar = None

    # ------------------------------------------------------------- utilities

    def _clear_results(self):
        if getattr(self, "_loading_bar", None) is not None:
            try:
                self._loading_bar.stop()
            except Exception:
                pass
            self._loading_bar = None
        try:
            for child in self.results_scroll.winfo_children():
                child.destroy()
        except Exception:
            pass

    def _set_search_busy(self, busy, text=None):
        self._search_busy = busy
        if hasattr(self, "search_btn") and self.search_btn.winfo_exists():
            copy = SEARCH_COPY.get(self.source, SEARCH_COPY["tidal"])
            self.search_btn.configure(
                state="disabled" if busy else "normal",
                text=text or ("Searching…" if busy else copy["button"]),
            )

    def _show_search_status(self, text):
        self._clear_results()
        card = CTk.CTkFrame(
            self.results_scroll,
            fg_color=COLORS["surface"],
            corner_radius=16,
            border_width=1,
            border_color=COLORS["border"],
        )
        card.pack(fill="x", padx=2, pady=(0, 10))
        CTk.CTkLabel(
            card,
            text=text,
            font=ui_font(12),
            text_color=COLORS["text_secondary"],
            anchor="w",
            justify="left",
        ).pack(fill="x", padx=20, pady=(18, 10))
        bar = CTk.CTkProgressBar(
            card,
            height=4,
            corner_radius=2,
            fg_color=COLORS["surface_soft"],
            progress_color=COLORS["accent"],
            mode="indeterminate",
        )
        bar.pack(fill="x", padx=20, pady=(0, 18))
        bar.start()
        self._loading_bar = bar

    def _show_message_card(
        self, title, text, action_text=None, action=None, tone="info"
    ):
        self._clear_results()
        if tone == "error":
            palette = (COLORS["error_soft"], COLORS["error"], "!")
        else:
            palette = (COLORS["accent_soft"], COLORS["accent_text"], "♪")
        card = CTk.CTkFrame(
            self.results_scroll,
            fg_color=COLORS["surface"],
            corner_radius=18,
            border_width=1,
            border_color=COLORS["border"],
        )
        card.pack(fill="x", padx=2, pady=(0, 10))
        body = CTk.CTkFrame(card, fg_color="transparent")
        body.pack(padx=28, pady=30)
        CTk.CTkLabel(
            body,
            text=palette[2],
            width=46,
            height=46,
            corner_radius=23,
            fg_color=palette[0],
            text_color=palette[1],
            font=ui_font(19, "bold"),
        ).pack(pady=(0, 12))
        CTk.CTkLabel(
            body,
            text=title,
            font=ui_font(17, "bold"),
            text_color=COLORS["text"],
            anchor="center",
        ).pack()
        CTk.CTkLabel(
            body,
            text=text,
            font=ui_font(11),
            text_color=COLORS["text_secondary"],
            wraplength=620,
            justify="center",
            anchor="center",
        ).pack(pady=(6, 0))
        if action_text and action:
            primary_button(body, action_text, command=action, width=190, height=36).pack(
                pady=(18, 0)
            )

    def _show_source_intro(self):
        self._clear_results()
        copy = SEARCH_COPY[self.source]
        meta = source_meta(self.source)

        card = CTk.CTkFrame(
            self.results_scroll,
            fg_color=COLORS["surface"],
            corner_radius=18,
            border_width=1,
            border_color=COLORS["border"],
        )
        card.pack(fill="x", padx=2, pady=(0, 10))
        body = CTk.CTkFrame(card, fg_color="transparent")
        body.pack(fill="x", padx=26, pady=26)

        top = CTk.CTkFrame(body, fg_color="transparent")
        top.pack(fill="x")

        icon_text = {"tidal": "♪", "youtube": "▶"}.get(self.source, "♪")
        CTk.CTkLabel(
            top,
            text=icon_text,
            width=54,
            height=54,
            corner_radius=16,
            fg_color=meta["soft"],
            text_color=meta["color"],
            font=ui_font(22, "bold"),
        ).pack(side="left", padx=(0, 16))

        titles = CTk.CTkFrame(top, fg_color="transparent")
        titles.pack(side="left", fill="x", expand=True)
        chip_label(
            titles,
            f"{meta['label']} · {meta['format']}",
            fg_color=meta["soft"],
            text_color=meta["color"],
        ).pack(anchor="w", pady=(2, 4))
        CTk.CTkLabel(
            titles,
            text=copy["intro_title"],
            font=ui_font(18, "bold"),
            text_color=COLORS["text"],
            anchor="w",
        ).pack(fill="x", anchor="w")

        CTk.CTkLabel(
            body,
            text=copy["intro_text"],
            font=ui_font(11),
            text_color=COLORS["text_secondary"],
            anchor="w",
            justify="left",
            wraplength=760,
        ).pack(fill="x", anchor="w", pady=(14, 12))

        features = CTk.CTkFrame(body, fg_color="transparent")
        features.pack(fill="x")
        for line in copy["highlights"].split("\n"):
            row = CTk.CTkFrame(features, fg_color="transparent")
            row.pack(fill="x", pady=2)
            CTk.CTkLabel(
                row,
                text="✓",
                width=20,
                font=ui_font(11, "bold"),
                text_color=COLORS["success"],
                anchor="w",
            ).pack(side="left")
            CTk.CTkLabel(
                row,
                text=line,
                font=ui_font(11),
                text_color=COLORS["text_secondary"],
                anchor="w",
            ).pack(side="left")

        if self.source == "tidal" and not self.config.access_token:
            primary_button(
                body,
                "Log in to Tidal",
                command=self.handle_login_click,
                width=170,
                height=36,
            ).pack(anchor="w", pady=(18, 0))

    def _update_search_copy(self):
        if not hasattr(self, "search_title_lbl"):
            return
        copy = SEARCH_COPY[self.source]
        self.search_title_lbl.configure(text=copy["title"])
        self.search_sub_lbl.configure(text=copy["subtitle"])
        self.search_entry.configure(placeholder_text=copy["placeholder"])
        if hasattr(self, "_search_busy") and self._search_busy:
            self.search_btn.configure(text="Searching…")
        else:
            self.search_btn.configure(text=copy["button"])
        if self.source == "tidal":
            self.search_type_menu.grid(row=0, column=2, sticky="w", padx=(8, 0))
        else:
            self.search_type_menu.grid_remove()
        self._update_search_hint()

    def _update_search_hint(self):
        if not hasattr(self, "search_hint_lbl"):
            return
        action = None
        action_text = None
        if self.source == "tidal":
            if self.config.access_token:
                text = "Tip · Paste a Tidal link, or search by song, album, playlist, or artist."
            else:
                text = "Tidal login is required to search and download from the lossless catalog."
                action_text = "Log in"
                action = self.handle_login_click
        else:
            bitrate = getattr(self.config, "mp3_bitrate", "320")
            text = f"Audio is converted to MP3 {bitrate} kbps with cover art and ID3 tags."

        self.search_hint_lbl.configure(text=text)
        if action:
            self.search_hint_action.configure(text=action_text, command=action)
            if not self.search_hint_action.winfo_ismapped():
                self.search_hint_action.pack(side="right", padx=(12, 0))
        else:
            self.search_hint_action.pack_forget()

    # ----------------------------------------------------------- search flow

    def clear_search_entry(self):
        self.search_entry.delete(0, "end")
        self.search_entry.focus_set()

    def trigger_search(self):
        query = self.search_entry.get().strip()
        if not query:
            self._show_message_card(
                "Start with a search",
                "Type a song, album, artist, or paste a link to begin.",
            )
            self.search_entry.focus_set()
            return

        if self.source == "tidal" and not self.config.access_token:
            self._show_message_card(
                "Tidal login required",
                "Connect your Tidal account to search the lossless catalog.",
                "Log in to Tidal",
                self.handle_login_click,
            )
            return

        self._search_gen = getattr(self, "_search_gen", 0) + 1
        gen = self._search_gen
        self._set_search_busy(True)

        if self.source == "tidal":
            self._show_search_status("Searching Tidal…")
            search_type = self.search_type_menu.get().lower()
            self.run_async(self.perform_search(query, search_type, gen=gen))
        else:
            self._show_search_status("Searching YouTube…")
            self.run_async(self.perform_youtube_search(query, gen=gen))

    @staticmethod
    def _normalize_tidal_type(value):
        mapping = {
            "track": "tracks",
            "tracks": "tracks",
            "album": "albums",
            "albums": "albums",
            "playlist": "playlists",
            "playlists": "playlists",
            "artist": "artists",
            "artists": "artists",
        }
        return mapping.get(str(value).lower(), "tracks")

    def _apply_search_type(self, search_type):
        self.search_type_menu.set(TIDAL_TYPE_LABELS.get(search_type, "Tracks"))

    async def perform_search(self, query, search_type, gen=None):
        query = query.strip()
        search_type = self._normalize_tidal_type(search_type)

        if is_external_music_link(query):
            self.after(0, lambda: self._show_search_status("Resolving external link…"))
            try:
                resolved = await resolve_external_link(query)
                resolved_query, resolved_type, display_info, service_name = resolved
            except Exception as exc:
                self.after(
                    0,
                    self.finish_search,
                    None,
                    search_type,
                    f"Could not resolve this link: {exc}",
                    gen,
                )
                return

            if not resolved_query:
                self.after(0, self.finish_search, None, search_type, None, gen)
                self.after(
                    0,
                    lambda: self._show_message_card(
                        "Link not recognised",
                        "Could not read metadata from this link. Try the original Tidal link or search by name.",
                        tone="error",
                    ),
                )
                return

            if resolved_type:
                search_type = self._normalize_tidal_type(resolved_type)
                self.after(0, self._apply_search_type, search_type)
            self.after(
                0,
                lambda info=display_info, svc=service_name: self._show_search_status(
                    f"Found on {svc} · {info}\nSearching Tidal…"
                ),
            )
            try:
                results = await self.api.smart_search(
                    resolved_query, search_type=search_type, limit=50
                )
                self.after(0, self.finish_search, results, search_type, None, gen)
            except Exception as exc:
                self.after(
                    0,
                    self.finish_search,
                    None,
                    search_type,
                    f"Search request failed: {exc}",
                    gen,
                )
            return

        url_type, url_id = parse_tidal_url(query)
        if url_type:
            try:
                if url_type == "track":
                    track = await self.api.get_track(url_id)
                    results = {"tracks": {"items": [track]}}
                    self.after(0, self.finish_search, results, "tracks", None, gen)
                elif url_type == "album":
                    album = await self.api.get_album(url_id)
                    results = {"albums": {"items": [album]}}
                    self.after(0, self.finish_search, results, "albums", None, gen)
                elif url_type == "playlist":
                    playlist = await self.api.get_playlist(url_id)
                    results = {"playlists": {"items": [playlist]}}
                    self.after(0, self.finish_search, results, "playlists", None, gen)
                elif url_type == "artist":
                    albums = await self.api.get_artist_albums(url_id)
                    self.after(0, self.finish_search, albums, "albums", None, gen)
            except Exception as exc:
                self.after(
                    0,
                    self.finish_search,
                    None,
                    search_type,
                    f"Failed to load this link: {exc}",
                    gen,
                )
            return

        try:
            results = await self.api.smart_search(
                query, search_type=search_type, limit=50
            )
            self.after(0, self.finish_search, results, search_type, None, gen)
        except Exception as exc:
            self.after(
                0,
                self.finish_search,
                None,
                search_type,
                f"Search request failed: {exc}",
                gen,
            )

    def finish_search(self, data, search_type, error_msg=None, gen=None):
        self._set_search_busy(False)
        if gen is not None and getattr(self, "_search_gen", 0) != gen:
            return
        if error_msg:
            self._show_message_card(
                "Search failed",
                error_msg,
                "Try again",
                self.trigger_search,
                tone="error",
            )
            return
        if data is not None:
            self.populate_results(data, search_type)

    def trigger_artist_albums_search(self, artist_id, artist_name=""):
        self.search_entry.delete(0, "end")
        self.search_entry.insert(0, f"https://tidal.com/artist/{artist_id}")
        self.search_type_menu.set("Albums")

        self._search_gen = getattr(self, "_search_gen", 0) + 1
        gen = self._search_gen
        self._set_search_busy(True)
        text = f"Fetching albums for {artist_name}…" if artist_name else "Fetching artist albums…"
        self._show_search_status(text)

        async def fetch_albums():
            try:
                albums = await self.api.get_artist_albums(artist_id)
                self.after(0, self.finish_search, albums, "albums", None, gen)
            except Exception as exc:
                self.after(
                    0,
                    self.finish_search,
                    None,
                    "albums",
                    f"Failed to retrieve albums: {exc}",
                    gen,
                )

        self.run_async(fetch_albums())

    # ------------------------------------------------------- Tidal rendering

    def _new_result_card(self):
        card = CTk.CTkFrame(
            self.results_scroll,
            fg_color=COLORS["surface"],
            corner_radius=16,
            border_width=1,
            border_color=COLORS["border"],
        )
        card.pack(fill="x", padx=2, pady=(0, 10))

        body = CTk.CTkFrame(card, fg_color="transparent")
        body.pack(fill="x", padx=14, pady=12)

        thumb = CTk.CTkLabel(
            body,
            text="♪",
            width=64,
            height=64,
            corner_radius=12,
            fg_color=COLORS["surface_soft"],
            text_color=COLORS["accent"],
            font=ui_font(20, "bold"),
        )
        thumb.pack(side="left", padx=(0, 14))

        actions = CTk.CTkFrame(body, fg_color="transparent")
        actions.pack(side="right", padx=(12, 0))

        info = CTk.CTkFrame(body, fg_color="transparent")
        info.pack(side="left", fill="both", expand=True)

        title = CTk.CTkLabel(
            info,
            text="",
            font=ui_font(13, "bold"),
            text_color=COLORS["text"],
            anchor="w",
            justify="left",
        )
        title.pack(fill="x", anchor="w")

        subtitle = CTk.CTkLabel(
            info,
            text="",
            font=ui_font(11),
            text_color=COLORS["text_secondary"],
            anchor="w",
            justify="left",
        )
        subtitle.pack(fill="x", anchor="w", pady=(2, 6))

        meta = CTk.CTkFrame(info, fg_color="transparent")
        meta.pack(fill="x", anchor="w")

        return card, thumb, info, actions, title, subtitle, meta

    def _add_chip(self, parent, text, fg_color, text_color):
        if not text:
            return None
        chip = chip_label(parent, text, fg_color=fg_color, text_color=text_color)
        chip.pack(side="left", padx=(0, 6))
        return chip

    def _add_duration(self, parent, seconds):
        text = format_duration(seconds)
        if not text:
            return
        CTk.CTkLabel(
            parent,
            text=text,
            font=ui_font(10),
            text_color=COLORS["muted"],
        ).pack(side="left", padx=(2, 0))

    def populate_results(self, data, search_type):
        self._clear_results()
        items = []
        if isinstance(data, dict) and isinstance(data.get("items"), list):
            items = data["items"]
        elif search_type == "tracks" and "tracks" in data:
            items = data["tracks"].get("items", [])
        elif search_type == "albums" and "albums" in data:
            items = data["albums"].get("items", [])
        elif search_type == "playlists" and "playlists" in data:
            items = data["playlists"].get("items", [])
        elif search_type == "artists" and "artists" in data:
            items = data["artists"].get("items", [])

        if not items:
            self._show_message_card(
                "No results found",
                "Nothing matched that search. Try another spelling, a different type, or paste a direct link.",
            )
            return

        for item in items:
            self._render_tidal_item(item, search_type)

    def _render_tidal_item(self, item, search_type):
        if search_type == "tracks":
            self._render_tidal_track(item)
        elif search_type in ("albums", "playlists"):
            self._render_tidal_collection(item, search_type)
        elif search_type == "artists":
            self._render_tidal_artist(item)

    def _render_tidal_track(self, item):
        _card, thumb, _info, actions, title_lbl, subtitle_lbl, meta = self._new_result_card()
        title = item.get("title", "Unknown title")
        artists = item.get("artists") or []
        artist = artists[0].get("name", "Unknown artist") if artists else "Unknown artist"
        album_info = item.get("album") or {}
        album = album_info.get("title", "")
        cover_id = album_info.get("cover")
        image_url = (
            f"https://resources.tidal.com/images/{cover_id.replace('-', '/')}/160x160.jpg"
            if cover_id
            else None
        )

        title_lbl.configure(text=truncate_middle(title, 70))
        subtitle_lbl.configure(
            text=f"{artist} · {album}" if album else artist
        )

        self._add_chip(
            meta,
            "Tidal",
            source_meta("tidal")["soft"],
            source_meta("tidal")["color"],
        )
        badge_text, badge_bg, badge_fg = get_quality_badge(item)
        quality_chip = self._add_chip(meta, badge_text, badge_bg, badge_fg)
        self._add_duration(meta, item.get("duration"))

        track_id = item.get("id")
        preview = ghost_button(
            actions,
            "▶",
            width=38,
            height=34,
            command=lambda tid=track_id, btn=None: None,
        )

        def toggle(btn=preview, tid=track_id):
            self.toggle_preview(tid, btn)

        preview.configure(command=toggle)
        preview.pack(side="left", padx=(0, 8))

        def download():
            self.queue_tidal_track(
                track_id,
                title,
                subtitle=artist,
                artist=artist,
                album=album,
            )

        primary_button(
            actions, "Download", command=download, width=104, height=34
        ).pack(side="left")

        if image_url:
            self.load_image(image_url, thumb, size=64)
        if quality_chip is not None and track_id:
            self.run_async(self.load_and_set_specs(track_id, quality_chip))

    def _render_tidal_collection(self, item, search_type):
        _card, thumb, _info, actions, title_lbl, subtitle_lbl, meta = self._new_result_card()
        title = item.get("title", "Unknown title")
        artists = item.get("artists") or []
        artist = artists[0].get("name", "Unknown artist") if artists else ""
        is_album = search_type == "albums"
        count = item.get("numberOfTracks")
        kind = "Album" if is_album else "Playlist"

        subtitle = artist
        if count:
            subtitle = f"{artist} · {count} tracks" if artist else f"{count} tracks"
        title_lbl.configure(text=truncate_middle(title, 70))
        subtitle_lbl.configure(text=subtitle or kind)

        self._add_chip(
            meta,
            "Tidal",
            source_meta("tidal")["soft"],
            source_meta("tidal")["color"],
        )
        badge_text, badge_bg, badge_fg = get_quality_badge(item)
        self._add_chip(meta, badge_text, badge_bg, badge_fg)
        CTk.CTkLabel(
            meta,
            text=kind,
            font=ui_font(10),
            text_color=COLORS["muted"],
        ).pack(side="left", padx=(2, 0))

        cover_id = item.get("cover") if is_album else item.get("squareImage")
        image_url = (
            f"https://resources.tidal.com/images/{cover_id.replace('-', '/')}/160x160.jpg"
            if cover_id
            else None
        )
        item_id = item.get("id") if is_album else item.get("uuid") or item.get("id")

        if is_album:
            command = lambda: self.queue_album_downloads(item_id, title)
        else:
            command = lambda: self.queue_playlist_downloads(item_id, title)

        primary_button(
            actions, "Select tracks", command=command, width=118, height=34
        ).pack(side="left")

        if image_url:
            self.load_image(image_url, thumb, size=64)

    def _render_tidal_artist(self, item):
        _card, thumb, _info, actions, title_lbl, subtitle_lbl, meta = self._new_result_card()
        name = item.get("name", "Unknown artist")
        title_lbl.configure(text=truncate_middle(name, 70))
        subtitle_lbl.configure(text="Artist")
        self._add_chip(
            meta,
            "Tidal",
            source_meta("tidal")["soft"],
            source_meta("tidal")["color"],
        )
        self._add_chip(
            meta, "Artist", COLORS["surface_soft"], COLORS["text_secondary"]
        )
        picture = item.get("picture")
        image_url = (
            f"https://resources.tidal.com/images/{picture.replace('-', '/')}/160x160.jpg"
            if picture
            else None
        )
        artist_id = item.get("id")
        ghost_button(
            actions,
            "View albums",
            command=lambda: self.trigger_artist_albums_search(artist_id, name),
            width=112,
            height=34,
        ).pack(side="left")
        if image_url:
            self.load_image(image_url, thumb, size=64)

    # ----------------------------------------------------- YouTube rendering

    async def perform_youtube_search(self, query, gen=None):
        try:
            if is_youtube_url(query):
                self.after(0, lambda: self._show_search_status("Reading YouTube link…"))
                resolved = await self.youtube_service.resolve_url(query)
                self.after(0, self.finish_youtube_resolve, resolved, None, gen)
            else:
                results = await self.youtube_service.search(query, limit=25)
                self.after(0, self.finish_youtube_search, results, None, gen)
        except Exception as exc:
            self.after(
                0,
                self.finish_youtube_search,
                None,
                f"YouTube request failed: {exc}",
                gen,
            )

    def finish_youtube_search(self, results, error_msg=None, gen=None):
        self._set_search_busy(False)
        if gen is not None and getattr(self, "_search_gen", 0) != gen:
            return
        if error_msg:
            self._show_message_card(
                "YouTube search failed",
                error_msg,
                "Try again",
                self.trigger_search,
                tone="error",
            )
            return
        if not results:
            self._show_message_card(
                "No videos found",
                "Try a different search, or paste a direct YouTube video or playlist link.",
            )
            return
        self._clear_results()
        for entry in results:
            self._render_youtube_video(entry)

    def finish_youtube_resolve(self, resolved, error_msg=None, gen=None):
        self._set_search_busy(False)
        if gen is not None and getattr(self, "_search_gen", 0) != gen:
            return
        if error_msg:
            self._show_message_card(
                "Could not read this YouTube link",
                error_msg,
                "Try again",
                self.trigger_search,
                tone="error",
            )
            return
        if not resolved:
            self._show_message_card(
                "Nothing to load", "This YouTube link did not contain any media."
            )
            return
        self._clear_results()
        if resolved.get("type") == "playlist":
            self._render_youtube_playlist(resolved)
        else:
            self._render_youtube_video(resolved.get("entry") or {})

    def _render_youtube_video(self, entry):
        _card, thumb, _info, actions, title_lbl, subtitle_lbl, meta = self._new_result_card()
        title = entry.get("display_title") or entry.get("title") or "Unknown video"
        artist = entry.get("artist") or "YouTube"
        duration = entry.get("duration") or 0
        title_lbl.configure(text=truncate_middle(title, 70))
        subtitle_lbl.configure(text=artist)
        self._add_chip(
            meta,
            "YouTube",
            source_meta("youtube")["soft"],
            source_meta("youtube")["color"],
        )
        self._add_chip(
            meta,
            f"MP3 {getattr(self.config, 'mp3_bitrate', '320')} kbps",
            COLORS["error_soft"],
            "#B91C1C",
        )
        self._add_duration(meta, duration)

        primary_button(
            actions,
            "Download",
            command=lambda: self.queue_youtube_entry(entry),
            width=104,
            height=34,
        ).pack(side="left")
        if entry.get("thumbnail"):
            self.load_image(entry["thumbnail"], thumb, size=64)

    def _render_youtube_playlist(self, collection):
        _card, thumb, _info, actions, title_lbl, subtitle_lbl, meta = self._new_result_card()
        title = collection.get("title") or "YouTube playlist"
        entries = collection.get("entries") or []
        artist = collection.get("artist") or "YouTube"
        title_lbl.configure(text=truncate_middle(title, 70))
        suffix = " · first 200 videos" if collection.get("truncated") else ""
        subtitle_lbl.configure(text=f"{artist} · {len(entries)} videos{suffix}")
        self._add_chip(
            meta,
            "YouTube playlist",
            source_meta("youtube")["soft"],
            source_meta("youtube")["color"],
        )

        ghost_button(
            actions,
            "Select videos",
            command=lambda: self._open_youtube_selection(entries, title),
            width=112,
            height=34,
        ).pack(side="left", padx=(0, 8))
        primary_button(
            actions,
            "Download all",
            command=lambda: self._queue_youtube_entries(entries, title),
            width=116,
            height=34,
        ).pack(side="left")
        if collection.get("thumbnail"):
            self.load_image(collection["thumbnail"], thumb, size=64)

    def _open_youtube_selection(self, entries, playlist_title):
        formatted = []
        for index, entry in enumerate(entries, start=1):
            formatted.append(
                {
                    "id": entry.get("video_id"),
                    "title": entry.get("display_title") or entry.get("title"),
                    "artist": entry.get("artist") or "YouTube",
                    "track_num": index,
                    "duration_str": entry.get("duration_str", ""),
                    "_entry": entry,
                }
            )
        if not formatted:
            messagebox.showinfo("Playlist", "This playlist has no downloadable videos.")
            return

        def on_confirm(selected):
            chosen = [t["_entry"] for t in selected if t.get("_entry")]
            self._queue_youtube_entries(chosen, playlist_title)

        TrackSelectionModal(
            parent=self,
            collection_type="YouTube playlist",
            collection_title=playlist_title,
            track_list=formatted,
            on_confirm_callback=on_confirm,
        )

    def _queue_youtube_entries(self, entries, parent_folder=None):
        if not entries:
            return
        for entry in entries:
            self.queue_youtube_entry(entry, parent_folder=parent_folder, switch=False)
        self.switch_view("queue")

    # ------------------------------------------------- Tidal collections

    def queue_album_downloads(self, album_id, album_title):
        self.run_async(self.fetch_and_queue_album(album_id, album_title))

    async def fetch_and_queue_album(self, album_id, album_title):
        try:
            tracks_resp = await self.api.get_album_tracks(album_id)
            items = tracks_resp.get("items", [])
            if not items:
                raise Exception("No tracks found on this album.")

            formatted = []
            for item in items:
                artists = item.get("artists") or []
                artist = (
                    artists[0].get("name", "Unknown artist")
                    if artists
                    else (item.get("artist") or {}).get("name", "Unknown artist")
                )
                duration = item.get("duration", 0)
                formatted.append(
                    {
                        "id": item["id"],
                        "title": item.get("title", "Unknown title"),
                        "artist": artist,
                        "track_num": item.get("trackNumber", len(formatted) + 1),
                        "disc_num": item.get("volumeNumber", 1),
                        "duration_str": format_duration(duration),
                    }
                )

            def open_dialog():
                TrackSelectionModal(
                    parent=self,
                    collection_type="Tidal album",
                    collection_title=album_title,
                    track_list=formatted,
                    on_confirm_callback=lambda selected: self.on_tracks_selected_for_download(
                        selected, album_title, is_playlist=False
                    ),
                )

            self.after(0, open_dialog)
        except Exception as exc:
            messagebox.showerror(
                "Album error", f"Failed to retrieve album tracks: {exc}"
            )

    def queue_playlist_downloads(self, playlist_id, playlist_title):
        self.run_async(self.fetch_and_queue_playlist(playlist_id, playlist_title))

    async def fetch_and_queue_playlist(self, playlist_id, playlist_title):
        try:
            items = await self.api.get_playlist_tracks(playlist_id)
            if not items:
                raise Exception("No tracks found in this playlist.")

            formatted = []
            for index, item in enumerate(items):
                track_info = item.get("item") if "item" in item else item
                if not track_info or "id" not in track_info:
                    continue
                artists = track_info.get("artists") or []
                artist = (
                    artists[0].get("name", "Unknown artist")
                    if artists
                    else (track_info.get("artist") or {}).get("name", "Unknown artist")
                )
                duration = track_info.get("duration", 0)
                formatted.append(
                    {
                        "id": track_info["id"],
                        "title": track_info.get("title", "Unknown title"),
                        "artist": artist,
                        "track_num": index + 1,
                        "disc_num": track_info.get("volumeNumber", 1),
                        "duration_str": format_duration(duration),
                    }
                )

            if not formatted:
                raise Exception("No downloadable tracks were found.")

            def open_dialog():
                TrackSelectionModal(
                    parent=self,
                    collection_type="Tidal playlist",
                    collection_title=playlist_title,
                    track_list=formatted,
                    on_confirm_callback=lambda selected: self.on_tracks_selected_for_download(
                        selected, playlist_title, is_playlist=True
                    ),
                )

            self.after(0, open_dialog)
        except Exception as exc:
            messagebox.showerror(
                "Playlist error", f"Failed to retrieve playlist tracks: {exc}"
            )

    def on_tracks_selected_for_download(
        self, selected_tracks, collection_title=None, is_playlist=False
    ):
        if not selected_tracks:
            return
        for track in selected_tracks:
            self.queue_tidal_track(
                track["id"],
                track.get("title", "Unknown title"),
                parent_folder=collection_title if is_playlist else None,
                subtitle=track.get("artist", "Unknown artist"),
                artist=track.get("artist", "Unknown artist"),
                album="" if is_playlist else (collection_title or ""),
            )
        self.switch_view("queue")

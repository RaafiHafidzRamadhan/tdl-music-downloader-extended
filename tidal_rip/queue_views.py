"""Download queue UI and the multi-source worker."""

import asyncio
import os
import threading
import time
from tkinter import messagebox

import customtkinter as CTk

from .components import (
    chip_label,
    danger_button,
    ghost_button,
    open_in_file_manager,
    primary_button,
    soft_button,
)
from .theme import COLORS, source_meta, ui_font
from .widgets import CircularProgress, truncate_middle
from .youtube_service import DownloadCancelled

try:
    import winsound
except ImportError:  # pragma: no cover - Windows is the primary target
    winsound = None


class QueueViewMixin:
    """Queue view, controls, stats, and the async download worker."""

    # ---------------------------------------------------------------- layout

    def create_queue_view(self):
        self.queue_view = CTk.CTkFrame(self.main_container, fg_color="transparent")
        self.queue_view.grid_columnconfigure(0, weight=1)
        self.queue_view.grid_rowconfigure(3, weight=1)

        header = CTk.CTkFrame(self.queue_view, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", pady=(0, 16))

        titles = CTk.CTkFrame(header, fg_color="transparent")
        titles.pack(side="left", fill="x", expand=True)
        CTk.CTkLabel(
            titles,
            text="Downloads",
            font=ui_font(26, "bold"),
            text_color=COLORS["text"],
            anchor="w",
        ).pack(fill="x", anchor="w")
        CTk.CTkLabel(
            titles,
            text="One queue for Tidal lossless audio and YouTube MP3s.",
            font=ui_font(12),
            text_color=COLORS["text_secondary"],
            anchor="w",
        ).pack(fill="x", anchor="w", pady=(4, 0))

        actions = CTk.CTkFrame(header, fg_color="transparent")
        actions.pack(side="right", padx=(16, 0))

        self.open_folder_btn = ghost_button(
            actions,
            "Open folder",
            command=lambda: open_in_file_manager(self.config.download_directory),
            width=104,
            height=34,
        )
        self.open_folder_btn.pack(side="right", padx=(8, 0))

        self.cancel_all_btn = danger_button(
            actions,
            "Cancel all",
            command=self.cancel_all_downloads,
            width=96,
            height=34,
        )
        self.cancel_all_btn.pack(side="right", padx=(8, 0))

        self.pause_all_btn = soft_button(
            actions,
            "Pause all",
            command=self.toggle_pause_all,
            width=96,
            height=34,
        )
        self.pause_all_btn.pack(side="right")

        stats = CTk.CTkFrame(self.queue_view, fg_color="transparent")
        stats.grid(row=1, column=0, sticky="ew", pady=(0, 16))
        self.stat_labels = {}
        stat_specs = (
            ("queued", "Queued", COLORS["accent"]),
            ("downloading", "Downloading", COLORS["warning"]),
            ("completed", "Completed", COLORS["success"]),
            ("failed", "Failed / stopped", COLORS["error"]),
        )
        for index, (key, label, color) in enumerate(stat_specs):
            stats.grid_columnconfigure(index, weight=1)
            card = CTk.CTkFrame(
                stats,
                fg_color=COLORS["surface"],
                corner_radius=14,
                border_width=1,
                border_color=COLORS["border"],
            )
            card.grid(
                row=0,
                column=index,
                sticky="ew",
                padx=(0 if index == 0 else 10, 0),
            )
            body = CTk.CTkFrame(card, fg_color="transparent")
            body.pack(fill="x", padx=14, pady=12)
            value = CTk.CTkLabel(
                body,
                text="0",
                font=ui_font(24, "bold"),
                text_color=color,
                anchor="w",
            )
            value.pack(fill="x", anchor="w")
            CTk.CTkLabel(
                body,
                text=label,
                font=ui_font(10),
                text_color=COLORS["text_secondary"],
                anchor="w",
            ).pack(fill="x", anchor="w", pady=(2, 0))
            self.stat_labels[key] = value

        queue_bar = CTk.CTkFrame(self.queue_view, fg_color="transparent")
        queue_bar.grid(row=2, column=0, sticky="ew", pady=(0, 8))
        CTk.CTkLabel(
            queue_bar,
            text="QUEUE",
            font=ui_font(10, "bold"),
            text_color=COLORS["muted"],
        ).pack(side="left")
        self.queue_summary_lbl = CTk.CTkLabel(
            queue_bar,
            text="No downloads yet",
            font=ui_font(11),
            text_color=COLORS["text_secondary"],
        )
        self.queue_summary_lbl.pack(side="left", padx=(10, 0))
        ghost_button(
            queue_bar,
            "Clear finished",
            command=self.clear_finished_downloads,
            width=110,
            height=30,
        ).pack(side="right")

        self.queue_scroll = CTk.CTkScrollableFrame(
            self.queue_view,
            fg_color="transparent",
            corner_radius=0,
            scrollbar_button_color=COLORS["border"],
            scrollbar_button_hover_color=COLORS["border_strong"],
        )
        self.queue_scroll.grid(row=3, column=0, sticky="nsew")

        self._queue_empty = None
        self._all_paused = False
        self._queue_was_active = False
        self._update_queue_empty()

    # --------------------------------------------------------------- helpers

    def _format_size(self, path):
        try:
            size = os.path.getsize(path)
        except OSError:
            return ""
        if size >= 1024 * 1024:
            return f"{size / (1024 * 1024):.1f} MB"
        if size >= 1024:
            return f"{size / 1024:.0f} KB"
        return f"{size} B"

    def _task_key(self, task):
        source = task.get("source", "tidal")
        if source == "tidal":
            return f"tidal:{task.get('track_id')}"
        ident = task.get("video_id") or task.get("url") or "unknown"
        return f"youtube:{ident}"

    def _show_queue_message(self, title, text):
        messagebox.showinfo(title, text)

    def _update_queue_empty(self):
        if self.queue_items:
            if self._queue_empty is not None:
                try:
                    self._queue_empty.destroy()
                except Exception:
                    pass
                self._queue_empty = None
            return
        if self._queue_empty is not None:
            return

        card = CTk.CTkFrame(
            self.queue_scroll,
            fg_color=COLORS["surface"],
            corner_radius=18,
            border_width=1,
            border_color=COLORS["border"],
        )
        card.pack(fill="x", padx=2, pady=(0, 10))
        body = CTk.CTkFrame(card, fg_color="transparent")
        body.pack(padx=28, pady=34)

        CTk.CTkLabel(
            body,
            text="↓",
            width=48,
            height=48,
            corner_radius=24,
            fg_color=COLORS["accent_soft"],
            text_color=COLORS["accent"],
            font=ui_font(20, "bold"),
        ).pack(pady=(0, 12))
        CTk.CTkLabel(
            body,
            text="Your queue is empty",
            font=ui_font(16, "bold"),
            text_color=COLORS["text"],
        ).pack()
        CTk.CTkLabel(
            body,
            text="Find music in Tidal or YouTube. Downloads will appear here with live progress rings.",
            font=ui_font(11),
            text_color=COLORS["text_secondary"],
            wraplength=520,
            justify="center",
        ).pack(pady=(6, 16))
        primary_button(
            body,
            "Find music",
            command=lambda: self.switch_view("search"),
            width=132,
            height=34,
        ).pack()
        self._queue_empty = card

    def _pack_action(self, button):
        button.pack(side="left", padx=(6, 0))

    def _refresh_item_controls(self, item):
        for button in (
            item["top_btn"],
            item["pause_btn"],
            item["cancel_btn"],
            item["retry_btn"],
            item["play_btn"],
            item["open_btn"],
        ):
            try:
                button.pack_forget()
            except Exception:
                pass

        status = item["status"]
        paused = item["task_state"].get("is_paused", False)
        if status == "queued":
            self._pack_action(item["top_btn"])
            item["pause_btn"].configure(text="Resume" if paused else "Pause")
            self._pack_action(item["pause_btn"])
            self._pack_action(item["cancel_btn"])
        elif status == "downloading":
            item["pause_btn"].configure(text="Resume" if paused else "Pause")
            self._pack_action(item["pause_btn"])
            self._pack_action(item["cancel_btn"])
        elif status in ("failed", "cancelled"):
            self._pack_action(item["retry_btn"])
        elif status == "completed" and item.get("final_path"):
            self._pack_action(item["play_btn"])
            self._pack_action(item["open_btn"])

    def _apply_pause_visual(self, item):
        paused = item["task_state"].get("is_paused", False)
        if item["status"] not in ("queued", "downloading"):
            return
        if paused:
            item["ring"].set(
                item.get("progress", 0.0),
                text="❚❚",
                color=COLORS["warning"],
                text_color=COLORS["warning"],
            )
            item["status_lbl"].configure(text="Paused", text_color=COLORS["warning"])
        elif item["status"] == "queued":
            item["ring"].reset("0%")
            item["status_lbl"].configure(text="Queued", text_color=COLORS["muted"])
        else:
            progress = item.get("progress", 0.0)
            item["ring"].set(
                progress,
                text=f"{int(progress * 100)}%",
                color=COLORS["accent"],
                text_color=COLORS["text"],
            )
            item["status_lbl"].configure(
                text="Resuming…", text_color=COLORS["text_secondary"]
            )
        self._refresh_item_controls(item)

    # ---------------------------------------------------------- queue entry

    def queue_tidal_track(
        self,
        track_id,
        title,
        parent_folder=None,
        subtitle=None,
        artist="",
        album="",
    ):
        task = {
            "source": "tidal",
            "track_id": track_id,
            "parent_folder": parent_folder,
            "meta": {
                "title": title,
                "artist": artist,
                "album": album,
            },
        }
        display_title = f"{title} — {artist}" if artist else title
        self.queue_task(
            task,
            title=display_title,
            subtitle=subtitle or artist or "Tidal · Lossless audio",
        )

    def queue_youtube_entry(self, entry, parent_folder=None, switch=True):
        video_id = entry.get("video_id") or entry.get("id")
        url = entry.get("url") or (
            f"https://www.youtube.com/watch?v={video_id}" if video_id else None
        )
        meta = {
            "title": entry.get("display_title") or entry.get("title") or "Unknown title",
            "artist": entry.get("artist") or "YouTube",
            "album": "",
            "duration": entry.get("duration") or 0,
            "cover_url": entry.get("thumbnail"),
            "video_id": video_id,
        }
        task = {
            "source": "youtube",
            "url": url,
            "video_id": video_id,
            "parent_folder": parent_folder,
            "meta": meta,
        }
        subtitle = meta["artist"]
        if parent_folder:
            subtitle = f"{meta['artist']} · {parent_folder}"
        self.queue_task(task, title=meta["title"], subtitle=subtitle, switch=switch)

    def queue_task(
        self,
        task,
        title=None,
        subtitle=None,
        switch=True,
        notify_duplicate=False,
    ):
        key = self._task_key(task)
        existing = self.queue_items.get(key)
        if existing is not None:
            if existing["status"] in ("queued", "downloading"):
                if notify_duplicate:
                    self._show_queue_message(
                        "Already queued", f"'{title or existing['title']}' is already in the queue."
                    )
                if switch:
                    self.switch_view("queue")
                return key
            existing["row"].destroy()
            self.queue_items.pop(key, None)
            if key in self.queue_order:
                self.queue_order.remove(key)
            if key in self.pending_downloads:
                self.pending_downloads.remove(key)

        meta = task.get("meta") or {}
        display_title = title or meta.get("title") or "Unknown title"
        display_subtitle = subtitle or meta.get("artist") or ""

        self._create_queue_row(key, task, display_title, display_subtitle)
        self.queue_order.append(key)
        self.pending_downloads.append(key)
        self._update_queue_empty()
        self.update_queue_summary()
        if switch:
            self.switch_view("queue")
        return key

    def _create_queue_row(self, key, task, title, subtitle):
        source = task.get("source", "tidal")
        meta = source_meta(source)

        row = CTk.CTkFrame(
            self.queue_scroll,
            fg_color=COLORS["surface"],
            corner_radius=16,
            border_width=1,
            border_color=COLORS["border"],
        )
        row.pack(fill="x", padx=2, pady=(0, 10))

        body = CTk.CTkFrame(row, fg_color="transparent")
        body.pack(fill="x", padx=14, pady=12)

        ring = CircularProgress(
            body,
            size=58,
            thickness=6,
            bg=COLORS["surface"],
            track_color=COLORS["border"],
            color=meta["color"],
            text_color=COLORS["text"],
            font_size=10,
            text="0%",
        )
        ring.pack(side="left", padx=(0, 14))

        actions = CTk.CTkFrame(body, fg_color="transparent")
        actions.pack(side="right", padx=(12, 0))

        info = CTk.CTkFrame(body, fg_color="transparent")
        info.pack(side="left", fill="both", expand=True)

        CTk.CTkLabel(
            info,
            text=truncate_middle(title, 62),
            font=ui_font(13, "bold"),
            text_color=COLORS["text"],
            anchor="w",
        ).pack(fill="x", anchor="w")

        if subtitle:
            CTk.CTkLabel(
                info,
                text=truncate_middle(subtitle, 74),
                font=ui_font(11),
                text_color=COLORS["text_secondary"],
                anchor="w",
            ).pack(fill="x", anchor="w", pady=(1, 5))

        status_row = CTk.CTkFrame(info, fg_color="transparent")
        status_row.pack(fill="x")
        chip_label(
            status_row,
            meta["label"],
            fg_color=meta["soft"],
            text_color=meta["color"],
            height=20,
        ).pack(side="left")
        status_lbl = CTk.CTkLabel(
            status_row,
            text="Queued",
            font=ui_font(11),
            text_color=COLORS["muted"],
            anchor="w",
        )
        status_lbl.pack(side="left", padx=(8, 0))

        top_btn = ghost_button(
            actions,
            "Top",
            command=lambda k=key: self.move_item_top(k),
            width=50,
            height=30,
            font=ui_font(10),
        )
        pause_btn = ghost_button(
            actions,
            "Pause",
            command=lambda k=key: self.toggle_item_pause(k),
            width=64,
            height=30,
            font=ui_font(10),
        )
        cancel_btn = ghost_button(
            actions,
            "Cancel",
            command=lambda k=key: self.cancel_item(k),
            width=64,
            height=30,
            text_color=COLORS["error"],
            font=ui_font(10),
        )
        retry_btn = soft_button(
            actions,
            "Retry",
            command=lambda k=key: self.retry_item(k),
            width=62,
            height=30,
            font=ui_font(10),
        )
        play_btn = primary_button(
            actions,
            "Play",
            command=lambda k=key: self.play_item(k),
            width=58,
            height=30,
            font=ui_font(10),
        )
        open_btn = soft_button(
            actions,
            "Open",
            command=lambda k=key: self.open_item(k),
            width=58,
            height=30,
            font=ui_font(10),
        )

        self.queue_items[key] = {
            "key": key,
            "task": task,
            "source": source,
            "title": title,
            "subtitle": subtitle,
            "status": "queued",
            "row": row,
            "ring": ring,
            "status_lbl": status_lbl,
            "top_btn": top_btn,
            "pause_btn": pause_btn,
            "cancel_btn": cancel_btn,
            "retry_btn": retry_btn,
            "play_btn": play_btn,
            "open_btn": open_btn,
            "final_path": None,
            "progress": 0.0,
            "task_state": {"is_paused": False, "is_cancelled": False},
        }
        self._refresh_item_controls(self.queue_items[key])

    # ------------------------------------------------------------- controls

    def toggle_item_pause(self, key):
        item = self.queue_items.get(key)
        if not item or item["status"] not in ("queued", "downloading"):
            return
        state = item["task_state"]
        state["is_paused"] = not state.get("is_paused", False)
        if not state["is_paused"]:
            self._all_paused = False
            if hasattr(self, "pause_all_btn"):
                self.pause_all_btn.configure(text="Pause all")
        self._apply_pause_visual(item)

    def cancel_item(self, key):
        item = self.queue_items.get(key)
        if not item or item["status"] not in ("queued", "downloading"):
            return
        item["task_state"]["is_cancelled"] = True
        if item["status"] == "queued":
            if key in self.pending_downloads:
                self.pending_downloads.remove(key)
            item["status"] = "cancelled"
            item["ring"].set_cancelled()
            item["status_lbl"].configure(text="Cancelled", text_color=COLORS["muted"])
            self._refresh_item_controls(item)
            self.update_queue_summary()
        else:
            item["status_lbl"].configure(
                text="Cancelling…", text_color=COLORS["warning"]
            )

    def move_item_top(self, key):
        item = self.queue_items.get(key)
        if not item or item["status"] != "queued":
            return
        if key in self.pending_downloads:
            self.pending_downloads.remove(key)
            self.pending_downloads.insert(0, key)
        if key in self.queue_order:
            self.queue_order.remove(key)
            self.queue_order.insert(0, key)
        self._repack_queue_rows()

    def _repack_queue_rows(self):
        for key in self.queue_order:
            item = self.queue_items.get(key)
            if not item:
                continue
            try:
                item["row"].pack_forget()
                item["row"].pack(fill="x", padx=2, pady=(0, 10))
            except Exception:
                pass

    def retry_item(self, key):
        item = self.queue_items.get(key)
        if not item or item["status"] not in ("failed", "cancelled"):
            return
        item["status"] = "queued"
        item["progress"] = 0.0
        item["final_path"] = None
        item["task_state"]["is_cancelled"] = False
        item["task_state"]["is_paused"] = False
        item["ring"].reset("0%")
        item["status_lbl"].configure(text="Queued", text_color=COLORS["muted"])
        self._refresh_item_controls(item)
        if key not in self.pending_downloads:
            self.pending_downloads.append(key)
        if key not in self.queue_order:
            self.queue_order.append(key)
        self.update_queue_summary()

    def open_item(self, key):
        item = self.queue_items.get(key)
        if not item:
            return
        path = item.get("final_path")
        if path and os.path.exists(path):
            open_in_file_manager(path, select_file=True)
        else:
            open_in_file_manager(self.config.download_directory)

    def play_item(self, key):
        item = self.queue_items.get(key)
        if not item:
            return
        path = item.get("final_path")
        if not path or not os.path.exists(path):
            messagebox.showinfo(
                "Not available", "This download has not finished yet."
            )
            return
        if hasattr(self, "player_open_path") and self.player_open_path(path):
            return
        open_in_file_manager(path, select_file=True)

    def toggle_pause_all(self):
        active = [
            item
            for item in self.queue_items.values()
            if item["status"] in ("queued", "downloading")
        ]
        self._all_paused = not self._all_paused
        for item in active:
            item["task_state"]["is_paused"] = self._all_paused
            self._apply_pause_visual(item)
        self.pause_all_btn.configure(
            text="Resume all" if self._all_paused else "Pause all"
        )

    def cancel_all_downloads(self):
        active = [
            item
            for item in self.queue_items.values()
            if item["status"] in ("queued", "downloading")
        ]
        if not active:
            return
        if not messagebox.askyesno(
            "Cancel downloads", "Cancel all queued and active downloads?"
        ):
            return

        self._all_paused = False
        self.pause_all_btn.configure(text="Pause all")
        for item in active:
            item["task_state"]["is_cancelled"] = True
            item["task_state"]["is_paused"] = False
            if item["status"] == "queued":
                if item["key"] in self.pending_downloads:
                    self.pending_downloads.remove(item["key"])
                item["status"] = "cancelled"
                item["ring"].set_cancelled()
                item["status_lbl"].configure(
                    text="Cancelled", text_color=COLORS["muted"]
                )
                self._refresh_item_controls(item)
            else:
                item["status_lbl"].configure(
                    text="Cancelling…", text_color=COLORS["warning"]
                )
        self.update_queue_summary()

    def clear_finished_downloads(self):
        for key in list(self.queue_items.keys()):
            item = self.queue_items[key]
            if item["status"] not in ("completed", "failed", "cancelled"):
                continue
            try:
                item["row"].destroy()
            except Exception:
                pass
            self.queue_items.pop(key, None)
            if key in self.queue_order:
                self.queue_order.remove(key)
            if key in self.pending_downloads:
                self.pending_downloads.remove(key)
        self._update_queue_empty()
        self.update_queue_summary()

    def update_queue_summary(self):
        total = len(self.queue_items)
        queued = sum(1 for i in self.queue_items.values() if i["status"] == "queued")
        downloading = sum(
            1 for i in self.queue_items.values() if i["status"] == "downloading"
        )
        completed = sum(
            1 for i in self.queue_items.values() if i["status"] == "completed"
        )
        failed = sum(1 for i in self.queue_items.values() if i["status"] == "failed")
        cancelled = sum(
            1 for i in self.queue_items.values() if i["status"] == "cancelled"
        )
        pending = queued + downloading

        if hasattr(self, "stat_labels"):
            self.stat_labels["queued"].configure(text=str(queued))
            self.stat_labels["downloading"].configure(text=str(downloading))
            self.stat_labels["completed"].configure(text=str(completed))
            self.stat_labels["failed"].configure(text=str(failed + cancelled))

        if total == 0:
            self.queue_summary_lbl.configure(text="No downloads yet")
        elif pending > 0:
            self.queue_summary_lbl.configure(
                text=f"{pending} active · {completed} completed · {failed + cancelled} stopped"
            )
        else:
            self.queue_summary_lbl.configure(
                text=f"All caught up · {completed} completed · {failed + cancelled} stopped"
            )

        if hasattr(self, "nav_buttons") and "queue" in self.nav_buttons:
            self.nav_buttons["queue"].configure(
                text=f"↓   Downloads  ·  {pending}" if pending else "↓   Downloads"
            )

        if getattr(self, "_queue_was_active", False) and pending == 0 and completed > 0:
            self._queue_was_active = False
            self.play_completion_alert()
        elif pending > 0:
            self._queue_was_active = True

    def play_completion_alert(self):
        if not getattr(self.config, "play_sound_on_complete", True):
            return

        def sound():
            try:
                if winsound is not None:
                    winsound.MessageBeep(winsound.MB_ICONASTERISK)
                else:
                    print("\a", end="", flush=True)
            except Exception as exc:
                print(f"Completion sound failed: {exc}")

        threading.Thread(target=sound, daemon=True).start()

    # --------------------------------------------------------------- worker

    async def download_worker(self):
        max_concurrent = max(1, int(getattr(self.config, "concurrent_downloads", 3) or 3))
        semaphore = asyncio.Semaphore(max_concurrent)

        async def run_task(key):
            async with semaphore:
                item = self.queue_items.get(key)
                if not item or item["status"] != "queued":
                    return
                if item["task_state"].get("is_cancelled"):
                    return
                await self.process_single_download(key)

        while not getattr(self, "_shutdown", False):
            if self._all_paused or not self.pending_downloads:
                await asyncio.sleep(0.4)
                continue
            key = self.pending_downloads.pop(0)
            if key not in self.queue_items:
                continue
            asyncio.create_task(run_task(key))

    def _make_progress_callback(self, key):
        last = {"time": 0.0}

        async def progress_callback(downloaded, total, status_text):
            now = time.time()
            if (now - last["time"] < 0.2) and (0 < downloaded < total):
                return
            last["time"] = now
            try:
                progress = float(downloaded) / max(1.0, float(total))
            except (TypeError, ValueError, ZeroDivisionError):
                progress = 0.0
            self.after(0, self._update_item_progress, key, progress, status_text)

        return progress_callback

    async def process_single_download(self, key):
        item = self.queue_items.get(key)
        if not item:
            return
        item["status"] = "downloading"
        self.after(0, self._mark_downloading, key)

        callback = self._make_progress_callback(key)
        task = item["task"]
        task_state = item["task_state"]

        try:
            if item["source"] == "tidal":
                result = await self.downloader.download_track(
                    task.get("track_id"),
                    callback,
                    task.get("parent_folder"),
                    task_state,
                )
            else:
                result = await self.youtube_service.download_task(
                    task, callback, task_state
                )

            if task_state.get("is_cancelled"):
                self.after(0, self._finalize_cancelled, key)
            else:
                if not isinstance(result, dict):
                    result = {"final_path": str(result)}
                self.after(0, self._finalize_completed, key, result)
        except Exception as exc:
            cancelled = (
                task_state.get("is_cancelled")
                or isinstance(exc, DownloadCancelled)
                or "cancelled by user" in str(exc).lower()
            )
            if cancelled:
                self.after(0, self._finalize_cancelled, key)
            else:
                print(f"Download failed for {key}: {exc}")
                self.after(0, self._finalize_failed, key, str(exc))

    # ---------------------------------------------------------- UI updates

    def _mark_downloading(self, key):
        item = self.queue_items.get(key)
        if not item:
            return
        item["status"] = "downloading"
        item["status_lbl"].configure(
            text="Starting…", text_color=COLORS["text_secondary"]
        )
        item["ring"].set(0.0, text="0%", color=COLORS["accent"], text_color=COLORS["text"])
        self._refresh_item_controls(item)
        self.update_queue_summary()

    def _update_item_progress(self, key, progress, status_text):
        item = self.queue_items.get(key)
        if not item or item["status"] != "downloading":
            return
        item["progress"] = progress
        if item["task_state"].get("is_paused"):
            self._apply_pause_visual(item)
            return
        item["ring"].set(
            progress,
            text=f"{int(progress * 100)}%",
            color=COLORS["accent"],
            text_color=COLORS["text"],
        )
        text = truncate_middle(status_text or "Downloading…", 76)
        item["status_lbl"].configure(
            text=text, text_color=COLORS["text_secondary"]
        )

    def _finalize_completed(self, key, result):
        item = self.queue_items.get(key)
        if not item:
            return
        item["status"] = "completed"
        item["progress"] = 1.0
        final_path = result.get("final_path") or result.get("path")
        item["final_path"] = final_path
        item["ring"].set_complete("✓")

        spec = result.get("spec_str", "") if isinstance(result, dict) else ""
        size = self._format_size(final_path) if final_path else ""
        message = f"Completed{spec}"
        if size:
            message = f"{message} · {size}"
        item["status_lbl"].configure(
            text=truncate_middle(message, 76), text_color=COLORS["success"]
        )
        self._refresh_item_controls(item)
        self.update_queue_summary()
        if hasattr(self, "player_note_library_changed"):
            self.player_note_library_changed()

    def _finalize_failed(self, key, error):
        item = self.queue_items.get(key)
        if not item:
            return
        item["status"] = "failed"
        item["ring"].set_failed("!")
        item["status_lbl"].configure(
            text=truncate_middle(f"Failed · {error}", 76),
            text_color=COLORS["error"],
        )
        self._refresh_item_controls(item)
        self.update_queue_summary()

    def _finalize_cancelled(self, key):
        item = self.queue_items.get(key)
        if not item:
            return
        item["status"] = "cancelled"
        item["ring"].set_cancelled("–")
        item["status_lbl"].configure(
            text="Cancelled", text_color=COLORS["muted"]
        )
        self._refresh_item_controls(item)
        self.update_queue_summary()

"""YouTube search, playlist resolution, and MP3 download engine."""

import asyncio
import glob
import io
import os
import re
import shutil
import tempfile
import time
import urllib.parse

import aiohttp
import imageio_ffmpeg
import yt_dlp
from mutagen.id3 import APIC, ID3, TALB, TDRC, TIT2, TPE1, TRCK, ID3NoHeaderError
from PIL import Image

from .downloader import sanitize_filename
from .link_resolver import clean_music_title


class DownloadCancelled(Exception):
    """Raised internally when the user cancels a YouTube download."""


def format_duration(seconds):
    try:
        seconds = int(seconds or 0)
    except (TypeError, ValueError):
        seconds = 0
    if seconds <= 0:
        return ""
    return f"{seconds // 60}:{seconds % 60:02d}"


def is_youtube_url(text):
    if not isinstance(text, str):
        return False
    lowered = text.strip().lower()
    return any(
        domain in lowered
        for domain in ("youtube.com", "youtu.be", "music.youtube.com")
    )


def parse_youtube_url(url):
    """Returns {'type': 'video'|'playlist', ...} for a supported YouTube URL."""
    if not url:
        return None
    raw = url.strip()
    parsed = urllib.parse.urlparse(raw)
    host = (parsed.netloc or "").lower()
    path = parsed.path or ""
    query = urllib.parse.parse_qs(parsed.query)

    if host.endswith("youtu.be"):
        video_id = path.strip("/").split("/")[0]
        return {"type": "video", "video_id": video_id} if video_id else None

    if "youtube.com" not in host:
        return None

    video_id = (query.get("v") or [None])[0]
    if video_id:
        return {"type": "video", "video_id": video_id}

    shorts = re.match(r"^/(?:shorts|embed|live)/([A-Za-z0-9_-]{6,})", path)
    if shorts:
        return {"type": "video", "video_id": shorts.group(1)}

    playlist_id = (query.get("list") or [None])[0]
    if playlist_id:
        return {"type": "playlist", "playlist_id": playlist_id}

    return None


def build_output_path(download_dir, meta, parent_folder=None):
    """Builds the final MP3 path for a YouTube download."""
    base_dir = download_dir
    if parent_folder:
        base_dir = os.path.join(base_dir, sanitize_filename(parent_folder))

    artist = sanitize_filename(meta.get("artist") or "Unknown Artist")
    title = sanitize_filename(meta.get("title") or "Unknown Title")
    return os.path.join(base_dir, artist, f"{title}.mp3")


class YouTubeService:
    """Wraps yt-dlp so the UI can search, resolve, and download MP3 audio."""

    SEARCH_OPTS = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "extract_flat": "in_playlist",
        "noplaylist": True,
        "cachedir": False,
        "socket_timeout": 30,
    }

    def __init__(self, api, config):
        self.api = api
        self.config = config
        self._ffmpeg_path = None

    @property
    def ffmpeg_path(self):
        if not self._ffmpeg_path:
            self._ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()
        return self._ffmpeg_path

    @staticmethod
    def _normalize_entry(entry):
        video_id = entry.get("id")
        if not video_id:
            return None
        url = entry.get("webpage_url") or entry.get("url")
        if not url or not str(url).startswith("http"):
            url = f"https://www.youtube.com/watch?v={video_id}"

        thumbnails = entry.get("thumbnails") or []
        thumbnail = thumbnails[-1].get("url") if thumbnails else None
        if not thumbnail:
            thumbnail = f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"

        title = entry.get("title") or "Unknown title"
        artist = entry.get("uploader") or entry.get("channel") or "YouTube"
        duration = entry.get("duration") or 0
        return {
            "source": "youtube",
            "video_id": video_id,
            "id": video_id,
            "url": url,
            "title": title,
            "display_title": clean_music_title(title) or title,
            "artist": artist,
            "duration": duration,
            "duration_str": format_duration(duration),
            "thumbnail": thumbnail,
        }

    def _search_sync(self, query, limit):
        with yt_dlp.YoutubeDL(dict(self.SEARCH_OPTS)) as ydl:
            info = ydl.extract_info(f"ytsearch{limit}:{query}", download=False)
        entries = [self._normalize_entry(e) for e in (info.get("entries") or []) if e]
        return [entry for entry in entries if entry]

    async def search(self, query, limit=20):
        return await asyncio.to_thread(self._search_sync, query, limit)

    def _resolve_video_sync(self, url):
        opts = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "noplaylist": True,
            "cachedir": False,
            "socket_timeout": 30,
        }
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
        return self._normalize_entry(info)

    def _resolve_playlist_sync(self, url):
        opts = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "extract_flat": "in_playlist",
            "noplaylist": False,
            "playlistend": 200,
            "cachedir": False,
            "socket_timeout": 30,
        }
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)

        entries = [self._normalize_entry(e) for e in (info.get("entries") or []) if e]
        entries = [entry for entry in entries if entry]
        thumbnails = info.get("thumbnails") or []
        thumbnail = thumbnails[-1].get("url") if thumbnails else None
        if not thumbnail and entries:
            thumbnail = entries[0].get("thumbnail")
        return {
            "type": "playlist",
            "source": "youtube",
            "id": info.get("id") or "",
            "title": info.get("title") or "YouTube Playlist",
            "artist": info.get("uploader") or info.get("channel") or "YouTube",
            "thumbnail": thumbnail,
            "entries": entries,
            "webpage_url": info.get("webpage_url") or url,
            "truncated": bool(info.get("playlist_count") and info.get("playlist_count") > len(entries)),
        }

    async def resolve_url(self, url):
        parsed = parse_youtube_url(url)
        if not parsed:
            raise Exception("Unsupported YouTube link.")
        if parsed["type"] == "playlist":
            return await asyncio.to_thread(self._resolve_playlist_sync, url)
        entry = await asyncio.to_thread(self._resolve_video_sync, url)
        if not entry:
            raise Exception("Could not read this YouTube video.")
        return {"type": "video", "entry": entry}

    @staticmethod
    def _cancelled(task_state):
        return bool(task_state and task_state.get("is_cancelled"))

    @staticmethod
    def _paused(task_state):
        return bool(task_state and task_state.get("is_paused"))

    async def download_task(self, task, progress_callback=None, task_state=None):
        meta = dict(task.get("meta") or {})
        video_url = task.get("url")

        if self._cancelled(task_state):
            raise DownloadCancelled("Cancelled by user")

        if not video_url:
            raise Exception("No YouTube URL available for this download.")

        return await self._download_audio(
            video_url, meta, task, progress_callback, task_state
        )

    async def _download_audio(self, video_url, meta, task, progress_callback, task_state):
        source = task.get("source", "youtube")
        bitrate = str(getattr(self.config, "mp3_bitrate", "320") or "320")
        final_path = build_output_path(
            self.config.download_directory, meta, task.get("parent_folder")
        )
        os.makedirs(os.path.dirname(final_path), exist_ok=True)

        if os.path.exists(final_path) and os.path.getsize(final_path) > 0:
            if progress_callback:
                await progress_callback(1, 1, "Skipped (Already Downloaded)")
            return {
                "final_path": final_path,
                "extension": "mp3",
                "bitrate": bitrate,
                "spec_str": f" (MP3 {bitrate}kbps)",
                "source": source,
            }

        loop = asyncio.get_running_loop()
        tmp_root = os.path.join(self.config.config_dir, "tmp")
        os.makedirs(tmp_root, exist_ok=True)
        tmpdir = tempfile.mkdtemp(prefix="download_", dir=tmp_root)
        last_emit = {"time": 0.0}

        def emit(downloaded, total, text, force=False):
            if not progress_callback:
                return
            now = time.time()
            if not force and now - last_emit["time"] < 0.35:
                return
            last_emit["time"] = now
            asyncio.run_coroutine_threadsafe(
                progress_callback(downloaded, total, text), loop
            )

        def hook(data):
            if self._cancelled(task_state):
                raise DownloadCancelled("Cancelled by user")
            while self._paused(task_state):
                if self._cancelled(task_state):
                    raise DownloadCancelled("Cancelled by user")
                time.sleep(0.2)
            status = data.get("status")
            if status == "downloading":
                downloaded = data.get("downloaded_bytes") or 0
                total = data.get("total_bytes") or data.get("total_bytes_estimate") or 0
                speed = data.get("speed") or 0
                speed_text = f" • {speed / 1024 / 1024:.1f} MB/s" if speed else ""
                emit(downloaded, total, f"Downloading audio{speed_text}")
            elif status == "finished":
                emit(1, 1, f"Converting to MP3 ({bitrate} kbps)...", force=True)

        ydl_opts = {
            "format": "bestaudio/best",
            "outtmpl": os.path.join(tmpdir, "%(id)s.%(ext)s"),
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
            "noprogress": True,
            "overwrites": True,
            "retries": 3,
            "fragment_retries": 3,
            "socket_timeout": 30,
            "progress_hooks": [hook],
            "ffmpeg_location": self.ffmpeg_path,
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": bitrate,
                }
            ],
        }

        try:
            def run_download():
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.extract_info(video_url, download=True)

            await asyncio.to_thread(run_download)

            mp3_files = glob.glob(os.path.join(tmpdir, "*.mp3"))
            if not mp3_files:
                raise Exception("FFmpeg did not produce an MP3 file.")
            temp_mp3 = max(mp3_files, key=os.path.getsize)

            cover_bytes = await self._fetch_cover(meta.get("cover_url"))
            try:
                await asyncio.to_thread(self._tag_mp3, temp_mp3, meta, cover_bytes)
            except Exception as exc:
                print(f"Failed to apply MP3 tags: {exc}")

            if os.path.exists(final_path):
                try:
                    os.remove(final_path)
                except OSError:
                    pass
            os.replace(temp_mp3, final_path)

            spec = f" (MP3 {bitrate}kbps)"
            if progress_callback:
                await progress_callback(1, 1, f"Completed{spec}")
            return {
                "final_path": final_path,
                "extension": "mp3",
                "bitrate": bitrate,
                "spec_str": spec,
                "source": source,
            }
        except DownloadCancelled:
            raise
        except Exception as exc:
            raise Exception(f"YouTube download failed: {exc}") from exc
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    async def _fetch_cover(self, url):
        if not url:
            return None
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
                    return None
                data = await response.read()
            image = Image.open(io.BytesIO(data))
            if image.mode not in ("RGB", "RGBA"):
                image = image.convert("RGB")
            buffer = io.BytesIO()
            image.convert("RGB").save(buffer, format="JPEG", quality=90)
            return buffer.getvalue()
        except Exception as exc:
            print(f"Failed to fetch cover art: {exc}")
            return None
        finally:
            if owns_session and session:
                await session.close()

    @staticmethod
    def _tag_mp3(path, meta, cover_bytes):
        try:
            tags = ID3(path)
        except ID3NoHeaderError:
            tags = ID3()

        title = meta.get("title") or "Unknown Title"
        artist = meta.get("artist") or "Unknown Artist"
        album = meta.get("album") or ""
        track_num = meta.get("track_num")
        date = meta.get("date") or ""

        tags.delall("TIT2")
        tags.add(TIT2(encoding=3, text=title))
        tags.delall("TPE1")
        tags.add(TPE1(encoding=3, text=artist))
        if album:
            tags.delall("TALB")
            tags.add(TALB(encoding=3, text=album))
        if track_num:
            tags.delall("TRCK")
            tags.add(TRCK(encoding=3, text=str(track_num)))
        if date:
            tags.delall("TDRC")
            tags.add(TDRC(encoding=3, text=str(date)))

        if cover_bytes:
            tags.delall("APIC")
            tags.add(
                APIC(
                    encoding=3,
                    mime="image/jpeg",
                    type=3,
                    desc="Cover",
                    data=cover_bytes,
                )
            )
        tags.save(path, v2_version=3)

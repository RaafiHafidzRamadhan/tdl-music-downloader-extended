"""Local audio probing and playback for the downloaded music library."""

import base64
import ctypes
import hashlib
import json
import os
import subprocess
import uuid

import imageio_ffmpeg
import mutagen
from mutagen.flac import FLAC
from mutagen.id3 import ID3
from mutagen.mp3 import MP3
from mutagen.mp4 import MP4
from mutagen.oggopus import OggOpus
from mutagen.oggvorbis import OggVorbis
from mutagen.wave import WAVE

AUDIO_EXTENSIONS = {".flac", ".mp3", ".m4a", ".aac", ".wav", ".ogg", ".opus"}
MCI_DIRECT_EXTENSIONS = {".mp3", ".wav"}

FORMAT_BADGES = {
    "FLAC": ("#FEF3C7", "#92400E"),
    "MP3": ("#FEE2E2", "#B91C1C"),
    "M4A": ("#DBEAFE", "#1D4ED8"),
    "AAC": ("#DBEAFE", "#1D4ED8"),
    "WAV": ("#F1F5F9", "#475569"),
    "OGG": ("#EDE9FE", "#6D28D9"),
    "OPUS": ("#EDE9FE", "#6D28D9"),
    "AUDIO": ("#F1F5F9", "#475569"),
}


def format_time(seconds):
    try:
        total = int(round(float(seconds or 0)))
    except (TypeError, ValueError):
        total = 0
    if total < 0:
        total = 0
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def format_size(size):
    try:
        size = float(size or 0)
    except (TypeError, ValueError):
        return ""
    if size >= 1024 * 1024 * 1024:
        return f"{size / (1024 ** 3):.2f} GB"
    if size >= 1024 * 1024:
        return f"{size / (1024 ** 2):.1f} MB"
    if size >= 1024:
        return f"{size / 1024:.0f} KB"
    return f"{int(size)} B"


def _first_text(value):
    if isinstance(value, (list, tuple)):
        for item in value:
            text = str(item).strip()
            if text:
                return text
        return ""
    return str(value or "").strip()


def _read_tags(audio):
    tags = getattr(audio, "tags", None)
    if not tags:
        return "", "", ""
    if isinstance(tags, ID3):
        def frame(key):
            item = tags.get(key)
            return str(item.text[0]).strip() if item and item.text else ""
        return frame("TIT2"), frame("TPE1"), frame("TALB")
    if isinstance(audio, MP4):
        return (
            _first_text(tags.get("\xa9nam")),
            _first_text(tags.get("\xa9ART")),
            _first_text(tags.get("\xa9alb")),
        )
    return (
        _first_text(tags.get("title")),
        _first_text(tags.get("artist")),
        _first_text(tags.get("album")),
    )


def _read_cover(audio):
    try:
        if isinstance(audio, FLAC):
            if audio.pictures:
                return audio.pictures[0].data
        elif isinstance(audio, MP4):
            covers = (audio.tags or {}).get("covr") or []
            if covers:
                return bytes(covers[0])
        else:
            tags = getattr(audio, "tags", None)
            if isinstance(tags, ID3):
                pictures = tags.getall("APIC")
                if pictures:
                    return pictures[0].data
            elif tags:
                pictures = tags.get("metadata_block_picture") or []
                if pictures:
                    payload = json.loads(base64.b64decode(pictures[0]))
                    return base64.b64decode(payload["data"])
    except Exception:
        pass
    return None


def _format_detail(fmt, info):
    sample_rate = int(getattr(info, "sample_rate", 0) or 0)
    bit_depth = int(getattr(info, "bits_per_sample", 0) or 0)
    bitrate = int((getattr(info, "bitrate", 0) or 0) / 1000)
    sample_text = f"{sample_rate / 1000:g} kHz" if sample_rate else ""
    parts = []
    if fmt in ("FLAC", "WAV"):
        if bit_depth:
            parts.append(f"{bit_depth}-bit")
        if sample_text:
            parts.append(sample_text)
    elif fmt in ("MP3", "M4A", "AAC", "OGG", "OPUS"):
        if bitrate:
            parts.append(f"{bitrate} kbps")
        if sample_text:
            parts.append(sample_text)
    return " / ".join(parts)


def probe_audio(path, with_cover=True):
    """Reads tags, cover art, and technical audio details for one local file."""
    path = os.path.abspath(path)
    extension = os.path.splitext(path)[1].lower()
    fallback_format = extension.lstrip(".").upper() or "AUDIO"
    info = {
        "path": path,
        "title": os.path.splitext(os.path.basename(path))[0],
        "artist": "",
        "album": "",
        "duration": 0.0,
        "format": fallback_format,
        "detail": "",
        "badge": fallback_format,
        "cover": None,
        "bitrate": 0,
        "sample_rate": 0,
        "bit_depth": 0,
        "channels": 0,
        "size": 0,
    }
    try:
        info["size"] = os.path.getsize(path)
    except OSError:
        pass

    try:
        audio = mutagen.File(path)
    except Exception:
        audio = None

    if audio is not None:
        fmt = fallback_format
        if isinstance(audio, FLAC):
            fmt = "FLAC"
        elif isinstance(audio, MP3):
            fmt = "MP3"
        elif isinstance(audio, MP4):
            fmt = "M4A"
        elif isinstance(audio, WAVE):
            fmt = "WAV"
        elif isinstance(audio, OggVorbis):
            fmt = "OGG"
        elif isinstance(audio, OggOpus):
            fmt = "OPUS"

        title, artist, album = _read_tags(audio)
        tech = getattr(audio, "info", None)
        detail = _format_detail(fmt, tech)
        info.update(
            {
                "title": title or info["title"],
                "artist": artist,
                "album": album,
                "format": fmt,
                "detail": detail,
                "badge": f"{fmt} · {detail}" if detail else fmt,
                "cover": _read_cover(audio) if with_cover else None,
                "duration": float(getattr(tech, "length", 0) or 0),
                "bitrate": int((getattr(tech, "bitrate", 0) or 0) / 1000),
                "sample_rate": int(getattr(tech, "sample_rate", 0) or 0),
                "bit_depth": int(getattr(tech, "bits_per_sample", 0) or 0),
                "channels": int(getattr(tech, "channels", 0) or 0),
            }
        )
    return info


def scan_library(root):
    """Recursively scans the download folder for playable audio files."""
    results = []
    if not root or not os.path.isdir(root):
        return results
    for directory, _folders, filenames in os.walk(root):
        for name in filenames:
            if os.path.splitext(name)[1].lower() in AUDIO_EXTENSIONS:
                try:
                    results.append(
                        probe_audio(os.path.join(directory, name), with_cover=False)
                    )
                except Exception:
                    continue
    results.sort(
        key=lambda item: (
            (item.get("artist") or "~").casefold(),
            (item.get("album") or "").casefold(),
            item.get("title", "").casefold(),
        )
    )
    return results


def _playback_cache_dir():
    directory = os.path.join(os.path.expanduser("~/.tidal_rip"), "playback")
    os.makedirs(directory, exist_ok=True)
    return directory


def prepare_playback(path):
    """Returns a path MCI can open, transcoding FLAC/M4A/OGG to a cached WAV."""
    extension = os.path.splitext(path)[1].lower()
    if extension in MCI_DIRECT_EXTENSIONS:
        return path, False

    stat = os.stat(path)
    key = f"{os.path.abspath(path)}:{stat.st_mtime_ns}:{stat.st_size}"
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:20]
    target = os.path.join(_playback_cache_dir(), f"{digest}.wav")
    if os.path.exists(target) and os.path.getsize(target) > 1024:
        return target, True

    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    result = subprocess.run(
        [
            ffmpeg,
            "-y",
            "-loglevel",
            "error",
            "-i",
            path,
            "-vn",
            "-acodec",
            "pcm_s16le",
            "-ar",
            "44100",
            "-ac",
            "2",
            target,
        ],
        capture_output=True,
        creationflags=creation_flags,
    )
    if result.returncode != 0 or not os.path.exists(target):
        try:
            os.remove(target)
        except OSError:
            pass
        detail = result.stderr.decode("utf-8", errors="ignore").strip().splitlines()
        raise RuntimeError(detail[-1] if detail else "Could not decode this audio file.")
    return target, True


def cleanup_playback_cache():
    directory = os.path.join(os.path.expanduser("~/.tidal_rip"), "playback")
    if not os.path.isdir(directory):
        return
    for name in os.listdir(directory):
        if name.endswith(".wav"):
            try:
                os.remove(os.path.join(directory, name))
            except OSError:
                pass


def _mci_error_text(winmm, code):
    buffer = ctypes.create_unicode_buffer(256)
    try:
        winmm.mciGetErrorStringW(code, buffer, 256)
    except Exception:
        return str(code)
    return buffer.value or str(code)


class PlaybackEngine:
    """Small stateful wrapper around the Windows MCI audio interface."""

    def __init__(self):
        self._winmm = ctypes.WinDLL("winmm") if os.name == "nt" else None
        self._alias = f"tdlmusic{uuid.uuid4().hex[:6]}"
        self._opened = False
        self._state = "stopped"
        self._volume = 0.8
        self._length_ms = 0
        self.path = None

    def _send(self, command):
        if self._winmm is None:
            return 1
        return self._winmm.mciSendStringW(command, None, 0, 0)

    def _query(self, command):
        if self._winmm is None:
            return 1, ""
        buffer = ctypes.create_unicode_buffer(128)
        error = self._winmm.mciSendStringW(command, buffer, 128, 0)
        return error, buffer.value.strip()

    @property
    def state(self):
        return self._state

    @property
    def volume(self):
        return self._volume

    def load(self, path):
        self.close()
        attempts = [f'open "{path}" alias {self._alias}']
        if os.path.splitext(path)[1].lower() == ".mp3":
            attempts.append(f'open "{path}" type mpegvideo alias {self._alias}')
        error = 1
        for command in attempts:
            error = self._send(command)
            if error == 0:
                break
        if error:
            raise RuntimeError(
                f"Windows could not open this audio file ({_mci_error_text(self._winmm, error)})."
            )
        self._opened = True
        self.path = path
        self._state = "stopped"
        self._send(f"set {self._alias} time format milliseconds")
        self._send(f"setaudio {self._alias} volume to {int(self._volume * 1000)}")
        _error, length = self._query(f"status {self._alias} length")
        try:
            self._length_ms = int(length or 0)
        except ValueError:
            self._length_ms = 0
        return self._length_ms

    def play(self):
        if not self._opened:
            return
        if self._send(f"play {self._alias}") == 0:
            self._state = "playing"

    def pause(self):
        if not self._opened:
            return
        if self._send(f"pause {self._alias}") == 0:
            self._state = "paused"

    def resume(self):
        self.play()

    def stop(self):
        if not self._opened:
            return
        self._send(f"stop {self._alias}")
        self._send(f"seek {self._alias} to 0")
        self._state = "stopped"

    def finish(self):
        if not self._opened:
            return
        self._send(f"stop {self._alias}")
        self._state = "stopped"

    def seek(self, milliseconds):
        if not self._opened:
            return
        target = max(0, int(milliseconds))
        if self._length_ms:
            target = min(target, max(0, self._length_ms - 150))
        was_playing = self._state == "playing"
        previous_state = self._state
        if self._send(f"seek {self._alias} to {target}") == 0:
            if was_playing:
                self.play()
            else:
                self._state = "paused" if previous_state == "paused" else "stopped"

    def position(self):
        _error, value = self._query(f"status {self._alias} position")
        try:
            return max(0, int(value or 0))
        except ValueError:
            return 0

    def length(self):
        return self._length_ms

    def mode(self):
        _error, value = self._query(f"status {self._alias} mode")
        return value

    def set_volume(self, value):
        self._volume = max(0.0, min(1.0, float(value)))
        if self._opened:
            self._send(
                f"setaudio {self._alias} volume to {int(self._volume * 1000)}"
            )

    def close(self):
        if self._opened:
            self._send(f"close {self._alias}")
        self._opened = False
        self._state = "stopped"
        self._length_ms = 0
        self.path = None

"""Reusable UI widgets, including the Canvas-based circular progress ring."""

import tkinter as tk

from PIL import Image, ImageDraw

from .theme import COLORS, FONT_FAMILY


class CircularProgress(tk.Canvas):
    """A lightweight circular progress ring drawn on a Tk canvas."""

    def __init__(
        self,
        master,
        size=58,
        thickness=6,
        bg=COLORS["surface"],
        track_color=COLORS["border"],
        color=COLORS["accent"],
        text_color=COLORS["text"],
        font_size=9,
        value=0.0,
        text="0%",
        **kwargs,
    ):
        super().__init__(
            master,
            width=size,
            height=size,
            bg=bg,
            highlightthickness=0,
            bd=0,
            **kwargs,
        )
        self._size = size
        self._thickness = thickness
        self._value = -1.0
        pad = thickness / 2 + 2
        bbox = (pad, pad, size - pad, size - pad)
        self._track = self.create_arc(
            *bbox,
            start=0,
            extent=359.999,
            style="arc",
            outline=track_color,
            width=thickness,
        )
        self._arc = self.create_arc(
            *bbox,
            start=90,
            extent=0,
            style="arc",
            outline=color,
            width=thickness,
        )
        self._text = self.create_text(
            size / 2,
            size / 2,
            text=text,
            fill=text_color,
            font=(FONT_FAMILY, font_size, "bold"),
        )
        self.set(value, text=text)

    def set(self, value, text=None, color=None, text_color=None):
        value = max(0.0, min(1.0, float(value)))
        if color:
            self.itemconfigure(self._arc, outline=color)
        if text_color:
            self.itemconfigure(self._text, fill=text_color)
        if text is not None:
            self.itemconfigure(self._text, text=text)
        if abs(value - self._value) < 0.004 and text is None:
            return
        self._value = value
        self.itemconfigure(self._arc, extent=-359.999 * value if value > 0 else 0)

    def set_complete(self, text="✓"):
        self.set(1.0, text=text, color=COLORS["success"], text_color=COLORS["success"])

    def set_failed(self, text="!"):
        self.set(1.0, text=text, color=COLORS["error"], text_color=COLORS["error"])

    def set_cancelled(self, text="–"):
        self.set(0.0, text=text, color=COLORS["muted"], text_color=COLORS["muted"])

    def reset(self, text="0%"):
        self.set(0.0, text=text, color=COLORS["accent"], text_color=COLORS["text"])


def rounded_image(image, size=64, radius=12):
    """Returns a square, rounded RGBA image suitable for CTkImage."""
    if image.mode not in ("RGB", "RGBA"):
        image = image.convert("RGB")
    width, height = image.size
    edge = min(width, height)
    image = image.crop(
        (
            (width - edge) // 2,
            (height - edge) // 2,
            (width + edge) // 2,
            (height + edge) // 2,
        )
    ).resize((size * 2, size * 2), Image.LANCZOS)

    mask = Image.new("L", (size * 2, size * 2), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        (0, 0, size * 2, size * 2), radius=radius * 2, fill=255
    )
    result = image.convert("RGBA")
    result.putalpha(mask)
    return result


def truncate_middle(text, max_chars=34):
    if not text or len(text) <= max_chars:
        return text or ""
    keep = max_chars - 3
    left = (keep + 1) // 2
    right = keep // 2
    return f"{text[:left]}...{text[-right:]}"

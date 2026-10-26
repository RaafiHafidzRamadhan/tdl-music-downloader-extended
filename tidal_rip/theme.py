"""Visual design tokens for the light white/blue application theme."""

import customtkinter as CTk

FONT_FAMILY = "Segoe UI"

COLORS = {
    "bg": "#F4F7FC",
    "surface": "#FFFFFF",
    "surface_soft": "#EEF4FF",
    "surface_hover": "#E8F0FE",
    "surface_muted": "#F8FAFC",
    "border": "#E2E8F0",
    "border_strong": "#CBD5E1",
    "accent": "#2563EB",
    "accent_hover": "#1D4ED8",
    "accent_soft": "#DBEAFE",
    "accent_text": "#1D4ED8",
    "text": "#0F172A",
    "text_secondary": "#475569",
    "muted": "#94A3B8",
    "success": "#10B981",
    "success_soft": "#D1FAE5",
    "error": "#EF4444",
    "error_soft": "#FEE2E2",
    "warning": "#F59E0B",
    "warning_soft": "#FEF3C7",
}

SOURCE_META = {
    "tidal": {
        "label": "Tidal",
        "format": "Hi-Res FLAC",
        "color": "#0284C7",
        "soft": "#E0F2FE",
    },
    "youtube": {
        "label": "YouTube",
        "format": "MP3 320 kbps",
        "color": "#DC2626",
        "soft": "#FEE2E2",
    },
}


def setup_theme():
    CTk.set_appearance_mode("light")
    CTk.set_default_color_theme("blue")


def ui_font(size=12, weight="normal", family=FONT_FAMILY):
    return CTk.CTkFont(family=family, size=size, weight=weight)


def source_meta(source):
    return SOURCE_META.get(source, SOURCE_META["tidal"])


def text_color_for_bg(hex_color):
    """Picks a readable text color for a filled badge."""
    value = hex_color.lstrip("#")
    if len(value) != 6:
        return COLORS["text"]
    r, g, b = (int(value[i:i + 2], 16) for i in (0, 2, 4))
    luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255
    return "#0F172A" if luminance > 0.68 else "#FFFFFF"

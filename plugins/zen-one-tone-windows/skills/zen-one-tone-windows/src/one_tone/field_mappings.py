from __future__ import annotations

from dataclasses import dataclass
import re
import json
from pathlib import Path
from typing import Any
from typing import Mapping

from .palette import contrast_ratio, parse_hex_color, readable_text


@dataclass(frozen=True)
class FieldMapping:
    field: str
    visual_role: str
    palette_key: str
    visual_region: str
    checked_on: str | None = None
    text_class: str = "none"
    paired_background_role: str = "not-applicable"
    opacity_policy: str = "not-applicable"
    registered_baselines: tuple[str, ...] = ()
    condition: str = ""


def _fields(names: str, role: str, *, key: str | None = None, region: str = "workbench", checked_on: str | None = None, text_class: str | None = None) -> tuple[FieldMapping, ...]:
    default_text_class, paired = {
        "foreground": ("dense-primary", "surface"),
        "muted_foreground": ("secondary", "surface"),
        "selection": ("state", "selection"),
        "accent_text": ("semantic", "surface"),
        "error_text": ("semantic", "surface"),
        "warning_text": ("semantic", "surface"),
        "success_text": ("semantic", "surface"),
        "accent_foreground": ("state", "accent"),
        "prediction_foreground": ("secondary", "surface"),
    }.get(role, ("none", "not-applicable"))
    text_class = text_class or default_text_class
    return tuple(FieldMapping(name, role, key or role, region, checked_on, text_class, paired, "opaque" if text_class != "none" else "not-applicable") for name in names.split())


# One distributable, explicit mapping; fixtures keep independent official inventories.
VSCODE_FIELD_DATA = json.loads(Path(__file__).with_name("vscode_fields.json").read_text(encoding="utf-8"))
_vscode_mappings = []
for name, (role, key, opacity, baselines, condition, text_class, background) in VSCODE_FIELD_DATA["fields"].items():
    region = "workbench git decorations" if name.startswith("gitDecoration.") else "editor" if name.startswith(("editor", "terminal")) else "workbench"
    _vscode_mappings.append(FieldMapping(name, role, key, region, None, text_class, background, opacity, tuple(baselines), condition))
VSCODE_FIELD_MAPPINGS = tuple(_vscode_mappings)

CHROME_COLOR_ROLES = {
    **dict.fromkeys("frame frame_incognito".split(), "surface"),
    **dict.fromkeys("frame_inactive frame_incognito_inactive background_tab_inactive background_tab_incognito_inactive ntp_background".split(), "light_mode_surface"),
    **dict.fromkeys("background_tab background_tab_incognito".split(), "surface_subtle"),
    "toolbar": "toolbar_surface", "omnibox_background": "surface_raised", "button_background": "accent",
    **dict.fromkeys("toolbar_text toolbar_button_icon tab_background_text tab_background_text_incognito tab_text bookmark_text ntp_header ntp_text omnibox_text".split(), "foreground"),
    **dict.fromkeys("tab_background_text_inactive tab_background_text_incognito_inactive".split(), "inactive_text"),
    "ntp_link": "accent_text",
}
CHROME_TINT_ROLES = {"buttons": "accent", "background_tab": "surface_subtle",
                     "frame": "surface", "frame_incognito": "surface",
                     "frame_inactive": "light_mode_surface", "frame_incognito_inactive": "light_mode_surface"}


def vscode_capabilities(baseline: str) -> dict[str, str]:
    return {mapping.field: "not-applicable" if mapping.condition.startswith("not-applicable")
            else "supported" if baseline in mapping.registered_baselines else "unsupported"
            for mapping in VSCODE_FIELD_MAPPINGS}


TERMINAL_FIELD_MAPPINGS = (
    *_fields("background", "surface", region="terminal"),
    *_fields("foreground", "foreground", region="terminal"),
    # ANSI slots are used as backgrounds too; black pairs with primary/white text.
    *_fields("black", "surface", region="terminal"),
    *_fields("white brightWhite", "foreground", region="terminal", text_class="semantic"),
    *_fields("brightBlack", "muted_foreground", region="terminal", text_class="semantic"),
    *_fields("selectionBackground", "selection", key="selection_background", region="terminal"),
    *_fields("cursorColor", "accent_text", region="terminal"),
    *_fields("red brightRed", "error_text", region="terminal"),
    *_fields("green brightGreen", "success_text", region="terminal"),
    *_fields("yellow brightYellow", "warning_text", region="terminal"),
    *_fields("blue purple cyan brightBlue brightPurple brightCyan", "accent_text", region="terminal"),
    *_fields("window.frame tab.background", "accent", region="terminal"),
    *_fields("profile.colorScheme window.applicationTheme", "surface", region="terminal"),
    *_fields("profile.adjustIndistinguishableColors", "foreground", region="terminal", text_class="none"),
    *_fields("InlinePrediction ListPrediction", "prediction_foreground", region="terminal"),
    *_fields("ListPredictionSelected", "selection", key="selection_foreground", region="terminal"),
    *_fields("window.unfocusedFrame", "muted_foreground", region="terminal"),
    *_fields("tabRow.background tab.unfocusedBackground", "surface", key="surface_subtle", region="terminal tabs"),
    *_fields("tabRow.unfocusedBackground", "surface", key="background", region="terminal tabs"),
)


TERMINAL_APPEARANCE_FIELDS = {
    "profile.colorScheme": ({"light": "One Tone Light", "dark": "One Tone Dark"}, (1, 16)),
    "profile.tabColor": ("remove", (1, 0)),
    "profile.useAcrylic": (False, (1, 0)),
    "profile.opacity": (100, (1, 12)),
    "profile.backgroundImage": ("", (1, 0)),
    "theme": ({"light": "One Tone Light", "dark": "One Tone Dark"}, (1, 17)),
    "window.useMica": (False, (1, 17)),
    "window.frame": (None, (1, 22)),
    "window.unfocusedFrame": (None, (1, 22)),
    "profile.adjustIndistinguishableColors": ("always", (1, 16)),
}


def terminal_capabilities(instance: Mapping[str, Any]) -> dict[str, str]:
    version = str(instance.get("native_correction", {}).get("version", ""))
    match = re.fullmatch(r"(\d+)\.(\d+)\.\d+(?:\.\d+)?", version)
    baseline = tuple(map(int, match.groups())) if match else (0, 0)
    statuses = {name: "supported" if baseline >= minimum else "unsupported"
                for name, (_, minimum) in TERMINAL_APPEARANCE_FIELDS.items()}
    build = instance.get("windows_build")
    for name in ("window.useMica", "window.frame", "window.unfocusedFrame"):
        if isinstance(build, int) and build < 22621:
            statuses[name] = "not-applicable"
        elif not isinstance(build, int):
            statuses[name] = "unsupported"
    return statuses


_TARGET_MAPPINGS = {
    "terminal": TERMINAL_FIELD_MAPPINGS,
    "vscode": VSCODE_FIELD_MAPPINGS,
    "trae": VSCODE_FIELD_MAPPINGS,
}


def field_mappings_for(target: str) -> tuple[FieldMapping, ...]:
    return _TARGET_MAPPINGS.get(target, ())


def vscode_field_mappings() -> tuple[FieldMapping, ...]:
    return VSCODE_FIELD_MAPPINGS


def terminal_scheme_colors(palette: Mapping[str, str]) -> dict[str, str]:
    names = {"background", "foreground", "selectionBackground", "cursorColor", "black", "red", "green", "yellow", "blue", "purple", "cyan", "white", "brightBlack", "brightRed", "brightGreen", "brightYellow", "brightBlue", "brightPurple", "brightCyan", "brightWhite"}
    return {mapping.field: palette[mapping.palette_key] for mapping in TERMINAL_FIELD_MAPPINGS if mapping.field in names}


def terminal_palette_key(field: str) -> str:
    return next(mapping.palette_key for mapping in TERMINAL_FIELD_MAPPINGS if mapping.field == field)


def vscode_theme_colors(
    palette: Mapping[str, str],
    mode: str,
    baseline: str = "1.140.0",
) -> dict[str, str]:
    contextual = {
        "sidebar_surface": palette["surface"] if mode == "light" else palette["surface_subtle"],
        "light_mode_surface": palette["surface"] if mode == "light" else palette["background"],
        "light_mode_foreground": palette["foreground"] if mode == "light" else palette["background_foreground"],
    }
    statuses = vscode_capabilities(baseline)
    def composite(color: str) -> str:
        alpha = int(color[-2:], 16) / 255
        return "#" + "".join(f"{round(overlay * alpha + base * (1 - alpha)):02X}" for overlay, base in zip(parse_hex_color(color[:7]), parse_hex_color(palette["surface"])))

    colors = {}
    for mapping in VSCODE_FIELD_MAPPINGS:
        if statuses[mapping.field] != "supported":
            continue
        color = contextual.get(mapping.palette_key, palette.get(mapping.palette_key))
        if mapping.opacity_policy == "semantic-overlay":
            # Keep diff/merge regions distinct without reducing body-text readability.
            endpoint = 255 if mode == "light" else 0
            for weight in range(101):
                candidate = "#" + "".join(f"{round(channel * (1 - weight / 100) + endpoint * weight / 100):02X}" for channel in parse_hex_color(color)) + "40"
                background = composite(candidate)
                if contrast_ratio(background, palette["surface"]) >= 1.2 and contrast_ratio(palette["foreground"], background) >= 7:
                    color = candidate
                    break
            else:
                raise ValueError(f"{mapping.field} cannot preserve region and text contrast")
        elif mapping.opacity_policy == "overlay":
            color += "40"
        colors[mapping.field] = color
    def background_color(reference: str) -> str:
        color = colors[reference] if reference in colors else contextual.get(reference, palette.get(reference))
        if color is None:
            raise ValueError(f"Unknown background reference: {reference}")
        if len(color) == 9:
            color = composite(color)
        return color
    for mapping in VSCODE_FIELD_MAPPINGS:
        if mapping.field not in colors:
            continue
        paired = mapping.paired_background_role
        if mapping.text_class != "none" and paired not in {"not-applicable", "selection"}:
            backgrounds = [background_color(reference) for reference in paired.removeprefix("field:").split("|")]
            minimum = 7 if mapping.text_class == "dense-primary" else 4.5
            for background in backgrounds:
                colors[mapping.field] = readable_text(colors[mapping.field], background, minimum)
            if any(contrast_ratio(colors[mapping.field], background) < minimum for background in backgrounds):
                raise ValueError(f"{mapping.field} cannot satisfy its actual backgrounds")
    return colors

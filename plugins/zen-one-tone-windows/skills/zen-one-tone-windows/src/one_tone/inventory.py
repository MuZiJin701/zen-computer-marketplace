from __future__ import annotations

from typing import Any

from .field_mappings import CHROME_COLOR_ROLES, CHROME_TINT_ROLES, TERMINAL_APPEARANCE_FIELDS, VSCODE_FIELD_DATA, field_mappings_for, terminal_capabilities, vscode_capabilities

FIELD_INVENTORY: dict[str, tuple[str, ...]] = {
    "windows": (
        "EnableTransparency", "wallpaper", "AccentPalette", "StartTaskbarColorPrevalence", "TitleBarColorPrevalence",
        "AccentColorMenu", "StartColorMenu", "AccentColor", "ColorizationColor", "ColorizationAfterglow",
        "AppsUseLightTheme", "SystemUsesLightTheme", "AutoColorization", "highContrast",
    ),
    "chatgpt-app": (
        "appearanceTheme",
        "appearanceLightChromeTheme.surface", "appearanceLightChromeTheme.ink", "appearanceLightChromeTheme.accent",
        "appearanceLightChromeTheme.contrast", "appearanceLightChromeTheme.opaqueWindows", "appearanceLightChromeTheme.fonts",
        "appearanceLightChromeTheme.semanticColors.diffAdded",
        "appearanceLightChromeTheme.semanticColors.diffRemoved", "appearanceLightChromeTheme.semanticColors.skill",
        "appearanceDarkChromeTheme.surface", "appearanceDarkChromeTheme.ink", "appearanceDarkChromeTheme.accent",
        "appearanceDarkChromeTheme.contrast", "appearanceDarkChromeTheme.opaqueWindows", "appearanceDarkChromeTheme.fonts",
        "appearanceDarkChromeTheme.semanticColors.diffAdded",
        "appearanceDarkChromeTheme.semanticColors.diffRemoved", "appearanceDarkChromeTheme.semanticColors.skill",
    ),
    "chrome": (*CHROME_COLOR_ROLES, *(f"tints.{field}" for field in CHROME_TINT_ROLES),
               "properties.ntp_background_alignment", "properties.ntp_background_repeat", "properties.ntp_logo_alternate"),
}

for _target in ("terminal", "vscode", "trae"):
    FIELD_INVENTORY[_target] = tuple(mapping.field for mapping in field_mappings_for(_target))

PRESERVED_FIELDS = {
    "windows": ("AppsUseLightTheme", "SystemUsesLightTheme", "AutoColorization", "highContrast", "system.fonts"),
    "terminal": tuple(f"profile.font.{name}" for name in ("face", "size", "weight", "features", "axes", "cellWidth", "cellHeight")) +
                tuple(f"profile.{name}" for name in ("padding", "antialiasingMode", "intenseTextStyle", "cursorShape", "cursorHeight")) +
                ("tab.showCloseButton", "tab.iconStyle", "window.experimental.rainbowFrame"),
    "vscode": ("editor.fontFamily", "editor.fontSize", "editor.fontWeight", "editor.fontLigatures", "editor.fontVariations", "editor.cursorStyle",
               "terminal.integrated.fontFamily", "terminal.integrated.fontSize", "terminal.integrated.fontWeight", "terminal.integrated.fontWeightBold",
               "terminal.integrated.customGlyphs", "terminal.integrated.minimumContrastRatio", "window.autoDetectHighContrast",
               "workbench.preferredHighContrastColorTheme", "workbench.preferredHighContrastLightColorTheme"),
    "chrome": ("content.fonts", "window.opacity"),
    "chatgpt-app": ("ui.fontSize", "ui.translucentSidebar", "embedded_terminal.ansi", "embedded_terminal.minimumContrastRatio"),
}
PRESERVED_FIELDS["trae"] = (*PRESERVED_FIELDS["vscode"], "private.aiPanel.colors")
FIELD_INVENTORY["terminal"] = tuple(dict.fromkeys((*FIELD_INVENTORY["terminal"], *TERMINAL_APPEARANCE_FIELDS)))
for _target, _fields in PRESERVED_FIELDS.items():
    FIELD_INVENTORY[_target] = tuple(dict.fromkeys((*FIELD_INVENTORY[_target], *_fields)))


_SOURCES = {
    "windows": "https://learn.microsoft.com/en-us/windows/apps/develop/settings/settings-common",
    "terminal": "https://github.com/microsoft/terminal/blob/v1.25.2733.0/doc/cascadia/profiles.schema.json",
    "vscode": VSCODE_FIELD_DATA["source"],
    "trae": VSCODE_FIELD_DATA["source"],
    "chatgpt-app": "verified-v1-runtime-schema",
    "chrome": "https://github.com/chromium/chromium/blob/77270bd36581caca2ab02fe4526cc921560ad089/chrome/browser/themes/browser_theme_pack.cc",
}
_BASELINES = {
    "windows": "Windows 10 22H2 / Windows 11 22H2",
    "terminal": "Windows Terminal documented profile schema",
    "vscode": "VS Code 1.140.0 registered colors and pinned public documentation",
    "trae": "Workbench 1.107.1 / 1.140.0 registrations intersected with pinned public documentation",
    "chatgpt-app": "verified ChatGPT App v1 color schema",
    "chrome": "Chrome Manifest V3 theme schema",
}
_INVENTORY_VERSION = "2026-10-05.v4"

_REFERENCE_THEMES = {
    "windows": "Windows user-visible color settings",
    "terminal": "Windows Terminal built-in Light scheme",
    "vscode": "VS Code Light Modern 1.140.0",
    "trae": "TRAE Workbench 1.107.1; installed version discovered in Preview",
    "chatgpt-app": "ChatGPT App verified v1 Light theme table",
    "chrome": "Chrome Manifest V3 Light theme",
}
_EVIDENCE_SOURCES = {
    "windows": "verified registry mechanism; high contrast uses official SPI_GETHIGHCONTRAST",
    "terminal": "official schema plus built-in Light scheme",
    "vscode": "installed built-in Light theme plus official schema",
    "trae": "installed built-in Light theme plus official schema",
    "chatgpt-app": "verified ChatGPT App runtime schema",
    "chrome": "official schema",
}
_LIST_SELECTION_FIELDS = frozenset({
    "list.activeselectionbackground",
    "list.activeselectionforeground",
    "list.inactiveselectionbackground",
    "list.inactiveselectionforeground",
    "list.focusbackground",
    "list.focusforeground",
})


def _text_class(name: str) -> str:
    lowered = name.casefold()
    if lowered.startswith("gitdecoration."):
        return "semantic"
    if lowered in {"inlineprediction", "listprediction", "listpredictionselected"}:
        return "secondary" if lowered != "listpredictionselected" else "state"
    if lowered in _LIST_SELECTION_FIELDS:
        return "state"
    if any(token in lowered for token in ("placeholder", "disabled", "inactive", "description")):
        return "secondary"
    if any(token in lowered for token in (
        "error", "warning", "success", "info", "hint", "selection", "findmatch", "badge", "button", "hover",
    )):
        return "state"
    if any(token in lowered for token in ("ansi", "link", "semantic", "diffadded", "diffremoved", "skill")):
        return "semantic"
    if "foreground" in lowered or name.endswith(".ink") or lowered.endswith("_text"):
        return "dense-primary"
    if any(token in lowered for token in ("black", "red", "green", "yellow", "blue", "purple", "cyan", "white")):
        return "semantic"
    return "none"


def _paired_background_role(name: str, text_class: str) -> str:
    if text_class == "none":
        return "not-applicable"
    lowered = name.casefold()
    if lowered in _LIST_SELECTION_FIELDS:
        return "selection"
    if "selection" in lowered or lowered == "listpredictionselected":
        return "selection"
    if lowered.startswith("gitdecoration."):
        return "surface"
    if "badge" in lowered or "button" in lowered:
        return "accent"
    return "surface"


def _opacity_policy(text_class: str) -> str:
    return "opaque" if text_class != "none" else "not-applicable"


def _field_label(name: str) -> str:
    return name.rsplit(".", 1)[-1].replace("_", " ").replace("Color", " color").strip().capitalize()


def _field_region(target: str, name: str) -> str:
    lowered = name.casefold()
    if target == "windows":
        return "taskbar" if "taskbar" in lowered or "start" in lowered else "windows shell"
    if target == "terminal":
        return "terminal tabs" if "tab" in lowered else "terminal"
    if target in {"vscode", "trae"}:
        if lowered.startswith("gitdecoration."):
            return "workbench git decorations"
        return "editor" if lowered.startswith("editor") or lowered.startswith("terminal") else "workbench"
    if target == "chrome":
        return "browser chrome"
    if target == "chatgpt-app":
        return "ChatGPT App"
    return target


def _field_role(name: str) -> str:
    lowered = name.casefold()
    if lowered in _LIST_SELECTION_FIELDS:
        return "selection"
    if lowered.startswith("gitdecoration."):
        if any(token in lowered for token in ("added", "untracked", "stagemodified")):
            return "success_text"
        if "modified" in lowered:
            return "warning_text"
        if any(token in lowered for token in ("renamed", "submodule")):
            return "accent_text"
        if any(token in lowered for token in ("deleted", "conflicting", "stagedeleted")):
            return "error_text"
        if any(token in lowered for token in ("ignored", "inactive")):
            return "muted_foreground"
    if lowered in {"inlineprediction", "listprediction"}:
        return "muted_foreground"
    if lowered == "listpredictionselected":
        return "selection"
    for token, role in (
        ("background", "surface"),
        ("foreground", "foreground"),
        ("border", "border"),
        ("cursor", "accent_text"),
        ("selection", "selection"),
        ("accent", "accent"),
        ("link", "accent_text"),
        ("error", "error_text"),
        ("warning", "warning_text"),
    ):
        if token in lowered:
            return role
    return "surface"


def field_inventory_for(target: str) -> tuple[dict[str, str], ...]:
    """Return the evidence-backed, user-readable Field inventory for a Target."""
    mappings = {mapping.field: mapping for mapping in field_mappings_for(target)}
    baseline = "1.107.1" if target == "trae" else "1.140.0"
    color_statuses = vscode_capabilities(baseline) if target in {"vscode", "trae"} else {}
    entries = []
    for name in inventory_for(target):
        mapping = mappings.get(name)
        preserved = name in PRESERVED_FIELDS.get(target, ())
        capability = (
            "unsupported" if name in {"window.opacity", "ui.fontSize", "ui.translucentSidebar", "embedded_terminal.ansi", "embedded_terminal.minimumContrastRatio", "private.aiPanel.colors"}
            else "not-applicable" if preserved or name in {"properties.ntp_background_alignment", "properties.ntp_background_repeat"}
            else color_statuses.get(name, "unsupported") if target in {"vscode", "trae"}
            else "supported"
        )
        text_class = mapping.text_class if mapping else _text_class(name)
        entries.append(
            {
                "technical_field": name,
                "label": _field_label(name),
                "field_category": (
                    "theme_structure" if name.endswith(".fonts")
                    else "font" if "font" in name.casefold()
                    else "display_property" if preserved or name in TERMINAL_APPEARANCE_FIELDS or name in {"EnableTransparency", "appearanceTheme"} or any(token in name.casefold() for token in ("properties.", "display", "prevalence", "contrast", "opaquewindows", "adjustindistinguishablecolors"))
                    else "color"
                ),
                "visual_role": mapping.visual_role if mapping else _field_role(name),
                "visual_region": mapping.visual_region if mapping else _field_region(target, name),
                "mode_support": "light,dark",
                "official_source": "https://learn.microsoft.com/en-us/windows/terminal/customize-settings/profile-appearance#adjust-indistinguishable-colors" if name == "profile.adjustIndistinguishableColors" else _SOURCES.get(target, "unknown"),
                "version_baseline": "Windows Terminal >= 1.16; executable version discovered during Preview" if name == "profile.adjustIndistinguishableColors" else _BASELINES.get(target, "verified runtime schema"),
                "inventory_version": _INVENTORY_VERSION,
                "capability_status": capability,
                "handling_policy": "preserve" if preserved else "preserve-or-repair-empty-table" if name.endswith(".fonts") else "remove-override" if name == "profile.tabColor" else "manage",
                "applicability": mapping.condition if mapping else "No NTP background image" if name in {"properties.ntp_background_alignment", "properties.ntp_background_repeat"} else "verified Target schema",
                "registered_baselines": ",".join(mapping.registered_baselines) if mapping else "",
                "text_class": text_class,
                "paired_background_role": mapping.paired_background_role if mapping else _paired_background_role(name, text_class),
                "opacity_policy": mapping.opacity_policy if mapping else _opacity_policy(text_class),
                "reference_theme": _REFERENCE_THEMES.get(target, "verified runtime schema"),
                "evidence_source": _EVIDENCE_SOURCES.get(target, "official schema"),
            }
        )
    return tuple(entries)


def inventory_report(
    target: str,
    statuses: dict[str, str] | None = None,
    generated_values: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], ...]:
    statuses = statuses or {}
    generated_values = generated_values or {}
    return tuple(
        {
            **entry,
            "capability_status": statuses.get(entry["technical_field"], entry["capability_status"]),
            "generated_value": generated_values.get(entry["technical_field"]),
            "verification_evidence": entry["official_source"],
        }
        for entry in field_inventory_for(target)
    )


def inventory_groups(
    target: str,
    statuses: dict[str, str] | None = None,
    generated_values: dict[str, Any] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for entry in inventory_report(target, statuses, generated_values):
        groups.setdefault(entry["visual_region"], []).append(entry)
    return groups


def inventory_for(target: str) -> tuple[str, ...]:
    return FIELD_INVENTORY.get(target, ())


def expected_capabilities(targets: tuple[str, ...], target_instances=None) -> dict[str, dict[str, str]]:
    result = {target: {entry["technical_field"]: entry["capability_status"] for entry in field_inventory_for(target)} for target in targets}
    for target in targets:
        instance = (target_instances or {}).get(target, {})
        if target in {"vscode", "trae"}:
            result[target].update(vscode_capabilities(instance.get("color_baseline", "")))
        elif target == "terminal":
            result[target].update(terminal_capabilities(instance))
            result[target].update({name: instance.get("psreadline", {}).get("status", "unsupported") for name in ("InlinePrediction", "ListPrediction", "ListPredictionSelected")})
            result[target]["profile.adjustIndistinguishableColors"] = instance.get("native_correction", {}).get("status", "unsupported")
        elif target == "windows":
            if instance.get("high_contrast") is not False:
                result[target].update({name: "unsupported" for name, status in result[target].items() if status == "supported"})
            elif instance.get("shell_mode") != "dark":
                result[target]["StartTaskbarColorPrevalence"] = "unsupported"
        if instance.get("status") == "skipped":
            result[target].update({name: "unsupported" for name, status in result[target].items() if status == "supported"})
    return result

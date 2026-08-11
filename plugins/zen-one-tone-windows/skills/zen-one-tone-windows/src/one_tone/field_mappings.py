from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Mapping


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


VSCODE_FIELD_MAPPINGS = (
    *_fields("foreground icon.foreground editor.foreground editorLineNumber.activeForeground sideBar.foreground sideBarTitle.foreground titleBar.activeForeground tab.activeForeground statusBar.foreground notifications.foreground settings.headerForeground breadcrumb.focusForeground terminal.foreground", "foreground", region="editor"),
    *_fields("disabledForeground descriptionForeground editorLineNumber.foreground editor.placeholder.foreground activityBar.inactiveForeground activityBarTop.inactiveForeground panelTitle.inactiveForeground input.placeholderForeground", "muted_foreground", region="editor"),
    *_fields("editor.background terminal.background tab.activeBackground", "surface", region="editor"),
    *_fields("editor.selectionBackground editor.findMatchBackground list.activeSelectionBackground list.inactiveSelectionBackground list.focusBackground list.hoverBackground", "selection", key="selection_background", region="editor"),
    *_fields("editor.selectionForeground editor.findMatchForeground list.activeSelectionForeground list.inactiveSelectionForeground list.focusForeground", "selection", key="selection_foreground", region="editor"),
    *_fields("editorCursor.foreground editorMultiCursor.primary.foreground editorMultiCursor.secondary.foreground editorInfo.foreground list.highlightForeground list.focusHighlightForeground terminalCursor.foreground terminal.ansiBlue terminal.ansiMagenta terminal.ansiCyan terminal.ansiBrightBlue terminal.ansiBrightMagenta terminal.ansiBrightCyan textLink.foreground textLink.activeForeground", "accent_text", region="editor"),
    *_fields("editorError.foreground errorForeground", "error_text", region="editor", text_class="state"),
    *_fields("editorWarning.foreground", "warning_text", region="editor", text_class="state"),
    *_fields("editorHint.foreground", "success_text", region="editor", text_class="state"),
    *_fields("terminal.ansiRed terminal.ansiBrightRed", "error_text", region="editor"),
    *_fields("terminal.ansiYellow terminal.ansiBrightYellow", "warning_text", region="editor"),
    *_fields("terminal.ansiGreen terminal.ansiBrightGreen", "success_text", region="editor"),
    *_fields("editorGroupHeader.tabsBorder sideBar.border sideBarTitle.border sideBarSectionHeader.border activityBar.border titleBar.border panel.border statusBar.border input.border editorWidget.border", "border", region="workbench"),
    *_fields("activityBar.activeBorder activityBarBadge.background activityBarTop.activeBorder tab.activeBorderTop panelTitle.activeBorder badge.background focusBorder button.background settings.modifiedItemIndicator", "accent", region="workbench"),
    *_fields("activityBarBadge.foreground badge.foreground button.foreground", "accent_foreground", region="workbench"),
    *_fields("titleBar.activeBackground statusBar.background input.background dropdown.background editorWidget.background", "surface_raised", region="workbench"),
    *_fields("editorGroupHeader.tabsBackground sideBar.background sideBarTitle.background", "surface", key="sidebar_surface", region="workbench"),
    *_fields("sideBarSectionHeader.background activityBar.background activityBarTop.background titleBar.inactiveBackground tab.inactiveBackground panel.background breadcrumb.background", "surface", key="light_mode_surface", region="workbench"),
    *_fields("sideBarSectionHeader.foreground activityBar.foreground activityBarTop.foreground titleBar.inactiveForeground tab.inactiveForeground panel.foreground panelTitle.activeForeground input.foreground dropdown.foreground notificationCenterHeader.foreground breadcrumb.foreground", "foreground", key="light_mode_foreground", region="workbench"),
    *_fields("terminal.ansiBlack terminal.ansiWhite terminal.ansiBrightBlack terminal.ansiBrightWhite", "foreground", region="editor"),
    *_fields("gitDecoration.addedResourceForeground gitDecoration.untrackedResourceForeground gitDecoration.stageModifiedResourceForeground", "success_text", region="workbench git decorations", checked_on="sidebar_surface"),
    *_fields("gitDecoration.modifiedResourceForeground", "warning_text", region="workbench git decorations", checked_on="sidebar_surface"),
    *_fields("gitDecoration.deletedResourceForeground gitDecoration.conflictingResourceForeground gitDecoration.stageDeletedResourceForeground", "error_text", region="workbench git decorations", checked_on="sidebar_surface"),
    *_fields("gitDecoration.ignoredResourceForeground", "muted_foreground", region="workbench git decorations", checked_on="sidebar_surface"),
    *_fields("gitDecoration.renamedResourceForeground gitDecoration.submoduleResourceForeground", "accent_text", region="workbench git decorations", checked_on="sidebar_surface"),
)


TERMINAL_FIELD_MAPPINGS = (
    *_fields("background", "surface", region="terminal"),
    *_fields("foreground black white brightBlack brightWhite", "foreground", region="terminal"),
    *_fields("selectionBackground", "selection", key="selection_background", region="terminal"),
    *_fields("selectionForeground", "selection", key="selection_foreground", region="terminal"),
    *_fields("cursorColor", "accent_text", region="terminal"),
    *_fields("red brightRed", "error_text", region="terminal"),
    *_fields("green brightGreen", "success_text", region="terminal"),
    *_fields("yellow brightYellow", "warning_text", region="terminal"),
    *_fields("blue purple cyan brightBlue brightPurple brightCyan", "accent_text", region="terminal"),
    *_fields("profile.tabColor window.frame tab.background", "accent", region="terminal"),
    *_fields("profile.colorScheme theme.applicationTheme", "surface", region="terminal"),
    *_fields("InlinePrediction ListPrediction", "prediction_foreground", region="terminal"),
    *_fields("ListPredictionSelected", "selection", key="selection_foreground", region="terminal"),
    *_fields("window.unfocusedFrame", "muted_foreground", region="terminal"),
    *_fields("tabRow.background tab.unfocusedBackground", "surface", key="surface_subtle", region="terminal tabs"),
    *_fields("tabRow.unfocusedBackground", "surface", key="background", region="terminal tabs"),
)


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
    names = {"background", "foreground", "selectionBackground", "selectionForeground", "cursorColor", "black", "red", "green", "yellow", "blue", "purple", "cyan", "white", "brightBlack", "brightRed", "brightGreen", "brightYellow", "brightBlue", "brightPurple", "brightCyan", "brightWhite"}
    return {mapping.field: palette[mapping.palette_key] for mapping in TERMINAL_FIELD_MAPPINGS if mapping.field in names}


def terminal_palette_key(field: str) -> str:
    return next(mapping.palette_key for mapping in TERMINAL_FIELD_MAPPINGS if mapping.field == field)


def vscode_theme_colors(
    palette: Mapping[str, str],
    mode: str,
    checked: Callable[[str, str], str],
) -> dict[str, str]:
    contextual = {
        "sidebar_surface": palette["surface"] if mode == "light" else palette["surface_subtle"],
        "light_mode_surface": palette["surface"] if mode == "light" else palette["background"],
        "light_mode_foreground": palette["foreground"] if mode == "light" else palette["background_foreground"],
    }
    colors = {
        mapping.field: contextual[mapping.palette_key] if mapping.palette_key in contextual else palette[mapping.palette_key]
        for mapping in VSCODE_FIELD_MAPPINGS
    }
    for mapping in VSCODE_FIELD_MAPPINGS:
        if mapping.checked_on:
            colors[mapping.field] = checked(mapping.palette_key, contextual[mapping.checked_on])
    return colors

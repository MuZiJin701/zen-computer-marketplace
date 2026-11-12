# ADR 0006: Mode coherence and system-mode following

## Status

Accepted — 2026-07-26; updated by [ADR 0011](0011-single-plugin-antigravity-and-standard-editor-paths.md) — 2026-11-12; supersedes the auto-detect preservation parts of ADR 0003.

One-Tone keeps Light and Dark as variants of one Seed Color: corresponding large-area roles retain their hue and ordering while allowing clean, bright Light surfaces (`MODE_TONAL_LIGHTNESS_DELTA = 0.75`, `MODE_LIGHT_SURFACE_MAX_LUMINANCE = 0.96`). Apply enables native system-mode following where a Target supports paired themes (VS Code, TRAE, Antigravity IDE, ChatGPT App, and Antigravity 2.0), while Windows Terminal defaults to `One Tone Dark` (still registering both Light and Dark schemes/themes), Chrome remains manual, and Windows system mode is never changed or watched by a background service.


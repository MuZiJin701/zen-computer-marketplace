from __future__ import annotations

import base64
import json
import os
import re
import uuid
from pathlib import Path
from typing import Any, Iterable, Mapping


_SAFE_COMPONENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
BYTES_MARKER = "__one_tone_bytes__"


def strip_jsonc(text: str) -> str:
    """Strip UTF-8 BOM, // and /* */ comments, and trailing commas outside string literals."""
    source = text.removeprefix("\ufeff")
    no_comments: list[str] = []
    index = 0
    length = len(source)
    in_string = False
    escaped = False
    while index < length:
        char = source[index]
        if in_string:
            no_comments.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            index += 1
            continue
        if char == '"':
            in_string = True
            no_comments.append(char)
            index += 1
            continue
        if char == "/" and index + 1 < length:
            nxt = source[index + 1]
            if nxt == "/":
                index += 2
                while index < length and source[index] not in "\r\n":
                    index += 1
                continue
            if nxt == "*":
                index += 2
                while index + 1 < length and not (source[index] == "*" and source[index + 1] == "/"):
                    index += 1
                index = min(length, index + 2)
                continue
        no_comments.append(char)
        index += 1
    cleaned = "".join(no_comments)
    result: list[str] = []
    index = 0
    length = len(cleaned)
    in_string = False
    escaped = False
    while index < length:
        char = cleaned[index]
        if in_string:
            result.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            index += 1
            continue
        if char == '"':
            in_string = True
            result.append(char)
            index += 1
            continue
        if char == ",":
            lookahead = index + 1
            while lookahead < length and cleaned[lookahead] in " \t\r\n":
                lookahead += 1
            if lookahead < length and cleaned[lookahead] in "}]":
                index += 1
                continue
        result.append(char)
        index += 1
    return "".join(result)


def loads_jsonc(text: str) -> Any:
    return json.loads(strip_jsonc(text))


def json_safe(value: Any) -> Any:
    if isinstance(value, (bytes, bytearray)):
        return {BYTES_MARKER: base64.b64encode(bytes(value)).decode("ascii")}
    if isinstance(value, dict):
        return {key: json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    return value


def validate_safe_component(value: str, label: str) -> str:
    if not isinstance(value, str) or value in {"", ".", ".."} or not _SAFE_COMPONENT.fullmatch(value):
        raise ValueError(f"{label} must be a safe path component")
    return value


def atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def atomic_write_text(path: Path, text: str, *, encoding: str = "utf-8", newline: str | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("w", encoding=encoding, newline=newline) as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _strict_json_equal(left: Any, right: Any) -> bool:
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(_strict_json_equal(left[k], right[k]) for k in left)
    if isinstance(left, list):
        return len(left) == len(right) and all(_strict_json_equal(a, b) for a, b in zip(left, right))
    return left == right


def _skip_ws_and_comments(text: str, pos: int) -> int:
    length = len(text)
    while pos < length:
        char = text[pos]
        if char in " \t\r\n":
            pos += 1
            continue
        if char == "/" and pos + 1 < length:
            nxt = text[pos + 1]
            if nxt == "/":
                pos += 2
                while pos < length and text[pos] not in "\r\n":
                    pos += 1
                continue
            if nxt == "*":
                pos += 2
                while pos + 1 < length and not (text[pos] == "*" and text[pos + 1] == "/"):
                    pos += 1
                pos = min(length, pos + 2)
                continue
        break
    return pos


def _scan_string_end(text: str, start: int) -> int:
    pos = start + 1
    length = len(text)
    escaped = False
    while pos < length:
        char = text[pos]
        if escaped:
            escaped = False
        elif char == "\\":
            escaped = True
        elif char == '"':
            return pos + 1
        pos += 1
    raise ValueError("Unterminated JSON string")


def _scan_value_end(text: str, start: int) -> int:
    length = len(text)
    if start >= length:
        raise ValueError("Unexpected end of JSONC value")
    first = text[start]
    if first == '"':
        return _scan_string_end(text, start)
    if first in "{[":
        depth = 0
        pos = start
        while pos < length:
            pos = _skip_ws_and_comments(text, pos) if depth > 0 else pos
            if pos >= length:
                break
            char = text[pos]
            if char == '"':
                pos = _scan_string_end(text, pos)
                continue
            if char in "{[":
                depth += 1
            elif char in "}]":
                depth -= 1
                if depth == 0:
                    return pos + 1
            pos += 1
        raise ValueError("Unterminated composite JSONC value")
    pos = start
    while pos < length:
        char = text[pos]
        if char in ",}] \t\r\n":
            break
        if char == "/" and pos + 1 < length and text[pos + 1] in "/*":
            break
        pos += 1
    if pos == start:
        raise ValueError("Empty JSONC primitive value")
    return pos


def _find_root_object_properties(text: str) -> tuple[int, int, list[tuple[str, int, int, int, int | None]]]:
    pos = _skip_ws_and_comments(text, 0)
    if pos >= len(text) or text[pos] != "{":
        raise ValueError("JSONC root is not an object")
    root_open = pos
    pos = _skip_ws_and_comments(text, root_open + 1)
    props: list[tuple[str, int, int, int, int | None]] = []
    while pos < len(text) and text[pos] != "}":
        if text[pos] != '"':
            raise ValueError("Expected property name string in JSONC object")
        key_start = pos
        key_end = _scan_string_end(text, key_start)
        key = json.loads(text[key_start:key_end])
        pos = _skip_ws_and_comments(text, key_end)
        if pos >= len(text) or text[pos] != ":":
            raise ValueError("Expected ':' after JSONC property key")
        val_start = _skip_ws_and_comments(text, pos + 1)
        val_end = _scan_value_end(text, val_start)
        after_val = _skip_ws_and_comments(text, val_end)
        comma_pos: int | None = None
        if after_val < len(text) and text[after_val] == ",":
            comma_pos = after_val
            pos = _skip_ws_and_comments(text, after_val + 1)
        else:
            pos = after_val
        props.append((key, key_start, val_start, val_end, comma_pos))
    if pos >= len(text) or text[pos] != "}":
        raise ValueError("Unterminated JSONC root object")
    return root_open, pos, props


def _format_json_value(value: Any, base_indent: str, indent: int) -> str:
    dumped = json.dumps(value, ensure_ascii=False, indent=indent)
    if "\n" not in dumped:
        return dumped
    lines = dumped.splitlines()
    return "\n".join([lines[0], *(f"{base_indent}{line}" for line in lines[1:])])


def _detect_property_indent(text: str, props: list[tuple[str, int, int, int, int | None]], indent: int) -> str:
    if not props:
        return " " * indent
    key_start = props[0][1]
    line_start = max(text.rfind("\n", 0, key_start), text.rfind("\r", 0, key_start)) + 1
    prefix = text[line_start:key_start]
    return prefix if prefix and prefix.strip() == "" else (" " * indent)


def patch_jsonc_object(
    original_text: str,
    updates: Mapping[str, Any],
    removals: Iterable[str] = (),
    *,
    expected_dict: Mapping[str, Any] | None = None,
    indent: int = 2,
) -> str:
    """Update/insert/remove top-level JSONC keys while preserving comments, falling back safely."""
    bom = "\ufeff" if original_text.startswith("\ufeff") else ""
    body = original_text[len(bom):]
    removal_set = set(removals) - set(updates)
    if expected_dict is not None:
        expected = dict(expected_dict)
    else:
        try:
            loaded = loads_jsonc(body) if body.strip() else {}
        except (ValueError, json.JSONDecodeError):
            loaded = {}
        expected = dict(loaded) if isinstance(loaded, dict) else {}
        for key in removal_set:
            expected.pop(key, None)
        for key, value in updates.items():
            expected[key] = value

    fallback = bom + json.dumps(expected, ensure_ascii=False, indent=indent) + "\n"
    if not body.strip():
        return fallback

    try:
        root_open, root_close, props = _find_root_object_properties(body)
        prop_indent = _detect_property_indent(body, props, indent)
        edits: list[tuple[int, int, str]] = []
        existing_keys: set[str] = set()
        kept_props: list[tuple[str, int, int, int, int | None]] = []

        for prop in props:
            key, key_start, val_start, val_end, comma_pos = prop
            existing_keys.add(key)
            if key in updates:
                line_start = max(body.rfind("\n", 0, key_start), body.rfind("\r", 0, key_start)) + 1
                line_prefix = body[line_start:key_start]
                base_indent = line_prefix if line_prefix.strip() == "" else prop_indent
                edits.append((val_start, val_end, _format_json_value(updates[key], base_indent, indent)))
                kept_props.append(prop)
            elif key in removal_set:
                del_start = key_start
                del_end = (comma_pos + 1) if comma_pos is not None else val_end
                line_start = max(body.rfind("\n", 0, key_start), body.rfind("\r", 0, key_start)) + 1
                line_end = body.find("\n", del_end)
                if line_end < 0:
                    line_end = len(body)
                else:
                    line_end += 1
                if body[line_start:key_start].strip() == "" and body[del_end:line_end].strip() == "":
                    del_start = line_start
                    del_end = line_end
                edits.append((del_start, del_end, ""))
            else:
                kept_props.append(prop)

        missing_updates = [(key, value) for key, value in updates.items() if key not in existing_keys]
        if missing_updates:
            if kept_props and kept_props[-1][4] is None:
                last_val_end = kept_props[-1][3]
                edits.append((last_val_end, last_val_end, ","))
            formatted_new = [
                f"{prop_indent}{json.dumps(key, ensure_ascii=False)}: {_format_json_value(value, prop_indent, indent)}"
                for key, value in missing_updates
            ]
            insert_block = ",\n".join(formatted_new)
            before_close = body[root_open + 1:root_close]
            last_nl = body.rfind("\n", root_open, root_close)
            if last_nl >= 0 and body[last_nl + 1:root_close].strip() == "":
                insert_pos = last_nl + 1
                edits.append((insert_pos, insert_pos, f"{insert_block}\n"))
            else:
                prefix_nl = "\n" if before_close and not before_close.endswith("\n") else ""
                if not before_close.strip():
                    prefix_nl = "\n"
                edits.append((root_close, root_close, f"{prefix_nl}{insert_block}\n"))
        elif kept_props and props and props[-1][4] is None and kept_props[-1] != props[-1] and kept_props[-1][4] is not None:
            last_comma = kept_props[-1][4]
            edits.append((last_comma, last_comma + 1, ""))

        patched = body
        for start, end, replacement in sorted(edits, key=lambda item: (item[0], item[1]), reverse=True):
            patched = patched[:start] + replacement + patched[end:]
        if patched and not patched.endswith("\n"):
            patched += "\n"
        parsed = loads_jsonc(patched)
        if isinstance(parsed, dict) and _strict_json_equal(parsed, expected):
            return bom + patched
    except (ValueError, json.JSONDecodeError, TypeError):
        pass
    return fallback

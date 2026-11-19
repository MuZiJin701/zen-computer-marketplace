from __future__ import annotations

import base64
import json
import os
import re
import uuid
from pathlib import Path
from typing import Any


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

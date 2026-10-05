"""Defensive coercion for model output (the model sometimes returns null/str/dict)."""

from __future__ import annotations

from typing import Any


def as_text(value: Any, max_len: int = 2000) -> str:
    if value is None:
        return ""

    if isinstance(value, (list, tuple)):
        value = ", ".join(str(item) for item in value if item)

    return str(value).strip()[:max_len]


def as_number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None

    try:
        number = float(value)
    except (TypeError, ValueError):
        return None

    if number < 0 or number > 60:
        return None

    return round(number, 1)


def as_str_list(value: Any, limit: int = 60, item_len: int = 80) -> list[str]:
    """Return a de-duplicated list of short strings (case-insensitive)."""

    if value is None:
        return []

    if isinstance(value, str):
        value = [part for part in value.replace("\n", ",").split(",")]

    if not isinstance(value, (list, tuple)):
        return []

    seen: set[str] = set()
    result: list[str] = []

    for item in value:
        if isinstance(item, dict):
            item = item.get("name") or item.get("title") or ""

        text = str(item).strip()[:item_len] if item is not None else ""
        key = text.lower()

        if not text or key in seen:
            continue

        seen.add(key)
        result.append(text)

        if len(result) >= limit:
            break

    return result


def as_object_list(
    value: Any,
    keys: tuple[str, ...],
    primary: str,
    limit: int = 30,
) -> list[dict[str, Any]]:
    """
    Coerce a list of entries into dicts that contain ``keys``.

    A bare string becomes ``{primary: string}`` so the UI can always rely
    on the same shape.
    """

    if not isinstance(value, (list, tuple)):
        return []

    result: list[dict[str, Any]] = []

    for item in value:
        if isinstance(item, str):
            item = {primary: item}

        if not isinstance(item, dict):
            continue

        entry: dict[str, Any] = {}

        for key in keys:
            raw = item.get(key)

            if key == "technologies":
                entry[key] = as_str_list(raw, limit=20)
            else:
                entry[key] = as_text(raw, 600)

        if any(entry.values()):
            result.append(entry)

        if len(result) >= limit:
            break

    return result

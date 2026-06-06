"""Small Markdown and CSV rendering helpers for deterministic reports."""

from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


def generated_at() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def display(value: Any) -> str:
    if value is None:
        return "N/A"
    text = str(value).strip()
    return text if text else "N/A"


def cell(value: Any) -> str:
    return display(value).replace("\n", " ").replace("|", "/")


def compact(value: Any, max_len: int = 140) -> str:
    text = cell(value)
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."


def table(headers: list[str], rows: Iterable[Iterable[Any]]) -> str:
    lines = [" | ".join(headers), " | ".join("---" for _ in headers)]
    for row in rows:
        lines.append(" | ".join(cell(value) for value in row))
    return "\n".join(lines)


def field_table(rows: Iterable[tuple[str, Any]]) -> str:
    return table(["Field", "Value"], rows)


def section(title: str, body: str) -> str:
    return f"## {title}\n\n{body.strip()}\n"


def bullet_list(items: Iterable[str]) -> str:
    items = [item for item in items if item]
    if not items:
        return "- N/A"
    return "\n".join(f"- {item}" for item in items)


def write_text(path: Path | str, text: str) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    return target


def write_csv(path: Path | str, rows: list[dict[str, Any]], fields: list[str]) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field) for field in fields})
    return target


def row_to_dict(row: Any) -> dict[str, Any]:
    if row is None:
        return {}
    return {key: row[key] for key in row.keys()}


def rows_to_dicts(rows: Iterable[Any]) -> list[dict[str, Any]]:
    return [row_to_dict(row) for row in rows]

"""Read and advance the 30-day content calendar.

The calendar is a markdown table so a human can edit it in any editor. This
module is the only writer, so that "which slot is next" never depends on the
model remembering what it published.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

VALID_STATUSES = ("pending", "done", "skipped")
STALE_AFTER = timedelta(days=7)

_COLUMNS = 7  # #, Date, Pillar, Angle, Status, Published, URL
_SEPARATOR_PATTERN = re.compile(r"^\s*\|[\s:|-]+\|\s*$")


@dataclass(frozen=True)
class Slot:
    number: int
    date: date
    pillar: str
    angle: str
    status: str
    published: date | None
    url: str


def _split_row(line: str) -> list[str] | None:
    """Split a markdown table row into trimmed cells, or None if not a data row."""
    stripped = line.strip()
    if not stripped.startswith("|") or not stripped.endswith("|"):
        return None
    if _SEPARATOR_PATTERN.match(line):
        return None
    cells = [cell.strip() for cell in stripped[1:-1].split("|")]
    if len(cells) != _COLUMNS:
        return None
    if not cells[0].isdigit():  # drops the header row
        return None
    return cells


def _parse_date(value: str) -> date | None:
    if not value:
        return None
    return datetime.strptime(value, "%Y-%m-%d").date()


def parse_calendar(text: str) -> list[Slot]:
    """Parse every data row of the calendar table. Prose around it is ignored."""
    slots: list[Slot] = []
    for line in text.splitlines():
        cells = _split_row(line)
        if cells is None:
            continue
        number, planned, pillar, angle, status, published, url = cells
        if status not in VALID_STATUSES:
            raise ValueError(
                f"invalid status {status!r} in row {number}; expected one of {VALID_STATUSES}"
            )
        slots.append(
            Slot(
                number=int(number),
                date=_parse_date(planned),
                pillar=pillar,
                angle=angle,
                status=status,
                published=_parse_date(published),
                url=url,
            )
        )
    return slots


def next_pending(slots: list[Slot]) -> Slot | None:
    """The earliest pending slot by planned date, or None if there is none."""
    pending = [slot for slot in slots if slot.status == "pending"]
    if not pending:
        return None
    return min(pending, key=lambda slot: slot.date)


def is_active(slots: list[Slot], today: date) -> bool:
    """A calendar is active while a pending slot is no more than 7 days stale."""
    upcoming = next_pending(slots)
    if upcoming is None:
        return False
    return today - upcoming.date <= STALE_AFTER


def draft_path(calendar_path: Path, number: int) -> Path:
    """Where slot `number`'s draft lives: a <YYYY-MM>-posts/ dir beside the calendar.

    The draft file is published verbatim, so it holds nothing but the post text.
    """
    stem = calendar_path.name.removesuffix("-calendar.md")
    if stem == calendar_path.name:
        raise ValueError(f"not a calendar path: {calendar_path.name!r} (expected *-calendar.md)")
    return calendar_path.parent / f"{stem}-posts" / f"{number:02d}.txt"


def mark_done(text: str, number: int, url: str, published: date) -> str:
    """Return `text` with slot `number` flipped to done. Never republishes."""
    lines = text.splitlines(keepends=True)
    for index, line in enumerate(lines):
        cells = _split_row(line)
        if cells is None or int(cells[0]) != number:
            continue
        if cells[4] == "done":
            raise ValueError(f"slot {number} is already done: {cells[6]}")
        cells[4] = "done"
        cells[5] = published.isoformat()
        cells[6] = url
        newline = "\n" if line.endswith("\n") else ""
        lines[index] = "| " + " | ".join(cells) + " |" + newline
        return "".join(lines)
    raise ValueError(f"no slot numbered {number} in this calendar")

from datetime import date
from pathlib import Path

import pytest

from tools.calendar_state import (
    Slot,
    draft_path,
    is_active,
    mark_done,
    next_pending,
    parse_calendar,
)

CALENDAR = """# Calendario de conteudo — 2026-08

Pilares: Python craft, MCP tooling, fintech eng, dev pleno.

| # | Date       | Pillar       | Angle                             | Status  | Published  | URL |
|---|------------|--------------|-----------------------------------|---------|------------|-----|
| 1 | 2026-08-11 | Python craft | Por que troquei Celery por RQ     | done    | 2026-08-11 | https://linkedin.com/feed/update/1 |
| 2 | 2026-08-12 | MCP tooling  | O que um MCP server realmente faz | pending |            |     |
| 3 | 2026-08-13 | fintech eng  | Antecipacao de recebiveis em 1h   | pending |            |     |
| 4 | 2026-08-18 | dev pleno    | O que mudou do junior para pleno  | skipped |            |     |
"""


class TestParseCalendar:
    def test_parses_every_row(self):
        assert len(parse_calendar(CALENDAR)) == 4

    def test_parses_field_values(self):
        first = parse_calendar(CALENDAR)[0]
        assert first == Slot(
            number=1,
            date=date(2026, 8, 11),
            pillar="Python craft",
            angle="Por que troquei Celery por RQ",
            status="done",
            published=date(2026, 8, 11),
            url="https://linkedin.com/feed/update/1",
        )

    def test_empty_published_and_url_become_none_and_blank(self):
        second = parse_calendar(CALENDAR)[1]
        assert second.published is None
        assert second.url == ""

    def test_ignores_prose_and_the_header_separator(self):
        assert [slot.number for slot in parse_calendar(CALENDAR)] == [1, 2, 3, 4]

    def test_returns_empty_list_when_no_table_present(self):
        assert parse_calendar("# Sem tabela\n\nNada aqui.") == []

    def test_rejects_an_unknown_status(self):
        broken = CALENDAR.replace("| pending |", "| publicado |", 1)
        with pytest.raises(ValueError, match="invalid status"):
            parse_calendar(broken)


class TestNextPending:
    def test_returns_the_earliest_pending_slot(self):
        assert next_pending(parse_calendar(CALENDAR)).number == 2

    def test_skips_done_and_skipped_slots(self):
        assert next_pending(parse_calendar(CALENDAR)).status == "pending"

    def test_orders_by_date_not_by_row_position(self):
        slots = [
            Slot(2, date(2026, 8, 20), "b", "b", "pending", None, ""),
            Slot(1, date(2026, 8, 12), "a", "a", "pending", None, ""),
        ]
        assert next_pending(slots).number == 1

    def test_returns_none_when_nothing_is_pending(self):
        slots = [Slot(1, date(2026, 8, 11), "a", "a", "done", date(2026, 8, 11), "u")]
        assert next_pending(slots) is None


class TestIsActive:
    def test_active_when_a_pending_slot_is_in_the_future(self):
        assert is_active(parse_calendar(CALENDAR), today=date(2026, 8, 12)) is True

    def test_active_when_a_pending_slot_is_less_than_seven_days_stale(self):
        assert is_active(parse_calendar(CALENDAR), today=date(2026, 8, 19)) is True

    def test_inactive_when_every_pending_slot_is_over_seven_days_stale(self):
        assert is_active(parse_calendar(CALENDAR), today=date(2026, 8, 21)) is False

    def test_inactive_when_nothing_is_pending(self):
        slots = [Slot(1, date(2026, 8, 11), "a", "a", "done", date(2026, 8, 11), "u")]
        assert is_active(slots, today=date(2026, 8, 11)) is False


class TestDraftPath:
    def test_maps_slot_to_zero_padded_txt_beside_the_calendar(self):
        path = Path("plans/calendar/2026-08-calendar.md")
        assert draft_path(path, 3) == Path("plans/calendar/2026-08-posts/03.txt")

    def test_two_digit_slots_keep_their_width(self):
        assert draft_path(Path("plans/calendar/2026-08-calendar.md"), 29).name == "29.txt"

    def test_rejects_a_non_calendar_filename(self):
        with pytest.raises(ValueError, match="calendar"):
            draft_path(Path("plans/calendar/notes.md"), 1)


class TestMarkDone:
    def test_sets_status_published_and_url(self):
        updated = mark_done(CALENDAR, 2, "https://linkedin.com/feed/update/2", date(2026, 8, 12))
        slot = parse_calendar(updated)[1]
        assert slot.status == "done"
        assert slot.published == date(2026, 8, 12)
        assert slot.url == "https://linkedin.com/feed/update/2"

    def test_leaves_other_rows_untouched(self):
        updated = mark_done(CALENDAR, 2, "https://linkedin.com/feed/update/2", date(2026, 8, 12))
        assert parse_calendar(updated)[2] == parse_calendar(CALENDAR)[2]

    def test_preserves_surrounding_prose(self):
        updated = mark_done(CALENDAR, 2, "https://linkedin.com/feed/update/2", date(2026, 8, 12))
        assert "Pilares: Python craft, MCP tooling, fintech eng, dev pleno." in updated

    def test_raises_for_an_unknown_slot_number(self):
        with pytest.raises(ValueError, match="no slot numbered 99"):
            mark_done(CALENDAR, 99, "https://x", date(2026, 8, 12))

    def test_refuses_to_republish_a_done_slot(self):
        with pytest.raises(ValueError, match="already done"):
            mark_done(CALENDAR, 1, "https://x", date(2026, 8, 12))

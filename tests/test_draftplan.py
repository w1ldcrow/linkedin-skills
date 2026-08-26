from pathlib import Path

import pytest

from tools.calendar_state import draft_path
from tools.draftplan import (
    FORMAT_MIX,
    FORMATS,
    _is_pure_rotation,
    plan_drafts,
    plan_pillars,
)

CALENDAR = """# Calendário de teste

| # | Date       | Pillar | Angle | Status  | Published | URL |
|---|------------|--------|-------|---------|-----------|-----|
{rows}
"""


def write_calendar(tmp_path: Path, slots: int) -> Path:
    rows = "\n".join(
        f"| {n} | 2026-09-{n:02d} | Pilar | Ângulo {n} | pending | | |"
        for n in range(1, slots + 1)
    )
    path = tmp_path / "2026-09-calendar.md"
    path.write_text(CALENDAR.format(rows=rows), encoding="utf-8")
    return path


class TestPillars:
    def test_no_pillar_twice_in_a_row(self):
        order = plan_pillars(["A", "B", "C"], 13, seed=7)
        assert len(order) == 13
        assert all(a != b for a, b in zip(order, order[1:]))

    def test_never_a_pure_rotation(self):
        for seed in range(20):
            assert not _is_pure_rotation(plan_pillars(["A", "B", "C"], 12, seed=seed))

    def test_same_seed_same_order(self):
        assert plan_pillars(["A", "B"], 8, seed=3) == plan_pillars(["A", "B"], 8, seed=3)


class TestPlanDrafts:
    def test_same_seed_is_reproducible(self, tmp_path):
        calendar = write_calendar(tmp_path, 13)
        assert plan_drafts(calendar, seed=202609) == plan_drafts(calendar, seed=202609)

    def test_neighbors_never_share_formato_or_abertura(self, tmp_path):
        calendar = write_calendar(tmp_path, 28)
        rows = plan_drafts(calendar, seed=202609)["slots"]
        for a, b in zip(rows, rows[1:]):
            assert a["formato"] != b["formato"]
            assert a["abertura"] != b["abertura"]

    def test_endings_never_run_three_deep(self, tmp_path):
        calendar = write_calendar(tmp_path, 28)
        rows = plan_drafts(calendar, seed=202609)["slots"]
        for a, b, c in zip(rows, rows[1:], rows[2:]):
            assert not (a["fechamento"] == b["fechamento"] == c["fechamento"])

    def test_visuals_cover_half_the_slots(self, tmp_path):
        calendar = write_calendar(tmp_path, 28)
        rows = plan_drafts(calendar, seed=202609)["slots"]
        assert sum(row["visual"] for row in rows) == 14

    def test_short_slots_never_get_a_visual(self, tmp_path):
        calendar = write_calendar(tmp_path, 28)
        rows = plan_drafts(calendar, seed=202609)["slots"]
        for row in rows:
            if row["visual"]:
                assert row["formato"] != "curto"

    def test_existing_card_keeps_its_slot_visual(self, tmp_path):
        calendar = write_calendar(tmp_path, 28)
        rows = plan_drafts(calendar, seed=202609)["slots"]
        curto = next(row["slot"] for row in rows if row["formato"] == "curto")
        card = draft_path(calendar, curto).with_suffix(".svg")
        card.parent.mkdir(parents=True, exist_ok=True)
        card.write_text("<svg/>", encoding="utf-8")
        rows = plan_drafts(calendar, seed=202609)["slots"]
        assert next(row for row in rows if row["slot"] == curto)["visual"]

    def test_publish_times_stay_in_the_window(self, tmp_path):
        calendar = write_calendar(tmp_path, 13)
        for row in plan_drafts(calendar, seed=1)["slots"]:
            hours, minutes = map(int, row["hora"].split(":"))
            assert 8 * 60 + 30 <= hours * 60 + minutes <= 11 * 60
            assert minutes % 5 == 0

    def test_format_bands_agree_with_the_quota_keys(self):
        assert set(FORMAT_MIX) == set(FORMATS)

    def test_empty_calendar_refuses(self, tmp_path):
        path = tmp_path / "2026-09-calendar.md"
        path.write_text("# vazio\n", encoding="utf-8")
        with pytest.raises(SystemExit):
            plan_drafts(path, seed=1)

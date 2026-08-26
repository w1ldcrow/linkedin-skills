"""Seeded lottery for calendar and draft variety.

A model asked to "vary" converges on its own favorite alternation, which is
itself a pattern. This tool rolls the dice instead — deterministically, from a
seed derived from the calendar month — and the drafting step obeys the roll.
Randomness comes from here; taste stays with the model and context/voice.md.

CLI:
    python3 tools/draftplan.py pillars --pillars "A;B;C" --slots 13 [--seed N]
        Non-cyclic pillar order for a new calendar (step 3). No pillar twice
        in a row, and never a fixed rotation.

    python3 tools/draftplan.py drafts CALENDAR.md [--seed N] [--force]
        Per-slot assignments for drafting (step 5): formato (curto/medio/
        longo), abertura, fechamento, publish time, and which slots get a
        visual. Written to <YYYY-MM>-plan.json beside the calendar. Slots
        whose draft file already exists are measured, not assigned.

The default seed is the calendar month as YYYYMM, so a month's plan is
reproducible with no state beyond the calendar itself.
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from batchcheck import classify_ending, classify_opening
    from calendar_state import draft_path, parse_calendar
else:
    from tools.batchcheck import classify_ending, classify_opening
    from tools.calendar_state import draft_path, parse_calendar

# Formats and their character bands — must agree with context/voice.md.
FORMATS = {"curto": (300, 700), "medio": (800, 1400), "longo": (1500, 2900)}

# Share of a month per format / opening / ending. Fractions are rounded down;
# the remainder goes to the middle value of each dimension.
FORMAT_MIX = {"curto": 0.25, "medio": 0.50, "longo": 0.25}
OPENING_MIX = {"afirmacao": 0.30, "voce": 0.20, "eu": 0.20, "numero": 0.15, "pergunta": 0.15}
ENDING_MIX = {"curta": 0.50, "media": 0.35, "longa": 0.15}

# Publish window: minutes after midnight, 5-minute grain.
TIME_WINDOW = (8 * 60 + 30, 11 * 60)
TIME_GRAIN = 5

# Share of ALL slots that get a visual card, drawn from the medium and long
# slots (a short post never needs one). A card already rendered beside its
# draft keeps its slot visual regardless of the roll.
VISUAL_SHARE = 0.5

_ATTEMPTS = 20_000


def _quota(mix: dict[str, float], total: int, remainder_key: str) -> list[str]:
    counts = {key: int(share * total) for key, share in mix.items()}
    counts[remainder_key] += total - sum(counts.values())
    pool: list[str] = []
    for key, count in counts.items():
        pool.extend([key] * count)
    return pool


def _no_adjacent(sequence: list[str]) -> bool:
    return all(a != b for a, b in zip(sequence, sequence[1:]))


def _no_run(sequence: list[str], run: int) -> bool:
    streak = 1
    for a, b in zip(sequence, sequence[1:]):
        streak = streak + 1 if a == b else 1
        if streak >= run:
            return False
    return True


def _shuffled_until(rng: random.Random, pool: list[str], ok) -> list[str]:
    candidate = list(pool)
    for _ in range(_ATTEMPTS):
        rng.shuffle(candidate)
        if ok(candidate):
            return candidate
    raise SystemExit("could not satisfy variety constraints; loosen the mix or check the quotas")


def _arrange_no_adjacent(rng: random.Random, pool: list[str]) -> list[str]:
    """Random arrangement with no two equal neighbors.

    Pure rejection sampling dies when one value fills half the slots (the only
    survivors are near-perfect alternations), so this builds greedily: at each
    position it picks randomly among the values that still leave the rest
    arrangeable — a value is unsafe once another value would exceed half of
    what remains.
    """
    from collections import Counter

    for _ in range(100):
        counts = Counter(pool)
        out: list[str] = []
        prev: str | None = None
        while sum(counts.values()):
            remaining = sum(counts.values())
            safe: list[str] = []
            for value, count in counts.items():
                if count == 0 or value == prev:
                    continue
                rest = remaining - 1
                # feasibility after picking `value`: no leftover value may
                # exceed ceil(rest/2), and a value holding exactly that
                # ceiling on an odd rest must not be `value` itself (it would
                # need to open the tail, which `value` just blocked).
                leftover = {v: (c - 1 if v == value else c) for v, c in counts.items()}
                peak = max(leftover.values(), default=0)
                if peak > (rest + 1) // 2:
                    continue
                if rest % 2 == 1 and leftover.get(value, 0) == (rest + 1) // 2:
                    continue
                safe.append(value)
            if not safe:
                break
            choice = rng.choice(safe)
            counts[choice] -= 1
            out.append(choice)
            prev = choice
        if len(out) == len(pool):
            return out
    raise SystemExit("could not satisfy variety constraints; loosen the mix or check the quotas")


def _is_pure_rotation(sequence: list[str]) -> bool:
    """True when the sequence is one cycle repeated — a detectable template."""
    distinct = list(dict.fromkeys(sequence))
    if len(distinct) < 2:
        return True
    return all(value == distinct[i % len(distinct)] for i, value in enumerate(sequence))


def plan_pillars(pillars: list[str], slots: int, seed: int) -> list[str]:
    rng = random.Random(seed)
    base, extra = divmod(slots, len(pillars))
    pool: list[str] = []
    for i, pillar in enumerate(pillars):
        pool.extend([pillar] * (base + (1 if i < extra else 0)))
    if len(pillars) < 3:
        # With two pillars the only no-adjacent order IS the alternation;
        # the anti-rotation rule would make the problem unsatisfiable.
        return _shuffled_until(rng, pool, _no_adjacent)
    return _shuffled_until(
        rng, pool, lambda seq: _no_adjacent(seq) and not _is_pure_rotation(seq)
    )


def _seed_from_calendar(path: Path) -> int:
    match = re.match(r"(\d{4})-(\d{2})-calendar\.md$", path.name)
    if not match:
        raise SystemExit(f"cannot derive a seed from {path.name!r}; pass --seed")
    return int(match.group(1) + match.group(2))


def _measure(text: str) -> dict:
    size = len(text.strip())
    if size <= FORMATS["curto"][1]:
        formato = "curto"
    elif size <= FORMATS["medio"][1]:
        formato = "medio"
    else:
        formato = "longo"
    return {
        "formato": formato,
        "abertura": classify_opening(text),
        "fechamento": classify_ending(text),
    }


def plan_drafts(calendar_path: Path, seed: int) -> dict:
    slots = parse_calendar(calendar_path.read_text(encoding="utf-8"))
    if not slots:
        raise SystemExit(f"no slots in {calendar_path}")
    rng = random.Random(seed)
    n = len(slots)

    # Remainder goes to "curto": handing it to "medio" can push the majority
    # format past half the slots, which makes no-adjacent-repeat unsatisfiable.
    formatos = _arrange_no_adjacent(rng, _quota(FORMAT_MIX, n, "curto"))
    aberturas = _arrange_no_adjacent(rng, _quota(OPENING_MIX, n, "afirmacao"))
    fechamentos = _shuffled_until(rng, _quota(ENDING_MIX, n, "media"), lambda s: _no_run(s, 3))

    rows: list[dict] = []
    for i, slot in enumerate(slots):
        path = draft_path(calendar_path, slot.number)
        minutes = rng.randrange(TIME_WINDOW[0], TIME_WINDOW[1] + 1, TIME_GRAIN)
        row = {
            "slot": slot.number,
            "data": slot.date.isoformat(),
            "hora": f"{minutes // 60:02d}:{minutes % 60:02d}",
            "visual": False,
        }
        if path.is_file():
            row.update(_measure(path.read_text(encoding="utf-8")))
            row["observado"] = True
        else:
            row.update(
                formato=formatos[i], abertura=aberturas[i], fechamento=fechamentos[i],
                observado=False,
            )
        low, high = FORMATS[row["formato"]]
        row["alvo"] = f"{low}-{high}"
        rows.append(row)

    # Cards are observed like drafts: one already rendered beside its draft
    # stays, no matter what this roll says.
    carded = {
        row["slot"]
        for row in rows
        if any(
            draft_path(calendar_path, row["slot"]).with_suffix(ext).is_file()
            for ext in (".svg", ".png")
        )
    }
    eligible = [
        row["slot"]
        for row in rows
        if row["formato"] != "curto" and row["slot"] not in carded
    ]
    target = max(1, round(n * VISUAL_SHARE))
    extra = min(len(eligible), max(0, target - len(carded)))
    chosen = carded | set(rng.sample(eligible, extra))
    for row in rows:
        row["visual"] = row["slot"] in chosen

    return {"seed": seed, "calendar": calendar_path.name, "slots": rows}


def _plan_path(calendar_path: Path) -> Path:
    stem = calendar_path.name.removesuffix("-calendar.md")
    return calendar_path.parent / f"{stem}-plan.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="draftplan", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_pillars = sub.add_parser("pillars", help="non-cyclic pillar order for a new calendar")
    p_pillars.add_argument("--pillars", required=True, help="semicolon-separated pillar names")
    p_pillars.add_argument("--slots", type=int, required=True)
    p_pillars.add_argument("--seed", type=int, required=True,
                           help="use the new calendar's month as YYYYMM")

    p_drafts = sub.add_parser("drafts", help="per-slot variety plan for drafting")
    p_drafts.add_argument("calendar", type=Path)
    p_drafts.add_argument("--seed", type=int, default=None,
                          help="defaults to the calendar month as YYYYMM")
    p_drafts.add_argument("--force", action="store_true", help="overwrite an existing plan")

    args = parser.parse_args(argv)

    if args.command == "pillars":
        pillars = [p.strip() for p in args.pillars.split(";") if p.strip()]
        if len(pillars) < 2:
            raise SystemExit("need at least two pillars")
        for i, pillar in enumerate(plan_pillars(pillars, args.slots, args.seed), start=1):
            print(f"{i:2d} {pillar}")
        return 0

    seed = args.seed if args.seed is not None else _seed_from_calendar(args.calendar)
    out = _plan_path(args.calendar)
    if out.exists() and not args.force:
        raise SystemExit(f"{out} already exists; rerun with --force to replace it")
    plan = plan_drafts(args.calendar, seed)
    out.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"seed {plan['seed']} -> {out}")
    print(f"{'slot':>4} {'data':<10} {'formato':<7} {'alvo':<9} {'abertura':<9} {'fecho':<6} {'hora':<5} visual")
    for row in plan["slots"]:
        marker = "sim" if row["visual"] else ""
        origin = "*" if row["observado"] else " "
        print(
            f"{row['slot']:>4} {row['data']:<10} {row['formato']:<7} {row['alvo']:<9} "
            f"{row['abertura']:<9} {row['fechamento']:<6} {row['hora']:<5} {marker}{origin}"
        )
    print("(* = medido de um draft existente; sorteio cobre só horário e visual)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Cross-draft sloppiness rules for a month of posts.

voicecheck.py judges one text in isolation. This linter judges the batch: posts
that land in the feed a day apart and open the same way, share phrasing, or
repeat one structural skeleton read as a template being refilled — and a
template reads as AI. Only the mechanical comparisons live here; taste stays
with the model and context/voice.md.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Two drafts this close together (in batch positions, roughly days) must not
# open with the same words. Further apart than this, a reader has forgotten.
OPENING_WINDOW = 7

# Word n-gram length considered "the same phrase" when shared by two drafts.
PHRASE_NGRAM = 5

# This many consecutive drafts with the same paragraph count reads as a template.
UNIFORM_RUN = 3

# A month must mix short, medium and long posts. Across a batch of at least
# LENGTH_SPREAD_MIN_DRAFTS drafts, the longest must be at least
# LENGTH_SPREAD_RATIO times the shortest — otherwise every post is one size,
# which is the loudest template smell of all.
LENGTH_SPREAD_MIN_DRAFTS = 8
LENGTH_SPREAD_RATIO = 2.0

# This many consecutive drafts inside one narrow size band (longest at most
# LENGTH_RUN_BAND times the shortest) reads as a template even when paragraph
# counts differ.
LENGTH_RUN = 5
LENGTH_RUN_BAND = 1.4

# Shape statistics only mean something once the batch is feed-sized; below
# this many drafts the shape rules stay silent.
MIN_SHAPE_DRAFTS = 8

# Opening shapes a first sentence can take, by mechanical proxy.
OPENING_SHAPES = ("pergunta", "numero", "eu", "voce", "afirmacao")

# No single opening shape may exceed this share of the batch.
OPENING_DOMINANCE = 0.40

# Length bands (chars) for a draft's closing sentence: the aphorism tell.
ENDING_SHORT_MAX = 90
ENDING_MEDIUM_MAX = 180

# This many consecutive drafts closing in the same band reads as a template.
ENDING_RUN = 3

# No single ending band may exceed this share of the batch.
ENDING_DOMINANCE = 0.60

# A content trigram shared by this many drafts is a pet phrase: violation at
# PET_PHRASE_FAIL drafts, warning at PET_PHRASE_WARN.
PET_PHRASE_FAIL = 4
PET_PHRASE_WARN = 3

# Filler expressions that read as one author's tic when they spread; warned
# when found in at least this many drafts.
FILLER_PHRASES = ("de verdade", "na prática", "no fim das contas", "de fato")
FILLER_WARN = 4

# Warning thresholds per 1000 characters: em dashes and colons are the
# punctuation marks AI text leans on hardest.
DASH_DENSITY_WARN = 3.0
COLON_DENSITY_WARN = 6.0

# Three consecutive drafts whose mean sentence length sits within 10% of each
# other read as one temperature.
RHYTHM_RUN = 3
RHYTHM_BAND = 1.10

_STOPWORDS = frozenset(
    """a o os as um uma uns umas de do da dos das em no na nos nas por para pra
    com sem sob sobre e ou mas que se é são ser foi era ao aos à às não nao mais
    menos muito muita muitos muitas já ja só so como quando onde isso esse essa
    este esta isto aquele aquela aquilo ele ela eles elas você voce vocês eu nós
    seu sua seus suas meu minha te me lhe nem até ate entre depois antes também
    tambem tem têm vai vão pode podem cada todo toda todos todas outro outra
    outros outras num numa pelo pela pelos pelas então entao assim ainda aqui
    quem qual quais uma vez ali lá""".split()
)


@dataclass(frozen=True)
class Violation:
    rule: str
    detail: str
    excerpt: str


_WORD_PATTERN = re.compile(r"[\wÀ-ÿ]+")


def _words(text: str) -> list[str]:
    return [word.lower() for word in _WORD_PATTERN.findall(text)]


def _opening(text: str, count: int) -> tuple[str, ...]:
    for line in text.splitlines():
        words = _words(line)
        if words:
            return tuple(words[:count])
    return ()


def _paragraph_count(text: str) -> int:
    return len([block for block in re.split(r"\n\s*\n", text.strip()) if block.strip()])


def _ngrams(text: str, size: int) -> set[tuple[str, ...]]:
    words = _words(text)
    return {tuple(words[i : i + size]) for i in range(len(words) - size + 1)}


_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")

_FIRST_PERSON = re.compile(
    r"\b(eu|meu|minha|escrevo|uso|vejo|recebo|passei|aprendi|defendo|prefiro|"
    r"comecei|testei|migrei|coloquei|rodo|confiro|delego|recomendo|já vi|já usei)\b",
    re.IGNORECASE,
)

_DIRECT_ADDRESS = re.compile(r"\b(você|voce|vocês|seu|sua|seus|suas|te)\b", re.IGNORECASE)


def _sentences(text: str) -> list[str]:
    pieces: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if line:
            pieces.extend(part for part in _SENTENCE_SPLIT.split(line) if part)
    return pieces


def _first_sentence(text: str) -> str:
    for line in text.splitlines():
        line = line.strip()
        if line:
            return _SENTENCE_SPLIT.split(line)[0]
    return ""


def _last_sentence(text: str) -> str:
    sentences = _sentences(text)
    return sentences[-1] if sentences else ""


def classify_opening(text: str) -> str:
    """Mechanical proxy for the shape of a draft's first sentence."""
    sentence = _first_sentence(text)
    if sentence.endswith("?"):
        return "pergunta"
    if re.search(r"\d", sentence):
        return "numero"
    if _FIRST_PERSON.search(sentence):
        return "eu"
    if _DIRECT_ADDRESS.search(sentence):
        return "voce"
    return "afirmacao"


def classify_ending(text: str) -> str:
    """Band of the closing sentence: curta is the aphorism default."""
    size = len(_last_sentence(text))
    if size <= ENDING_SHORT_MAX:
        return "curta"
    if size <= ENDING_MEDIUM_MAX:
        return "media"
    return "longa"


def _content_trigrams(text: str) -> set[tuple[str, ...]]:
    """Trigrams carrying at least one content word — pet-phrase candidates."""
    return {
        gram
        for gram in _ngrams(text, 3)
        if any(word not in _STOPWORDS for word in gram)
    }


def _shared_trigrams(drafts: list[tuple[int, str]], minimum: int) -> list[tuple[tuple[str, ...], list[int]]]:
    """Content trigrams present in at least `minimum` drafts, with their slots."""
    owners: dict[tuple[str, ...], list[int]] = {}
    for number, text in drafts:
        for gram in _content_trigrams(text):
            owners.setdefault(gram, []).append(number)
    return sorted(
        (gram, slots) for gram, slots in owners.items() if len(slots) >= minimum
    )


def check_batch(drafts: list[tuple[int, str]]) -> list[Violation]:
    """Compare drafts against each other. `drafts` is (slot number, text) in slot order."""
    violations: list[Violation] = []
    if len(drafts) < 2:
        return violations

    openings = [(number, _opening(text, 2)) for number, text in drafts]
    for i, (number_a, opening_a) in enumerate(openings):
        for number_b, opening_b in openings[i + 1 : i + 1 + OPENING_WINDOW]:
            if opening_a and opening_a == opening_b:
                violations.append(
                    Violation(
                        rule="duplicate_opening",
                        detail=f"slots {number_a} and {number_b} open with the same words",
                        excerpt=" ".join(opening_a),
                    )
                )

    for (number_a, text_a), (number_b, text_b) in zip(drafts, drafts[1:]):
        first_a, first_b = _opening(text_a, 1), _opening(text_b, 1)
        if first_a and first_a == first_b and _opening(text_a, 2) != _opening(text_b, 2):
            violations.append(
                Violation(
                    rule="consecutive_opening",
                    detail=f"slots {number_a} and {number_b} start with the same first word",
                    excerpt=first_a[0],
                )
            )

    grams = [(number, _ngrams(text, PHRASE_NGRAM)) for number, text in drafts]
    for i, (number_a, grams_a) in enumerate(grams):
        for number_b, grams_b in grams[i + 1 :]:
            shared = grams_a & grams_b
            if shared:
                example = " ".join(min(shared))
                violations.append(
                    Violation(
                        rule="repeated_phrase",
                        detail=f"slots {number_a} and {number_b} share {len(shared)} phrase(s)",
                        excerpt=example,
                    )
                )

    counts = [(number, _paragraph_count(text)) for number, text in drafts]
    run_start = 0
    for i in range(1, len(counts) + 1):
        if i < len(counts) and counts[i][1] == counts[run_start][1]:
            continue
        if i - run_start >= UNIFORM_RUN:
            first, last = counts[run_start][0], counts[i - 1][0]
            violations.append(
                Violation(
                    rule="uniform_structure",
                    detail=f"slots {first} through {last} all have {counts[run_start][1]} paragraphs",
                    excerpt=f"{i - run_start} drafts in a row",
                )
            )
        run_start = i

    lengths = [(number, len(text.strip())) for number, text in drafts]
    if len(lengths) >= LENGTH_SPREAD_MIN_DRAFTS:
        shortest = min(lengths, key=lambda pair: pair[1])
        longest = max(lengths, key=lambda pair: pair[1])
        if longest[1] < shortest[1] * LENGTH_SPREAD_RATIO:
            violations.append(
                Violation(
                    rule="uniform_length",
                    detail=(
                        f"the whole batch sits in one size band: shortest is slot "
                        f"{shortest[0]} ({shortest[1]} chars), longest is slot "
                        f"{longest[0]} ({longest[1]} chars)"
                    ),
                    excerpt=f"longest/shortest = {longest[1] / shortest[1]:.2f}, need >= {LENGTH_SPREAD_RATIO}",
                )
            )

    intervals: list[tuple[int, int]] = []
    for start in range(len(lengths) - LENGTH_RUN + 1):
        window = [size for _, size in lengths[start : start + LENGTH_RUN]]
        if max(window) > min(window) * LENGTH_RUN_BAND:
            continue
        end = start + LENGTH_RUN - 1
        if intervals and start <= intervals[-1][1]:
            intervals[-1] = (intervals[-1][0], end)
        else:
            intervals.append((start, end))
    for start, end in intervals:
        first, last = lengths[start][0], lengths[end][0]
        violations.append(
            Violation(
                rule="length_run",
                detail=f"slots {first} through {last} are all nearly the same size",
                excerpt=f"{end - start + 1} drafts in a row within {LENGTH_RUN_BAND}x of each other",
            )
        )

    if len(drafts) >= MIN_SHAPE_DRAFTS:
        openings_shapes = [(number, classify_opening(text)) for number, text in drafts]
        for (number_a, shape_a), (number_b, shape_b) in zip(openings_shapes, openings_shapes[1:]):
            if shape_a == shape_b:
                violations.append(
                    Violation(
                        rule="opening_shape_run",
                        detail=f"slots {number_a} and {number_b} open with the same shape",
                        excerpt=shape_a,
                    )
                )
        for shape in OPENING_SHAPES:
            count = sum(1 for _, s in openings_shapes if s == shape)
            if count > OPENING_DOMINANCE * len(drafts):
                violations.append(
                    Violation(
                        rule="opening_shape_mix",
                        detail=f"{count} of {len(drafts)} drafts open as {shape!r}",
                        excerpt=f"cap is {OPENING_DOMINANCE:.0%} of the batch",
                    )
                )

        endings = [(number, classify_ending(text)) for number, text in drafts]
        run_start = 0
        for i in range(1, len(endings) + 1):
            if i < len(endings) and endings[i][1] == endings[run_start][1]:
                continue
            if i - run_start >= ENDING_RUN:
                first, last = endings[run_start][0], endings[i - 1][0]
                violations.append(
                    Violation(
                        rule="ending_shape_run",
                        detail=f"slots {first} through {last} all close with a {endings[run_start][1]} sentence",
                        excerpt=f"{i - run_start} drafts in a row",
                    )
                )
            run_start = i
        for band in ("curta", "media", "longa"):
            count = sum(1 for _, b in endings if b == band)
            if count > ENDING_DOMINANCE * len(drafts):
                violations.append(
                    Violation(
                        rule="ending_shape_mix",
                        detail=f"{count} of {len(drafts)} drafts close with a {band} sentence",
                        excerpt=f"cap is {ENDING_DOMINANCE:.0%} of the batch",
                    )
                )

        for gram, slots in _shared_trigrams(drafts, PET_PHRASE_FAIL):
            violations.append(
                Violation(
                    rule="pet_phrase",
                    detail=f"slots {', '.join(map(str, slots))} all lean on the same phrase",
                    excerpt=" ".join(gram),
                )
            )

    return violations


def check_batch_warnings(drafts: list[tuple[int, str]]) -> list[Violation]:
    """Softer smells: printed, never fatal. Taste calls these, not the exit code."""
    warnings: list[Violation] = []
    if len(drafts) < MIN_SHAPE_DRAFTS:
        return warnings

    for gram, slots in _shared_trigrams(drafts, PET_PHRASE_WARN):
        if len(slots) < PET_PHRASE_FAIL:
            warnings.append(
                Violation(
                    rule="pet_phrase_forming",
                    detail=f"slots {', '.join(map(str, slots))} share a phrase; one more and it fails",
                    excerpt=" ".join(gram),
                )
            )

    for phrase in FILLER_PHRASES:
        slots = [number for number, text in drafts if phrase in text.lower()]
        if len(slots) >= FILLER_WARN:
            warnings.append(
                Violation(
                    rule="filler_spread",
                    detail=f"filler {phrase!r} appears in slots {', '.join(map(str, slots))}",
                    excerpt=f"{len(slots)} drafts",
                )
            )

    for number, text in drafts:
        size = max(len(text), 1)
        dashes = 1000 * text.count("—") / size
        colons = 1000 * text.count(":") / size
        if dashes > DASH_DENSITY_WARN:
            warnings.append(
                Violation(
                    rule="dash_density",
                    detail=f"slot {number} uses {dashes:.1f} em dashes per 1000 chars",
                    excerpt=f"threshold {DASH_DENSITY_WARN}",
                )
            )
        if colons > COLON_DENSITY_WARN:
            warnings.append(
                Violation(
                    rule="colon_density",
                    detail=f"slot {number} uses {colons:.1f} colons per 1000 chars",
                    excerpt=f"threshold {COLON_DENSITY_WARN}",
                )
            )

    means: list[tuple[int, float]] = []
    for number, text in drafts:
        sentences = _sentences(text)
        if sentences:
            means.append((number, sum(len(_words(s)) for s in sentences) / len(sentences)))
    for start in range(len(means) - RHYTHM_RUN + 1):
        window = [mean for _, mean in means[start : start + RHYTHM_RUN]]
        if min(window) > 0 and max(window) <= min(window) * RHYTHM_BAND:
            warnings.append(
                Violation(
                    rule="flat_rhythm",
                    detail=(
                        f"slots {means[start][0]} through {means[start + RHYTHM_RUN - 1][0]} "
                        f"share one sentence rhythm (~{window[0]:.0f} words/sentence)"
                    ),
                    excerpt=f"{RHYTHM_RUN} drafts within {RHYTHM_BAND}x",
                )
            )

    return warnings


def main(argv: list[str] | None = None) -> int:
    import argparse
    import sys
    from pathlib import Path

    parser = argparse.ArgumentParser(
        prog="batchcheck",
        description="Compare a month of post drafts against each other for template smells.",
    )
    parser.add_argument("directory", help="posts directory holding one NN.txt per slot")
    args = parser.parse_args(argv)

    directory = Path(args.directory)
    if not directory.is_dir():
        print(f"batchcheck: directory not found: {directory}", file=sys.stderr)
        return 2

    drafts: list[tuple[int, str]] = []
    for path in directory.glob("*.txt"):
        if not path.stem.isdigit():
            print(f"batchcheck: draft files must be named NN.txt, got: {path.name}", file=sys.stderr)
            return 2
        drafts.append((int(path.stem), path.read_text(encoding="utf-8")))
    drafts.sort(key=lambda pair: pair[0])

    if len(drafts) < 2:
        print(f"OK: {len(drafts)} draft(s) in {directory}, nothing to compare")
        return 0

    violations = check_batch(drafts)
    warnings = check_batch_warnings(drafts)
    for warning in warnings:
        print(f"warn {warning.rule}: {warning.detail} -> {warning.excerpt!r}")

    if not violations:
        suffix = f" ({len(warnings)} warning(s) above are taste calls)" if warnings else ""
        print(f"OK: {len(drafts)} drafts in {directory} pass all batch rules{suffix}")
        return 0

    for violation in violations:
        print(f"{violation.rule}: {violation.detail} -> {violation.excerpt!r}")
    print(f"\n{len(violations)} violation(s). Rewrite the flagged drafts; do not ship with a warning.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

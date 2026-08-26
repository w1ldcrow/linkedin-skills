"""Deterministic voice rules for generated LinkedIn text.

The rules a regex can decide live here. The rules that need judgment live in
context/voice.md (the owner's own contract, built from context/voice.template.md)
and are applied by the model after this linter passes.

Banned-phrase lists exist for pt-BR and en. Every other rule — emoji, length,
hashtags, statement ending, concrete specific — is language-agnostic.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Violation:
    rule: str
    detail: str
    excerpt: str


_EMOJI_PATTERN = re.compile(
    "["
    "\U0001f300-\U0001faff"  # pictographs, transport, supplemental symbols
    "\U00002600-\U000027bf"  # misc symbols and dingbats
    "\U0001f1e6-\U0001f1ff"  # regional indicators (flags)
    "\U00002b00-\U00002bff"  # misc symbols and arrows
    "\U0000fe0f"  # emoji variation selector
    "]"
)

# (pattern, detail). Patterns are matched case-insensitively against raw text.
_BANNED: list[tuple[str, str]] = [
    (r"comenta\s+a[íi]", "engagement bait"),
    (r"concorda\s*\?", "engagement bait"),
    (r"e\s+voc[êe],?\s+o\s+que\s+acha", "engagement bait"),
    (r"\bbora\s*\?", "engagement bait"),
    (r"n[ãa]o\s+[ée]\s+sobre\s+.{1,60}?[.!]\s*[ée]\s+sobre", "antithesis construction"),
    (r"\bspoiler\s*:", "clickbait marker"),
    (r"\bplot\s+twist\b", "clickbait marker"),
    (r"\ba\s+real\s+[ée]\s+que\b", "clickbait marker"),
    (r"\bdeixa\s+eu\s+te\s+contar\b", "clickbait marker"),
    (r"\brevolucion[áa]ri[oa]\b", "unearned superlative"),
    (r"\bgame\s*.?changer\b", "unearned superlative"),
    (r"\bincr[íi]vel\b", "unearned superlative"),
    (r"\babsurd[oa]\b", "unearned superlative"),
    (r"\bhumildemente\b", "false humility"),
    (r"\borgulhos[oa]\s+em\s+(compartilhar|anunciar)\b", "announcement cliche"),
    (r"\bfeliz\s+em\s+anunciar\b", "announcement cliche"),
    (r"\berrei\s+muito\s+at[ée]\b", "manufactured vulnerability"),
    (r"\b\d+\s+li[çc][õo]es\s+que\s+aprendi\b", "listicle hook"),
    (r"\b\d+\s+coisas\s+que\s+ningu[ée]m\s+te\s+conta\b", "listicle hook"),
    (r"\bno\s+mundo\s+de\s+hoje\b", "LLM tell"),
    (r"\bcada\s+vez\s+mais\b", "LLM tell"),
    (r"\bvale\s+ressaltar\b", "LLM tell"),
    (r"\bem\s+um\s+cen[áa]rio\s+onde\b", "LLM tell"),
    (r"\b[óo]timo\s+post\b", "empty comment"),
    (r"\bexcelente\s+post\b", "empty comment"),
    (r"\bparab[ée]ns\s+pelo\s+post\b", "empty comment"),
    # English equivalents. The structural rules below are language-agnostic;
    # this list and the pt-BR one above are the only language-specific parts.
    (r"\bthoughts\s*\?", "engagement bait"),
    (r"\bagree\s*\?", "engagement bait"),
    (r"\bwhat\s+do\s+you\s+think\s*\?", "engagement bait"),
    (r"\blet\s+that\s+sink\s+in\b", "engagement bait"),
    (r"\bit['’]?s\s+not\s+about\s+.{1,60}?[.!]\s*it['’]?s\s+about\b", "antithesis construction"),
    (r"\bhot\s+take\s*:", "clickbait marker"),
    (r"\bunpopular\s+opinion\s*:", "clickbait marker"),
    (r"\bhere['’]?s\s+the\s+thing\b", "clickbait marker"),
    (r"\blet\s+me\s+tell\s+you\b", "clickbait marker"),
    (r"\brevolutionary\b", "unearned superlative"),
    (r"\bmind[\s-]?blowing\b", "unearned superlative"),
    (r"\bincredible\b", "unearned superlative"),
    (r"\binsane\b", "unearned superlative"),
    (r"\bi['’]?m\s+humbled\b", "false humility"),
    (r"\bhumbled\s+(to|and|by)\b", "false humility"),
    (r"\b(thrilled|excited|proud|happy)\s+to\s+(announce|share)\b", "announcement cliche"),
    (r"\bi\s+failed\s+(so\s+)?(many|countless)\s+times\s+(until|before)\b", "manufactured vulnerability"),
    (r"\b\d+\s+lessons\s+(i|we)\s+learned\b", "listicle hook"),
    (r"\b\d+\s+things\s+(nobody|no\s+one)\s+tells\s+you\b", "listicle hook"),
    (r"\bin\s+today['’]?s\s+(fast-paced\s+|digital\s+|ever-changing\s+)?world\b", "LLM tell"),
    (r"\bit['’]?s\s+worth\s+noting\b", "LLM tell"),
    (r"\bin\s+a\s+world\s+where\b", "LLM tell"),
    (r"\bdelve\s+into\b", "LLM tell"),
    (r"\bgreat\s+post\b", "empty comment"),
    (r"\bamazing\s+post\b", "empty comment"),
    (r"\b(congrats|congratulations)\s+on\s+the\s+post\b", "empty comment"),
]

_BANNED_COMPILED = [(re.compile(p, re.IGNORECASE), detail) for p, detail in _BANNED]


def find_emojis(text: str) -> list[Violation]:
    """Return one Violation per emoji codepoint found."""
    return [
        Violation(rule="emoji", detail="emojis are banned in all output", excerpt=match.group(0))
        for match in _EMOJI_PATTERN.finditer(text)
    ]


def find_banned_phrases(text: str) -> list[Violation]:
    """Return one Violation per banned phrase occurrence, in order of appearance."""
    found: list[tuple[int, Violation]] = []
    for pattern, detail in _BANNED_COMPILED:
        for match in pattern.finditer(text):
            found.append(
                (match.start(), Violation(rule="banned_phrase", detail=detail, excerpt=match.group(0)))
            )
    found.sort(key=lambda pair: pair[0])
    return [violation for _, violation in found]


# (min_chars, max_chars) per kind of generated string.
LIMITS: dict[str, tuple[int, int]] = {
    "post": (300, 2900),  # LinkedIn caps at 3000; length varies per post — batchcheck polices the mix
    "comment": (120, 600),
    "headline": (1, 220),  # LinkedIn headline cap
    "about": (1, 2600),  # LinkedIn About cap
    "note": (1, 200),  # always-safe connection note length
}

_HASHTAG_PATTERN = re.compile(r"#\w+", re.UNICODE)

# Kinds that must contain at least one concrete specific.
_NEEDS_CONCRETE = {"post", "comment"}

# Kinds that must not end on a question mark.
_NEEDS_STATEMENT_ENDING = {"post", "comment"}

_TECH_TERMS = {
    "python", "django", "fastapi", "flask", "celery", "rq", "postgres", "postgresql",
    "mysql", "redis", "sqlite", "docker", "kubernetes", "k8s", "terraform", "aws",
    "gcp", "azure", "linux", "nginx", "grpc", "graphql", "rest", "sql", "orm",
    "pytest", "mypy", "ruff", "poetry", "uv", "git", "github", "gitlab", "ci",
    "mcp", "llm", "openai", "anthropic", "claude", "typescript", "javascript",
    "node", "react", "next", "vue", "kafka", "rabbitmq", "airflow", "pandas",
    "numpy", "asyncio", "pydantic", "sqlalchemy", "alembic", "supabase", "vercel",
}


def _find_length(text: str, kind: str) -> list[Violation]:
    low, high = LIMITS[kind]
    size = len(text)
    if size < low:
        return [Violation("length", f"{kind} must be at least {low} characters", f"{size} chars")]
    if size > high:
        return [Violation("length", f"{kind} must be at most {high} characters", f"{size} chars")]
    return []


def _find_hashtag_problems(text: str) -> list[Violation]:
    tags = _HASHTAG_PATTERN.findall(text)
    violations: list[Violation] = []
    if len(tags) > 3:
        violations.append(Violation("hashtags", "at most 3 hashtags", " ".join(tags)))
    for tag in tags:
        if tag != tag.lower():
            violations.append(Violation("hashtags", "hashtags must be lowercase", tag))
    return violations


def _find_question_ending(text: str) -> list[Violation]:
    stripped = text.rstrip()
    if stripped.endswith("?"):
        return [
            Violation("ends_with_question", "must end on a statement, not a question", stripped[-60:])
        ]
    return []


def _find_missing_concrete(text: str) -> list[Violation]:
    if re.search(r"\d", text):
        return []
    words = set(re.findall(r"[\w+#.]+", text.lower()))
    if words & _TECH_TERMS:
        return []
    return [
        Violation(
            "no_concrete",
            "needs at least one concrete specific: a number, a version, or a named tool",
            text[:80],
        )
    ]


def check(text: str, kind: str = "post") -> list[Violation]:
    """Run every deterministic rule that applies to `kind`."""
    if kind not in LIMITS:
        raise ValueError(f"unknown kind: {kind!r}; expected one of {sorted(LIMITS)}")

    violations = find_emojis(text) + find_banned_phrases(text)
    violations += _find_length(text, kind)
    violations += _find_hashtag_problems(text)
    if kind in _NEEDS_STATEMENT_ENDING:
        violations += _find_question_ending(text)
    if kind in _NEEDS_CONCRETE:
        violations += _find_missing_concrete(text)
    return violations


def main(argv: list[str] | None = None) -> int:
    import argparse
    import sys
    from pathlib import Path

    parser = argparse.ArgumentParser(
        prog="voicecheck",
        description="Lint generated LinkedIn text against the linkedin-skills voice contract.",
    )
    parser.add_argument("path", help="file containing the text to check")
    parser.add_argument("--kind", default="post", choices=sorted(LIMITS), help="kind of string")
    args = parser.parse_args(argv)

    source = Path(args.path)
    if not source.is_file():
        print(f"voicecheck: file not found: {source}", file=sys.stderr)
        return 2

    violations = check(source.read_text(encoding="utf-8"), kind=args.kind)
    if not violations:
        print(f"OK: {source} passes all {args.kind} rules")
        return 0

    for violation in violations:
        print(f"{violation.rule}: {violation.detail} -> {violation.excerpt!r}")
    print(f"\n{len(violations)} violation(s). Rewrite; do not ship with a warning.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

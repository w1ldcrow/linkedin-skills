"""Tailor a résumé to a job posting without inventing anything, then render it.

A résumé is a JSON (see `context/resume.template.json`). A tailored version keeps
the same JSON shape plus `target` and `changes`, and may only rephrase, reorder
and re-emphasize what the source already says.

    check   a tailored JSON against its source — exits 1 on any invented fact
            (--translation: a translated base against the original — same facts, new words)
    render  a résumé JSON to PDF (headless Chromium-family browser)
    index   a folder of tailored JSONs to an index.md

What `check` refuses, because each one is a lie on a résumé:
  - a different name, contact, link, education, employer, job title, place or period
  - an experience added, removed or reordered, or a bullet count that changed
  - a number that is not in the source
  - a technology, tool or practice that is not in the source
  - a seniority word ("sênior", "lead", ...) that is not in the source
  - a skills label that is not in the source
It warns when a bullet no longer resembles any source bullet, or when the text
grew or shrank enough to change the page count.

Stdlib only.
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata
from pathlib import Path

KNOWN_TECH = [
    "python", "golang", "java", "kotlin", "rust", "ruby", "php", "scala", "elixir", "c#", "c++", ".net",
    "typescript", "javascript", "node", "node.js", "deno", "bun",
    "django", "flask", "fastapi", "pydantic", "sqlalchemy", "alembic", "celery", "spring", "rails", "laravel",
    "express", "nestjs", "react", "angular", "vue", "next.js", "graphql", "grpc", "websockets", "rest",
    "docker", "kubernetes", "k8s", "helm", "terraform", "pulumi", "ansible", "argocd", "jenkins",
    "github actions", "gitlab", "circleci", "aws", "lambda", "ec2", "s3", "sqs", "sns", "ecs", "eks",
    "gcp", "google cloud", "azure", "cloudflare", "vercel", "linux", "nginx",
    "postgres", "postgresql", "mysql", "mariadb", "mongodb", "redis", "dynamodb", "cassandra",
    "elasticsearch", "opensearch", "bigquery", "snowflake", "redshift", "clickhouse", "sqlite",
    "kafka", "rabbitmq", "nats", "pubsub", "airflow", "spark", "dbt", "pandas", "numpy",
    "pytest", "unittest", "selenium", "playwright", "puppeteer", "pyppeteer", "scrapy", "httpx",
    "prometheus", "grafana", "datadog", "honeycomb", "sentry", "opentelemetry", "new relic", "elk",
    "power bi", "looker", "tableau", "metabase",
    "solidity", "solana", "evm", "web3", "ethereum",
    "llm", "openai", "langchain", "rag",
    "microsservicos", "microservices", "mensageria", "messaging", "event-driven", "orientada a eventos",
    "ddd", "tdd", "bdd", "clean architecture", "arquitetura limpa", "solid", "design patterns",
    "serverless", "multi-tenant", "saas", "b2b", "b2c", "scrum", "kanban",
]
SENIORITY = [
    "senior", "sr", "pleno", "junior", "jr", "lead", "lider", "tech lead", "staff",
    "especialista", "specialist", "arquiteto", "architect", "gerente", "manager", "coordenador",
]
_TECH_SHAPED = re.compile(r"[A-Za-z][A-Za-z0-9.+#/-]*[A-Za-z0-9+#]|[A-Za-z]")
_NUMBER = re.compile(r"\d+(?:[.,]\d+)?")
_COUNTED = re.compile(r"(\d+(?:[.,]\d+)?)[+%º°]?\s+([a-z]+)")
_YEAR = re.compile(r"(?:19|20)\d\d")
_WORD = re.compile(r"[a-z0-9]{4,}")
SECTION_LABELS = {"summary": "Resumo", "skills": "Competências", "experience": "Experiência", "education": "Formação"}
BROWSERS = [
    "chrome-headless-shell", "chromium", "chromium-browser", "google-chrome-stable", "google-chrome",
    "brave", "brave-browser", "microsoft-edge",
]
HEADLESS_CACHES = [
    "~/.cache/puppeteer/chrome-headless-shell/*/chrome-headless-shell-*/chrome-headless-shell",
    "~/.cache/ms-playwright/chromium_headless_shell-*/chrome-headless-shell-*/chrome-headless-shell",
]


def fold(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.lower())
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def _has(corpus: str, term: str) -> bool:
    return re.search(r"(?<![\w.#+])" + re.escape(term) + r"s?(?![\w#+])", corpus) is not None


def free_text(resume: dict) -> list[str]:
    """Everything a tailored version is allowed to rephrase."""
    parts = [resume.get("headline", ""), resume.get("summary", "")]
    parts += [f"{group['label']}: {group['items']}" for group in resume.get("skills", [])]
    for job in resume.get("experience", []):
        parts.append(job.get("context", ""))
        parts.extend(job.get("bullets", []))
    return [part for part in parts if part]


def _corpus(resume: dict) -> str:
    fixed = [resume.get("name", ""), *resume.get("contact", []), *resume.get("links", [])]
    for job in resume.get("experience", []):
        fixed += [job.get("title", ""), job.get("company", ""), job.get("place", ""), job.get("period", "")]
    for school in resume.get("education", []):
        fixed += [school.get("title", ""), school.get("school", ""), school.get("period", "")]
    return fold(" ".join(fixed + free_text(resume)))


def tech_terms(text: str) -> set[str]:
    """Tokens that name a technology: known names, CamelCase, ACRONYMS, dotted or versioned names."""
    folded = fold(text)
    found = {term for term in KNOWN_TECH if _has(folded, term)}
    for token in _TECH_SHAPED.findall(text):
        inner_upper = any(char.isupper() for char in token[1:])
        acronym = len(token) >= 2 and token.replace("/", "").isupper()
        dotted = any(mark in token[1:-1] for mark in ".#+") or token.endswith(("#", "++"))
        versioned = any(char.isdigit() for char in token) and any(char.isalpha() for char in token)
        if inner_upper or acronym or dotted or versioned:
            found.add(fold(token).rstrip("s"))
    return found


def counted_numbers(folded: str) -> set[tuple[str, str]]:
    """(number, the word it counts): "5 pessoas" may not become "5 anos". Years are exempt."""
    return {(number, unit) for number, unit in _COUNTED.findall(folded) if not _YEAR.fullmatch(number)}


def _identity(resume: dict) -> dict:
    return {
        "name": resume.get("name"),
        "contact": resume.get("contact"),
        "links": resume.get("links"),
        "education": resume.get("education"),
        "experience": [
            [job.get(key) for key in ("title", "company", "place", "period")] for job in resume.get("experience", [])
        ],
    }


def _overlap(a: str, b: str) -> float:
    left, right = set(_WORD.findall(fold(a))), set(_WORD.findall(fold(b)))
    return len(left & right) / len(left | right) if left | right else 1.0


def check(source: dict, tailored: dict) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    mine, theirs = _identity(source), _identity(tailored)
    for field in ("name", "contact", "links", "education"):
        if mine[field] != theirs[field]:
            errors.append(f"{field} differs from the source")
    if len(mine["experience"]) != len(theirs["experience"]):
        errors.append("experience entries were added or removed")
    else:
        for index, (was, now) in enumerate(zip(mine["experience"], theirs["experience"])):
            if was != now:
                errors.append(f"experience {index + 1}: title, company, place or period changed ({' | '.join(map(str, now))})")
        for index, (was, now) in enumerate(zip(source["experience"], tailored["experience"])):
            if len(was.get("bullets", [])) != len(now.get("bullets", [])):
                errors.append(f"experience {index + 1}: bullet count changed")
            for bullet in now.get("bullets", []):
                best = max((_overlap(bullet, original) for original in was.get("bullets", [])), default=0.0)
                if best < 0.25:
                    warnings.append(f"experience {index + 1}: bullet resembles no source bullet: {bullet[:70]}")

    corpus = _corpus(source)
    labels = {fold(group["label"]) for group in source.get("skills", [])}
    for group in tailored.get("skills", []):
        if fold(group["label"]) not in labels:
            errors.append(f"skills label not in the source: {group['label']}")

    errors += _fact_errors(source, tailored, counted=True)
    text = " ".join(free_text(tailored))
    before, after = len(" ".join(free_text(source))), len(text)
    if not 0.8 <= after / max(before, 1) <= 1.15:
        warnings.append(f"text length {after} vs source {before} — check the page count")
    return errors, warnings


def _fact_errors(source: dict, other: dict, counted: bool) -> list[str]:
    errors = []
    corpus = _corpus(source)
    text = " ".join(free_text(other))
    numbers = set(_NUMBER.findall(corpus))
    for number in sorted(set(_NUMBER.findall(text)) - numbers):
        errors.append(f"number not in the source: {number}")
    if counted:
        for number, unit in sorted(counted_numbers(fold(text)) - counted_numbers(corpus)):
            if number in numbers:
                errors.append(f"number used for something else than in the source: {number} {unit}")
    for term in sorted(tech_terms(text)):
        if not _has(corpus, term):
            errors.append(f"technology or practice not in the source: {term}")
    folded = fold(text)
    for word in SENIORITY:
        if _has(folded, word) and not _has(corpus, word):
            errors.append(f"seniority word not in the source: {word}")
    return errors


def check_translation(source: dict, translated: dict) -> tuple[list[str], list[str]]:
    """A translated base: words change, facts do not. Tailor from it with the strict check."""
    errors: list[str] = []
    for field in ("name", "contact", "links"):
        if source.get(field) != translated.get(field):
            errors.append(f"{field} differs from the source")
    jobs, translated_jobs = source.get("experience", []), translated.get("experience", [])
    if len(jobs) != len(translated_jobs):
        errors.append("experience entries were added or removed")
    for index, (was, now) in enumerate(zip(jobs, translated_jobs)):
        for key in ("company", "period"):
            if was.get(key) != now.get(key):
                errors.append(f"experience {index + 1}: {key} changed")
        if len(was.get("bullets", [])) != len(now.get("bullets", [])):
            errors.append(f"experience {index + 1}: bullet count changed")
    schools = [(item.get("school"), item.get("period")) for item in source.get("education", [])]
    if schools != [(item.get("school"), item.get("period")) for item in translated.get("education", [])]:
        errors.append("education schools or periods differ from the source")
    if len(source.get("skills", [])) != len(translated.get("skills", [])):
        errors.append("skills groups were added or removed")
    errors += _fact_errors(source, translated, counted=False)
    return errors, []


def _e(text: str) -> str:
    return html.escape(text, quote=False)


def _joined(parts: list[str]) -> str:
    return '<span class="sep">|</span>'.join(_e(part) for part in parts if part)


def render_html(resume: dict) -> str:
    labels = {**SECTION_LABELS, **resume.get("labels", {})}
    skills = "".join(
        f'<p class="skill"><b>{_e(group["label"])}:</b> {_e(group["items"])}</p>' for group in resume.get("skills", [])
    )
    jobs = []
    for job in resume.get("experience", []):
        context = f'<p class="context">{_e(job["context"])}</p>' if job.get("context") else ""
        bullets = "".join(f"<li>{_e(bullet)}</li>" for bullet in job.get("bullets", []))
        jobs.append(
            f'<div class="job"><p class="role"><b>{_e(job["title"])}</b><span class="sep">|</span>'
            f'<span class="org">{_e(job["company"])}</span></p>'
            f'<p class="meta">{_joined([job.get("place", ""), job.get("period", "")])}</p>'
            f"{context}<ul>{bullets}</ul></div>"
        )
    schools = "".join(
        f'<p class="school"><b>{_e(item["title"])}</b><span class="sep">|</span>{_joined([item.get("school", ""), item.get("period", "")])}</p>'
        for item in resume.get("education", [])
    )
    return f"""<!doctype html>
<html lang="{_e(resume.get("lang", "pt-BR"))}">
<head>
<meta charset="utf-8">
<title>{_e(resume["name"])}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:ital,wght@0,400;0,600;0,700;1,400&display=block" rel="stylesheet">
<style>
@page {{ size: A4; margin: 13mm 15mm 12mm; }}
:root {{ --ink: #1f2328; --muted: #6b7280; --accent: #2457a6; --rule: #d7dde6; }}
* {{ box-sizing: border-box; }}
body {{ margin: 0; font-family: Inter, "Helvetica Neue", Arial, sans-serif; font-size: 9.6pt; line-height: 1.42; color: var(--ink); }}
p {{ margin: 0; }}
h1 {{ font-size: 21pt; font-weight: 700; letter-spacing: -0.01em; margin: 0; line-height: 1.15; }}
.headline {{ color: var(--accent); font-weight: 600; font-size: 10.5pt; margin-top: 1px; }}
.contact {{ color: var(--muted); font-size: 8.4pt; margin-top: 5px; line-height: 1.5; }}
.contact .links {{ color: var(--accent); }}
.sep {{ color: #b8c0cc; margin: 0 4px; font-weight: 400; }}
h2 {{ color: var(--accent); font-size: 7.8pt; font-weight: 700; letter-spacing: 0.04em; text-transform: uppercase;
      margin: 14px 0 6px; padding-bottom: 3px; border-bottom: 1px solid var(--rule); }}
.skill {{ margin: 1.5px 0; }}
.job {{ margin-bottom: 7px; break-inside: avoid-page; }}
.role .org {{ color: var(--accent); font-weight: 600; }}
.meta {{ color: var(--muted); font-size: 8.4pt; }}
.context {{ font-style: italic; color: #3b4250; margin-top: 3px; }}
ul {{ margin: 3px 0 0; padding-left: 13px; }}
li {{ margin: 1px 0; padding-left: 1px; }}
li::marker {{ color: var(--accent); }}
.school {{ margin: 1.5px 0; }}
</style>
</head>
<body>
<h1>{_e(resume["name"])}</h1>
<p class="headline">{_e(resume.get("headline", ""))}</p>
<div class="contact">
  <p>{_joined(resume.get("contact", []))}</p>
  <p class="links">{_joined(resume.get("links", []))}</p>
</div>
<h2>{_e(labels["summary"])}</h2>
<p>{_e(resume.get("summary", ""))}</p>
<h2>{_e(labels["skills"])}</h2>
{skills}
<h2>{_e(labels["experience"])}</h2>
{"".join(jobs)}
<h2>{_e(labels["education"])}</h2>
{schools}
</body>
</html>
"""


def _version(path: Path) -> tuple[int, ...]:
    return tuple(int(part) for part in re.findall(r"\d+", str(path)))


def find_browser() -> str | None:
    """CHROME, then a cached headless shell (newest first), then a browser on PATH."""
    if os.environ.get("CHROME"):
        return os.environ["CHROME"]
    for pattern in HEADLESS_CACHES:
        home, _, rest = pattern.partition("/")
        found = sorted(Path(home).expanduser().glob(rest), key=_version, reverse=True)
        if found:
            return str(found[0])
    for name in BROWSERS:
        found = shutil.which(name)
        if found:
            return found
    return None


def render_pdf(resume: dict, out: Path, keep_html: bool = False) -> Path:
    browser = find_browser()
    if not browser:
        raise RuntimeError("no Chromium-family browser found; set CHROME=/path/to/browser")
    out.parent.mkdir(parents=True, exist_ok=True)
    page = out.with_suffix(".html")
    page.write_text(render_html(resume))
    with tempfile.TemporaryDirectory() as profile:
        subprocess.run(
            [
                browser, "--headless=new", "--no-sandbox", "--no-zygote", "--disable-gpu",
                "--disable-dev-shm-usage", "--no-first-run", f"--user-data-dir={profile}",
                "--no-pdf-header-footer", "--virtual-time-budget=10000",
                f"--print-to-pdf={out}", page.resolve().as_uri(),
            ],
            check=True, capture_output=True, timeout=120,
        )
    if not keep_html:
        page.unlink()
    return out


def build_index(folder: Path) -> str:
    rows = ["# Currículos adaptados", ""]
    for path in sorted(folder.glob("*.json")):
        resume = json.loads(path.read_text())
        target = resume.get("target", {})
        pdf = path.with_suffix(".pdf")
        rows.append(f"## {path.stem} — {target.get('title', '?')} · {target.get('company', '?')}")
        rows.append("")
        rows.append(f"- Vaga: {target.get('url', '—')}")
        rows.append(f"- PDF: `{pdf.name if pdf.exists() else 'não renderizado'}`")
        rows.extend(f"- {change}" for change in resume.get("changes", []))
        rows.append("")
    return "\n".join(rows)


def _check(args) -> int:
    source = json.loads(Path(args.source).read_text())
    verify = check_translation if args.translation else check
    failed = False
    for path in args.tailored:
        errors, warnings = verify(source, json.loads(Path(path).read_text()))
        status = "FAIL" if errors else "ok"
        print(f"{status}  {path}")
        for line in errors:
            print(f"  error: {line}")
        for line in warnings:
            print(f"  warn:  {line}")
        failed = failed or bool(errors)
    return 1 if failed else 0


def _render(args) -> int:
    for path in args.resume:
        source = Path(path)
        out = Path(args.out) if args.out and len(args.resume) == 1 else source.with_suffix(".pdf")
        print(render_pdf(json.loads(source.read_text()), out, args.html))
    return 0


def _index(args) -> int:
    folder = Path(args.folder)
    (folder / "index.md").write_text(build_index(folder))
    print(folder / "index.md")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)

    checker = sub.add_parser("check", help="refuse invented facts in tailored résumés")
    checker.add_argument("source")
    checker.add_argument("tailored", nargs="+")
    checker.add_argument("--translation", action="store_true", help="check a translated base against the original")
    checker.set_defaults(run=_check)

    renderer = sub.add_parser("render", help="résumé JSON to PDF")
    renderer.add_argument("resume", nargs="+")
    renderer.add_argument("-o", "--out")
    renderer.add_argument("--html", action="store_true", help="keep the intermediate HTML")
    renderer.set_defaults(run=_render)

    indexer = sub.add_parser("index", help="write index.md for a folder of tailored résumés")
    indexer.add_argument("folder")
    indexer.set_defaults(run=_index)

    args = parser.parse_args(argv)
    return args.run(args)


if __name__ == "__main__":
    sys.exit(main())

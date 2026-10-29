"""Scout public LinkedIn job postings and classify them against a job profile.

Reads only LinkedIn's guest job endpoints — the pages an anonymous visitor gets,
no login, no cookies — at a polite pace, and stops at the first sign of
throttling instead of pushing through it.

    fetch  run the profile's searches, read each surviving posting, write a raw JSON
    score  classify a raw JSON into high / medium / low / discard
    sheet  print the candidates for the model's review, descriptions included

high is profile match AND remote from where the candidate lives AND recently
posted. medium is a match plus one of the other two. Everything else is low,
unless a blocker — a role the profile avoids, a dealbreaker, on-site elsewhere,
remote restricted to another country — makes it a discard.

Stdlib only.
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from html.parser import HTMLParser
from pathlib import Path

SEARCH_URL = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
POSTING_URL = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{}"
VIEW_URL = "https://www.linkedin.com/jobs/view/{}/"
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/130.0 Safari/537.36"
)
PAGE_SIZE = 10
RETRY_STATUS = {429, 500, 502, 503, 504, 999}
END_STATUS = {400, 404, 410}
WORKPLACE_FILTER = {"onsite": "1", "remote": "2", "hybrid": "3"}
EXPERIENCE_FILTER = {
    "internship": "1",
    "entry": "2",
    "associate": "3",
    "mid-senior": "4",
    "director": "5",
    "executive": "6",
}
SEARCH_DEFAULTS = {
    "location": "Brazil",
    "workplace": ["remote"],
    "hours": 168,
    "experience": [],
    "max_pages": 3,
}
THRESHOLD_DEFAULTS = {"match": 0.6, "recent_hours": 72, "skill_saturation": 12}
CACHE_TTL = timedelta(days=60)
VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}
BLOCK_TAGS = {"p", "div", "br", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6", "section", "tr"}

PRIORITY_ORDER = {"high": 0, "medium": 1, "low": 2, "discard": 3}
LEVELS = ["intern", "junior", "mid", "senior", "lead", "director"]
TITLE_LEVELS = [
    ("intern", ["intern", "internship", "estagio", "estagiario", "estagiaria", "trainee"]),
    ("director", ["director", "diretor", "diretora", "vp", "head of", "chief", "cto"]),
    ("lead", ["staff", "principal", "lead", "tech lead", "lider", "architect", "arquiteto", "arquiteta"]),
    ("senior", ["senior", "sr", "iii", "especialista", "specialist"]),
    ("junior", ["junior", "jr", "entry level"]),
    ("mid", ["pleno", "plena", "mid", "mid-level", "ii"]),
]
CRITERIA_LEVELS = {
    "internship": {"intern"},
    "entry level": {"junior"},
    "associate": {"mid"},
    "mid-senior level": {"mid", "senior"},
    "director": {"director"},
    "executive": {"director"},
}
REMOTE_WORDS = ["remote", "remoto", "remota", "home office", "anywhere", "work from home"]
HYBRID_WORDS = ["hybrid", "hibrido", "hibrida"]
ONSITE_WORDS = ["on-site", "onsite", "on site", "presencial", "in-office"]
LANGUAGES = {
    "german": "german", "alemao": "german",
    "french": "french", "frances": "french",
    "spanish": "spanish", "espanhol": "spanish",
    "dutch": "dutch", "holandes": "dutch",
    "italian": "italian", "italiano": "italian",
    "japanese": "japanese", "japones": "japanese",
    "mandarin": "mandarin", "mandarim": "mandarin",
    "chinese": "chinese", "chines": "chinese",
    "korean": "korean", "coreano": "korean",
    "polish": "polish", "hebrew": "hebrew", "arabic": "arabic", "turkish": "turkish",
    "swedish": "swedish", "danish": "danish", "norwegian": "norwegian", "finnish": "finnish",
    "russian": "russian", "hindi": "hindi",
}
_FLUENCY = r"(?:fluent|fluency|native|proficient|proficiency|business[- ]level|fluente|fluencia|nativo|avancado)"
_LANGUAGE_NAMES = "|".join(LANGUAGES)
LANGUAGE_REQUIRED = [
    re.compile(_FLUENCY + r"\W+(?:in\W+|em\W+)?(" + _LANGUAGE_NAMES + r")\b"),
    re.compile(r"\b(" + _LANGUAGE_NAMES + r")\W+(?:\(\s*)?" + _FLUENCY),
]
_AGE = re.compile(r"(\d+)\s*(minute|min|hour|hora|day|dia|week|semana|month|mes|year|ano)")
UNIT_HOURS = {
    "minute": 1 / 60, "min": 1 / 60,
    "hour": 1, "hora": 1,
    "day": 24, "dia": 24,
    "week": 168, "semana": 168,
    "month": 720, "mes": 720,
    "year": 8760, "ano": 8760,
}


class FetchError(RuntimeError):
    """LinkedIn kept refusing (429/999/5xx or no network) after every retry."""


class _Node:
    __slots__ = ("tag", "attrs", "children")

    def __init__(self, tag: str, attrs: dict[str, str]):
        self.tag = tag
        self.attrs = attrs
        self.children: list[_Node | str] = []

    def walk(self):
        stack: list[_Node] = [self]
        while stack:
            node = stack.pop()
            yield node
            stack.extend(child for child in reversed(node.children) if isinstance(child, _Node))

    def find_all(self, cls: str | None = None, tag: str | None = None) -> list[_Node]:
        return [
            node
            for node in self.walk()
            if (tag is None or node.tag == tag)
            and (cls is None or cls in node.attrs.get("class", "").split())
        ]

    def find(self, cls: str | None = None, tag: str | None = None) -> _Node | None:
        found = self.find_all(cls, tag)
        return found[0] if found else None


class _TreeBuilder(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = _Node("#root", {})
        self.stack = [self.root]

    def handle_starttag(self, tag, attrs):
        node = _Node(tag, {key: value or "" for key, value in attrs})
        self.stack[-1].children.append(node)
        if tag not in VOID_TAGS:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.stack[-1].children.append(_Node(tag, {key: value or "" for key, value in attrs}))

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag:
                del self.stack[index:]
                return

    def handle_data(self, data):
        self.stack[-1].children.append(data)


def parse_html(html: str) -> _Node:
    builder = _TreeBuilder()
    builder.feed(html)
    builder.close()
    return builder.root


def _inline_text(node: _Node | None) -> str:
    if node is None:
        return ""
    parts: list[str] = []
    stack: list[_Node | str] = [node]
    while stack:
        item = stack.pop()
        if isinstance(item, str):
            parts.append(item)
        else:
            stack.extend(reversed(item.children))
    return " ".join("".join(parts).split())


def _block_text(node: _Node | None) -> str:
    """Plain text that keeps paragraphs and list items on their own lines."""
    if node is None:
        return ""
    parts: list[str] = []

    def visit(item: _Node | str):
        if isinstance(item, str):
            parts.append(item)
            return
        if item.tag == "li":
            parts.append("\n- ")
        elif item.tag in BLOCK_TAGS:
            parts.append("\n")
        for child in item.children:
            visit(child)
        if item.tag in BLOCK_TAGS or item.tag == "li":
            parts.append("\n")

    visit(node)
    lines = (" ".join(line.split()) for line in "".join(parts).splitlines())
    return "\n".join(line for line in lines if line and line != "-")


def fold(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.lower())
    return "".join(char for char in decomposed if not unicodedata.combining(char))


@lru_cache(maxsize=None)
def _pattern(term: str) -> re.Pattern[str]:
    return re.compile(r"(?<![\w.#+])" + re.escape(fold(term)) + r"(?![\w#+])")


def hits(folded: str, terms) -> list[str]:
    return [term for term in terms if _pattern(term).search(folded)]


def iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_iso(value: str) -> datetime:
    if len(value) == 10:
        return datetime.fromisoformat(value).replace(tzinfo=timezone.utc)
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def parse_age(text: str) -> float | None:
    folded = fold(text)
    match = _AGE.search(folded)
    if match:
        return int(match.group(1)) * UNIT_HOURS[match.group(2)]
    if "just now" in folded or "agora" in folded:
        return 0.0
    return None


def parse_search(html: str) -> list[dict]:
    cards = []
    for node in parse_html(html).find_all(cls="job-search-card"):
        urn = re.search(r"jobPosting:(\d+)", node.attrs.get("data-entity-urn", ""))
        link = node.find(cls="base-card__full-link")
        href = re.search(r"-(\d{6,})(?:[/?]|$)", link.attrs.get("href", "")) if link else None
        job_id = (urn or href).group(1) if (urn or href) else None
        if not job_id:
            continue
        company = node.find(cls="base-search-card__subtitle")
        company_link = company.find(tag="a") if company else None
        listed = node.find(tag="time")
        cards.append(
            {
                "id": job_id,
                "url": VIEW_URL.format(job_id),
                "title": _inline_text(node.find(cls="base-search-card__title")),
                "company": _inline_text(company),
                "company_url": company_link.attrs.get("href", "").split("?")[0] if company_link else "",
                "location": _inline_text(node.find(cls="job-search-card__location")),
                "listed": listed.attrs.get("datetime", "") if listed else "",
                "salary": _inline_text(node.find(cls="job-search-card__salary-info")),
            }
        )
    return cards


def parse_posting(html: str, now: datetime) -> dict:
    root = parse_html(html)
    criteria = {
        _inline_text(item.find(cls="description__job-criteria-subheader")): _inline_text(
            item.find(cls="description__job-criteria-text")
        )
        for item in root.find_all(cls="description__job-criteria-item")
    }
    posted = _inline_text(root.find(cls="posted-time-ago__text"))
    age = parse_age(posted)
    return {
        "posted_at": iso(now - timedelta(hours=age)) if age is not None else "",
        "reposted": "repost" in posted.lower(),
        "applicants": _inline_text(root.find(cls="num-applicants__caption")),
        "seniority": criteria.get("Seniority level", ""),
        "employment_type": criteria.get("Employment type", ""),
        "job_function": criteria.get("Job function", ""),
        "industries": criteria.get("Industries", ""),
        "salary": _inline_text(root.find(cls="compensation__salary")),
        "apply": "external" if "offsite-apply" in html else "linkedin",
        "description": _block_text(root.find(cls="show-more-less-html__markup")),
    }


class Client:
    """GETs at a jittered human pace; backs off on throttling, then gives up loudly."""

    def __init__(self, delay=1.5, retries=3, backoff=10.0, urlopen=urllib.request.urlopen, sleep=time.sleep):
        self.delay = delay
        self.retries = retries
        self.backoff = backoff
        self.urlopen = urlopen
        self.sleep = sleep
        self.requests = 0
        self._last = 0.0

    def _pace(self):
        gap = self.delay * random.uniform(0.7, 1.5)
        wait = self._last + gap - time.monotonic()
        if wait > 0:
            self.sleep(wait)
        self._last = time.monotonic()

    def get(self, url: str) -> str | None:
        for attempt in range(self.retries + 1):
            self._pace()
            self.requests += 1
            request = urllib.request.Request(
                url, headers={"User-Agent": USER_AGENT, "Accept-Language": "en-US,en;q=0.9"}
            )
            try:
                with self.urlopen(request, timeout=20) as response:
                    return response.read().decode("utf-8", "replace")
            except urllib.error.HTTPError as error:
                if error.code in END_STATUS:
                    return None
                if error.code not in RETRY_STATUS:
                    raise
                reason = f"HTTP {error.code}"
            except (urllib.error.URLError, TimeoutError) as error:
                reason = str(error)
            if attempt < self.retries:
                self.sleep(self.backoff * 3**attempt)
        raise FetchError(f"{reason} after {self.retries + 1} tries: {url}")


def search_url(spec: dict, start: int) -> str:
    params = {"keywords": spec["keywords"], "location": spec["location"], "sortBy": "DD", "start": start}
    if spec.get("workplace"):
        params["f_WT"] = ",".join(WORKPLACE_FILTER[kind] for kind in spec["workplace"])
    if spec.get("hours"):
        params["f_TPR"] = f"r{int(spec['hours'] * 3600)}"
    if spec.get("experience"):
        params["f_E"] = ",".join(EXPERIENCE_FILTER[level] for level in spec["experience"])
    return f"{SEARCH_URL}?{urllib.parse.urlencode(params)}"


def label(spec: dict) -> str:
    return f"{spec['keywords']} @ {spec['location']}"


def collect(client: Client, searches: list[dict], jobs: dict[str, dict], log=print) -> None:
    """Fill `jobs` in place, so whatever was read survives a FetchError midway."""
    for spec in searches:
        for page in range(spec["max_pages"]):
            html = client.get(search_url(spec, page * PAGE_SIZE))
            cards = parse_search(html) if html else []
            for card in cards:
                job = jobs.setdefault(card["id"], {**card, "found_by": [], "workplace_filter": []})
                if label(spec) not in job["found_by"]:
                    job["found_by"].append(label(spec))
                for kind in spec.get("workplace", []):
                    if kind not in job["workplace_filter"]:
                        job["workplace_filter"].append(kind)
            log(f"  {label(spec)} · page {page + 1}: {len(cards)}")
            if len(cards) < PAGE_SIZE:
                break


def read_details(client: Client, jobs: list[dict], cache: Path, limit: int, now: datetime, log=print) -> int:
    fetched = 0
    for job in sorted(jobs, key=lambda item: item.get("listed", ""), reverse=True):
        path = cache / f"{job['id']}.json"
        if path.exists():
            job["detail"] = json.loads(path.read_text())
            continue
        job["detail"] = None
        if fetched >= limit:
            continue
        html = client.get(POSTING_URL.format(job["id"]))
        fetched += 1
        if html is None:
            continue
        job["detail"] = parse_posting(html, now)
        path.write_text(json.dumps(job["detail"], ensure_ascii=False))
        if fetched % 10 == 0:
            log(f"  details: {fetched}")
    return fetched


def prune_cache(cache: Path, now: datetime) -> None:
    cutoff = (now - CACHE_TTL).timestamp()
    for path in cache.glob("*.json"):
        if path.stat().st_mtime < cutoff:
            path.unlink()


def load_profile(path: str) -> dict:
    profile = json.loads(Path(path).read_text())
    profile["thresholds"] = {**THRESHOLD_DEFAULTS, **profile.get("thresholds", {})}
    profile["search_defaults"] = {**SEARCH_DEFAULTS, **profile.get("search_defaults", {})}
    return profile


def title_blockers(title: str, profile: dict) -> list[str]:
    avoided = hits(fold(title), profile.get("titles", {}).get("avoid", []))
    return [f"título fora do alvo: {', '.join(avoided)}"] if avoided else []


def job_levels(title: str, seniority: str) -> set[str]:
    folded = fold(title)
    for level, words in TITLE_LEVELS:
        if hits(folded, words):
            return {level}
    return set(CRITERIA_LEVELS.get(fold(seniority), set()))


def level_fit(levels: set[str], accepted: set[str]) -> float:
    if not levels or not accepted:
        return 0.9
    if levels & accepted:
        return 1.0
    gap = min(abs(LEVELS.index(a) - LEVELS.index(b)) for a in levels for b in accepted)
    return 0.6 if gap == 1 else 0.2


def workplace_of(job: dict, body: str) -> str:
    """Title beats description beats LinkedIn's filter tag, which posters often get wrong."""
    head = fold(f"{job['title']} {job['location']}")
    if hits(head, HYBRID_WORDS):
        return "hybrid"
    if hits(head, ONSITE_WORDS):
        return "onsite"
    if hits(head, REMOTE_WORDS):
        return "remote"
    if not hits(body, REMOTE_WORDS):
        if hits(body, HYBRID_WORDS):
            return "hybrid"
        if hits(body, ONSITE_WORDS):
            return "onsite"
    filters = job.get("workplace_filter", [])
    if len(filters) == 1:
        return filters[0]
    return "remote" if hits(body, REMOTE_WORDS) else "unknown"


def scope_of(location: str, body: str, remote: dict) -> tuple[str, list[str]]:
    """Where a remote hire may live: home, region, abroad, restricted or unknown."""
    restricted = hits(body, remote.get("restricted_phrases", []))
    opened = hits(body, remote.get("open_phrases", []))
    if restricted and not opened:
        return "restricted", restricted
    parts = [part.strip() for part in fold(location).split(",")]
    where = parts[-1]
    if hits(where, remote.get("home", [])):
        return "home", []
    if hits(where, remote.get("regions", [])):
        return "region", []
    if not where:
        return "unknown", []
    return ("region" if opened else "abroad"), []


def required_languages(body: str, spoken: list[str]) -> list[str]:
    found = {LANGUAGES[match] for pattern in LANGUAGE_REQUIRED for match in pattern.findall(body)}
    return sorted(found - {fold(language) for language in spoken})


def hours_since(job: dict, now: datetime) -> float | None:
    stamp = (job.get("detail") or {}).get("posted_at") or job.get("listed")
    if not stamp:
        return None
    return max(0.0, (now - parse_iso(stamp)).total_seconds() / 3600)


def _age_label(hours: float) -> str:
    if hours < 1:
        return "há menos de 1h"
    if hours < 48:
        return f"há {round(hours)}h"
    return f"há {round(hours / 24)} dias"


def classify(job: dict, profile: dict, now: datetime, review: dict | None = None) -> dict:
    detail = job.get("detail") or {}
    candidate = profile.get("candidate", {})
    remote = profile.get("remote", {})
    thresholds = profile["thresholds"]
    title = fold(job["title"])
    body = fold(" ".join([job["title"], detail.get("description", ""), detail.get("job_function", "")]))

    blockers = title_blockers(job["title"], profile)
    reasons: list[str] = []
    red_flags: list[str] = []

    matched, weight = [], 0.0
    for skill in profile.get("skills", []):
        aliases = skill.get("aliases") or [skill["name"]]
        if hits(body, aliases):
            matched.append(skill["name"])
            weight += skill.get("weight", 1) * (2 if hits(title, aliases) else 1)
    skills_score = min(1.0, weight / thresholds["skill_saturation"])
    title_score = 1.0 if hits(title, profile.get("titles", {}).get("want", [])) else 0.4
    levels = job_levels(job["title"], detail.get("seniority", ""))
    level_score = level_fit(levels, set(candidate.get("seniority", [])))
    match = (0.7 * skills_score + 0.3 * title_score) * level_score

    off_stack = profile.get("off_stack", [])
    off_title = hits(title, off_stack)
    off_body = [term for term in hits(body, off_stack) if term not in off_title]
    match -= min(0.2, 0.05 * len(off_body))
    if off_title:
        match *= 0.25
        red_flags.append(f"stack fora do perfil no título: {', '.join(off_title)}")
    languages = required_languages(body, candidate.get("languages", []))
    if languages:
        match *= 0.6
        red_flags.append(f"pede fluência em {', '.join(languages)}")
    if level_score < 0.9:
        red_flags.append(f"senioridade: {', '.join(sorted(levels))}")
    if not detail:
        red_flags.append("descrição não lida — match só pelo título")
    match = round(max(0.0, min(1.0, match)), 3)
    keyword_match = match

    dealbreakers = hits(body, profile.get("dealbreakers", []))
    if dealbreakers:
        blockers.append(f"dealbreaker: {', '.join(dealbreakers)}")

    workplace = workplace_of(job, body)
    scope, restriction = scope_of(job["location"], body, remote)
    cities = candidate.get("cities", [])
    in_city = bool(hits(fold(job["location"]), cities))

    match_source = "keywords"
    note = None
    if review:
        if "match" in review:
            match, match_source = round(float(review["match"]), 3), "review"
        if review.get("workplace"):
            workplace = review["workplace"]
        if review.get("scope"):
            scope, restriction = review["scope"], []
        red_flags.extend(review.get("red_flags", []))
        if review.get("discard"):
            blockers.append(f"revisão: {review['discard']}")
        note = review.get("why")

    if workplace == "remote" and scope == "restricted":
        blockers.append(f"remoto restrito: {', '.join(restriction) or 'outro país'}")
    if workplace in ("hybrid", "onsite") and not in_city:
        blockers.append(f"{workplace} fora de {', '.join(cities) or 'sua cidade'}: {job['location']}")

    remote_ok = workplace == "remote" and scope in ("home", "region")
    if remote_ok:
        remote_score = 1.0
    elif workplace == "remote":
        remote_score = {"unknown": 0.7, "abroad": 0.3}.get(scope, 0.0)
    elif in_city:
        remote_score = {"hybrid": 0.5, "onsite": 0.3}.get(workplace, 0.4)
    else:
        remote_score = 0.4 if workplace == "unknown" else 0.0
    if workplace == "remote" and scope == "abroad":
        red_flags.append(f"remoto em {job['location']} — confirmar se aceita quem mora fora")
    if workplace == "unknown":
        red_flags.append("modelo de trabalho não informado")

    hours = hours_since(job, now)
    recency = 0.5 ** (hours / thresholds["recent_hours"]) if hours is not None else 0.3
    checks = {
        "match": match >= thresholds["match"],
        "remote": remote_ok,
        "recent": hours is not None and hours <= thresholds["recent_hours"],
    }
    if blockers:
        priority = "discard"
    elif all(checks.values()):
        priority = "high"
    elif checks["match"] and (checks["remote"] or checks["recent"]):
        priority = "medium"
    else:
        priority = "low"

    if matched:
        reasons.append(f"skills: {', '.join(matched)}")
    reasons.append(f"{workplace} · {scope}" if workplace == "remote" else workplace)
    if hours is not None:
        reasons.append(f"postada {_age_label(hours)}" + (" (repost)" if detail.get("reposted") else ""))

    return {
        "id": job["id"],
        "url": job["url"],
        "title": job["title"],
        "company": job["company"],
        "company_url": job.get("company_url", ""),
        "location": job["location"],
        "workplace": workplace,
        "scope": scope,
        "posted_at": detail.get("posted_at") or job.get("listed", ""),
        "hours_ago": round(hours, 1) if hours is not None else None,
        "reposted": bool(detail.get("reposted")),
        "applicants": detail.get("applicants", ""),
        "seniority": detail.get("seniority", ""),
        "employment_type": detail.get("employment_type", ""),
        "salary": detail.get("salary") or job.get("salary", ""),
        "apply": detail.get("apply", ""),
        "priority": priority,
        "score": round(0.5 * match + 0.3 * remote_score + 0.2 * recency, 3),
        "scores": {
            "match": match,
            "match_keywords": keyword_match,
            "match_source": match_source,
            "remote": remote_score,
            "recency": round(recency, 3),
        },
        "checks": checks,
        "matched_skills": matched,
        "off_stack": off_title + off_body,
        "reasons": reasons,
        "red_flags": red_flags,
        "blockers": blockers,
        "review": note,
        "found_by": job.get("found_by", []),
    }


SHARED_REVIEW_FIELDS = ("match", "workplace", "why", "red_flags", "discard")
_POSTING_REF = re.compile(r"\b(?:ref|id)\s*#?\s*\d+\b")


def opening_key(job: dict) -> tuple[str, str]:
    return " ".join(_POSTING_REF.sub("", fold(job["title"])).split()), fold(job["company"]).strip()


def dedupe(jobs: list[dict]) -> list[dict]:
    """One entry per title+company; the same opening posted per city goes under `also`."""
    kept: dict[tuple[str, str], dict] = {}
    for job in jobs:
        key = opening_key(job)
        if key in kept:
            kept[key]["also"].append({"id": job["id"], "url": job["url"], "location": job["location"]})
        else:
            kept[key] = {**job, "also": []}
    return list(kept.values())


def score(raw: dict, profile: dict, now: datetime, reviews: dict | None = None, seen: dict | None = None) -> dict:
    reviews = reviews or {}
    shared: dict[tuple[str, str], dict] = {}
    for job in raw["jobs"]:
        if job["id"] in reviews:
            fields = {k: v for k, v in reviews[job["id"]].items() if k in SHARED_REVIEW_FIELDS}
            shared.setdefault(opening_key(job), fields)
    jobs = [
        classify(job, profile, now, reviews.get(job["id"]) or shared.get(opening_key(job)))
        for job in raw["jobs"]
    ]
    if seen is not None:
        for job in jobs:
            first = seen.setdefault(job["id"], raw["fetched_at"])
            job["first_seen"] = first
            job["new"] = first >= raw["fetched_at"]
    jobs.sort(key=lambda job: (PRIORITY_ORDER[job["priority"]], -job["score"]))
    jobs = dedupe(jobs)
    counts = {priority: sum(job["priority"] == priority for job in jobs) for priority in PRIORITY_ORDER}
    if seen is not None:
        counts["new"] = sum(job["new"] for job in jobs)
    return {
        "generated_at": iso(now),
        "fetched_at": raw["fetched_at"],
        "partial": raw.get("partial", False),
        "searches": raw.get("searches", []),
        "thresholds": profile["thresholds"],
        "counts": counts,
        "jobs": jobs,
    }


def review_sheet(raw: dict, profile: dict, now: datetime, limit: int, chars: int) -> str:
    """Candidates worth a model's read: near or above the match bar, not already discarded."""
    details = {job["id"]: job.get("detail") or {} for job in raw["jobs"]}
    bar = profile["thresholds"]["match"] - 0.15
    picked = [
        job
        for job in score(raw, profile, now)["jobs"]
        if job["priority"] != "discard"
        and details[job["id"]].get("description")
        and (job["scores"]["match"] >= bar or (job["checks"]["remote"] and job["checks"]["recent"]))
    ][:limit]
    blocks = []
    for job in picked:
        description = details[job["id"]]["description"]
        if len(description) > chars:
            description = description[:chars].rsplit(" ", 1)[0] + " […]"
        blocks.append(
            "\n".join(
                [
                    f"## {job['id']} · {job['title']} — {job['company']}",
                    f"{job['location']} · {job['workplace']} ({job['scope']}) · "
                    f"{job['hours_ago']}h · {job['seniority'] or 'senioridade ?'} · {job['applicants'] or '?'}",
                    f"keyword match {job['scores']['match']} · skills: {', '.join(job['matched_skills']) or '—'}"
                    f" · flags: {'; '.join(job['red_flags']) or '—'}",
                    job["url"],
                    "",
                    description,
                ]
            )
        )
    return f"{len(picked)} candidatos para revisão\n\n" + "\n\n---\n\n".join(blocks)


def _parse_search_arg(value: str) -> dict:
    keywords, _, location = value.partition("@")
    spec = {"keywords": keywords.strip()}
    if location.strip():
        spec["location"] = location.strip()
    return spec


def _fetch(args) -> int:
    profile = load_profile(args.profile)
    defaults = dict(profile["search_defaults"])
    if args.hours:
        defaults["hours"] = args.hours
    if args.max_pages:
        defaults["max_pages"] = args.max_pages
    specs = [_parse_search_arg(value) for value in args.search] if args.search else profile.get("searches", [])
    if not specs:
        print("no searches: add `searches` to the profile or pass --search 'keywords@location'", file=sys.stderr)
        return 2
    searches = [{**defaults, **spec} for spec in specs]

    now = datetime.now(timezone.utc)
    cache = Path(args.cache)
    cache.mkdir(parents=True, exist_ok=True)
    prune_cache(cache, now)
    client = Client(delay=args.delay)
    jobs: dict[str, dict] = {}
    partial = False

    def log(line: str):
        print(line, file=sys.stderr)

    try:
        log(f"searching ({len(searches)} queries)")
        collect(client, searches, jobs, log)
        wanted = [job for job in jobs.values() if not title_blockers(job["title"], profile)]
        for job in jobs.values():
            job.setdefault("detail", None)
        log(f"{len(jobs)} postings, {len(wanted)} past the title gate — reading details")
        read_details(client, wanted, cache, args.max_details, now, log)
    except FetchError as error:
        partial = True
        log(f"stopped early: {error}")

    raw = {
        "fetched_at": iso(now),
        "partial": partial,
        "searches": [label(spec) for spec in searches],
        "requests": client.requests,
        "jobs": list(jobs.values()),
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(raw, ensure_ascii=False, indent=2))
    print(f"{len(jobs)} postings, {client.requests} requests{' (partial)' if partial else ''} -> {out}")
    return 0


def _score(args) -> int:
    profile = load_profile(args.profile)
    raw = json.loads(Path(args.raw).read_text())
    now = parse_iso(args.now) if args.now else datetime.now(timezone.utc)
    reviews = json.loads(Path(args.review).read_text()) if args.review else None
    seen_path = Path(args.seen) if args.seen else None
    seen = json.loads(seen_path.read_text()) if seen_path and seen_path.exists() else ({} if seen_path else None)
    result = score(raw, profile, now, reviews, seen)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    if seen_path:
        seen_path.write_text(json.dumps(seen, indent=0, sort_keys=True))
    counts = result["counts"]
    print(" · ".join(f"{key} {value}" for key, value in counts.items()) + f" -> {out}")
    for job in result["jobs"]:
        if job["priority"] != "high":
            break
        flag = "NEW " if job.get("new") else ""
        print(f"  {flag}{job['score']:.2f}  {job['title']} — {job['company']} · {job['reasons'][-1]} · {job['url']}")
    return 0


def _sheet(args) -> int:
    profile = load_profile(args.profile)
    raw = json.loads(Path(args.raw).read_text())
    now = parse_iso(args.now) if args.now else datetime.now(timezone.utc)
    print(review_sheet(raw, profile, now, args.limit, args.chars))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)

    fetch = sub.add_parser("fetch", help="run the searches and read the postings")
    fetch.add_argument("--profile", required=True)
    fetch.add_argument("-o", "--out", required=True)
    fetch.add_argument("--cache", default="plans/jobs/cache")
    fetch.add_argument("--search", action="append", metavar="KEYWORDS@LOCATION")
    fetch.add_argument("--hours", type=float)
    fetch.add_argument("--max-pages", type=int)
    fetch.add_argument("--max-details", type=int, default=150)
    fetch.add_argument("--delay", type=float, default=1.5)
    fetch.set_defaults(run=_fetch)

    scorer = sub.add_parser("score", help="classify a raw fetch")
    scorer.add_argument("raw")
    scorer.add_argument("--profile", required=True)
    scorer.add_argument("-o", "--out", required=True)
    scorer.add_argument("--review")
    scorer.add_argument("--seen")
    scorer.add_argument("--now")
    scorer.set_defaults(run=_score)

    sheet = sub.add_parser("sheet", help="print the candidates for review")
    sheet.add_argument("raw")
    sheet.add_argument("--profile", required=True)
    sheet.add_argument("--limit", type=int, default=40)
    sheet.add_argument("--chars", type=int, default=3000)
    sheet.add_argument("--now")
    sheet.set_defaults(run=_sheet)

    args = parser.parse_args(argv)
    return args.run(args)


if __name__ == "__main__":
    sys.exit(main())

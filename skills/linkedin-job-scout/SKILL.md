---
name: linkedin-job-scout
description: Use when sweeping LinkedIn for job openings and ranking them for the profile owner — "varre vagas no linkedin", "acha vagas remotas pra mim", "quais vagas novas tem", "job hunt", "scan jobs". Searches LinkedIn's public job listings, reads each posting, and classifies every one into a JSON as high / medium / low / discard, where high means profile match AND remote from where the owner lives AND recently posted.
---

# LinkedIn Job Scout

Read and rank. This skill never applies, never messages a recruiter, and never
logs in: it reads the public job pages any anonymous visitor gets, and hands the
owner a ranked JSON plus the short list worth opening today.

**high** = profile match **and** remote from where the owner lives **and** posted
within `thresholds.recent_hours`. **medium** = a match plus one of the other two.
**low** = everything else. **discard** = a blocker: a title the profile avoids, a
dealbreaker (clearance, citizenship), hybrid or on-site outside the owner's city,
or remote restricted to another country.

## Rules of engagement

- **Guest endpoints only.** `tools/jobscout.py` reads
  `jobs-guest/jobs/api/seeMoreJobPostings/search` and `jobs-guest/jobs/api/jobPosting/<id>`
  — the same pages LinkedIn serves logged out. Never pass cookies, `li_at`, or
  credentials; never drive the owner's logged-in browser to scrape jobs at volume.
  An account flagged for scraping is the owner's real network, lost.
- **Polite pace, honest stop.** One request every ~1.5 s with jitter, ~200 a run at
  most. On 429/999 the client backs off three times and then stops; the run keeps
  what it read and is marked `partial`. Do not re-run right away — wait at least
  30 minutes, or run fewer searches.
- **Be honest about the terms.** LinkedIn's User Agreement forbids automated
  collection even of public pages. Low-volume reads of public job listings for the
  owner's own job search are low-risk, not sanctioned. The owner opted in knowing
  this. See `shared/linkedin-access.md`.
- **The owner applies.** The output is a list to read, not a queue to submit.
- **Local only.** `context/jobs.json` and `plans/jobs/` are gitignored.

## Step 0: resolve the repo root

```bash
REPO=$(dirname "$(dirname "$(readlink -f ~/.claude/skills/linkedin-job-scout)")")
cd "$REPO" && pwd
STAMP=$(date +%F-%H%M)
```

Every path below is relative to `$REPO`.

## Step 1: the job profile

`context/jobs.json` decides what "match" means. If it is missing, copy
`context/jobs.template.json` and tailor it before the first scan:

- Read `context/profile.md` if it exists (Stack, Trajetória) and any résumé the
  user points to. Skills go in `skills` with a weight — 3 for the core stack the
  owner would lead with, 2 for solid, 1 for a plus — and every spelling that
  appears in postings under `aliases`.
- `candidate.seniority` from the real years of experience (`junior`, `mid`,
  `senior`, `lead`); `candidate.cities` for hybrid the owner would accept;
  `candidate.languages` the owner is fluent in.
- `titles.want` / `titles.avoid`, `off_stack`, `searches` from the target roles.
- Whatever cannot be read from a file goes to the user in **one** AskUserQuestion
  call: target roles, seniority, a city where hybrid is fine, languages.

Show the user the file once it is written. On later runs, read it without asking.

Field reference:

| Field | Effect |
|---|---|
| `skills[]` | `{name, weight, aliases}` — matched weight (doubled when the title names the skill) / `thresholds.skill_saturation` is 70% of the match |
| `titles.want` | title hit = the full 30% title share; miss = 0.4 of it |
| `titles.avoid` | blocker → discard; also skipped before the detail fetch |
| `candidate.seniority` | multiplies the match — fits 1.0, unknown 0.9, one level off 0.6, further 0.2; read from the title, else LinkedIn's "Seniority level" |
| `candidate.cities` | hybrid or on-site here is kept (never high); anywhere else is a discard |
| `off_stack` | in the title: match × 0.25; in the description: −0.05 each (max −0.2) |
| `dealbreakers` | phrase in the posting → discard |
| `remote.home` / `regions` | location (its country part) that counts as hireable-from-home |
| `remote.open_phrases` | description opening the role to the owner's region; lifts a restriction |
| `remote.restricted_phrases` | description limiting hires to another country → discard |
| `thresholds` | `match` bar (0.6), `recent_hours` (72), `skill_saturation` (12) |
| `search_defaults` / `searches` | LinkedIn queries; `workplace` remote/hybrid/onsite, `hours` window, `experience`, `max_pages` (10 cards each) |

## Step 2: read the invocation

Workplace comes from the title, then the description, then LinkedIn's remote tag —
posters tag "100% presencial" jobs as remote often enough that the tag goes last.

Map what the user asked onto flags; do not edit `context/jobs.json` for a one-off:

| Ask | Flag on `fetch` |
|---|---|
| "só as de hoje", "últimas 24h" | `--hours 24` |
| "vagas de rust", "procura por X em Portugal" | `--search "rust@Brazil"` (repeatable; replaces the profile's searches) |
| "varredura rápida" | `--max-pages 1 --max-details 40` |

A lasting change ("para de me mostrar vaga de Angular") goes into the profile, and
you say so.

## Step 3: fetch

Takes a few minutes (searches × pages + one request per new posting; postings
already read are cached in `plans/jobs/cache/` for 60 days). Run it in the
background and wait for it:

```bash
python3 tools/jobscout.py fetch --profile context/jobs.json -o plans/jobs/$STAMP.raw.json
```

If it ends `partial`, say so plainly in the final summary and carry on with what
was read.

## Step 4: score, then review the candidates

```bash
python3 tools/jobscout.py score plans/jobs/$STAMP.raw.json --profile context/jobs.json \
  --seen plans/jobs/seen.json -o plans/jobs/$STAMP.json
python3 tools/jobscout.py sheet plans/jobs/$STAMP.raw.json --profile context/jobs.json --limit 40
```

The keyword score is a first pass. The sheet prints every candidate near or above
the match bar with its description. Read each one against `context/jobs.json`
(and `context/profile.md` if present) and write `plans/jobs/$STAMP.review.json`:

```json
{
  "4483891327": {
    "match": 0.8,
    "scope": "home",
    "why": "Next.js + Node em produto de pagamentos; pede 5 anos, o perfil tem 5",
    "red_flags": ["inglês fluente para calls diárias"]
  },
  "4483000000": {"match": 0.3, "why": "título full stack, mas o trabalho é 80% Java/Spring"},
  "4483111111": {"scope": "restricted", "why": "contrata só residentes no México (EOR)"}
}
```

- `match` 0–1, judged on the actual work: **0.9+** core stack and level both fit;
  **0.7** core stack fits, one real gap; **0.5** adjacent; **below 0.4** a different
  job. Never raise a number to push a posting into high.
- `scope`: `home`, `region`, `abroad` or `restricted` — only when the description
  says where hires may live. `workplace` (`remote`/`hybrid`/`onsite`) only when
  the description contradicts the listing.
- `discard`: a concrete reason found in the posting, quoted or paraphrased.
- `why`: one pt-BR line that cites the posting, not a compliment.
- Omit a field you have no evidence for; the keyword value stands.
- The sheet shows one copy per opening (same title and company in several
  cities). `match`, `workplace`, `why`, `red_flags` and `discard` carry over to
  the other copies; `scope` stays per copy, since the location differs.

Re-score with the review — the same `--seen` file is safe to reuse, `new` holds:

```bash
python3 tools/jobscout.py score plans/jobs/$STAMP.raw.json --profile context/jobs.json \
  --seen plans/jobs/seen.json --review plans/jobs/$STAMP.review.json -o plans/jobs/$STAMP.json
```

## Step 5: report

In pt-BR, short:

1. One line of counts — high / medium / low / discard / new — and `partial` if it was.
2. A table of the **high** jobs, new ones first: title, company, location, posted
   (`hours_ago`), applicants, the `why`, and the URL.
3. The three best **medium** jobs, each with the one check it missed.
4. The absolute path of `plans/jobs/$STAMP.json`.

Stop there. Do not open the postings, apply, or contact anyone.

## Output

`plans/jobs/<stamp>.json`:

```json
{
  "generated_at": "2026-10-29T15:40:00Z",
  "fetched_at": "2026-10-29T15:32:00Z",
  "partial": false,
  "searches": ["full stack @ Brazil"],
  "thresholds": {"match": 0.6, "recent_hours": 72, "skill_saturation": 12},
  "counts": {"high": 4, "medium": 11, "low": 38, "discard": 22, "new": 19},
  "jobs": [
    {
      "id": "4483891327",
      "url": "https://www.linkedin.com/jobs/view/4483891327/",
      "title": "Senior Full Stack Engineer",
      "company": "Acme",
      "location": "Brazil",
      "workplace": "remote",
      "scope": "home",
      "posted_at": "2026-10-29T07:00:00Z",
      "hours_ago": 8.7,
      "applicants": "Be among the first 25 applicants",
      "seniority": "Mid-Senior level",
      "priority": "high",
      "score": 0.91,
      "scores": {"match": 0.8, "match_keywords": 0.74, "match_source": "review", "remote": 1.0, "recency": 0.92},
      "checks": {"match": true, "remote": true, "recent": true},
      "matched_skills": ["TypeScript", "React", "Node.js"],
      "reasons": ["skills: TypeScript, React, Node.js", "remote · home", "postada há 9h"],
      "red_flags": [],
      "blockers": [],
      "review": "Next.js + Node em produto de pagamentos",
      "also": [{"id": "4483891400", "url": "https://www.linkedin.com/jobs/view/4483891400/", "location": "Recife, Pernambuco, Brazil"}],
      "new": true
    }
  ]
}
```

One entry per opening — copies in other cities sit under `also`. Sorted by
priority, then `score` (0.5 match + 0.3 remote + 0.2 recency). The raw
fetch, with full descriptions, stays next to it as `<stamp>.raw.json`.

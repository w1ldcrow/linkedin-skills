---
name: linkedin-job-scout
description: Use when sweeping LinkedIn for job openings and ranking them for the profile owner — "varre vagas no linkedin", "acha vagas remotas pra mim", "quais vagas novas tem", "job hunt", "scan jobs". Searches LinkedIn's public job listings, reads each posting, and classifies every one into a JSON as high / medium / low / discard, where high means profile match AND remote from where the owner lives AND recently posted. Also scans for someone else from their résumé, and tailors that résumé to the best openings without inventing anything ("adapta o currículo pras 10 melhores vagas", "tailor my CV to these jobs").
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
- **The person applies.** The output is a list to read and résumés to send by
  hand, not a queue to submit.
- **A tailored résumé is the same résumé.** Rephrase, reorder, re-emphasize —
  never add a skill, number, employer, title, date or seniority the source does
  not state. `tools/cvtailor.py check` enforces it; a failing file is fixed, never
  shipped with a note.
- **Local only.** `context/jobs.json`, `context/private/` and `plans/` are
  gitignored: profiles, résumés, contact data and output never enter the repo.

## Step 0: resolve the repo root and the subject

```bash
REPO=$(dirname "$(dirname "$(readlink -f ~/.claude/skills/linkedin-job-scout)")")
cd "$REPO" && pwd
STAMP=$(date +%F-%H%M)
```

The subject is the owner unless the user hands over someone else's résumé or
names someone with a folder in `context/private/`:

| Subject | `CTX` | `OUT` |
|---|---|---|
| the owner | `context` | `plans/jobs` |
| someone else (`<slug>` = first name, lowercase) | `context/private/<slug>` | `plans/jobs/<slug>` |

Every path below is relative to `$REPO`. The posting cache `plans/jobs/cache` is
shared — a posting reads the same for everyone.

## Step 1: the résumé and the job profile

**The résumé** — only when the user hands one over (PDF, DOCX, text) or asks for
tailoring. Extract it (`pdftotext -layout file.pdf -`) and write
`$CTX/resume.json` in the shape of `context/resume.template.json`, **word for
word**: no fixes, no rewording, every bullet as written. Then prove it:

```bash
python3 tools/cvtailor.py check $CTX/resume.json $CTX/resume.json
python3 tools/cvtailor.py render $CTX/resume.json -o $OUT/resume-source.pdf
pdftoppm -r 60 -png $OUT/resume-source.pdf $OUT/resume-source   # look at it next to the original
```

The render must match the original's content and page count before anything is
tailored from it.

**The job profile** — `$CTX/jobs.json` decides what "match" means. If it is
missing, copy `context/jobs.template.json` and tailor it before the first scan:

- Read `$CTX/resume.json`, `context/profile.md` for the owner, and any résumé the
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
For someone else, set `candidate.cities` to their city, not the owner's.

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
| `companies.deprioritize` | `[{names, factor, note}]` added to `shared/company-signals.json` — a matching company drops one priority level and its score × `factor` |
| `remote.home` / `regions` | location (its country part) that counts as hireable-from-home |
| `remote.open_phrases` | description opening the role to the owner's region; lifts a restriction |
| `remote.restricted_phrases` | description limiting hires to another country → discard |
| `thresholds` | `match` bar (0.6), `recent_hours` (72), `skill_saturation` (12) |
| `search_defaults` / `searches` | LinkedIn queries; `workplace` remote/hybrid/onsite, `hours` window, `experience`, `max_pages` (10 cards each) |

## Step 2: read the invocation

**Deprioritized companies.** `shared/company-signals.json` lists companies whose
postings rarely turn into a live opening — high volumes of recurring, generic
listings, often feeding a talent pool (BairesDev and Stefanini today). Every run
reads it: a match drops one priority level (high → medium → low), multiplies the
score by `factor` (0.6) and shows the `note` as a red flag. When the owner says a
company belongs there, add it to that file (shared by every profile) — or to
`companies.deprioritize` in one profile — and keep the note factual: what the
postings look like, never an accusation.

Workplace comes from the title, then the description, then LinkedIn's remote tag —
posters tag "100% presencial" jobs as remote often enough that the tag goes last.

Map what the user asked onto flags; do not edit `$CTX/jobs.json` for a one-off:

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
python3 tools/jobscout.py fetch --profile $CTX/jobs.json --cache plans/jobs/cache -o $OUT/$STAMP.raw.json
```

If it ends `partial`, say so plainly in the final summary and carry on with what
was read.

## Step 4: score, then review the candidates

```bash
python3 tools/jobscout.py score $OUT/$STAMP.raw.json --profile $CTX/jobs.json \
  --seen $OUT/seen.json -o $OUT/$STAMP.json
python3 tools/jobscout.py sheet $OUT/$STAMP.raw.json --profile $CTX/jobs.json --limit 40
```

The keyword score is a first pass. The sheet prints every candidate near or above
the match bar with its description. Read each one against `$CTX/jobs.json`
(and `$CTX/resume.json` or `context/profile.md`) and write `$OUT/$STAMP.review.json`:

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
python3 tools/jobscout.py score $OUT/$STAMP.raw.json --profile $CTX/jobs.json \
  --seen $OUT/seen.json --review $OUT/$STAMP.review.json -o $OUT/$STAMP.json
```

## Step 5: report

In pt-BR, short:

1. One line of counts — high / medium / low / discard / new — and `partial` if it was.
2. A table of the **high** jobs, new ones first: title, company, location, posted
   (`hours_ago`), applicants, the `why`, and the URL.
3. The three best **medium** jobs, each with the one check it missed.
4. The absolute path of `$OUT/$STAMP.json`.

Stop there unless tailoring was asked for. Do not apply or contact anyone.

## Step 6: tailor the résumé (only when asked)

Pick the top N openings from `$OUT/$STAMP.json`: high first, then medium jobs that
pass the remote check, then the rest of medium, each group by `score`; one per
opening (`also` copies are the same job); never a discard. A résumé for a job the
person cannot take from where they live is wasted, so remote outranks recent here. Read
each one in full:

```bash
python3 tools/jobscout.py show $OUT/$STAMP.raw.json <id> <id> ...
```

For each, copy `$CTX/resume.json` to `$OUT/$STAMP-cv/NN-<company-slug>-<id>.json`
(NN = rank, 01…) and adapt it **lightly**:

| May change | How |
|---|---|
| `headline` | append the core stack the posting leads with, from words already in the source ("Desenvolvedor Back-end Python") |
| `summary` | reorder and re-cut so the first sentence answers what the posting asks first; same facts |
| `skills` | reorder groups and items so the posting's stack comes first; labels stay as written |
| bullets | reorder within each job, most relevant first; reword only to use the posting's term for the very same thing |
| `context` | trim or reword, same facts |

Everything else is frozen: name, contact, links, employers, titles, places,
periods, education, the number of bullets per job, the language of the résumé.
A posting in English gets a `changes` line saying an English version would read
better; translating is a separate request (below).

Add to each file:

```json
"target": {"id": "4483891327", "title": "Backend Engineer (Python)", "company": "Acme", "url": "https://www.linkedin.com/jobs/view/4483891327/"},
"changes": ["Resumo abre com FastAPI + PostgreSQL, que a vaga lista primeiro", "Bullet de Kubernetes subiu para o 2º lugar"]
```

`changes` is for the person sending it: what moved and why, one line each, and
any requirement of the posting the source does not cover ("a vaga pede Kafka —
não está no currículo, não foi adicionado").

Then check, render, index:

```bash
python3 tools/cvtailor.py check $CTX/resume.json $OUT/$STAMP-cv/*.json   # must print ok for every file
python3 tools/cvtailor.py render $OUT/$STAMP-cv/*.json
python3 tools/cvtailor.py index $OUT/$STAMP-cv
python3 tools/jobscout.py score $OUT/$STAMP.raw.json --profile $CTX/jobs.json --seen $OUT/seen.json \
  --review $OUT/$STAMP.review.json --resumes $OUT/$STAMP-cv -o $OUT/$STAMP.json
```

The last command writes `resume: {json, pdf}` — absolute paths — into each
tailored job in `$OUT/$STAMP.json`, so the ranking and the files travel together.

Every `error` is a fact the source does not support: rewrite until `ok`. Read
every `warn`. Confirm each PDF keeps the source's page count (`pdfinfo`), and look
at one rendered page. Report the folder, the list (rank, job, company, link), and
the gaps the `changes` lines named.

**Translations (on request).** Translate once, check once, then tailor:

1. Write `$CTX/resume.<lang>.json` — a faithful translation of `$CTX/resume.json`,
   bullet for bullet, with `lang` and `labels` set (`Summary`, `Skills`, …).
   Amounts keep their figures (`R$ 800 mil` → `R$ 800k`).
2. `python3 tools/cvtailor.py check --translation $CTX/resume.json $CTX/resume.<lang>.json`
   — same name, contact, links, companies, periods, schools, bullet and skill-group
   counts; no number, technology or seniority word the original lacks.
3. For each posting, write `NN-<company>-<id>.<lang>.json` next to the original-language
   version — same order and emphasis, from the translated base — and check it
   strictly against that base:
   `python3 tools/cvtailor.py check $CTX/resume.<lang>.json $OUT/$STAMP-cv/*.<lang>.json`.
4. Render, index and re-score as above; the job's `resume.translations.<lang>`
   gets the paths.

The renderer looks for `CHROME`, then a cached `chrome-headless-shell`
(Puppeteer or Playwright), then a Chromium-family browser on `PATH`. Inter comes
from Google Fonts, so the first render needs network.

## Output

`$OUT/<stamp>.json`:

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
      "scores": {"match": 0.8, "match_keywords": 0.74, "match_source": "review", "remote": 1.0, "recency": 0.92, "company": 1.0},
      "checks": {"match": true, "remote": true, "recent": true},
      "matched_skills": ["TypeScript", "React", "Node.js"],
      "reasons": ["skills: TypeScript, React, Node.js", "remote · home", "postada há 9h"],
      "red_flags": [],
      "blockers": [],
      "review": "Next.js + Node em produto de pagamentos",
      "also": [{"id": "4483891400", "url": "https://www.linkedin.com/jobs/view/4483891400/", "location": "Recife, Pernambuco, Brazil"}],
      "resume": {
        "json": "/abs/plans/jobs/2026-10-29-1532-cv/01-acme-4483891327.json",
        "pdf": "/abs/…/01-acme-4483891327.pdf",
        "translations": {"en": {"json": "/abs/…/01-acme-4483891327.en.json", "pdf": "/abs/…/01-acme-4483891327.en.pdf"}}
      },
      "new": true
    }
  ]
}
```

One entry per opening — copies in other cities sit under `also`. `resume` appears
only when the run was scored with `--resumes` (`null` for jobs without one). Sorted by
priority, then `score` ((0.5 match + 0.3 remote + 0.2 recency) × company factor). The raw
fetch, with full descriptions, stays next to it as `<stamp>.raw.json`.

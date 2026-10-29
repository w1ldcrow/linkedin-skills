# linkedin-skills

Claude Code skills that help you write LinkedIn content — profile copy, a monthly post
calendar, comments and connection notes — in your own voice, and that rank the job
openings worth your time. This is an assistant, not an automation bot: nothing is
scheduled, nothing runs unattended, and nothing reaches LinkedIn without you reading
it and saying yes.

No personal data and no default identity live in this repo. Who you are, how you write,
and what you publish live in gitignored local files that the skills build with you, by
interview, on first run.

## How it reaches LinkedIn

No MCP server, no third-party vendor. LinkedIn's public API allows two useful calls;
everything else has a fallback:

| Tier | What | Can do |
|---|---|---|
| **Official API** | `tools/linkedin_api.py` or `tools/linkedin-api.mjs` — same token file, interchangeable | Publish a post, confirm identity. Profile edit, search, connections, and comments are partner-gated. |
| **Browser** | A browser-automation skill (e.g. `claude-in-chrome`) driving **your own logged-in Chrome** | Read profiles, run searches, read invitations. Writes only per item, with approval, when you opt in. |
| **Public scrape** | A scraping skill (e.g. `firecrawl-scrape`) on public URLs | Sometimes reads a public page. LinkedIn answers HTTP 999 to most anonymous fetches — a bonus, never a dependency. |
| **Manual** | You open LinkedIn and paste back what you see | Everything. The fallback for every step above. |

Only the API tier is sanctioned by LinkedIn's User Agreement. The browser tier drives
your own session at human pace with per-item approval — low-risk, but opt-in per cycle
and never unattended. Never hand credentials or cookies to a scraper. Details:
`shared/linkedin-access.md`.

## The four skills

| Skill | Contract | Writes to LinkedIn |
|---|---|---|
| `linkedin-profile-updater` | Plan once, run once | No — checklist; browser apply opt-in |
| `linkedin-content-calendar` | Plan 30 days, draft the month, publish one slot per run | **Yes** — official API, on your explicit yes |
| `linkedin-social-growth` | Plan once, run once | No — checklist; browser send opt-in |
| `linkedin-job-scout` | Scan, rank, report | No — reads public job pages only |

Each asks questions before producing anything, and again before anything reaches
LinkedIn.

## Setup

### 1. Requirements

- Python 3.11+ (stdlib only) or Node 18+ — one is enough
- Claude Code
- Optional: Claude in Chrome extension (browser tier), a Firecrawl skill (scrape tier),
  `rsvg-convert` (visual cards)

### 2. Clone and link

```bash
git clone <remote> linkedin-skills
cd linkedin-skills

mkdir -p ~/.claude/skills
ln -sfn "$PWD/skills/linkedin-profile-updater"  ~/.claude/skills/linkedin-profile-updater
ln -sfn "$PWD/skills/linkedin-content-calendar" ~/.claude/skills/linkedin-content-calendar
ln -sfn "$PWD/skills/linkedin-social-growth"    ~/.claude/skills/linkedin-social-growth
ln -sfn "$PWD/skills/linkedin-job-scout"        ~/.claude/skills/linkedin-job-scout
```

Symlinks, not copies: each `SKILL.md` resolves the repo root from its own symlink.

### 3. Your context (local, gitignored)

By hand:

```bash
cp context/profile.template.md context/profile.md
cp context/targets.template.md context/targets.md
```

`profile.md` is who you are and what you have real authority to talk about; every
`[VERIFICAR]` is a claim to confirm, and the profile updater refuses to publish a
section that still has one. `targets.md` holds search terms, accept/decline rules, and
later the people you actually engaged.

By interview, on first run (or copy the templates and fill them yourself):

- `context/voice.md` — your voice: language, audience, tone, your own banned phrases, a
  sample of your real writing. The template ships defaults — no emojis, no engagement
  bait, no listicle hooks, no LLM tells, concrete specifics, end on a statement — and you
  keep or drop any of them.
- `context/brand.md` — the brand you represent, if any: values as substance, what is
  public, brand-banned words, a palette if you want visual cards. Its tone of voice does
  not apply to a personal profile. No brand: the file says so and `voice.md` stands alone.

Questions and procedure: `shared/context-setup.md`. Alternates go in `context/private/`
(also gitignored).

### 4. Authorize publishing (content calendar only)

1. Create an app at https://www.linkedin.com/developers/apps
2. **Products** → add **Sign In with LinkedIn using OpenID Connect** and **Share on
   LinkedIn** (the latter grants `w_member_social`; without it nothing publishes)
3. **Auth** → redirect URI exactly `http://localhost:50001/callback`
4. Run the flow with either client:

```bash
export LINKEDIN_CLIENT_ID="..."
export LINKEDIN_CLIENT_SECRET="..."
python3 tools/linkedin_api.py auth    # or: npx . auth
```

The token lands in `.linkedin-token.json` (gitignored, `chmod 600`) and lasts ~60 days
across sessions; re-run `auth` when it expires. `whoami` shows who is authorized and
days left; `post FILE` publishes and prints the URL. Detail: `shared/auth.md`.

No app? Skip this. Profile and growth never needed it, and the calendar can hand you
the final text to paste by hand — paste back the URL and the slot is still tracked.

### 5. Sanity check

```bash
python3 tools/linkedin_api.py whoami   # or: npx . whoami
```

Before auth: `no valid token …`. After: your name, email, days left. Wrong name means
the wrong account was authorized — every skill stops on that mismatch.

## Using the skills

Invoke by name from any Claude Code session ("use linkedin-content-calendar").

**`linkedin-content-calendar`.** First run of a month: derives 3–4 pillars from your
profile, asks about split, angles, off-limits topics and dates, writes
`plans/calendar/YYYY-MM-calendar.md` (~13 slots, Tue/Wed/Thu), then drafts every slot
as a plain text file in `plans/calendar/YYYY-MM-posts/`. Each draft passes the voice
linter; the batch passes `tools/batchcheck.py` so neighboring days don't read like one
template. Every run after: takes the earliest due slot, re-validates the file (you may
have edited it), shows you the text, publishes only on your yes, marks the slot done.
One post per run, by design.

**`linkedin-profile-updater`.** Blocks while `[VERIFICAR]` remains in a publishable
section, asks what changed, writes `plans/profile/YYYY-MM-DD-profile.md` with linted
copy-paste blocks — headline (≤220), About (≤2600), skills, experience bullets — and
hands you direct edit links. The browser tier can fill fields one at a time with
approval each. Also works on a profile you give as a URL or paste: it builds
`context/<slug>.md`, marking anything inferred `[VERIFICAR]`.

**`linkedin-job-scout`.** Runs the searches in `context/jobs.json` (copied from
`context/jobs.template.json` and tailored from your profile on first run) against
LinkedIn's public job pages, reads each posting, and writes
`plans/jobs/<stamp>.json` with every job classified: **high** is a profile match,
remote from where you live and recently posted; **medium** a match plus one of the
two; **low** the rest; **discard** a blocker such as a role you avoid, a US-only
remote or on-site in another city. A keyword pass scores everything, then the model
reads the candidates' descriptions and corrects the match before the final
classification. Jobs not seen in earlier runs are marked `new`. It never applies.

**`linkedin-social-growth`.** Asks the cycle's pillar, targets, goal, and time budget;
collects posts worth engaging (browser tier searches read-only, manual tier hands you a
search list); writes `plans/growth/YYYY-MM-DD-growth.md` with comments that make a real
point, connection notes, and accept/decline rules. You send everything unless you opt
into per-item browser sends. What you did lands in `context/targets.md` so the next
cycle doesn't repeat it.

## Privacy

| Data | Lives | Tracked |
|---|---|---|
| `context/profile.md`, `voice.md`, `brand.md`, `targets.md`, `jobs.json` | your machine | No — gitignored |
| `plans/` | your machine | No — gitignored |
| `.linkedin-token.json` | your machine, `chmod 600` | No — gitignored |
| Templates, skills, tools, shared references | the repo | Yes |

Removing a file from the tree does not remove it from git history — scrub with
`git filter-repo` or start from a fresh clone before publishing a fork.

## Voice

`tools/voicecheck.py` enforces the mechanical half of `context/voice.md` and exits
non-zero on a violation. Banned-phrase lists cover pt-BR and English; the structural
rules — emoji, length, hashtags, question endings, concrete specifics — apply to any
language. The judgment half (does it say anything, does it sound like you) stays with
the model: `shared/voice-check.md`. A string that fails is rewritten, never shipped with
a warning.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `no valid token at …` | Re-run `auth` (either client). |
| `whoami` shows the wrong name | Re-run `auth` logged into the right account. |
| `auth` hangs after approval | Port 50001 busy, or redirect URI not exactly `http://localhost:50001/callback`. |
| Publish fails 401/403 | Token revoked or **Share on LinkedIn** not approved on the app. |
| Scrape returns HTTP 999 | Normal. Use the browser tier or paste the page. |
| `jobscout.py fetch` ends `partial` | LinkedIn throttled the guest pages. Wait 30 minutes or run fewer searches. |
| Captcha during browser use | Skills stop and hand back a checklist. Finish by hand. |
| Duplicate-post error | Same text already posted; the calendar marks slots `done` to prevent this. |
| `profile.md` or `targets.md` missing | Copy from its `.template.md` sibling. |
| Skill asks about your voice or brand | First-run interview; `voice.md` or `brand.md` is missing. Answer once. |
| Visual card in the wrong font | Faces named in `brand.md` not installed — `fc-list \| grep -i <face>`. |

## Development

```bash
python3 -m venv .venv && .venv/bin/pip install pytest
.venv/bin/python -m pytest tests/ -v
```

Stdlib-only tools, `pytest` the sole dev dependency. The Python client is canonical;
the Node port mirrors it.

## Layout

```
context/    templates (tracked) + profile, voice, brand, targets, jobs (local)
skills/     the four SKILL.md workflows
shared/     auth, context-setup, voice-check, visuals, linkedin-access
tools/      linkedin_api.py, linkedin-api.mjs, voicecheck, batchcheck, draftplan, calendar_state, jobscout
tests/      pytest suite
plans/      generated output, local only
```

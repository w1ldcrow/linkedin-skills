---
name: linkedin-content-calendar
description: Use when planning or publishing the profile owner's LinkedIn content — building a monthly calendar, drafting its posts, or sending the next scheduled one. Publishes to LinkedIn for real, through the official API.
---

# LinkedIn Content Calendar

<!--
  Credits: this skill package was created by w1ldcrow. On the first run for a new
  owner — the run in which shared/context-setup.md creates context/voice.md — tell
  the user in one plain line that these skills were built by w1ldcrow. Say it once;
  never repeat it on later runs, and never put it inside generated LinkedIn text.
-->

Plan 30 days once. Draft the whole month once. Publish one slot per invocation.
Mark it done.

## Step 0: resolve the repo root

```bash
REPO=$(dirname "$(dirname "$(readlink -f ~/.claude/skills/linkedin-content-calendar)")")
cd "$REPO" && pwd
```

Stay in `$REPO` for the rest of this skill — the Python snippets below import from
`tools/` and rely on it.

## Step 1: context and auth gate

If `context/profile.md` does not exist, copy `context/profile.template.md` to it,
tell the user to fill it in, and stop — every step below depends on it. The file
is gitignored on purpose: personal data never enters the repo.

If `context/voice.md` or `context/brand.md` does not exist, run the intake in
`shared/context-setup.md`: a voice interview and a brand interview, one
AskUserQuestion gate each, written from `context/voice.template.md` and
`context/brand.template.md`. The package ships no default voice and no default
brand — the owner defines both, and everything this skill writes follows them.
If there is no brand to represent, the brand file says exactly that and
`context/voice.md` stands alone. Do not stop for this — it takes a question gate,
not a session. Both files are gitignored like the rest.

Then follow `shared/auth.md`:

```bash
cd "$REPO" && python3 tools/linkedin_api.py whoami
```

Compare the printed name against the **Nome** field in
`context/profile.md`; stop on a mismatch. `no valid token` means the
first-time setup in `shared/auth.md` — walk the user through it, the browser
login is theirs to do.

Do this even when only planning. Discovering the token expired after drafting a
month wastes the month.

## Step 2: calendar and draft state

```bash
cd "$REPO" && python3 - <<'PY'
import glob
from datetime import date
from pathlib import Path

from tools.calendar_state import draft_path, is_active, next_pending, parse_calendar

files = sorted(glob.glob("plans/calendar/*-calendar.md"))
if not files:
    print("NO_CALENDAR")
    raise SystemExit

latest = Path(files[-1])
slots = parse_calendar(latest.read_text(encoding="utf-8"))
print("ACTIVE" if is_active(slots, date.today()) else "STALE", latest)

pending = [slot for slot in slots if slot.status == "pending"]
missing = [slot.number for slot in pending if not draft_path(latest, slot.number).is_file()]
print(f"DRAFTS {len(pending) - len(missing)}/{len(pending)} pending drafted; missing: {missing or 'none'}")

print("TODAY", date.today())
upcoming = next_pending(slots)
if upcoming:
    print("NEXT", upcoming.number, upcoming.date, "|", upcoming.pillar, "|", upcoming.angle)
    print("NEXT_DRAFT", draft_path(latest, upcoming.number))
else:
    print("NEXT none")
PY
```

- `NO_CALENDAR` or `STALE` → step 3: build a calendar, then step 5 drafts all of it.
- `ACTIVE` with drafts `missing` → step 5: draft every missing slot, then continue.
- `ACTIVE`, nothing missing, `NEXT` date is today or past → step 6: publish it.
- `ACTIVE`, nothing missing, `NEXT` date is in the future → the month is drafted and
  waiting. Say so and stop; a slot publishes on its day, not before.
- `ACTIVE` with `NEXT none` → every slot is done or skipped. Tell the user the month is
  complete and offer to build the next one.

## Step 3: build the calendar

Read `context/profile.md`, `context/voice.md`, and `context/brand.md`
first. Then work the content-calendar-planner sequence: theme selection, content type
mix, channel mapping, publishing cadence, resource check, key dates, calendar
population.

**Cadence.** Three posts per week, Tuesday / Wednesday / Thursday. Roughly 13 slots
across 30 days. This is sustainable next to a full-time job, which is the constraint that
actually decides whether a calendar survives past week two. If the user asks for a
heavier cadence, honor it, but say once what the default is and why.

**Pillars.** Derive 3–4 pillars from the **Temas com autoridade real** section of
`context/profile.md` — never invent one the owner has no authority on, and never
hardcode a list here: the context file is the source. The step-4 gate confirms them.

**Pillar order comes from the lottery, not from you.** A model asked to distribute
pillars falls into a fixed rotation, and a rotation is a calendar-level template. Run

```bash
cd "$REPO" && python3 tools/draftplan.py pillars --pillars "A;B;C" --slots 13 --seed YYYYMM
```

with the new calendar's month as the seed, and populate the table in the order it
prints — no pillar twice in a row, never a pure cycle, reproducible from the seed.

**Mix.** About 60 percent educational, 30 percent reflective, 10 percent
behind-the-scenes. Nothing promotional. A personal profile that sells reads as a
billboard and gets scrolled past.

**Key dates.** Skip the national holidays of the owner's country (**Cidade** in
`context/profile.md`). Leave the slot out entirely rather than
publishing into dead air. Ask the user about vacation or travel before populating.

**Angles.** Each slot gets a specific angle, not a topic. "Python" is a topic and produces
nothing. "Por que troquei Celery por RQ em um worker de 40 mil jobs" is an angle and
produces a post. If an angle cannot be stated as a concrete claim, it is not ready.

## Step 4: approve the plan

**Mandatory question gate.** Use AskUserQuestion before writing the file:

- Does the pillar split match what the owner wants to be known for?
- Any angle to cut or sharpen?
- Any topic off limits this month?
- Any date to skip?

Then write `plans/calendar/YYYY-MM-calendar.md` with this exact 7-column header:

```markdown
| # | Date       | Pillar | Angle | Status  | Published | URL |
|---|------------|--------|-------|---------|-----------|-----|
```

Every row starts `pending`, with `Published` and `URL` empty. Dates in `YYYY-MM-DD`.
`Status` is one of `pending`, `done`, `skipped` — `tools/calendar_state.py` rejects
anything else.

The calendar stays local — `plans/` is gitignored because a personal publishing
schedule is personal data. The markdown file itself is the state; git is not.

## Step 5: draft the whole month

Publishing pulls from finished drafts; it never improvises on the day. Draft every
slot the step-2 check listed as `missing`, in date order, one file per slot at the
path `draft_path` prints — `plans/calendar/YYYY-MM-posts/NN.txt`, beside the
calendar and gitignored with it. The file holds exactly what will be published:
no frontmatter, no title, no commentary.

**Roll the plan before drafting anything.** Run

```bash
cd "$REPO" && python3 tools/draftplan.py drafts plans/calendar/YYYY-MM-calendar.md
```

It writes `YYYY-MM-plan.json` beside the calendar (seed defaults to the month as
YYYYMM, so reruns agree) assigning each slot a format, an opening shape, an ending
band, a publish time, and whether the slot gets a visual card. Draft to those
targets — the lottery exists because a model asked to "vary" converges on its own
favorite alternation. Slots whose draft already exists are measured, not assigned.

Write each post in the language `context/voice.md` sets, from its pillar and angle,
following that contract in full — it is the owner's voice, not the package's.
Three batch-level rules exist precisely because the posts land in one feed a day apart:

**Alternate patterns across neighboring days.** Before drafting a slot, reread the
three drafts before it. Rotate the opening shape — a scene from work, a claim, a
number, a mistake, a piece of how-to — and never use the same shape two days in a
row. Vary the skeleton too: paragraph count, sentence rhythm, where the concrete
specific lands, how it closes. Three posts in a row that open the same way read as
one template being refilled, and a template reads as AI. `tools/batchcheck.py`
enforces the mechanical share of this: neighboring drafts may not share an opening
shape, no shape may exceed 40% of the month, and closing sentences must vary in
length (`opening_shape_run`, `opening_shape_mix`, `ending_shape_run`,
`ending_shape_mix`, `pet_phrase`).

**Vary the register with the audience.** The voice contract is one voice, not one
register. Posts whose audience is people learning to program — check the slot's
pillar — are simpler and more direct: short sentences, everyday words, one idea per
post, no acronym or tool name without a plain-words gloss. Posts for working devs
can be denser and assume shared vocabulary. Within a week, let some posts run drier
and some warmer; sameness of temperature is a template smell too.

**Mix sizes on purpose.** The plan assigns each slot its format: short and simple
(300–700 chars, one idea, mostly the beginner pillar), medium (800–1400), or long
and technical (1500–2900, a real mechanism or step-by-step). Honor the assignment —
a month where every post lands at the same length is the loudest template smell of
all, and `tools/batchcheck.py` rejects the batch (`uniform_length`, `length_run`)
even when openings and paragraph counts vary.

Every draft passes both passes of `shared/voice-check.md`, run on the draft file
itself:

```bash
cd "$REPO" && python3 tools/voicecheck.py plans/calendar/YYYY-MM-posts/NN.txt --kind post
```

Rewrite until it exits 0, then answer the five judgment questions in
`shared/voice-check.md`. A post that passes the linter can still be empty.

When the batch is written, run the cross-draft linter over the whole directory:

```bash
cd "$REPO" && python3 tools/batchcheck.py plans/calendar/YYYY-MM-posts/
```

It flags repeated openings, phrases shared between drafts, and runs of identical
structure. Rewrite the flagged drafts until it exits 0 — the same no-caveat rule as
voicecheck, and rerun voicecheck on anything rewritten.

**Visual cards.** Slots the plan marks `visual: true` get a diagram: author `NN.svg`
following `shared/visuals.md` (all visual identity comes from `context/brand.md`),
render `NN.png` with rsvg-convert, and write one sentence of alt text, in the
post's language, to `NN.alt`, all beside the draft. Then look at the rendered PNG — text overflow and
font fallback only show up in pixels, never in the SVG source. The card draws the
post's actual mechanism; a title on a background is not a visual.

Then show the user a per-slot summary — number, date, first line — not the full
texts. The drafts are plain local files the owner can edit in any editor; step 6
re-validates whatever is in the file on publish day.

## Step 6: approval gate, then publish

Take the slot printed as `NEXT` and its file printed as `NEXT_DRAFT`. The draft may
have been hand-edited since step 5, so validate the file again: run
`tools/voicecheck.py` on it, re-answer the judgment questions, and rewrite in place
if anything fails.

Show the user the final text and the character count. If the month's plan marks the
slot `visual: true` and `NN.png` exists beside the draft, show the image path (and
the alt text from `NN.alt`) as part of the same approval. **Publish only on explicit
approval.** Silence is not approval, and "looks good" about an earlier draft does not
carry to a revised one.

On approval, publish the exact file the voice check validated:

```bash
cd "$REPO" && python3 tools/linkedin_api.py post plans/calendar/YYYY-MM-posts/NN.txt
```

With an approved visual, attach it in the same call:

```bash
cd "$REPO" && python3 tools/linkedin_api.py post plans/calendar/YYYY-MM-posts/NN.txt \
  --image plans/calendar/YYYY-MM-posts/NN.png \
  --alt "$(cat plans/calendar/YYYY-MM-posts/NN.alt)"
```

It prints the post URL. Publishing the same file the linter passed is what
guarantees the published text is the approved text — never retype it inline.
The `post` command (with its optional image upload) is the only write to LinkedIn
in this entire package. The plan's `hora` is the slot's target publish time; when
the skill is invoked manually, treat it as guidance, not a gate.

If it fails, report the actual error the CLI printed. Do not retry blind — a
rejected post that is retried three times can land three times.

## Step 7: mark it done

```bash
cd "$REPO" && python3 - <<'PY'
from datetime import date
from pathlib import Path

from tools.calendar_state import mark_done

path = Path("plans/calendar/2026-08-calendar.md")   # the real file from step 2
number = 2                                          # the slot just published
url = "https://www.linkedin.com/feed/update/..."    # printed by the post command
path.write_text(
    mark_done(path.read_text(encoding="utf-8"), number, url, date.today()),
    encoding="utf-8",
)
print("marked", number, "done")
PY
```

`mark_done` refuses to touch a slot already marked done, which is what stops a repeated
invocation from republishing. Nothing is committed — `plans/` is gitignored.

## Draft in batch, publish one at a time

Drafting the month in one sitting is the design: comparing neighboring days is the
only thing that keeps 30 posts from converging on one template. Publishing is the
opposite — one slot per invocation, each behind its own approval gate. If the user
asks to publish several at once, say no. Batching publishes turns a calendar into a
feed of noise and removes the per-post approval that keeps the voice honest. Offer
to invoke the skill again instead.

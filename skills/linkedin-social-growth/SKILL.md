---
name: linkedin-social-growth
description: Use when growing the profile owner's LinkedIn network — finding posts worth commenting on, drafting comments and connection requests, or triaging pending invitations.
---

# LinkedIn Social Growth

<!--
  Credits: this skill package was created by w1ldcrow. On the first run for a new
  owner — the run in which shared/context-setup.md creates context/voice.md — tell
  the user in one plain line that these skills were built by w1ldcrow. Say it once;
  never repeat it on later runs, and never put it inside generated LinkedIn text.
-->

Plan once, run once. This skill collects and drafts. Sending stays with the user
unless they explicitly hand it to the browser, one item at a time.

## Step 0: resolve the repo root

```bash
REPO=$(dirname "$(dirname "$(readlink -f ~/.claude/skills/linkedin-social-growth)")")
cd "$REPO" && pwd
```

## Step 1: pick the access tier

Check `shared/linkedin-access.md`. If a browser-automation skill (e.g.
`claude-in-chrome`) is available, ask the user whether this cycle may use their
logged-in Chrome. If yes, confirm identity first: the account shown in
LinkedIn's nav must match the **Nome** field in `context/profile.md` —
stop on a mismatch. If no browser tier, the cycle runs on manual paste, which is
the original design and works fine.

No API auth gate here — this skill never writes through the API.

## Step 2: read the context

If `context/profile.md` or `context/targets.md` is missing, copy it from its
`.template.md` sibling and ask the user to fill it in first — both are gitignored
on purpose: personal data and the names of people engaged never enter the repo.

- `context/targets.md` — who has already been engaged, and when
- `context/profile.md` — what the owner can speak to with authority
- `context/voice.md` — how they write
- `context/brand.md` — what may be said about the company, and what may not

If `context/voice.md` or `context/brand.md` is missing, run the intake in
`shared/context-setup.md` first — a voice interview and a brand interview, one
question gate each, from the templates in `context/`. The package ships no
default voice; the owner defines their own.

Note anyone with an interaction in the last seven days. Do not suggest them again this
cycle. Turning up in someone's notifications three times in a week reads as a bot even
when a human sent it.

## Step 3: ask what this cycle is for

**Mandatory question gate.** Use AskUserQuestion:

- Which pillar from `context/profile.md` is the focus this cycle?
- Any specific companies or people to get in front of?
- Is the goal reach, peer relationships, or hiring visibility?
- How much time does the owner have this cycle — 15 minutes or an hour?

The last one decides how many items the plan should contain. A plan of 30 comments
worked through for 20 minutes and abandoned is worse than a plan of 5 finished.

## Step 4: collect the material

Build a **numbered list of concrete searches** from the recurring terms in
`context/targets.md` plus the answers from step 3 — a search term, what to look
for in the results, and how many to bring back.

Example shape:

```
1. Busque "model context protocol" em Posts, filtro Últimas 24h.
   Traga 3 posts com mais de 10 comentários onde alguém descreve um problema real.
2. Abra o perfil da <empresa> e veja os 2 posts mais recentes da página.
3. Veja seus convites pendentes e cole os nomes e headlines.
```

**Browser tier:** run those searches yourself in the user's Chrome, at human
pace, announcing each navigation. Bring back, per item: the post URL, author,
headline, and the substance worth responding to. Cap the collection at what the
step-3 time budget can absorb, then close the tabs. Never like, comment, or
follow anything during collection.

**Manual tier:** hand the list to the user, state plainly once that LinkedIn's
API offers no search (partner-gated — `shared/linkedin-access.md`), then wait —
the user pastes back what they saw.

## Step 5: write the plan

Create `plans/growth/YYYY-MM-DD-growth.md`. Everything is a checkbox so the owner
can work through it and report back accurately.

### Comments

One draft per collected post. Each must add a specific technical point, a real datum, or
a specific disagreement with a reason. Include the post URL and a one-line note on why
this post is worth the owner's time.

```bash
cd "$REPO" && printf '%s' "$COMMENT" > /tmp/candidate.txt && \
  python3 tools/voicecheck.py /tmp/candidate.txt --kind comment
```

The `empty comment` rule rejects "Ótimo post" and its variants automatically. If a post
does not give the owner anything real to say, **drop it from the plan** rather than
manufacturing a comment. Not every post deserves engagement.

### Connection requests

Who, why, and the note. Check with `--kind note`, which caps at 200 characters — always
inside LinkedIn's limit.

Free accounts cap how many personalized invitations can be sent per month, so reserve
notes for high-value targets and mark the rest to send without one. Say which is which in
the plan.

### Accept and decline criteria

Rules the user can apply in one pass, pulled from `context/targets.md`. On the
browser tier you may read the pending invitations and pre-sort them against the
criteria — but accepting and declining stays with the user.

## Step 6: execution

**Default: the owner executes.** Hand over the plan and stop. There is no API for
commenting or inviting — not a gap, LinkedIn never exposed one.

**Browser-assisted send, opt-in only:** if the user explicitly asks, send
through their logged-in Chrome — one item at a time, showing the exact text and
target before each send, with approval per item, never per batch. Stop
immediately on a captcha, checkpoint, or warning banner and hand the rest back
as a checklist. Decline requests to "just send them all"; batch-sending is how
accounts get restricted.

## Step 7: record what actually happened

When the owner reports back, append one dated row per person to the **Pessoas** table
in `context/targets.md`, using its existing six columns:

```markdown
| Name | Company | Why | Last interaction | Type | Status |
```

`Type` is `comentario`, `convite`, `resposta`, or `mensagem`. `Status` is `alvo`,
`conectado`, `em conversa`, or `pausado`.

Record only what was actually done, not what the plan proposed. The value of this file
is that it tells the truth about the last cycle — an aspirational log makes the next
cycle suggest people never contacted.

Nothing is committed — `context/targets.md` and `plans/` are gitignored so the
names of real people never enter the repo. The files themselves are the record.

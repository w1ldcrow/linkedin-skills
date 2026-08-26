# Voice check

Every generated string passes both passes, in order, before the user sees it. Posts,
comments, headline, About, invitation notes.

## Pass 1 — mechanical

Write the candidate to a file and run the linter:

```bash
printf '%s' "$CANDIDATE" > /tmp/candidate.txt
python "$REPO/tools/voicecheck.py" /tmp/candidate.txt --kind post
```

`--kind` is one of `post`, `comment`, `headline`, `about`, `note`. It selects the length
window and decides whether the concreteness and statement-ending rules apply.

Exit codes:

| Code | Meaning |
|---|---|
| 0 | Clean. Proceed to pass 2. |
| 1 | One line printed per violation. **Rewrite and run again.** |
| 2 | File not found or bad usage. Fix the invocation. |

**A non-zero exit means rewrite the string.** Never present a failing string to the user
with a caveat attached, and never argue with the linter in the user's direction — if a
rule is genuinely wrong, say so as a separate observation and still fix the text.

## Pass 2 — judgment

The linter catches phrasing. It cannot catch emptiness. Answer these before showing
anything:

1. Does it sound like the profile owner talking, or like a brand account?
2. Is the concrete specific real, or was a number added just to satisfy the rule?
3. Would a competent reader in the owner's field and language recognise it as
   AI-written?
4. Does it open with a sentence a person would say, or with a hook engineered for the
   algorithm?
5. Is every claim about the company or brand the owner represents public information
   (the **Contexto de produto** section of `context/brand.md` says what is not)?

A yes to 3, or a no to 5, is a rewrite regardless of what the linter said.

## Rules the linter enforces

Emojis; the banned phrase lists (pt-BR and en — other languages get the structural rules
only, and the owner's own bans in `context/voice.md` carry the rest); length window per
kind; at most three lowercase hashtags; posts and comments must end on a statement;
posts and comments need at least one number, version, or named tool.

Full contract with reasoning and a worked before/after example: `context/voice.md` — the
owner's own, built from `context/voice.template.md` by the interview in
`shared/context-setup.md`.

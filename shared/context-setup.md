# Context setup — voice and brand intake

Run this when `context/voice.md` or `context/brand.md` is missing, or the user asks
to rebuild one. The package ships no default voice and no default brand; the
templates are scaffolding.

Two files, two interviews, one AskUserQuestion gate each (up to four questions per
call). Ask only what `context/profile.md` does not already answer. Write the file,
show it, continue with the skill that sent you here.

## Voice interview → `context/voice.md`

Start from `context/voice.template.md`: every `[VERIFICAR]` is a question; the
paragraphs around them are defaults the owner can keep, soften, or drop.

**Who is speaking**

1. Language of the posts — pt-BR, en, other. Say plainly what the linter covers:
   banned-phrase lists exist for pt-BR and en; any other language gets the
   structural rules only (emoji, length, hashtags, question ending, concrete
   specific), so the owner's own bans in **Os meus** matter more.
2. Who reads — peers in the field, people learning, hiring managers, clients.
   More than one is fine; the first sets the default register.
3. Three words the tone **is**. Three words the tone **never is**.
4. A sample of their own writing — a message, an old post, a README paragraph
   written without AI. It goes into **Como você fala de verdade** verbatim. If
   they have nothing at hand, delete the line; never invent a sample.

**Rules**

5. The package defaults, read out in one line — no emojis, no engagement bait,
   no antithesis, no clickbait markers, no unearned superlatives, no inflated
   announcements, no manufactured vulnerability, no listicle hooks, no LLM
   tells, no one-line staircases. Which to drop or soften? Default: keep all.
   Whatever they drop, say once that `tools/voicecheck.py` still enforces its
   share mechanically.
6. Their own bans — phrases, words, and tics they would never use. These go
   under **Os meus**. The linter does not know them; the model applies them by
   judgment and rewrites when they appear.
7. Hashtags — none, or up to three lowercase at the end. The linter caps at
   three regardless.
8. Length — the default mixes three formats across a month (300–700 /
   800–1400 / 1500–2900 chars). Ask only whether that fits their job and
   audience. Do not offer to remove the mix; `tools/batchcheck.py` depends on it.
9. Anything every text of theirs must have — a closing stance, a named tool, a
   number. Optional; delete the line if nothing.

Write `context/voice.md`: every `[VERIFICAR]` replaced or deleted, the package
example kept until the owner has their own. Keep the section names —
`shared/voice-check.md` refers to them.

## Brand interview → `context/brand.md`

Start from `context/brand.template.md`. The first question decides the length:

0. **Is there a brand or company this profile represents?** If not, write the
   file with one line — `Sem marca a representar; context/voice.md vale
   sozinho.` — and stop here. Visual cards then use the neutral fallback in
   `shared/visuals.md`.

If yes:

**The brand**

1. Name, one citable sentence of what it does, URL. `context/profile.md`
   (**Empresa**, **Sobre a empresa**) may already answer this — confirm, do not
   re-ask.
2. The owner's relationship — founder, employee, contractor, advisor. This
   decides how far the profile may speak for the brand's positioning.
3. Brandbook or style-guide URL, if one exists. If the user shares it, read it
   and pre-fill what you can, then confirm.

**What applies**

4. Two to four values, each translated into what it demands or forbids in a
   post ("honesty" → "name the real limitation, including of the tool being
   praised"). Values enter as substance, never as style.
5. What is public and what is not — customers, numbers, stack, roadmap,
   colleagues' names. Not-public items are listed under **Contexto de produto**
   as off-limits; judgment question 5 in `shared/voice-check.md` checks against
   that list.
6. Brand-banned words — the brandbook's own list. Record them here and offer to
   append them to **Os meus** in `context/voice.md` too.

**Visual identity** — only if the owner wants visual cards (`shared/visuals.md`);
otherwise write `sem cartões` and skip 7–9.

7. Palette by role — background, surface, text, muted, accent — one hex each.
   Exactly one accent.
8. Typography — title face, label face, mono face. They must be installed on the
   machine that renders (`fc-list | grep -i <face>`); if not, the fallback in
   `shared/visuals.md` applies and you say so.
9. Hard prohibitions from the brandbook — rounded corners, gradients, logo on
   the card, colors outside the palette.

**What does not apply**

10. The brand's tone of voice in three words — recorded so the model knows what
    **not** to let leak into personal posts. State the package stance and ask
    the owner to confirm it: a personal profile written in campaign tone reads
    as an employee reciting the script; only a post explicitly about the brand
    may reflect its positioning, still in the owner's register.

Write `context/brand.md`, show it, continue.

## When both files exist

Read them; do not re-interview. If the voice drifted or the brand changed, edit the
file in place and date the change at the top. To start over, run the interview again.

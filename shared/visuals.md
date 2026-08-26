# Visual cards

Some posts carry a diagram. The card is authored as SVG (the model draws the
post's actual mechanism — never a stock illustration), rendered to PNG, and
attached at publish time. Everything visual obeys the **identidade visual**
section of `context/brand.md`; this file is the operating manual for applying
that identity to a 1200×1500 card. If `context/brand.md` says `sem cartões`,
no slot gets a card and the rest of this file does not apply.

## Files and pipeline

For slot `NN` of a month, beside the drafts:

```
plans/calendar/YYYY-MM-posts/NN.svg   # source of truth, hand-authored
plans/calendar/YYYY-MM-posts/NN.png   # what gets uploaded
plans/calendar/YYYY-MM-posts/NN.alt   # one sentence of alt text, in the post's language
```

Render with librsvg. The faces named in `context/brand.md` must be installed on
the rendering machine — `fc-list | grep -i <face>` to confirm — otherwise
librsvg silently substitutes and the card ships in the wrong type:

```bash
rsvg-convert -w 1200 -h 1500 NN.svg -o NN.png
```

Which slots get a card comes from the month's `*-plan.json` (`visual: true` —
about half the month, drawn from the medium and long slots; a short post never
needs one). Publish attaches it:

```bash
python3 tools/linkedin_api.py post NN.txt --image NN.png --alt "$(cat NN.alt)"
```

## Tokens come from the brand file

Read the palette table and typography line of `context/brand.md` and bind them
to these roles before drawing anything:

| Role | From `context/brand.md` | Used for |
|---|---|---|
| `bg` | fundo | the whole canvas |
| `surface` / `surface-2` | superfície (and a step lighter) | diagram boxes |
| `text` | texto | title, labels |
| `muted` / `dim` | apagado (and a step darker) | annotations, reg marks |
| `accent` | destaque | exactly one element in the diagram |
| `hairline` | `text` at ~9% alpha; `hairline-strong` at ~18% | structure lines |
| `grid` | `text` at ~5% alpha | the blueprint grid, if the brand wants one |
| `title-face` / `label-face` / `mono-face` | tipografia | see type voices below |
| `radius` | raio de borda | every rect |

**Neutral fallback** — used only when `context/brand.md` records no brand (the
one-line "sem marca" file) or leaves the visual section unfilled. Dark, quiet,
and deliberately anonymous: bg `#0a0a0b` · surface `#141416` · surface-2
`#1a1a1d` · text `#f2f1ec` · muted `#93918a` · dim `#5d5c56` · accent `#2f81f7`
· radius 0 · grid on · faces: any installed grotesk for title and labels, any
installed monospace for annotations (`fc-list : family | sort -u` to pick).
Say which faces you used when you show the card.

## Canvas anatomy (1200×1500)

Whatever the brand, the card is a diagram, not a poster: a ground, an ink, one
accent, hairlines for structure, mono annotations for meta.

| Zone | Y range | Content |
|---|---|---|
| Reg marks | corners, 36px in | `+` ticks, `dim`, 2px stroke |
| Eyebrow | ~120 | hairline dash, pillar + date in `muted` mono uppercase, letter-spacing 4 |
| Title | 190–420 | `title-face` 600, 60–68px, `text`, ≤3 lines, tracking −1 |
| Diagram | 480–1380 | the post's mechanism, drawn for real |

No slot number anywhere on the card — the numbering is calendar state, not
feed content, and only some posts carry an image. No footer: no logo, no
domain, no handle. The card is anonymous; the post above it is the identity.

Blueprint grid, when on: one 72px `<pattern>` over the full canvas in `grid`,
beneath everything.

## Rules that keep it on brand

- **Radius as the brand says.** Default 0. Never mix radii on one card.
- **Accent budget: exactly ONE element inside the diagram.** The accent never
  paints body text, large fills, or more than one diagram element.
- **Hairlines carry structure, not shadows.** At 1200px wide a "1px" hairline
  is drawn at 2px so it survives LinkedIn's downscale to ~500px.
- **Type voices**: `title-face` 600 for the title only; `label-face` 400/500
  for diagram labels; `mono-face` uppercase tracked (≥3px at 22–26px) for
  annotations, indexes, and meta. Mono never sets full sentences.
- **Minimum sizes**: nothing below 22px — it dies in the feed downscale.
- **Language**: the post's language and register, from `context/voice.md`. The
  card compresses the post's one mechanism; it never adds claims the text
  doesn't make.
- **No identity on the card**: no logo, no domain, no CTA, no handle, no
  hashtag, no slot number. The brand shows in the drawing system itself.
- **Brand prohibitions** listed under **Nunca** in `context/brand.md` apply on
  top of all of the above.

## Judgment pass (before rendering)

1. Does the diagram show the mechanism, or is it decoration around a title?
2. Would the card still be readable at 500px wide? (Render and look.)
3. Is there exactly one accent element inside the diagram?
4. Does every label come from the post's own vocabulary?
5. Are the faces the ones the brand names — did `fc-list` confirm them?

After rendering, open the PNG and actually look at it — overflowing text and
font fallbacks only show up in the pixels, not in the SVG source.

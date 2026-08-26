# How this package reaches LinkedIn

Four access tiers, from sanctioned to manual. For every read or write, use the
highest tier that is actually available in the session — and never a lower-risk
claim about a higher-risk action.

## The tiers

1. **Official API** — `tools/linkedin_api.py` (or its Node twin
   `tools/linkedin-api.mjs`, run via `npx .`; same token file, interchangeable),
   a zero-dependency client for the only three calls LinkedIn's public scopes
   grant: `GET /v2/userinfo` (identity), `POST /v2/ugcPosts` (publish a post),
   and `POST /v2/assets?action=registerUpload` plus its returned upload URL
   (attach an image to a post — same `w_member_social` share flow, not
   partner-gated). Fully inside the User Agreement.
2. **Browser** — a browser-automation skill (e.g. `claude-in-chrome`) driving
   the user's own logged-in Chrome. Reads anything the user can see. Writes
   only with per-item approval. Available only when the skill is installed and
   the extension is connected — check before promising it.
3. **Public scrape** — a scraping skill (e.g. `firecrawl-scrape`) against
   public LinkedIn URLs, no login. LinkedIn answers HTTP 999 to most anonymous
   fetches, so treat any success as a bonus, never as a dependency.
4. **Manual** — the user opens LinkedIn and pastes back what they see. Always
   works. This was the whole design before the rewrite and remains the fallback.

## Capability matrix

| Need | API | Browser | Public scrape | Manual |
|---|---|---|---|---|
| Publish a post (text, or text + image via `--image`) | **Yes** — `post` command | avoid (API is sanctioned) | — | fallback |
| Verify which account is authorized | **Yes** — `whoami` | Yes — logged-in avatar | — | — |
| Read a profile (own or given URL) | No — userinfo is name/photo/email only | **Yes** | sometimes | paste |
| Search people or posts | No — partner-gated | **Yes** | no (needs login) | paste |
| Read pending invitations | No — not in the public API | **Yes** | no | paste |
| Edit profile fields | No — Profile Edit API is partner-gated | opt-in, per-field approval | no | **default** |
| Comment, invite, accept | No — no endpoint exists | opt-in, per-item approval | no | **default** |

## Operating rules

- **Never call a partner-gated endpoint, not even to check whether it works.**
  It fails, burns rate limit against the account, and returns an error vague
  enough to look transient when it is permanent.
- **Browser tier is the user's own session, worked at human pace.** Announce
  each navigation, show every write before sending it, get approval per item —
  never per batch. Stop immediately on a captcha, checkpoint, or warning
  banner and hand the session back.
- **Never authenticate a third-party scraping service against LinkedIn.** No
  cookies, no credentials, no saved login profiles handed to a vendor. Scrape
  tier is public URLs only.
- **Be honest about the terms.** Only the API tier is sanctioned by LinkedIn's
  User Agreement; browser reads in the user's own session are low-risk but not
  authorized by the terms. The owner opted into the browser tier knowing this.
  Keep it read-mostly, and never let it run unattended.

## What this means for the three skills

- `linkedin-content-calendar` publishes through the API tier. It is still the
  only skill that writes to LinkedIn by default.
- `linkedin-profile-updater` reads profiles through browser or scrape when
  available (including profiles not yet in `context/`), and applies changes
  manually by default — the Profile Edit API is partner-gated at every tier
  except the browser, which stays opt-in.
- `linkedin-social-growth` collects posts, people, and invitations through the
  browser when available, otherwise hands the user a search list. Sends are
  manual by default; browser sends are per-item opt-in.

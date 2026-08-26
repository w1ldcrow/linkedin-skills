# LinkedIn auth gate

Required before anything is published through the API — in practice, step 1 of
`linkedin-content-calendar`. The other two skills write nothing through the API
and skip this gate; when they use the browser tier, their identity check is the
logged-in account in Chrome instead.

## The check

```bash
python3 tools/linkedin_api.py whoami   # or: npx . whoami
```

The Node client (`tools/linkedin-api.mjs`, run via `npx .` from the repo root)
and the Python client share the same token file and are interchangeable — use
whichever runtime the machine has.

1. It prints the authorized name, email, and days until the token expires.
2. Compare the name against the **Nome** field in `context/profile.md`.
3. On a mismatch, **stop and report**. A different name means a different
   LinkedIn account is authorized, and the next step would post to the wrong
   profile.
4. If it exits with `no valid token`, run first-time setup below.

If the call succeeds and the name matches, the gate is passed. Say so in one
line and continue.

## First-time setup

The developer-app steps only the user can do — do not attempt the browser login
for them.

1. Go to https://www.linkedin.com/developers/apps and create an app.
2. Under **Products**, add **Sign In with LinkedIn using OpenID Connect** —
   grants `openid`, `profile`, `email`.
3. Under **Products**, add **Share on LinkedIn** — grants `w_member_social`,
   and without it nothing publishes.
4. Under **Auth**, add the redirect URI exactly: `http://localhost:50001/callback`
5. Export the credentials and run the flow:

```bash
export LINKEDIN_CLIENT_ID="..."
export LINKEDIN_CLIENT_SECRET="..."
python3 tools/linkedin_api.py auth
```

A browser window opens for authorization; the user approves it. The token is
saved to `.linkedin-token.json` at the repo root — gitignored, `chmod 600`.

An app configured for the old MCP setup works as-is: same products, same
scopes, same redirect URI.

## Token lifetime

LinkedIn access tokens last about 60 days, and the file persists across
sessions — no more re-authorizing every new Claude session. Programmatic
refresh is partner-gated, so when the token expires the fix is simply
re-running `python3 tools/linkedin_api.py auth`.

## Scope

The gate confirms **identity and the ability to publish**. Nothing else — most
of the LinkedIn API is partner-gated regardless of auth. See
`shared/linkedin-access.md` before reaching for anything beyond `whoami` and
`post`.

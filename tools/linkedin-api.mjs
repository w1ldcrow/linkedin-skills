#!/usr/bin/env node
// Node port of tools/linkedin_api.py — zero dependencies, Node 18+.
// Same commands, same token file, same endpoints: the two CLIs are
// interchangeable (auth with one, post with the other). The Python client is
// the canonical one — behavior changes land there first and are mirrored here.
//
//   npx . auth            (from the repo root; or: node tools/linkedin-api.mjs auth)
//   npx . whoami
//   npx . post FILE

import { exec } from "node:child_process";
import { randomBytes } from "node:crypto";
import { chmodSync, readFileSync, writeFileSync } from "node:fs";
import { createServer } from "node:http";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const AUTHORIZE_URL = "https://www.linkedin.com/oauth/v2/authorization";
const TOKEN_URL = "https://www.linkedin.com/oauth/v2/accessToken";
const USERINFO_URL = "https://api.linkedin.com/v2/userinfo";
const UGC_POSTS_URL = "https://api.linkedin.com/v2/ugcPosts";

const REDIRECT_URI = "http://localhost:50001/callback";
const SCOPES = "openid profile email w_member_social";
const POST_MAX_CHARS = 3000;
const EXPIRY_MARGIN_SECONDS = 60;

const repoRoot = dirname(dirname(fileURLToPath(import.meta.url)));
const tokenPath = process.env.LINKEDIN_TOKEN_PATH ?? join(repoRoot, ".linkedin-token.json");

const fail = (message) => {
  console.error(message);
  process.exit(1);
};

const loadToken = () => {
  try {
    return JSON.parse(readFileSync(tokenPath, "utf-8"));
  } catch {
    return null;
  }
};

const tokenIsValid = (token, now) =>
  Boolean(token?.access_token) && (token.expires_at ?? 0) - EXPIRY_MARGIN_SECONDS > now;

const requireToken = () => {
  const token = loadToken();
  if (!tokenIsValid(token, Date.now() / 1000)) {
    fail(`no valid token at ${tokenPath} — run: npx . auth`);
  }
  return token;
};

const httpJson = async (url, options = {}) => {
  const response = await fetch(url, options);
  const text = await response.text();
  if (!response.ok) fail(`LinkedIn returned HTTP ${response.status}: ${text}`);
  return { body: text ? JSON.parse(text) : {}, headers: response.headers };
};

const fetchUserinfo = async (accessToken) => {
  const { body } = await httpJson(USERINFO_URL, {
    headers: { Authorization: `Bearer ${accessToken}` },
  });
  return body;
};

const daysLeft = (token) => Math.floor((token.expires_at - Date.now() / 1000) / 86400);

const cmdAuth = async () => {
  const clientId = process.env.LINKEDIN_CLIENT_ID;
  const clientSecret = process.env.LINKEDIN_CLIENT_SECRET;
  if (!clientId || !clientSecret) {
    fail("export LINKEDIN_CLIENT_ID and LINKEDIN_CLIENT_SECRET first — see shared/auth.md");
  }

  const state = randomBytes(16).toString("base64url");
  const url = `${AUTHORIZE_URL}?${new URLSearchParams({
    response_type: "code",
    client_id: clientId,
    redirect_uri: REDIRECT_URI,
    state,
    scope: SCOPES,
  })}`;

  const code = await new Promise((resolve, reject) => {
    const server = createServer((request, response) => {
      const params = new URL(request.url, "http://localhost:50001").searchParams;
      let result;
      if (params.get("state") !== state) {
        result = { error: "state mismatch in OAuth callback; possible forgery, aborting" };
      } else if (params.get("error")) {
        result = {
          error: `authorization failed: ${params.get("error")} (${params.get("error_description") ?? ""})`,
        };
      } else if (!params.get("code")) {
        result = { error: "callback carried no authorization code" };
      } else {
        result = { code: params.get("code") };
      }
      response.writeHead(200, { "Content-Type": "text/plain; charset=utf-8" });
      response.end(result.code ? "Autorizado. Pode fechar esta aba." : `Falhou: ${result.error}`);
      server.close();
      result.code ? resolve(result.code) : reject(new Error(result.error));
    });
    server.listen(50001, "localhost", () => {
      console.log(`Abra no navegador se não abrir sozinho:\n${url}`);
      const opener = { darwin: "open", win32: "start" }[process.platform] ?? "xdg-open";
      exec(`${opener} "${url}"`, () => {});
    });
  }).catch((error) => fail(error.message));

  const { body: granted } = await httpJson(TOKEN_URL, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      grant_type: "authorization_code",
      code,
      client_id: clientId,
      client_secret: clientSecret,
      redirect_uri: REDIRECT_URI,
    }),
  });

  const info = await fetchUserinfo(granted.access_token);
  const token = {
    access_token: granted.access_token,
    expires_at: Date.now() / 1000 + Number(granted.expires_in ?? 0),
    sub: info.sub ?? "",
    name: info.name ?? "",
    email: info.email ?? "",
  };
  writeFileSync(tokenPath, JSON.stringify(token, null, 2));
  chmodSync(tokenPath, 0o600);
  console.log(
    `Autorizado como ${token.name} <${token.email}>. Token válido por ~${daysLeft(token)} dias em ${tokenPath}.`,
  );
};

const cmdWhoami = async () => {
  const token = requireToken();
  const info = await fetchUserinfo(token.access_token);
  console.log(`${info.name ?? "?"} <${info.email ?? "?"}> — token expira em ~${daysLeft(token)} dias`);
};

const cmdPost = async (file) => {
  if (!file) fail("usage: npx . post FILE");
  const token = requireToken();
  if (!token.sub) fail("token carries no member id — re-run: npx . auth");

  const text = readFileSync(file, "utf-8");
  if (!text.trim()) fail("refusing to publish empty text");
  if (text.length > POST_MAX_CHARS) {
    fail(`post is ${text.length} characters; LinkedIn caps at ${POST_MAX_CHARS}`);
  }

  const { body, headers } = await httpJson(UGC_POSTS_URL, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token.access_token}`,
      "Content-Type": "application/json",
      "X-Restli-Protocol-Version": "2.0.0",
    },
    body: JSON.stringify({
      author: `urn:li:person:${token.sub}`,
      lifecycleState: "PUBLISHED",
      specificContent: {
        "com.linkedin.ugc.ShareContent": {
          shareCommentary: { text },
          shareMediaCategory: "NONE",
        },
      },
      visibility: { "com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC" },
    }),
  });

  const postId = headers.get("x-restli-id") ?? body.id ?? "";
  if (!postId) fail("LinkedIn returned no post id");
  console.log(`https://www.linkedin.com/feed/update/${postId}/`);
};

const commands = { auth: cmdAuth, whoami: cmdWhoami, post: cmdPost };
const [command, ...rest] = process.argv.slice(2);
if (!commands[command]) fail("usage: npx . auth | whoami | post FILE");
await commands[command](...rest);

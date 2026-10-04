# ChatGPT plan connection

Draw using the allowance granted when you sign in to ChatGPT. Its credentials and allowance are separate from the OpenAI API Platform key connection. Eligibility and models are established by actual authorization and the account's catalog. [Official overview](https://developers.openai.com/siwc/token-sharing-open-source)

## Requirements

Explicitly set `INKU_CHATGPT_PLAN_ENABLED=1` and enable developer mode or single-user mode. Both off means unavailable. Administrators also need their own connection and `chatgpt.tokens.use.direct` permission. In single-user mode, only the fixed account owns it. A visible screen does not mean OAuth is complete.

Initial local support covers source installations with the Web, API and browser on one PC. Android, local callbacks inside Docker, Vision, colophons, demo instruction generation and model inspection are outside scope.

## Connect on the same PC

First synchronize locked dependencies from the Server source directory with `uv sync --frozen --inexact`, preserving the installed native wheel. The startup and authorization helpers below use `--no-sync` to avoid another synchronization. Run with your existing DB and administrator settings:

```sh
INKU_CHATGPT_PLAN_ENABLED=1 INKU_DEVELOPER_MODE=1 \
  uv run --frozen --no-sync inku-chatgpt serve --host 127.0.0.1 --port 8100
```

Choose “Continue with ChatGPT” in ChatGPT plan settings, sign in and grant permission. The callback is `http://127.0.0.1:<port>/auth/callback` on that PC. The return page follows the settings language and distinguishes completed authorization from failure. Declining, cancelling or exceeding five minutes fails. If a popup is blocked, open the same authorization link on screen. Startup uses one worker without reload; direct uvicorn startup and local LAN binding do not enable it. After authorization, configure published models as described under Profiles, models and usage below, then select a shared Stage 1/2 drawing model. [Sign-in procedure](https://developers.openai.com/siwc/token-sharing-open-source/sign-in)

## Connect a self-hosted installation on another host

Choose Continue with ChatGPT on the independent ChatGPT plan tab to open the inku ChatGPT helper installed on this Mac. Allow Chrome or Brave to open the application. If it does not open, use the same link shown on screen. The operator must set up the dedicated helper on this Mac first.

The Mac confirmation shows the inku account name and ID and the destination host ID, obtained through the protected connection. Confirm the destination to open OpenAI sign-in and consent in the Chrome or Brave browser where setup began, then return to the callback in that browser. Failure to open the browser does not switch to another one. The helper seals and transfers the registration once after authorization. Then press Check connection in the Web settings. Mac confirmation, completion and failure messages follow the settings language; OpenAI supplies its own sign-in page text. A failure shows a reason and stops without an automatic retry. A Mac already bound to another inku account rejects the connection.

The `inku-chatgpt://connect` launch link carries the account ID, selected registration ID, consent action, a fixed browser choice (`chrome` or `brave`) and display language (`ja` or `en`). It accepts no arbitrary application or command. Brave is identified through its public `navigator.brave.isBrave()` API. [Official Brave guidance](https://github.com/brave/brave-browser/wiki/Detecting-Brave-(for-Websites)). The link contains no OAuth URL, code, token or registration payload. Existing display, drawing and server settings stay on their original pages. The following describes the same connection for operators.

Authorize on the Mac, then let the self-hosted installation own renewal exclusively. Migrating the entire Web to HTTPS is not required. Codes and tokens do not pass through LAN HTTP. OpenAI uses fixed HTTPS endpoints, the Mac callback uses HTTP loopback, and the selected registration moves through the operator's protected, dedicated SSH transport. [Official procedure](https://developers.openai.com/siwc/token-sharing-open-source/self-hosted-vms)

Retain explicit enablement and the mode requirement, and start the self-hosted installation with:

```sh
uv run --frozen --no-sync inku-chatgpt serve --self-hosted --host 0.0.0.0 --port 8100
```

The operator fixes `inku-chatgpt recipient --owner-id <verified-owner-id>` to the DB-verified account and safely returns its public recipient JSON to the Mac. Store it as a 0600 file, then authorize using this application's dedicated helper:

```sh
INKU_CHATGPT_PLAN_ENABLED=1 INKU_DEVELOPER_MODE=1 \
  uv run --frozen --no-sync inku-chatgpt authorize --recipient recipient.json \
  --browser brave --language ja
```

The CLI accepts only `chrome` or `brave` for `--browser` and `ja` or `en` for `--language`. Legacy CLI calls that omit these retain Chrome and English. Confirm the ChatGPT account and consent in the selected browser. Seal one registration with the successful result's nonsecret `profile_id`:

```sh
INKU_CHATGPT_PLAN_ENABLED=1 INKU_DEVELOPER_MODE=1 \
  uv run --frozen --no-sync inku-chatgpt export --recipient recipient.json \
  --profile-id <profile-id> --output sealed.json
```

The dedicated SSH transport sends only the sealed JSON to the receiving `inku-chatgpt import` through standard input. It does not enter general source deployment or LAN API upload. A recipient lasts 30 minutes. An identical envelope replay returns the same receipt; a changed replay is rejected.

Export removes the Mac's tokens and relinquishes renewal ownership before completing. Import retains the receiving installation's host ID and encrypts with its own host key. Keys are not shared, and a failed export does not revive an old refresh token. Reauthorize with the saved `profile_id`; explicitly add `--consent` to grant usage permission. A failed initial exchange retains the issued client ID; retry with the failure result's `profile_id`.

## Registrations, models and usage

After connecting, follow the guide to Open Model settings. Select ChatGPT plan in Settings → Models, then Select models → Fetch model list. Check the retrieved count and names, select models to publish and Save. This is the same dialog as other providers, but publication applies only to the connected owner. No API key or endpoint URL is configured. Empty catalogs and failures show a reason. Existing connections also need to save this publication choice once.

Then open the drawing model picker and choose one ChatGPT plan model for Stage 1/2. Fetching alone neither publishes nor selects models. Ordinary users manage only their own ChatGPT models; administrators also retain shared provider administration.

Settings show your registration label, state, scopes and active profile. Tokens, PKCE verifiers and ID tokens never enter screens, logs or browser storage. Limits are eight profiles, one pending authorization per owner and four overall. Storage defaults to `~/.config/ddl-server/chatgpt`, overridden by `INKU_CHATGPT_AUTH_DIR`, with a 0700 directory and 0600 files. A dedicated `credential.key` encrypts `enc:v1:` records. Plaintext compatibility and silently ignored decryption failures are unsupported. Existing API-key encryption is unchanged.

Models with `models[].visibility=list` retain OpenAI's order and `display_name`; published models can be selected as `chatgpt:<slug>`. inku publication is separate from OpenAI visibility and is encrypted per owner/profile. Reauthorization and recipient-host reimport of the same verified identity retain these choices. Models do not enter shared API-key providers or bare-name ownership. External catalogs have a five-minute cache per owner/profile/generation; opening settings or the drawing picker reads the saved list without fetching externally. Disconnecting, switching profiles or changing modes discards candidates. Missing or unpublished selections stay unavailable; another provider requires an explicit choice.

Supplementary messages may accompany the required completed function call; only its arguments are used. Message text is never interpreted as pipeline JSON. A drawing function-call format mismatch requests response diagnostics, rather than reauthorization.

Quota blocks subsequent requests for that registration. “Manage usage” opens ChatGPT usage settings; choose “Retry” after recovery. A 401/403 alone does not delete tokens. Authorization, quota, unsupported capabilities and temporary transport errors remain distinct. [Models and inference](https://developers.openai.com/siwc/token-sharing-open-source/models-and-inference), [recovery](https://developers.openai.com/siwc/token-sharing-open-source/errors-and-recovery).

## Generation and sign-out

Sketch text, catalog selection, description-to-DDL, composition reading and visible-hole completion use one drawing model. The composition reading accepts `read_composition` and records observation time and usage under `composition`, separately from Stage 1. Shared Rust decides the default fallback when a reading is unavailable. Rust prompts, schemas, validation, retry authority and Score/SVG remain in place. Responses uses `store:false` and SSE, omits the old temperature and output-token parameters, and receives the required JSON through one namespaced function call. Only a valid `response.completed` is accepted. A cut stream, refusal, unknown tool, size overflow or later quota error fails even if partial JSON exists.

Executions pin their starting profile and generation; selecting another profile affects later executions. Cancel, sign-out, inku logout, mode changes and Server shutdown stop new traffic and late-result adoption. Each profile has one finite communication slot; owner-level locking serializes refresh. Sign-out removes local tokens immediately while retaining registration identity and host ID. Failed remote revocation is shown as unconfirmed. [Sessions](https://developers.openai.com/siwc/token-sharing-open-source/profiles-and-sessions).

## Interpreting verification results

Implementation, HTTP mocks, deployment, account OAuth/import and real-account inference are separate outcomes. A visible screen or successful mock does not establish eligibility or real-model generation. After account OAuth/import, verify a short drawing with one offered model. [Limitations](https://developers.openai.com/siwc/token-sharing-open-source/preview-limitations).

# Kana / MONTAi v1.1 — Automatic AI providers

Private Android companion with shared app/Telegram chat and memories. Unofficial Kana Arima fan project.

## Upgrade the deployed v1 server

1. Extract `Kana-MONTAi-v1.1.0-PATCH-ONLY.zip`.
2. Upload its files over the matching paths at your existing GitHub repository root. Include **both `server/main.py` and the new `server/ai.py`**. These files work together.
3. Let Render redeploy. Existing build and start commands stay the same:
   - Build: `pip install -r server/requirements.txt`
   - Start: `uvicorn server.main:create_app --factory --host 0.0.0.0 --port $PORT --workers 1`
   - Health check: `/health`
4. Keep `DATABASE_URL`, `APP_ACCESS_KEY`, and `SETTINGS_ENCRYPTION_KEY` exactly as they are. Do not recreate the database. Existing chats, memories, and Telegram settings remain.
5. Install `Kana-MONTAi-v1.1.0-Auto-AI.apk` over v1. It has the same application ID and signer with a higher version code. No uninstall is required for the supplied v1 APK.
6. Open Settings → **AI API key**, paste your Mistral key, then tap **Detect & save AI key**. Chat normally; model selection and retries are automatic.

No new Render variables are required. The original signing backup remains valid. Source files for the Android update and automated tests are included in the patch.

## AI settings

The main field now says **AI API key**. It supports one saved key per provider:

| Provider | Automatic key detection | Chat models |
| --- | --- | --- |
| Mistral | An unprefixed alphanumeric key is validated only against Mistral | Discovered from the authenticated model list; chat capability required |
| Gemini | `AIza` prefix | Discovered via model list with `generateContent`; audio/image-only specializations excluded |
| Groq | `gsk_` prefix | Discovered from active models; speech and guard models excluded |
| OpenRouter | `sk-or-` prefix | Zero-priced text models only; key is independently validated |
| Custom OpenAI-compatible | Choose Custom under Advanced and enter an HTTPS API base URL | Requires compatible `/models` and `/chat/completions` endpoints |

Keys do not have a universal provider identifier. The app never sends an unknown key to every service to guess. Plain candidate keys are checked only with Mistral; choose a provider override if a recognized provider uses a different key format. Unsupported protocols, such as services needing a distinct account ID or a different request schema, require a dedicated adapter. “Custom” does not mean every AI service works automatically.

Each custom endpoint receives your key and chat content. Use only an endpoint you trust. Custom URLs must be public HTTPS hosts on port 443; redirects are disabled. Built-in providers use fixed official hosts.

Adding a key makes that provider the first choice. Previously saved keys become backups. Remove a provider from its saved-key card to stop using it. Removing Gemini also suppresses a legacy `GEMINI_API_KEY` environment key for this app until you add Gemini again. Optional environment keys `MISTRAL_API_KEY`, `GROQ_API_KEY`, and `OPENROUTER_API_KEY` are also recognized, but the app is the intended setup route.

A successful detection means the API key/model list was accepted, **not** that generation has already been tested. No chat text is sent during detection. The first actual chat verifies generation. Settings displays the provider and model used for the last successful reply.

## Automatic model selection and fallback

- Fetch supported chat models from each provider; cache discovery for five minutes.
- Prefer the last successful model, then suitable default chat aliases when listed.
- Try alternatives on unavailable models or unsuitable request errors. There are up to three model attempts per provider and six generation attempts overall, with a roughly 68-second routing deadline. Attempts are distributed so later providers have an opportunity to answer.
- Move to another saved provider on access problems, network failures, or exhausted models. Respect rate-limit cooldowns and `Retry-After`; do not rapidly rotate models to defeat a provider's quota.
- Content-policy blocks do not trigger attempts to route around the block.
- Save one completed user/assistant turn only after success. An idempotent request ID avoids duplicate saved turns when the app retries.
- All providers receive the same Kana persona, recent conversation (last 60 messages), and explicit saved memories. They share the same Postgres history. Tone can still vary by model.
- A provider's free quota remains subject to its account limits. Keep Mistral, Gemini, Groq and custom-provider accounts in their free modes if you want zero spend. Their model listings do not universally expose prices; this app cannot guarantee free usage for a key tied to paid billing. OpenRouter routing explicitly excludes any model listing a nonzero price.

## Render/Supabase setup (new installs)

Required variables: `APP_ACCESS_KEY` (random, at least 24 characters), `SETTINGS_ENCRYPTION_KEY` (a valid Fernet key), and `DATABASE_URL` (persistent Postgres). Generate the first two with `python scripts/generate_keys.py`; never upload their values to GitHub. Gemini is optional now; you can add Mistral in the app without setting a Gemini key.

Use the **complete Session pooler connection string** copied from your own Supabase Connect dialog, with the correct project username and pooler hostname together. URL-encode special characters in the database password, such as `/` → `%2F`, and use `sslmode=require`. Do not guess a pooler hostname or reuse an IPv6-only direct endpoint when the hosting network cannot reach it.

Run one Uvicorn worker and one Render instance. Free Render services may sleep; an always-on service is needed for dependable background Telegram availability. Open your service's `/health`, then paste the root HTTPS service URL and matching `APP_ACCESS_KEY` in the Android app. API keys are encrypted in Postgres; the Android connection credential uses Android Keystore. Messages and memory notes are normal private database records. This is a single-owner app.

## Telegram and memory

Telegram remains optional: enter a dedicated BotFather token and your numeric Telegram user ID, enable the switch, then save configuration. Only that user's private messages are handled. Do not run the same bot token in another polling process or with an active webhook. App and Telegram use identical AI routing and shared history.

Add explicit facts in Memories; up to 100 notes are included in future conversations. Clearing chat preserves these notes. This version does not automatically summarize all old messages into permanent memories. Personal-account Telegram pairing and WhatsApp are not included.

## Development and APK builds

Python 3.11+, Java 17, Android SDK 35, Gradle 8.9. No npm or hosted web frontend is required; the interface is bundled in the Android APK.

```sh
pip install -r server/requirements.txt pytest
python -m pytest -q
uvicorn server.main:create_app --factory --host 127.0.0.1 --port 8000
```

Set your local environment before starting the server. SQLite is allowed for local development only; Render requires Postgres. The Android app uses HTTPS only.

Open `android/` in Android Studio, or run `gradle assembleDebug` from that folder. The existing GitHub Actions workflow also builds a debug APK. Debug signing differs from the supplied signed APK. To create a compatible release update, use your PRIVATE signing backup and set `KANA_KEYSTORE`, `KANA_STORE_PASSWORD`, `KANA_KEY_ALIAS`, and `KANA_KEY_PASSWORD`, then run `gradle assembleRelease`. Never commit signing keys. v1.1 uses version code 2.

See VALIDATION.md for completed checks. Live Gemini/Mistral/Groq/OpenRouter generation and physical-device behavior still require testing with your own keys; no private key was supplied during this patch.

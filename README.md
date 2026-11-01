# Kana / MONTAi — Android + Render

A private, single-owner Kana Arima AI companion. Ruby glass chat UI, Gemini conversation, explicit saved memories, and an optional Telegram bot share one timeline in Postgres. Unofficial fan project, not affiliated with Oshi no Ko or Google.

## Deploy from your phone

1. Create a GitHub repository, then upload the **contents** of this folder. `render.yaml`, `server/`, `android/`, and `.github/` belong at the repository root. Do not upload the separate PRIVATE setup archive or signing keys.
2. On Render, create a **Blueprint** from that repository, or use a Python Web Service with:
   - Build: `pip install -r server/requirements.txt`
   - Start: `uvicorn server.main:create_app --factory --host 0.0.0.0 --port $PORT --workers 1`
   - Health check: `/health`
3. Set the environment variables below. Use the supplied PRIVATE setup file for your generated keys, or generate your own. Keep the encryption key unchanged across redeploys.
4. Deploy. Open `https://YOUR-SERVICE.onrender.com/health` and check for `"ok":true`.
5. Install `Kana-MONTAi-v1.0.0.apk` (Android 8+). Open Settings, paste the Render URL **without `/health`**, and the matching `APP_ACCESS_KEY`. Tap **Connect to Kana**.
6. Enter your Gemini API key in the app, then **Save configuration**. Refresh available models if the default model is unavailable to your account. Chat!

### Render environment variables

| Name | Value |
| --- | --- |
| `APP_ACCESS_KEY` | Your private random access key, minimum 24 characters. Blueprint generates one automatically: copy the actual value from Render into the app, or replace it with the supplied private setup value. |
| `SETTINGS_ENCRYPTION_KEY` | Generated Fernet key from PRIVATE setup. Never change it while keeping the existing database, or saved API tokens cannot be decrypted. |
| `DATABASE_URL` | Supabase **Session pooler** Postgres connection string, including your database password; add `?sslmode=require`. Use Supabase's Connect dialog. Percent-encode special characters in the password. |
| `GEMINI_API_KEY` | Your Google AI Studio API key; alternatively save it through the app after connecting. |
| `GEMINI_MODEL` | Default `gemini-2.5-flash`; configurable in the app. Availability and free quota depend on your Gemini account. |
| `PYTHON_VERSION` | `3.11.11` (set in Blueprint). |

Use one Render instance and one Uvicorn worker. Postgres tables are created automatically; no SQL to paste. Existing saved settings take precedence over environment defaults. Tokens are encrypted in Postgres; messages and memory notes are normal private database records. Anyone holding the access key can read and manage your companion, so keep it private. This version is for one owner, not a public multi-user service.

Render free services may sleep when idle. The first connection can take longer; retry after the server wakes. Background Telegram polling is **not an uptime guarantee** on a sleeping service. Use an always-on Render plan if you want Telegram available continuously. The app does not need to stay open for an awake server to answer Telegram.

## Connect Telegram (optional)

1. Create a dedicated bot with BotFather. Do not run the same token on another polling service.
2. In app Settings, enter its bot token and your **numeric Telegram user ID**, not your phone number or username.
3. Enable Telegram and save. The backend validates the token and checks for existing webhooks. It does not remove a webhook silently.
4. Open the bot in Telegram and press Start. Only text DMs from the configured user ID are processed; all other people and groups are ignored.
5. App and Telegram use the same conversation and saved memory notes. `/start` explains the connection. Disable the switch to stop processing new Telegram messages.

Telegram personal-account pairing and WhatsApp are **not implemented in v1**. This release connects a Telegram bot, not your personal account. No messages are sent to friends on your behalf.

## Memory and chat behavior

- Previous 60 messages plus up to 100 saved memory notes are included in each AI request.
- Full history remains in Postgres, with an Earlier messages button in the app.
- The Memories tab lets you add and remove explicit facts. Old chats are not automatically summarized into permanent memory in this version.
- Clearing the conversation clears both app and Telegram history, with confirmation. Memory notes remain until individually removed.
- An unsuccessful Gemini request does not save a partial user turn. Retrying uses a request ID to avoid creating another completed turn if the first response was lost.
- Telegram retry state and update offsets persist across redeploys. A narrow crash window after Telegram accepts an outgoing message but before its update is acknowledged can still cause a duplicate Telegram delivery; Bot API has no idempotent send key.
- Kana is an AI roleplay with a friend dynamic. No model fine-tuning is included. You control the model and API key; the app makes no promise of unlimited free Gemini usage.

## Build your own APK

GitHub Actions: open **Actions → Build Kana APK → Run workflow**. Download the artifact when the job succeeds. This workflow creates a debug APK, whose signer can differ from the supplied APK and across runner builds. For updates that install over the supplied APK, use the PRIVATE signing backup and a signed release build instead.

Android Studio: open `android/`, use Java 17 / Android SDK 35 / Gradle 8.9, then build. This repo does not require Node, npm, Capacitor, or a running website. Its UI is bundled inside the APK; a native HTTPS bridge talks to your Render server. Connection credentials are encrypted with Android Keystore and app backups are disabled.

Command line with Gradle 8.9 installed:

```sh
cd android
gradle assembleDebug
```

For a signed release, set `KANA_KEYSTORE` to the absolute path to your keystore, plus `KANA_STORE_PASSWORD`, `KANA_KEY_ALIAS`, and `KANA_KEY_PASSWORD`, then run `gradle assembleRelease`. Keep signing files outside GitHub. Increase `versionCode` before installing later updates. The supplied preview APK uses the private backup's preview signer; migrate to a protected production signer before distributing publicly.

## Local backend development

Python 3.11+:

```sh
pip install -r server/requirements.txt
python scripts/generate_keys.py
# Export the generated APP_ACCESS_KEY and SETTINGS_ENCRYPTION_KEY.
# Set DATABASE_URL to Postgres, or use sqlite:///kana-local.db for local work.
uvicorn server.main:create_app --factory --host 127.0.0.1 --port 8000
```

The Android app requires an HTTPS endpoint; use an HTTPS development host for a real phone. Do not weaken certificate checks or enable cleartext traffic.

Tests:

```sh
pip install pytest
python -m pytest -q
```

Routes: public `GET/HEAD /` and `/health`; authenticated `/api/status`, `/api/messages`, `/api/chat`, `/api/settings`, `/api/models`, `/api/memories`. Authorization uses `Bearer APP_ACCESS_KEY`. There is no public web chat or admin page; the Android app is the interface.

## Verification and limitations

Backend automated tests cover authentication, atomic saved turns, retries, quota handling, encryption, memory CRUD, pagination, SQLite restart persistence, and Telegram owner filtering. Gemini and Telegram are mocked in automated tests. The APK has been compiled and its Android signature checked. Physical-device behavior, real Gemini replies, live Telegram delivery, Supabase connectivity and Render deployment require your own configured accounts and are not claimed as live-tested here. The included VALIDATION.md records completed checks.

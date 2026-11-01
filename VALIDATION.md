# Validation — v1.0.0

- Seven backend tests passed: access control; memory context and idempotent chat retry; saved secret encryption and input validation; Gemini quota errors without partial saved turns or secret leakage; disk-backed history; memory deletion and history pagination; Telegram owner-only private-message filtering with saved update offset.
- Mobile UI exercised in headless Chromium at 390×844 with a mocked native bridge: first-run setup, connection, send/reply, memory creation, and settings. No JavaScript errors.
- Layout checked for horizontal overflow at widths 320, 360, 390, and 480 pixels; none found. Home/chat/settings screenshots visually inspected locally.
- Android Java source compiled against API 35 and converted to DEX, resources packaged, APK aligned, signed and signature verified (v2 and v3). Minimum Android API 26; target API 35. Bundled assets are identical to the source folder.
- Live Gemini, Telegram, Render, and Supabase were not connected. A physical Android device/emulator was not available. These are the remaining deployment/device checks.
- Existing frontend tests use mocked data; they do not establish Android Keystore, native-network, or Telegram delivery behavior on a phone.

# v1.1 validation

- 16 automated backend tests pass. Coverage includes original auth/history/memory/Telegram restrictions plus Mistral autodetection, model fallback, successful-model preference, cross-provider fallback, quota cooldown, OpenRouter price filtering and authentication, provider removal, failed detection without key broadcasting, encryption and secret-safe errors, no partial saved turns, refusal handling, and private custom endpoint rejection.
- UI exercised with a mocked native bridge in headless Chromium: saved connection, generic key save, detection result, provider list/removal, custom override, chat, and 320–480px layouts. No JS errors or horizontal overflow. Settings screenshot inspected locally.
- Android Java compiled against API 35, resources/DEX packaged, APK aligned and signed with the original v1 signing key. Version code 2 / version 1.1.0. APK signature verified and bundled assets compared to source.
- No user's AI key was supplied. Live provider generation, real Supabase/Render connectivity after upgrade, and physical Android installation were not tested. API request/response handling is verified using mocked official-format responses.

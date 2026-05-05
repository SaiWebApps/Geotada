---
last_verified: 2026-05-04
---

# TestFlight Upload

You are an operator that guides the user through a TestFlight upload.

## Steps

1. Print the preflight checklist:

```
Pre-flight checklist (see docs/TESTFLIGHT-PREFLIGHT.md for details):

- [ ] Apple Developer Program active
- [ ] iOS Distribution certificate valid (Keychain Access > login > "iOS Distribution")
- [ ] Provisioning profile matches com.ondoway.app (App Store type)
- [ ] App registered in App Store Connect
- [ ] Credentials set: APPLE_ID env var + AC_PASSWORD keychain item, OR APP_STORE_API_KEY_ID + APP_STORE_ISSUER_ID env vars
- [ ] Proxy whitelist includes contentdelivery.itunes.apple.com and itunesconnect.apple.com
```

2. Ask the user: "Confirm all items are ready? (y/n)"

3. If confirmed, run:
```bash
make testflight
```

Do NOT suppress output. Let the full build and upload output stream to the terminal.

4. After success, remind the user:
   - "Build uploaded. Allow ~15 minutes for Apple processing before it appears in TestFlight."
   - "Check App Store Connect > TestFlight for status. Apple sends an email when processing completes."

## Error handling

If `make testflight` fails:
- Print the exact error output (never suppress or summarize).
- Point the user to `docs/TESTFLIGHT-PREFLIGHT.md` troubleshooting section.
- Do NOT attempt to diagnose signing or provisioning issues yourself.

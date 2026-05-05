# TestFlight Preflight Checklist

Run through this list before executing `make testflight`.

---

## Pre-flight Checks

- [ ] **Apple Developer Program** — membership active (not expired). Check at https://developer.apple.com/account
- [ ] **Distribution certificate** — valid iOS Distribution cert in Keychain Access. Filter by "iOS Distribution" in login keychain; check expiry date.
- [ ] **Provisioning profile** — App Store distribution profile matches bundle ID `com.ondoway.app`. Check in Xcode > Settings > Accounts > Manage Certificates, or download from Developer Portal.
- [ ] **App Store Connect** — app registered with matching bundle ID. At least one version must exist (even if incomplete).
- [ ] **Credentials configured** — see First-time Setup below.
- [ ] **Build number** — will auto-increment via `agvtool next-version -all`. No manual action needed.
- [ ] **Proxy whitelist** — `contentdelivery.itunes.apple.com` and `itunesconnect.apple.com` must bypass corporate proxy.

---

## First-time Setup

Choose ONE credential method:

### Option A: App-specific Password (simpler)

1. Go to https://appleid.apple.com > Sign-In and Security > App-Specific Passwords
2. Generate a password (label it "TestFlight CLI")
3. Store in Keychain:
   ```bash
   xcrun altool --store-password-in-keychain-item AC_PASSWORD \
     -u your-apple-id@example.com \
     -p <the-generated-password>
   ```
4. Export your Apple ID before running:
   ```bash
   export APPLE_ID=your-apple-id@example.com
   ```

### Option B: App Store Connect API Key (recommended for CI)

1. App Store Connect > Users and Access > Integrations > App Store Connect API
2. Generate a key with "App Manager" role or higher
3. Download the `.p8` file, place in `~/.private_keys/AuthKey_<KEY_ID>.p8`
4. Export before running:
   ```bash
   export APP_STORE_API_KEY_ID=<your-key-id>
   export APP_STORE_ISSUER_ID=<your-issuer-id>
   ```

---

## Running

```bash
make testflight
```

This will:
1. Bump the build number (agvtool)
2. Build the release IPA (flutter build ipa, pointing at production API)
3. Upload to App Store Connect via `xcrun altool`

After upload succeeds, allow ~15 minutes for Apple's processing before the build appears in TestFlight.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| "No signing certificate" | Missing or expired dist cert | Xcode > Settings > Accounts > Manage Certificates > + iOS Distribution |
| "No applicable devices found" | Wrong provisioning profile type | Ensure profile is "App Store" type, not Ad Hoc or Development |
| "Unable to upload" / connection timeout | Proxy blocking iTunes domains | Add `contentdelivery.itunes.apple.com` and `itunesconnect.apple.com` to NO_PROXY |
| "The bundle version must be higher" | Build number not incremented | Should not happen (agvtool runs first), but check `mobile/ios/Runner.xcodeproj/project.pbxproj` for CURRENT_PROJECT_VERSION |
| "Authentication failed" | Wrong credentials | Re-run keychain storage command (Option A) or verify .p8 file path (Option B) |
| Upload succeeds but build not in TestFlight after 30 min | Apple processing issue or compliance problem | Check email for rejection notice; check App Store Connect > TestFlight > Processing |

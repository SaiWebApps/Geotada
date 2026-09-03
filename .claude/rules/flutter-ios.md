---
paths:
  - "mobile/**"
  - "**/*.dart"
  - "**/*.swift"
  - "**/project.pbxproj"
---

# Flutter and iOS

- Never run Flutter tests in the background. Flutter buffers stdout completely, so you get
  nothing until it finishes.
- `make flutter-clean` is required after any asset change.
- `FlutterDeepLinkingEnabled` stays `false` while `app_links` is in use.
- A new `.swift` file must be added to `Runner.xcodeproj/project.pbxproj`. The build cannot
  see it from the filesystem alone.
- No hardcoded colors. Use `Theme.of(context).colorScheme.*`.
- `API_BASE_URL` is compiled into the IPA via `--dart-define` and is separate from
  `FRONTEND_URL`.

# Make target contract

Make is the supported command boundary. “Prerequisites” below means work the
target performs or provisions itself; callers do not need to run those commands
first. “Render” means a fresh, complete service-environment fetch for that
process—never a cached or filtered subset.

| Target | Self-provisioned prerequisites | Fresh Render | Standalone contract |
|---|---|---:|---|
| `help` | None | No | Yes |
| `doctor` | None; diagnostic | No | Yes |
| `bootstrap` | Python/Flutter deps, all local DBs, Valhalla, dev data | No | Yes, with host toolchain |
| `render-auth-setup` | Interactive macOS Keychain entry | API auth only | Yes |
| `render-auth-status` | Keychain lookup and service access check | API auth only | Yes |
| `config-status` | Three exact local-profile assertions | Yes | Yes |
| `sync` | None | No | Yes |
| `sync-apple` | Apple mirror reachability and lockfile backup | No | Yes, on Apple network |
| `requirements` | None | No | Yes |
| `lint` | None | No | Yes |
| `format` | None | No | Yes |
| `flutter-analyze` | None | No | Yes, with Flutter |
| `test` | Every database, data, Valhalla, browser/live/cloud shard | Where required | Yes; definitive suite |
| `audit` | Lint and `test` | Where required | Yes |
| `test-file` | Test/dev DBs, dev data, Valhalla | Only with `LIVE=1` | Yes, with `FILE` |
| `test-live` | Render auth, test/dev DBs, dev data, Valhalla | Yes | Yes |
| `test-workbench` | Test/workbench DBs | No; providers are stubbed | Yes |
| `golden-probe` | Test/dev DBs, dev data, Valhalla | No | Yes |
| `golden-diff` | Dev DB/data and Valhalla | No | Yes, with `FIXTURE` |
| `tour-batch-plan` | Dev DB/data and Valhalla | No | Yes |
| `tour-batch-live` | Dev DB/data and Valhalla | Yes | Yes, with approved hash |
| `tour-batch-review-plan` | Dev DB/data and Valhalla | No | Yes |
| `tour-batch-review-live` | Dev DB/data and Valhalla | Yes | Yes, with approved hash |
| `db-up` | Selected Docker service | No | Yes, `DB=dev\|test\|workbench` |
| `db-down` | Selected Docker service resolution | No | Yes |
| `db-status` | None | No | Yes |
| `db-reset` | Exact selected service and volume | No | Yes; local only |
| `db-parity` | Dev DB, or cloud read session | Cloud only | Yes |
| `valhalla-up` | Main-checkout compose path and health wait | No | Yes |
| `valhalla-down` | Main-checkout compose path | No | Yes |
| `valhalla-status` | None | No | Yes |
| `valhalla-build-tiles` | Destination directory | No | Yes, with network/disk |
| `api` | Dev DB/data | Yes | Yes; foreground server |
| `workbench` | Dev DB/data and Valhalla | Yes | Yes; foreground server |
| `dashboard` | Dev DB/data | No | Yes; foreground server |
| `flutter-web` | None | No | Yes, with Flutter/Chrome |
| `flutter-ios` | Dev DB/data, simulator boot, local API | Yes | Yes, with Xcode |
| `flutter-device` | None | No | Yes, with attached device |
| `flutter-pub-get` | None | No | Yes |
| `flutter-clean` | Flutter clean and dependency resolution | No | Yes |
| `survey-area-candidates` | Exact local profile | No | Yes, with `CITY` |
| `fix-area-radii` | Exact local profile | No | Yes, with `CITY` |
| `backfill-provenance` | Dev DB | No | Yes |
| `backfill-poi-role` | Exact local profile | No | Yes |
| `backfill-name-key` | Dev DB | No | Yes |
| `wiki-fetch` | Exact local profile | No | Yes, with `POI` |
| `gen-within-edges` | Exact local profile | No | Yes |
| `validate-beats` | Exact local profile | No | Yes |
| `deploy` | Dev DB, or explicit Aura resume | Cloud only | Yes, with `CITY`; cloud requires confirmation |
| `prune-orphans` | Dev DB, or explicit cloud selection | Cloud only | Yes, with `CITY`; deletes only with `APPLY=1` |
| `fetch-boundary` | Exact local profile | No | Yes, with slug/relation |
| `geocode-pois` | Exact local profile | No | Yes, with slug |
| `tour-build` | Dev DB/data and Valhalla | No | Yes |
| `measure-planned-audio` | Dev DB/data | No | Yes |
| `measure-governor` | Dev DB/data | No | Yes |
| `onboard-city` | Isolated temporary data/registry defaults | No | Yes, with city/modes |
| `flutter-ipa` | None | No | Yes, with signing toolchain |
| `testflight` | Credential validation, build-number bump, then fresh IPA | Yes | Yes, with App Store credentials |
| `render-watch` | Hook’s commit-identity and terminal-status guards | No service env | Yes, with Render CLI |
| `render-status` | Keychain API auth | API auth only | Yes |
| `setup-audio` | Exact local profile | Yes | Yes |
| `aura-resume-proof` | Explicit cloud profile | Yes | Yes; no graph writes |
| `flutter-test` | Project hang detector | No | Yes |
| `clean` | None | No | Yes; no databases |
| `_ensure-dev-db` | `db-up DB=dev` | No | Internal helper |
| `_ensure-test-db` | `db-up DB=test` | No | Internal helper |
| `_ensure-workbench-db` | `db-up DB=workbench` | No | Internal helper |
| `_ensure-dev-data` | Dev DB, additive provisioning, final parity | No | Internal helper |
| `_test-python` | Test/dev DBs, dev data, Valhalla | No | Internal shard |
| `_test-golden` | Test/dev DBs, dev data, Valhalla | No | Internal shard |
| `_test-grade` | Test/dev DBs, dev data, Valhalla | No | Internal shard |
| `_test-invariants` | Test/dev DBs, dev data, Valhalla | No | Internal shard |
| `_test-cloud` | Render auth and Aura read session | Yes | Internal read-only shard |

Cloud safety is structural: no pytest command receives the cloud profile,
`db-reset` accepts only three fixed local services, and cloud data mutations
require `TARGET=cloud CONFIRM_CLOUD_WRITE=1`.

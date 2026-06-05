# Security & Privacy Practices (Project Constraints)

This document defines non‑negotiable security and privacy constraints for future development. All new features and changes must comply with these requirements or explicitly document a deviation and get approval.

**1) Data Classification & Minimization**
- Collect only data required to deliver a user‑visible feature.
- Document the data type, purpose, retention period, and lawful basis (if applicable) before collection.
- Avoid collecting sensitive data (biometrics, precise location, government IDs) unless a written exception is approved.

**2) Consent & Transparency**
- Provide clear, plain‑language disclosures for any data collection beyond core product functionality.
- Obtain opt‑in consent for marketing, analytics beyond essentials, and any sensitive data.
- Allow users to revoke consent and explain the impact of revocation.

**3) Authentication & Authorization**
- Enforce strong authentication: MFA for admin/privileged users, recommended for all users.
- Use least‑privilege access across services and roles.
- Enforce authorization checks on every request, not just at the UI layer.
- Treat all input as untrusted and avoid client‑side authorization assumptions.

**4) Secure Session Management**
- Use short‑lived access tokens and rotate refresh tokens.
- Store tokens securely (httpOnly cookies where feasible).
- Bind sessions to user/device context where appropriate and invalidate on critical changes (password reset, role changes).

**5) Secrets & Credentials**
- No secrets in source control or logs.
- Use a managed secrets store and rotate secrets regularly.
- Scope secrets to the smallest required permissions and environments.

**6) Encryption**
- Encrypt data in transit using TLS 1.2+.
- Encrypt data at rest for databases, backups, and object storage.
- Use strong, current algorithms; avoid custom crypto.

**7) Logging & Monitoring**
- Log security‑relevant events (auth failures, permission denials, admin actions).
- Avoid logging PII or sensitive data; redact where necessary.
- Set alerts for anomalous behavior (e.g., spikes in failed logins).
- The distance layer (`src/tour/distance.py`) never logs raw lat/lng for arbitrary points. Fallback/diagnostic logs emit a POI id, or a `nearest_poi_id` plus a coarse (~100m) bucketed coord hash. See `_pii_safe_point_label`.

**8) Data Retention & Deletion**
- Define retention periods for all data types and enforce automated deletion.
- Provide user‑initiated data deletion with reasonable timelines.
- Ensure backups honor deletion requests where feasible.

**9) Third‑Party Risk**
- Vet third‑party SDKs and services for security and privacy posture.
- Limit data shared to minimum required.
- Track all vendors and data flows in a maintained inventory.

**10) Secure Development Lifecycle**
- Threat model material changes and high‑risk features.
- Use code review with security checklists for auth, data handling, and injection risks.
- Keep dependencies updated and scan for vulnerabilities.

**11) Input Validation & Output Encoding**
- Validate all inputs server‑side with allow‑lists.
- Use parameterized queries and ORM protections.
- Encode outputs to prevent XSS and injection.

**12) Infrastructure & Network Security**
- Segment networks; restrict access via firewall rules and security groups.
- Use principle of least exposure (no public databases).
- Maintain least‑privilege IAM policies.
- The OSRM routing server is bound to `127.0.0.1:5000` only (never `0.0.0.0`) — see `docker-compose.osrm.yml`. It is a routing-only service with no auth and must remain unreachable off-host.

**13) Privacy by Design**
- Default to the most privacy‑preserving settings.
- Ensure feature designs include privacy impact analysis for new data types.
- Avoid dark‑patterns that coerce data sharing.

**14) Incident Response**
- Maintain an incident response plan with roles, escalation, and timelines.
- Log retention must support forensic investigation.
- Provide user notifications when required by law or policy.

**15) Testing & Verification**
- Add security tests for auth, access control, and data‑handling flows.
- Include privacy regression tests for consent and data deletion.
- Conduct periodic penetration testing or third‑party assessments.

**16) Compliance & Documentation**
- Maintain a living data inventory and data flow diagrams.
- Ensure policies align with applicable regulations (e.g., GDPR/CCPA).
- Document exceptions with rationale, scope, and expiration date.

**Implementation Notes**
- New endpoints must include explicit authorization checks.
- New data fields require an update to the data inventory and retention policy.
- Feature PRs must include a checklist confirming compliance with this document.

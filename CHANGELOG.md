# Changelog

## 0.1.4-beta.7 — 2026-10-26 — REFRESH REQUEST NESTING

Opt-in beta prerelease. Stable v0.1.3 remains Latest.

- Fix Alibaba refresh request wire nesting: credentials belong in `params.request` for `/account/checkOrRefreshSession`; API version remains 1.0.4.
- Carry all issue #12 source: opt-in diagnostic manual refresh button (#9), safe response-shape diagnostics (#10), `application_rejection` distinction (#11), and signed nested refresh-body regression (#12).
- Preserve token expiry/rotation persistence, valid-session handling, bounded retries, bundled integration card, translations, and one-attempt device-write safety. No unrelated card improvements are claimed.
- Privacy: diagnostics retain allowlisted categories/types, not token values, passwords or raw response bodies.

User live evidence on 2026-10-26: one manual refresh with the issue #12 build succeeded (vendor code 200); tokens rotated, expiries advanced, authorization/connection stayed healthy, and cloud/device reads succeeded. Automatic timer refresh with this fixed version is NOT YET proven, including a 20-hour run. Earlier beta.6 rejected 21 automatic attempts and one early manual test.

Enable diagnostics to use the manual refresh diagnostic button. Roll back via HACS Redownload to stable v0.1.3 or beta.6 if needed; beta.6 does not fix refresh. No live cloud requests or appliance actions were performed during packaging.

## 0.1.4-beta.6 — 2026-10-25 — HASSFEST DEPENDENCY FIX

- Declare `http` in `after_dependencies`, retaining `frontend` and `lovelace`,
  to fix hassfest validation of the bundled card static-path registration.
- Bump the integration and versioned resource URL to beta.6. Preserve the
  bundled integrated card, independent Premium Card compatibility, dashboard
  YAML, session diagnostics, recovery behavior and native Mode translations.

## 0.1.4-beta.5 — 2026-10-25 — BUNDLED INTEGRATED CARD (prepared locally)

- Bundle the pinned MIT Premium Card v0.1.1-beta.1 snapshot as the distinct
  `custom:aigosmart-ha-integrated-card`, titled AigoSmart HA Integrated, with
  a readable attribution footer and isolated JavaScript scope.
- Preserve the separately installed `custom:aigosmart-premium-card`, resources,
  dashboard YAML, service semantics, numeric modes and confirmation interlocks.
  Both cards can load together; no migration or second frontend install is needed.
- Serve a unique versioned module through async static paths. Load the Lovelace
  storage collection before any resource inspection/write; register only our own
  resource idempotently. YAML resources remain user-managed; failures are optional.
- Preserve all beta.4 session recovery, diagnostics and one-attempt device safety.
- Include vendor hashes, exact MIT license, reproducible sync, ZIP assets and
  offline storage/coexistence/control regression coverage.


## 0.1.4-beta.4 — 2026-10-25 — SESSION RECOVERY + DIAGNOSTIC BETA

- Preserve still-valid IoT tokens after failed proactive renewal; never reuse a known rejected token.
- Serialize manual login with renewal, retain failed-login credentials, and preserve rotation persistence.
- Add bounded exponential cooldowns with jitter for renewal/read outages; retain original failure categories during cooldown.
- Rate-limit recovery warnings, summarize suppression and log successful recovery transitions.
- Add allowlisted response envelope, field/type, expiry representation, validation, HTTP category and vendor-code diagnostics. Never retain response values or bodies.
- Request HA reauthentication after repeated structurally unusable renewal once the old token expires; no password storage or invented TTL.
- Preserve beta.3 Mode translations, numeric writes, IDs, card compatibility and one-attempt write safety.
- Compare both reference implementations and provider docs in [the investigation report](docs/SESSION_REFRESH_BETA4.md). The production root cause remains unconfirmed; natural expiry testing is required.

## 0.1.4-beta.3 — 2026-10-24 — NATIVE MODE DROPDOWN LABELS

- Enable native HA select option translations via `translation_key: mode` and
  `entity.select.mode.state` with raw keys `0`, `1`, `2`.
- Correct beta.2's overly broad assumption about numeric translation keys:
  Core 2026.10.3 and its pinned frontend 20260930.5 support these keys. Actual
  production-control browser tests confirm rendered labels and numeric services.
- Supply consistent English/German/Polish state translations. Opt in only when
  the complete runtime TSL mapping agrees with the tested meanings; other models
  retain their raw dropdown values and original dynamic description attributes.
- Preserve select ID/unique ID, numeric states/options and integer IoT writes,
  `mode_labels`, `current_mode_label`, status and description sensor states.
- Preserve all v0.1.3 recovery/control behavior and beta diagnostics. No Premium
  Card change, schema migration, automatic write retry or extra cloud request.
- Run regressions on HA 2026.10.3 and add native browser evidence in CI, beyond
  HACS/hassfest validation. Include safe fixture screenshots in the documentation.

Only the beta branch is published as a pre-release. Stable main and existing
releases remain unchanged; issue #3 stays open for installed-HA verification.

## 0.1.4-beta.2 — 2026-10-24 — DIAGNOSTICS + ENUM LABELS BETA

- Reuse beta.1 diagnostics and every stable v0.1.3 feature/fix; no main merge or
  tag overwrite. Keep existing numeric states, Mode select options and IDs.
- Address the display request in issue #3 with TSL-derived current Mode/status
  label attributes and additional Mode/Status description sensors. Runtime TSL
  takes precedence over tested-model examples; unknown values are not guessed.
- Translate the new sensor names in English/German/Polish. Leave select machine
  keys unchanged: static native select translations cannot safely represent
  arbitrary model-specific descriptions without changing the stable contract.
- Document raw mappings, synthetic fixture limits and compatibility with Premium
  Card v0.1.1-beta.1 and stable integration v0.1.3.
- Add all-known-value, other-model, unknown/unsafe-label and registry-preservation
  tests. Retain all recovery, privacy and single-attempt command regressions.

Long-term live operation and the installed frontend have not been validated.
Issue #3 remains open pending real Home Assistant verification.

## 0.1.4-beta.1 — 2026-10-24 — DIAGNOSTICS BETA

This opt-in beta is released only from `beta/diagnostics-v014`. Stable `main`
and v0.1.3 remain unchanged. Long-term live operation is not validated.

- Preserve the three existing diagnostic sensors and their unique IDs.
- Add passive last successful cloud/device read times, last sanitized failed API
  operation, last refresh attempt/result, failed refresh attempt count,
  connection/recovery status and IoT/refresh-token expiration timestamps.
- Extend downloadable diagnostics with a fixed structured allowlist, UTC times
  and safe defaults when no runtime is available. Never export credentials,
  identifiers, headers or raw cloud payloads.
- Keep every diagnostic entity disabled by default and in the diagnostic category.
  No extra requests or per-second timers; reuse existing coordinator updates.
- New activity history and counters reset on integration reload/HA restart;
  persisted token deadlines and last successful refresh retain their old meaning.
- Add offline privacy, event accounting, no-extra-IO, registry compatibility,
  cloud/offline recovery and write non-replay regressions.

Kettle control policy, reconfiguration, token refresh and retry behavior are
unchanged. See `docs/BETA_DIAGNOSTICS.md` for definitions and installation.

## 0.1.3 — 2026-10-24

- Add a Reconfigure menu action that starts Home Assistant reauthentication,
  using existing email/password login and optional email verification.
- Check the original account and kettle before updating the existing entry;
  preserve device/entity identity, options and references, and reload on success.
- Drain old refresh work before saving replacement credentials to prevent a
  concurrent rotating refresh from overwriting the new login.
- Treat repeated authenticated-read rejection after refresh as requiring reauth;
  keep cloud/network failures retryable without replaying commands.
- Preserve a confirmation read after refresh even at the read backoff limit.
- Log sanitized setup/poll/refresh stage and reason categories, including setup
  failures before runtime data exists.
- Add offline recovery, verification, concurrency and startup regression tests.

Long-term live recovery has not yet been verified. The reported approximately
12-hour outage was not reproduced against the cloud.
See VALIDATION.md for confirmed defects, hypotheses and test limitations.

## 0.1.2 — 2026-10-23

- Store all five Alibaba session fields, their API TTLs and absolute expiry times.
- Renew sessions with `/account/checkOrRefreshSession` before expiry; preserve
  rotated credentials in Home Assistant Config Entries and restore them on restart.
- Share a single refresh task across entities; preserve successful rotation even
  when an awaiting request is cancelled.
- Retry only reads/refresh on temporary failures, with bounded backoff and a refresh
  cooldown. Never replay heating or other control commands.
- Start standard HA reauthentication only for expired/missing/rejected refresh
  credentials. Migrate v1 entries in place; v0.1.1 users need one login.
- Add three diagnostic sensors disabled by default, plus a credential-free
  diagnostic export. Keep device controls, TSL validation and ranges unchanged.
- Add offline coverage for expiry, token rotation, restart, outages, races,
  cancellation, migration, diagnostic privacy and command non-replay.

Refresh support was validated with mocked transports only; no live API or
hardware validation was performed for this release.

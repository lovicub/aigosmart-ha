# Changelog

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

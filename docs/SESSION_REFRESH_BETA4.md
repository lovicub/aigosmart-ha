# v0.1.4-beta.4: session recovery investigation

This is a **recovery and diagnostic beta**, not a confirmed resolution of the
reported 12–24 hour production failure. No live account response was available;
no Home Assistant installation or device was contacted. Stable main stays v0.1.3.

## Evidence and comparison

Source reviewed on 2026-10-25:

- [MarcoM1993/ha-aigostar, 39f7bab](https://github.com/MarcoM1993/ha-aigostar/tree/39f7bab1edd36161e41430ed1e01439e4e8b51ab):
  `alibaba_api.py`, integration `__init__.py`, MIT license.
- [JuanmanDev/aigo-smart, 66173b5](https://github.com/JuanmanDev/aigo-smart/tree/66173b5235a70e2b7bf6bf136823d168972ca2c1):
  `lib/cloud.py`, `api.py`, `coordinator.py`, MIT license.
- [Alibaba OpenAccount endpoint guide](https://g.alicdn.com/linkbusiness-fe/iotx-linkbusiness-common/1.0.5/sitedocs/dch3zc.html):
  `/account/checkOrRefreshSession` returns a `code: 200`, `data` object;
  `iotTokenExpire` and `refreshTokenExpire` are **durations in seconds**.
  Its sample uses nested request parameters, unlike both working references'
  flat `refreshToken`/`identityId` parameters for version 1.0.4. We retain the
  reference-supported request, rather than changing an unobserved contract.
- [Alibaba authentication SDK guidance](https://gaic.alicdn.com/doc/homelink-doc/mobile-android-sdk-authentication.html)
  describes multi-login invalidation as a possible cause of refresh rejection.
  SDK error numbers are not assumed to be gateway business error codes.

| Behavior | Marco | Juan | AigoSmart beta.4 | Plausible relevance |
| --- | --- | --- | --- | --- |
| Refresh request | Flat token + identity; no IoT token; API 1.0.4 | Same | Same, unchanged | No observed envelope mismatch |
| Response envelope | `data` object, requires IoT token | Same | Same; other shapes safely diagnosed/rejected | Alternate production envelope remains unverified |
| Missing IoT expiry | Uses 7200-second default in HA wrapper | Uses 7200-second default | Rejects; reports exact field | Could explain validation failure, but no production evidence |
| Expiry interpretation | Relative seconds | Relative seconds | Relative seconds; persisted absolute deadlines | Current units match endpoint guide, unlike SDK's differently named timestamp fields |
| Refresh/identity omitted | Preserve previous values | Preserve previous values | Preserve previous token/identity and original refresh deadline | Already supported before beta.4 |
| Rotated refresh without lifetime | No refresh-expiry enforcement | No refresh-expiry enforcement | Rejects atomically; preserves previous session | Possible validation cause; lifetime of new token cannot safely be invented |
| Full-login fallback | Stored password; full login after refresh exception | Stored password; full login on session errors | No stored password; HA interactive reauth | Explains why references can recover from revoked renewal credentials |
| Concurrent renewal | No shared lock observed in periodic callback | Thread lock for full relogin; stale-token check | Existing shielded refresh task plus new async manual-login guard | Prevents login invalidating an in-flight refresh and old state overwriting new credentials |
| Backoff | Periodic timer | Exponential relogin cooldown | Bounded exponential cooldown with jitter, read cooldown | Avoids per-poll requests during outage |
| Email verification | Login challenge supported | Refused relogin requests HA reauth | Existing HA code flow; never sends email automatically | Provider interaction can require user action |
| Write replay | Not adopted | Session-error retry decorator also covers operations | Exactly one write; recovery retries reads only | Safety requirement preserved |

Reference source is reviewed, not copied or imported. Existing attribution is
preserved; see THIRD_PARTY_NOTICES.md. Their raw-response/exception logging and
password retention are not adopted.

## Confirmed defects and changes

1. Before beta.4, an unsuccessful proactive refresh blocked reads while the
   original IoT token still had time left. All concurrent waiters now retain
   access to that valid token after a temporary/validation failure. A known
   rejected token never receives this fallback. Confirmed auth rejection still
   requests reauth.
2. The cooldown previously converted response-validation failure to
   `cloud_unavailable`, despite making no request. It now carries the original
   category and a cooldown marker; cooldown does not produce recovery warnings.
   Business 429/5xx codes are also classified as unavailable, not malformed data.
3. Repeated warnings occurred at refresh, read and coordinator boundaries.
   Warnings are limited by fixed stage/category to once per five minutes,
   include suppressed-call counts, and report recovery once at INFO. The counts
   represent suppressed log calls, not distinct requests. Limits apply across
   loaded entries in this process; no identity is retained in log keys.
4. Refresh retries have jitter (three total attempts for transient failures).
   Failed cycles back off from 60 seconds to a 900-second base, ±20% jitter
   (maximum 1080 seconds). Exhausted transient reads also enter a shared cooldown.
   Normal HA polling resumes after cooldown; no extra polling is introduced.
5. Structurally unusable refresh responses do not enter the transport retry
   loop. After three unusable cycles and expiry of the old token, HA reauth is
   requested, because full login requires an unstored password. Transport outages
   continue bounded automatic recovery. A service returning valid data later
   recovers without reconfiguration, unless reauth has already been required.
6. Manual login now pauses new renewal, drains the shielded task, serializes
   simultaneous manual login attempts, and only closes the old manager after
   successful account/device verification. Failed login preserves old credentials.
7. Malformed persisted expiry types no longer cause timestamp comparison errors:
   an invalid IoT deadline causes renewal; invalid refresh deadline requires reauth.

Atomic response acceptance, token rotation persistence, cancellation shielding,
controlled startup recovery, numeric Mode values/translations, entity IDs,
manual reconfiguration and one-attempt writes are retained. No schema migration,
password storage, automatic email sending or Premium Card change is introduced.

## What remains unconfirmed

The October 25 production log categories alone do not identify the rejected field,
HTTP result, or vendor rejection. A missing expiry, altered envelope, invalidated
refresh token, transport outage or different service behavior are **hypotheses**.
Neither continued Alexa/app control nor successful reconfiguration proves an
Alibaba outage or proves expiry-field omission. A malformed response may follow
server-side rotation; without a usable response the next attempt could be rejected.
We cannot reconstruct those lost credentials.

The endpoint guide documents all five session fields but does not define omitted
IoT expiry semantics or alternative envelopes. This beta deliberately does not
substitute 7200, reinterpret SDK timestamp fields, accept nested success payloads,
or extend a rotated token using a prior token's lifetime. Required fields remain
strict; absent unchanged refresh/identity data keeps the existing absolute deadline.
An abrupt process or host crash after provider rotation but before HA's config
storage reaches disk cannot be made transactionally atomic with the remote API.
Graceful unload drains renewal; restart/cancelled waiter regressions cover that path.

## Safe diagnostics and next natural refresh

After installing, leave normal polling enabled. No forced control action is needed.
Download the integration diagnostics from Settings → Devices & services → AigoSmart.
Inspect:

- `refresh.response`: envelope/data types; fixed expected field names and their
  types; expiry representation (`duration_seconds`, missing, invalid type/numeric);
  exact missing/invalid validation field; HTTP status category and allowlisted code.
- `refresh.last_attempt`, `last_result`, `failed_attempt_count`, `failed_cycles`,
  `cooldown_active`, `retry_at`, `read_retry_at`.
- `last_successful_refresh`, cloud/device read timestamps, authorization and
  connection state, last failed operation and both token deadlines.
- Rate-limited `AigoSmart refresh response_shape=` warnings, especially if startup
  fails before a runtime diagnostic download is available. Successful refresh shape
  is available in diagnostics; recovery/suppression summaries are logged at INFO.

The projection never retains token values, identities, email, password, code,
headers/cookies, unknown field names or response bodies. Numeric expiry values
are not logged from responses; deadlines already stored for session operation
remain available through the existing diagnostics. Unknown vendor codes are UNKNOWN.
If sharing additional HA logs, inspect those separately; this integration's fixed
projection does not sanitize logs produced by other integrations or the host.

## Beta installation and stable-release gate

In HACS open AigoSmart HA → menu → Redownload/Download a different version → select
`v0.1.4-beta.4` (enable beta versions if needed), download, and restart Home Assistant.
Confirm version 0.1.4-beta.4. Existing configuration/entities remain. If required,
use the HA reauthentication prompt or **Neu konfigurieren**; enter any email code
only in that flow. Do not attach credentials or raw responses to issue #3.

Before stable release, observe at least two natural token-expiry cycles (beyond
48 hours), successful rotation and reads across restart, and recovery after a
real temporary connectivity failure. Capture safe shape/category diagnostics on
any recurrence, and verify the installed Mode dropdown, card and existing
automations. A provider-rejected refresh requiring a new email code still needs
interactive reauthentication; automatic survival of that provider restriction is
not promised. Keep issue #3 open until production evidence supports resolution.

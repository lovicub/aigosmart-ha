# v0.1.4-beta.4 — passive diagnostics beta

See [session recovery investigation](SESSION_REFRESH_BETA4.md) for beta.4 changes, safe refresh diagnostics and remaining production verification.

This beta is confined to `beta/diagnostics-v014`. It does not change stable main,
replace the stable v0.1.3 release or modify the Premium Card. It observes existing
session/coordinator work. It does not add requests, retry commands or change
refresh scheduling, retry limits, reauthentication or kettle control policy.

## Data definitions

| Diagnostic | Meaning |
| --- | --- |
| Session time remaining | Existing seconds until IoT-token expiry, clamped at zero; updates with coordinator/session events, not every second |
| Last successful refresh | Existing persisted timestamp of the last successful refresh |
| Authorization status | Existing authorized / refresh_unavailable / reauth_required state |
| Last successful cloud read | Latest successful model/TSL, device-list or property read |
| Last successful device read | Latest successful property read, including an existing command-confirmation read |
| Last failed API operation | Fixed stage and reason categories for the most recent failed read, refresh or write; retained after recovery, even when that attempt was retried successfully |
| Last refresh attempt | Time of the most recent individual refresh request |
| Last refresh result | success, in_progress or a fixed failure category; null before any attempt |
| Failed refresh count | Cumulative failed refresh attempts in this session-manager lifetime; three failed backoff requests count as three, cooldown skips count as zero; success does not reset it |
| Connection status | unknown, connected, recovering, device_offline, refreshing, refresh_unavailable or reauth_required; authorization/refresh failure takes precedence |
| IoT / refresh token expiration | UTC absolute expiry timestamps already held in the session, without token values |

New activity timestamps, last failure and counters are held in memory and reset
on reload/restart, including a successful account reconnection. Persisted token
expiry and last successful refresh remain available after restart. A last failed
operation is history, not necessarily a current outage. A successful cloud read
is not evidence the kettle was read: device-list/model success only updates the
cloud timestamp. Device offline means the normal device-list check did not find
the original device online. Successful property reads mark connected again.
A local missing/expired refresh credential requires reauth but is not counted as
a failed API request when no refresh request was sent.

Diagnostic entities use `EntityCategory.DIAGNOSTIC`, default to disabled and share
the existing device. The original `AigoSessionSensor` class, three original keys
and unique-ID construction are preserved. Existing user enablement/name/area
choices remain in the entity registry. New sensors also default to disabled.

## Safe download

The original top-level fields (`authorization_status`, `session_time_remaining`,
`last_successful_refresh`) retain their types. New `reads`, `refresh`,
`last_failed_api_operation`, `connection_status` and `token_expiration` sections
contain only timestamps, counts and allowlisted categories. New structured times
are ISO 8601 UTC; original `last_successful_refresh` remains Unix seconds.
Unknown values are null (or unknown status). With no active runtime, only safe
persisted expiry/refresh values and empty event history are exported.

No email, account credentials, access/refresh tokens, identity/device IDs, raw
cloud response, exception message or request header is included. Data comes from
existing activity, never from a cloud request initiated by a diagnostic download.

## HACS installation and rollback

1. Open **HACS** and find **AigoSmart HA**.
2. Choose **⋮ → Update information** if the beta is not listed yet.
3. Choose **⋮ → Redownload**.
4. Expand **Need a different version?**, open **Release**, and select
   **v0.1.4-beta.4**. Older HACS UIs may use a **Show beta versions** toggle.
5. Choose **Download**, then restart Home Assistant.
6. Enable selected diagnostics in **Settings → Devices & services → Entities**,
   including disabled entities in the filter. Download JSON from the integration
   entry menu when needed.

Do not remove or recreate the integration. To roll back, repeat the version
selection with **v0.1.3**, download and restart HA. Stable users are not moved to
the beta: GitHub publishes it as a pre-release with `latest=false`.

HACS menu reference: https://www.hacs.xyz/docs/use/repositories/dashboard/

Long-term live recovery and installed frontend behavior have not been validated.
Offline tests cover registry identity, instrumentation, serialization/privacy,
expiry, failure/recovery and the existing control/reconnect/refresh regressions.

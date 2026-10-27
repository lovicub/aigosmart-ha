# Local experimental manual IoT token refresh

This worktree starts at origin/beta/diagnostics-v014 commit
8e326c9adc31784162774d0083bb96e476bf73a4. The manifest remains
0.1.4-beta.6, including the http after-dependency. This is an uncommitted local
experiment, not a new beta or release. No cloud/device access or installation was
performed by the agent. It does not establish the cause of 12–20-hour failures.

## Manual installation and rollback by the user

1. Before replacing anything, create and download a Home Assistant backup that
   includes configuration and integration storage. Separately copy the complete
   current `config/custom_components/aigosmart` directory to a safe location
   outside `custom_components`. Keep the original archive/version details.
   Treat backups as private: config-entry storage can contain session credentials.
2. Build with `python3 tools/build_manual_refresh_zip.py` if needed. The local
   archive is `dist/aigosmart-ha-0.1.4-beta.6-local-manual-refresh-diagnostics.zip`. It contains
   `custom_components/aigosmart/` and this guide. Unzip into a temporary directory,
   then replace only `config/custom_components/aigosmart` with the archive's
   integration directory. Restart Home Assistant yourself. The manifest version
   deliberately stays unchanged; do not rely on HACS to distinguish this build.
3. In Settings → Devices & services → AigoSmart → device, find **Refresh IoT
   Token** in Diagnostics (German and Polish names are translated). It is a HA
   button entity, not an action in the diagnostic JSON or either card. It remains
   available when kettle polling fails, provided renewal credentials remain valid.
4. Press once and inspect the existing refresh diagnostics: last attempt/result,
   failed attempt count, last successful refresh and IoT/refresh expiration.
   Failures display a Home Assistant error, even if the old token is still valid.
   Concurrent callers share one shielded renewal; further manual attempts are
   limited for 60 seconds. Existing provider retries and failure cooldown still
   apply. A logical renewal may make up to three bounded provider attempts on
   transient failures. Login in progress, expired renewal credentials, closed
   managers and required reauthentication prevent new manual renewal.
5. To roll back, stop Home Assistant yourself, restore the complete saved
   integration directory (removing the experimental directory first), then start
   Home Assistant. Restoring code does not undo server-side token rotation. Prefer
   current valid session storage; if HA requires reauthentication, use its normal
   flow. Restore the full HA backup only when necessary, understanding that its
   old credentials may already have been revoked by the server.

A user clicking this button can rotate/revoke a server-side token and require
Home Assistant reauthentication. No password is stored and no TTL is invented.
The button only renews the session; it does not poll, replay commands or send
heating/device writes. Background polling/timers retain their existing behavior.
Existing sensor states/IDs and diagnostic JSON keys remain compatible; response metadata gains additive shape fields. Counts
and attempt history are in memory; successful refresh time and expiration reuse
existing persisted session fields. No tokens are added to logs or diagnostics.

## Sanitized observation and limits (issue 10)

User-provided observation only; no raw response was supplied or reconstructed.
Before the manual press: authorized, zero failed refreshes, approximately ten
hours of IoT validity. Around 2026-10-25T22:05:43Z the attempt failed validation:
envelope other, data null, all five session fields/expiry representations missing,
UNKNOWN vendor code and HTTP 2xx. Expiration stayed unchanged; device reads
succeeded around 22:05:51Z. This does not establish revocation or its cause.

Published request validation and signed(non-form) both require code equal to
numeric 200 before accepting session data. Subject to the installed source and
that execution path, null session data therefore likely passed that application
code check. Existing telemetry did not retain proof of the original code/type:
the old failure merge overwrote its safe code, and exact-type envelope lookup
misclassified the APIResponse dict subclass. HTTP 2xx alone never proves app
success, renewal, token validity, or why data was null. A provider anomaly or a
different response contract are hypotheses, not confirmed causes. No protocol
contract, expiry acceptance, endpoint, or retry count has been changed.

The local correction recognizes dict subclasses and adds fixed root_fields types
for code/status/success/ok/message/error/error_description, code_category,
data_state (absent/null/object/invalid), and trigger
(manual/timer/proactive/rejected_token). Values, unknown keys, unknown codes and
messages are never retained. Existing fields remain; safe vendor code and HTTP
category survive local session-validation errors. validation distinguishes
transport, http_status and json_decode from session validation. A shared task's
trigger identifies its initiating caller; joining callers do not relabel it.

The next naturally scheduled automatic refresh could confirm its trigger,
application code classification, root field types, whether data is absent/null or
an object, and which required fields/expiries exist. A successful attempt would
confirm accepted session renewal and updated expiry/persistence. Another null
response would establish recurrence on the automatic path, not its server-side
cause. No extra automatic refresh is forced by this change.

## Offline validation

The byte-identical issue-9 carry-forward passed all 206 Python tests before
correction. Source hashes are recorded in LOCAL_SOURCE_CONTINUITY.json; issue-9
was read only. The corrected tree passes 211 Python tests with each of cryptography 50.0.1
and 48.0.1, plus the Node integrated-card test. JSON parsing and git diff
whitespace checks pass. The ZIP builder checks integrity and every packaged
file against its local source bytes.
Mock-only precision tests cover 2xx/code 200/null, valid success, masked errors,
HTTP failure, dict subclass recognition, redaction and safe-code preservation.
Existing regressions cover button concurrency/cooldown, stable config/unique IDs,
login coordination, storage and entities. No cloud/device calls, installed HA UI
validation or live soak test were performed.

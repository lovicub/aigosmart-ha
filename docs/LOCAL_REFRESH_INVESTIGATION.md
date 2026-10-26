# Local natural-expiry refresh investigation — issue 11

Worktree: `/home/adam/codex-bridge/workspaces/issue-11-aigosmart-ha`.
No beta published. Manifest remains **0.1.4-beta.6**, with `http` in
`after_dependencies`. No commit, push, PR, release, deployment, installation,
live cloud request, credential read or device operation was performed.

## Source continuity and evidence limits

Before edits, copied all 13 issue-10 modified/untracked files and verified their
bytes plus the entire integration against the read-only source worktree
`/home/adam/codex-bridge/workspaces/issue-10-aigosmart-ha`. Its local manual-refresh
ZIP also matches its source bytes. The copied baseline passed 211 Python tests.
`ISSUE11_SOURCE_CONTINUITY.json` records source HEAD, hashes and parity checks;
`LOCAL_SOURCE_CONTINUITY.json` is the unchanged issue-10 record. Issue 10 was not
modified. Its button, en/de/pl translations, Integrated Card, unique IDs and cloud
recovery are retained.

## PROVEN facts

The operator supplied sanitized diagnostics, not a raw response. At natural expiry
on 2026-10-26, authorization was `refresh_unavailable`, remaining time zero,
last successful refresh null, last device read 08:18:51.383680 UTC. Attempt 21
at 12:20:32.560988 failed by 12:20:32.686122 with HTTP 2xx, object envelope,
unknown integer code, string message, absent data and all five session fields
missing. The IoT deadline was 08:18:51.749658 UTC; refresh deadline was
2026-11-02 20:18:51.749658 UTC. Cooldown and 21 failed cycles were recorded.
Earlier manual refresh also failed while the old token still supported reads.
Neither the actual numeric code nor message contents can be reconstructed.
This is evidence of a non-success application reply, not usable replacement
session data. A locally unexpired refresh deadline does not prove server acceptance.

The audited path is `refresh_iot_token_sync` → `signed(IOT, REFRESH)` →
`request` → transport/JSON decoding → `validate_response` → redundant signed code
check → `accept_session`. Request validation can raise before signed returns.
Issue-10 captures session shape before validation and transport attaches shape
on HTTP errors, so shape survives those exceptions. It preserves safe code and
HTTP metadata when subsequent local session validation has neither. However,
non-200 business codes formerly used generic `response_validation`, mixing
application rejection with malformed success. Unknown numeric codes remain
UNKNOWN by design: the source evidence supplies no safe meaning for this code.

`_refresh` shares a shielded task across callers, retries transient failures up
to three times, persists complete accepted rotation, and backs failed cycles off
60–900 base seconds with ±20% jitter. Still-valid tokens survive non-auth refresh
failure; rejected/expired tokens do not. Cooldown carries the original reason.
Three structurally unusable cycles after expiry can require interactive reauth;
unknown business rejection continues existing bounded recovery. Reads alone can
retry after renewal; writes are never replayed. Acceptance is atomic, requires
IoT token/lifetime, preserves omitted unchanged refresh token/identity and the
original refresh deadline, and requires a new lifetime for rotated refresh tokens.
No TTL or full-login fallback is invented.

## Local reference audit

Read local snapshots `/tmp/marco-api.py`, `/tmp/marco-init.py`,
`/tmp/juan-cloud.py`, `/tmp/juan-api.py`, `/tmp/juan-coordinator.py`, and repository
`docs/SESSION_REFRESH_BETA4.md`. The snapshots were not executed. Repository
history identifies Marco commit 39f7bab and Juan commit 66173b5; their identity
was not independently verified online in this task.

Both snapshots send flat `refreshToken`/`identityId`, API **1.0.4**, and omit the
IoT token on refresh. JSON has request language/appKey/apiVer and params; signing
uses JSON MD5, sorted x-ca headers, date, path, HMAC-SHA1 and Content-MD5. Our
body/version `1.0.0` matches Marco; Juan uses outer `1.0`. Both require code equal
to numeric 200 (string `"200"` fails). Marco defaults to the EU-central gateway;
Juan selects its IoT host from region discovery. Our supported account region
is explicitly EU-central. No observed evidence supports changing it or signing.
Reference wrappers default missing IoT lifetime to 7200; that unsupported fallback
is not adopted. References preserve omitted rotation fields but do not enforce
refresh expiry as strictly; their password-based relogin is not adopted.

The beta4 document records a prior official OpenAccount endpoint-guide review:
all five fields, durations in seconds, and a nested sample unlike the flat
reference requests. It also records SDK multi-login invalidation guidance.
No saved official HTML was found in the searched local locations. These are
historical repository notes, **not fresh official-document verification**.
No online verification is claimed. SDK errors are not gateway code mappings.

## Local improvements and hypotheses

Added fixed `code_type`, `message_state` (key present/absent only) and
`error_category`; existing diagnostic keys stay available. Reviewed exact code
literals remain bounded by existing SAFE_CODES; arbitrary numbers/strings and
raw messages, tokens, identifiers, headers and unknown keys remain redacted.
No new business-code allowlist was guessed. `application_rejection` now survives
exceptions, diagnostic state, recovery errors, cooldown and downloads. Evidenced
auth rejection retains existing handling; transport, HTTP error, JSON decoding,
malformed success and invalid/missing code shapes are distinct. Refresh success
requires integer 200, closing accidental float-200 acceptance; string 200 remains
rejected, matching the reference contract. Required session validation is intact.

No provable request/signing defect was found. Revoked refresh credentials,
multi-login invalidation, account policy, region/provider mismatch and server
behavior remain HYPOTHESES. The response has no session data to rescue; relaxing
field checks cannot fix this observed reply. A malformed earlier response could
have followed rotation, but that is also unproven.

Still needed: one safe observation from this exact build, including code type,
allowlisted code if any, error category, trigger, deadlines, attempts and last
read/refresh. If code stays UNKNOWN, its meaning needs separate provider-reviewed
mapping; do not share raw messages or arbitrarily expand the allowlist.

## Validation and reproducible artifact

Executed baseline 211 tests; final full Python suite under installed Python 3.14.4
and cryptography 50.0.1, then 48.0.1 via `/tmp/aigosmart-crypto-48-0-1`.
Final result: **215 tests passed with each crypto pin**; JS: **33 tests passed**.
Logs: `/tmp/issue11-baseline.log`, `/tmp/issue11-tests50.log`,
`/tmp/issue11-tests48.log`, `/tmp/issue11-js.log`. All API responses are
mocked. Tests cover unknown numeric rejection/message/no data, null 200 data,
code sanitization/types, rotation/persistence, auth/transport/JSON errors,
concurrent timers/manual callers, cooldown, unchanged still-valid credentials,
and no raw leakage. Existing JS card suite also ran with local Node 22.23.4.
No HA browser/hassfest/HACS/network checks were run.

Build: `python3 tools/build_refresh_investigation_zip.py`.
Output: `dist/aigosmart-ha-0.1.4-beta.6-local-refresh-investigation.zip`.
The builder fixes timestamps/permissions/order, builds twice, asserts equal hashes,
checks exact file membership and every archived byte against source. It includes
the full integration, frontend license, continuity records, both local guides and
builder. Tests stay in this worktree.

Changed beyond issue 10: `custom_components/aigosmart/protocol.py`,
`custom_components/aigosmart/recovery.py`, `tests/test_refresh_precision.py`;
added `tests/test_refresh_rejection.py`, `tools/build_refresh_investigation_zip.py`,
`docs/ISSUE11_SOURCE_CONTINUITY.json`, and this report. The complete inherited
issue-10 file list/hashes are in the continuity record.

## Next observation and rollback — user only

No installation or observation is performed by this task. If the operator chooses
to test later, save the currently installed integration and a private HA backup
first. Follow `LOCAL_MANUAL_REFRESH.md` for replacement/rollback. Rollback target
is the issue-10 local ZIP, not merely published beta.6. Code rollback cannot undo
cloud token rotation; restoring stale credentials may require normal HA reauth.

If required, use normal interactive reauthentication once. Save sanitized
before diagnostics. Prefer waiting for one natural timer refresh. Alternatively,
if explicitly chosen by the operator, press the diagnostic button **once** outside
cooldown, with no other login/refresh activity. A logical attempt can include
existing transient retries. Do not repeatedly press or issue kettle commands.
Save after diagnostics with the same fields and timestamps, build/ZIP hash, and
whether another app/account login occurred; include no account/device identifiers.
On rejection, retain evidence and use normal reauth if needed; no speculative
full login automation or request experiments are recommended.

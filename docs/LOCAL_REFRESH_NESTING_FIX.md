# Issue 12: local refresh nesting correctness patch

Local experiment only, continuing the complete uncommitted issue-11 result.
Manifest remains 0.1.4-beta.6. No commit, push, PR, tag, release, installation,
credential access, live Alibaba call or device action was performed.

## Finding and minimal change

Official Alibaba OpenAccount usage guide, section `通过refreshToken获取iotToken`:
https://g.alicdn.com/linkbusiness-fe/iotx-linkbusiness-common/1.0.5/sitedocs/dch3zc.html
(accessed 2026-10-26, refresh section lines 858–907).
Its `/account/checkOrRefreshSession` example nests refreshToken and identityId
inside params.request. Independently inspected signed(): it serializes the passed
params directly into the final JSON, then computes MD5 and HMAC over the complete
body and request metadata. The previous refresh call passed flat fields, so the
wire body was flat. This patch wraps those two fields in request at that call only.

The guide lists apiVer 1.0.0 and outer version 1.0. Existing integration uses
apiVer 1.0.4 and outer version 1.0.0. Both remain unchanged and are asserted in
wire tests: this older guide does not establish that the current gateway rejects
1.0.4 or that either version change is necessary. That discrepancy remains an
explicit compatibility uncertainty for a controlled user test, not a reason to
bundle an unproven version change with the nesting correction.

The operator's 2026-10-26 18:23:03Z manual observation (after reauth while token
valid) showed HTTP 2xx, unknown integer root code, string message, absent data,
application_rejection, unchanged expiry and a subsequent successful device read.
Earlier timer attempts failed identically 21 times. This proves application-level
rejection, not the exact error code or that nesting was its sole cause. This fresh
official-source finding supersedes issue 11's historical conclusion that no
provable request defect was found; that report is preserved as historical evidence.
Only a real controlled user test can confirm live Alibaba compatibility.

## Continuity and offline verification

Started at 8e326c9adc31784162774d0083bb96e476bf73a4. Before code edits copied
and byte-verified 84 files from the read-only issue-11 worktree, including its
untracked tests/docs/builders and ZIPs. Baseline passed 215 tests. The inherited
investigation ZIP matches every archived source file. ISSUE12_BASELINE_PARITY.json
records all baseline hashes; all issue-11 originals were rechecked unchanged.
Only protocol.py and the existing flat-body expectation in test_session_refresh.py
changed among baseline sources. Added wire tests, this report, parity record and
local builder. All other source bytes, translations, premium/Integrated Card,
config IDs, manual button, application_rejection diagnostics and tests remain.

Executed with existing /home/adam/projects/aigosmart/.venv/bin/python (Python 3.14.4,
Home Assistant test dependencies already installed; no HA instance installed/run):

- Baseline: `python -m unittest discover -s tests`: 215 passed.
- Final cryptography 50.0.1: same command, 217 passed.
- Final cryptography 48.0.1: same command with
  `PYTHONPATH=/tmp/aigosmart-crypto-48-0-1`, 217 passed; imported version asserted.
- Node 22.23.4: `node tests/integrated_card.test.mjs`: 33 passed.

Logs: /tmp/issue12-baseline.log, /tmp/issue12-tests50.log,
/tmp/issue12-tests48.log, /tmp/issue12-js.log. An initial system-Python attempt
failed because it lacked Home Assistant dependencies; the verified baseline and
final runs used the existing test environment. Tests use mocked transports and
socket guards; new tests capture actual serialized POST bytes and independently
recompute Content-MD5 and HMAC with a synthetic signing key. They assert exact
nested fields, no flat duplicates/refresh IoT header, unchanged versions,
nonce/timestamp, rotation/deadlines and unchanged actual login SESSION and device
read payloads. Retained suites cover rejection/redaction, malformed success,
manual/timer shared renewal, concurrency, cooldown, persistence and diagnostics.
The standard packaging test rewrites the local standard ZIP; its inherited bytes
were restored from issue 11 afterward. Use only the distinctly named new ZIP.

Build: `python3 tools/build_refresh_nesting_zip.py`. The builder verifies exact
membership, every archived byte, integrity and identical hashes across two builds.
It includes the entire integration (including frontend LICENSE), historical local
guides, this report, continuity records and builders. Tests remain in this worktree.

## Optional controlled user test and rollback

1. Save a private HA backup and the full currently installed integration directory
   outside custom_components. Keep the issue-11 investigation ZIP as rollback.
2. Extract `dist/aigosmart-ha-0.1.4-beta.6-local-refresh-nesting-fix.zip` to a
   temporary folder. Replace only config/custom_components/aigosmart with its
   integration directory; restart HA yourself. Version stays beta.6, so record the
   distinct filename and SHA256. Historical guides name older ZIPs; use this ZIP.
3. Complete normal interactive reauthentication once if needed. With authorization
   valid, outside cooldown and no competing login activity, download fresh before
   diagnostics. Record UTC time, authorization state, token deadlines, last
   success, attempt count, trigger and last device-read timestamp.
4. Press the diagnostic **Refresh IoT Token** button exactly ONCE. Do not issue
   device commands. A shared attempt can include existing bounded transient
   retries; a joining timer may retain its initiating trigger. Download fresh after
   diagnostics and record the same fields, result, HTTP category, code type,
   allowlisted vendor code, error_category and data/field shapes. Success should
   advance expiry/last-success; rejection must preserve valid existing credentials.
   Share only sanitized diagnostics and build hash, never credentials/raw messages.
5. If rejected, preserve evidence; do not repeatedly press. Use normal HA reauth
   if required. To roll back, stop HA yourself, restore the complete saved issue-11
   integration directory (or that ZIP's integration), and restart. Code rollback
   cannot reverse server-side rotation; retain current valid session storage and
   use normal reauth if stale credentials no longer work.

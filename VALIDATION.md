# Validation results — v0.1.2

Date: 2026-10-23. Python 3.14.4, installed Home Assistant 2026.10.2.

| Check | Result |
| --- | --- |
| Full offline suite, cryptography 50.0.1 | 122 passed |
| Full offline suite, cryptography 48.0.1 from separate target | 122 passed |
| New automatic-session tests | 31 passed (included in both full runs) |
| Python syntax and repository JSON | Validated locally |
| Git diff whitespace | Passed |
| Release ZIP integrity, version and source comparison | Passed |
| Official hassfest / HACS workflows | Not run locally; pending GitHub execution |
| Live cloud / kettle validation | Not performed for v0.1.2 |

Run from the repository root:

```sh
python -m unittest discover -s tests -v
python tools/build_zip.py
git diff --check
```

`tests/test_session_refresh.py` covers:

- All session fields and seconds-based TTL conversion; malformed TTL rejection.
- Refresh envelope with no expired IoT token; rotation and omitted-token retention.
- Proactive timer scheduling for multiple TTLs, independent of polling interval.
- Expired IoT token, persisted deadlines and token recovery after a restart.
- Network loss, business/HTTP server failures, bounded backoff and cooldown.
- Refresh expiry/rejection and standard HA reauthentication.
- Thirty simultaneous refresh requests, concurrent rejected-token requests,
  and cancellation of a waiter during rotation.
- Read retries and recovery after a rejected IoT token.
- Entry schema migration, one-time legacy reauthentication and startup retry.
- Credential-free diagnostics/logs and disabled-by-default diagnostic sensors.
- No entry reload after token persistence; options changes still reload.
- No heating command replay after authentication failure; no command sent while
  refresh is unavailable; unload cancels the timer and clears in-memory secrets.

The existing 91 tests also pass. Their synthetic login session fixture now
includes the TTLs and identity ID required by the API contract. HA mocks include
session data, and config flow assertions verify refresh credential persistence.
Control policy, live TSL validation, command payloads and allowed ranges remain
covered by the original tests. No real API connection was used: tests mock
transports and install socket connection guards.

The 48.0.1 run validates these integration tests with that library, not an override
of HA's complete dependency set. The manifest has `requirements=[]`.

The clean release artifact is `dist/aigosmart-ha-0.1.2.zip`. It contains integration
files, public documentation and licensing only, without local HA configuration,
credentials, private reports, tests or Python caches. Official GitHub validators
and live hardware behavior remain unverified; no push or release was performed.

# Validation results — v0.1.4-beta.1

Date: 2026-10-24. Python 3.14.4, Home Assistant 2026.10.2.
Branch: `beta/diagnostics-v014`, based on stable main/v0.1.3 commit
`87a6ebe74d04eb94144976ce191b4af97fb55ae2`. Main and the stable tag must remain
at that commit; this beta is not merged into main.

| Beta check | Result |
| --- | --- |
| Full offline suite, cryptography 50.0.1 | 150 passed |
| Full offline suite, cryptography 48.0.1, isolated target | 150 passed |
| New diagnostic regressions | 14 passed, included above |
| Python syntax, JSON, whitespace, intended files and secret-pattern review | Passed locally |
| ZIP integrity and source comparison | Passed locally |
| HACS / hassfest / Python GitHub Actions | Required on the beta branch commit before pre-release publication; see its Actions run |
| Live cloud / kettle / installed frontend | Not tested |

The 136 stable tests remain in the full suite, including command non-replay,
reauth/reconfigure, refresh rotation, concurrent refresh/reconnection, outages,
restart and registry preservation. Beta tests additionally cover:

- Safe structured downloads and timestamps with/without runtime state.
- Cloud read versus device property-read success times.
- Recovered failures retained as sanitized historical categories.
- Individual failed refresh attempts versus cooldown skips; successful recovery.
- Missing credentials versus actual rejected refresh requests.
- One shared refresh for concurrent callers; no requests from repeated diagnostic
  reads; no polling on diagnostic sensors; in-flight refresh visibility.
- Preserved original unique IDs, entity IDs, custom names and areas using actual
  HA entity registries; all diagnostic sensors disabled by default.
- Invalid/non-finite/oversized timestamp inputs never exposing stored strings.
- Reload counter reset while persisted last-refresh time retains its meaning.
- Passive device-offline/recovery status and sanitized single-attempt write failure.

All tests mock transports and block network connections. Cryptography versions
are explicitly imported/verified; the 48.0.1 import target does not replace HA's
entire dependency set. Local logs: `/tmp/aigo-v014-beta-tests-50.log` and
`/tmp/aigo-v014-beta-tests-48.log`. Build: `python tools/build_zip.py` produces
`dist/aigosmart-ha-0.1.4-beta.1.zip`, including the beta diagnostic definitions.

All activity history/counts are in memory; reload/restart resets them. Token
expiration and last successful refresh reuse persisted stable session fields.
See `docs/BETA_DIAGNOSTICS.md` for exact semantics and HACS installation.

Publication is a GitHub pre-release from the checked beta commit, explicitly
`--prerelease --latest=false`. The latest stable release remains v0.1.3. No
installed configuration entries, Premium Card or live heating commands are used.
Long-term live operation is unverified. Final CI, tag/version and stable-main
invariance are verified during publication and reported with the pre-release URL.

---

# Stable v0.1.3 validation — historical baseline

Date: 2026-10-24. Python 3.14.4, Home Assistant 2026.10.2.

| Check | Result |
| --- | --- |
| Complete offline suite, cryptography 50.0.1 | 136 passed |
| Complete offline suite, cryptography 48.0.1, isolated import target | 136 passed |
| Python syntax, JSON, manifest and translation consistency | Passed |
| Git whitespace check | Passed |
| Release ZIP integrity and source comparison | Passed |
| Official hassfest / HACS | Required GitHub checks on the publication PR; see its check results |
| Live cloud, installed frontend and physical kettle | Not tested |

Both crypto versions were verified by importing them in the respective test
environments. The 48.0.1 target overrides only cryptography for these integration
tests, not Home Assistant's complete dependency constraints. Tests mock transports
and block socket connections. No heating or other live write was sent.

## Confirmed source findings

- A second authenticated-read rejection after a successful refresh used to become
  a generic temporary read error. It now raises `ConfigEntryAuthFailed`, allowing
  HA setup/coordinator handling to start standard reauthentication.
- Startup and coordinator wrappers discarded stage/reason distinctions. Safe
  allowlisted log categories now survive these boundaries; setup logs exist even
  before `runtime_data` is assigned. Exception text, bodies and identifiers are
  never interpolated into these recovery logs.
- No user-initiated reconfigure step existed. Reconfigure now starts/reuses a
  standard reauth flow and hands it to the frontend via HA's `next_flow`. Calling
  `async_start_reauth` inside reconfigure is ignored by HA's active-flow guard;
  real flow-manager tests verify the explicit handoff and reuse behavior.
- Reauthentication could save a new login while an old rotating refresh remained
  in flight. Reconnection now stops the old manager and awaits its refresh before
  saving the new session. An event-controlled regression checks this ordering.
- A rejection on the final read retry previously refreshed without performing a
  confirmation read. Authentication recovery now has a separate bounded attempt
  from the transient read backoff budget.

The pre-existing refresh logic already subtracts a proportional expiry margin
(up to ten minutes), schedules a timer independently of polling, shares one
shielded refresh task, persists complete rotated credentials before success,
preserves omitted refresh-token absolute expiry, uses a 60-second outage
cooldown and restores absolute deadlines after restart. Those behaviors remain
covered. Refresh and safe reads use bounded 1/3-second backoff. Writes remain
single-attempt; confirmation reads never replay a command.

## Unconfirmed explanations for the reported 12-hour outage

No cloud responses, deployed session metadata or sanitized stage logs from the
11:18 incident were supplied. Token expiry/revocation, a cloud outage, unexpected
refresh response shape, token rotation semantics and an account verification
challenge remain hypotheses. A twelve-hour TTL is tested as a scheduling case;
it is not established as the affected account's actual TTL. No claim is made
that a particular server-side failure was reproduced or that a live 12-hour
soak test passed.

## Regression coverage and limits

The suite includes manual reconfigure delegation; account/kettle rejection;
credential/code rejection and successful code login; updates to an existing entry;
preservation of entry ID, unique ID, device ID and options; refresh/reconnect races;
refresh expiry and rotation; repeated 401/403; successful read recovery; failed
refresh reauth; cloud outage/cooldown and recovery; restart; TSL setup failure and
subsequent recovery; sanitized logs; and no automatic write replay.

Flow tests include real HA config entries, flow management and device/entity/area
registries, with mocked cloud transports and reload scheduling. They verify the
manual flow handoff, successful/failed automatic reauth, code verification,
absence of duplicate entries/devices/entities, stable entity ID, custom entity
name and area assignment. Additional tests verify polling recovery from an API
outage and offline-device state without restarting HA. Recorder history and
installed dashboards/frontend are not exercised; their references remain stable
because entry/device/entity identifiers and registry records are preserved.
Long-term live recovery has not yet been verified. The user will test the real
HACS upgrade after publication.

## Reproduction

Run from the repository root using Python with Home Assistant 2026.10.2 installed:

```sh
python -c "import cryptography; assert cryptography.__version__ == '50.0.1'"
python -m unittest discover -s tests -v
PYTHONPATH=/tmp/aigosmart-crypto-48-0-1 python -c "import cryptography; assert cryptography.__version__ == '48.0.1'"
PYTHONPATH=/tmp/aigosmart-crypto-48-0-1 python -m unittest discover -s tests -v
python tools/build_zip.py
git diff --check
```

Local full-suite output: `/tmp/aigo-v013-tests-50.log` and
`/tmp/aigo-v013-tests-48.log`. Release artifact:
`dist/aigosmart-ha-0.1.3.zip`. Publication is authorized only after successful
Python, HACS and hassfest GitHub checks. No installed HA configuration entries or
Premium Card files were changed. See the publication PR and GitHub release for
final CI and publication status.

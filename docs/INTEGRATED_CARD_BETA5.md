# Integrated card provenance and local validation

Prepared locally as 0.1.4-beta.5, without publication, commits, cloud traffic or
hardware actions. Worktree: `/home/adam/codex-bridge/workspaces/issue-7-aigosmart-ha`.
Initial and final Git HEAD: `c9765961d2a9c4eb6e4e8323069b9d2379180e66`, detached
at `origin/beta/diagnostics-v014`. Verified manifest beta.4, beta.4 changelog and
session recovery fixes before editing. Target working-tree manifest: beta.5.

## Vendor pin

Read-only source checkout:
`/home/adam/projects/aigosmart/publication/aigosmart-premium-card`.
Verified clean HEAD `f4bb918d261d63a49ed40f27c194b5f8be555e8d`, source-declared
version **0.1.1-beta.1** (no tag at that checkout HEAD). Source unchanged.
Repository: https://github.com/lovicub/aigosmart-premium-card.

SHA-256:

| File | Hash |
| --- | --- |
| Original JS snapshot | `52502c7e5dd185a3f43f0bc61a90616ff510f9487e22a9095ebc258979617016` |
| Integrated JS | `8e3f21f538e5bee0852cc2e3ab5f5ebb10875f7a83e605c8e94ac9bfd0d8d636` |
| Exact MIT LICENSE | `647f8ffc11b731e404d1aa56734eefaf7a0c6924ea90031fa440dc0d6438cd6e` |

The exact upstream snapshot, license and machine-readable hashes live in
`custom_components/aigosmart/frontend/`. Only the integrated JS is served or
registered. Original copyright: © 2026 AigoSmart project contributors. Regression
tests were adapted from the same pinned source under MIT.

Reproduce with no network access:

```sh
python3 tools/vendor_integrated_card.py /path/to/verified/card/checkout
python3 tools/build_zip.py
```

The vendor script refuses a mismatched HEAD or changed JS/license. It reads Git
objects and source files only, writes exclusively to this integration worktree,
and applies deterministic naming, IIFE scope and footer changes. The transform
leaves service calls, enum mappings, event handlers and safety interlocks intact.
HACS copies the complete integration tree; the manual ZIP explicitly includes JS,
provenance and license. No frontend build or external asset download is needed.

## Resource safety

Optional `after_dependencies` order frontend/Lovelace when configured. A single
per-runtime callback waits for Lovelace setup or HA startup. An async lock serializes
registration across entries. `async_register_static_paths`/`StaticPathConfig` serves
only the integrated file at its own namespaced path. Integration and card versions
form its cache query. Resources survive entry unload; runtime state resets on HA
restart. No cloud client is used by frontend setup.

In storage mode, `resources.async_get_info()` triggers HA's public lazy load before
`async_items()` or any mutation; `loaded is True` is required. This addresses the
collection-loading hazard described in Core issue #165767 without private APIs or
direct storage writes. Failure/unconfirmed load logs a fixed warning and skips
registration. Only an exact local path match is updated, with no deletion of old
standalone or unrelated resources. YAML mode serves assets without mutating resources.

## Offline acceptance and remaining manual checks

Run with a local Python environment containing Home Assistant 2026.10.2 (local cryptography 50.0.1):

```sh
python -m unittest discover -s tests -v
node --check custom_components/aigosmart/frontend/aigosmart-ha-integrated-card.js
node tests/integrated_card.test.mjs
```

Python checks include a real HA lazy ResourceStorageCollection with a mocked
storage backend, load failure/unconfirmed load, preservation of existing resources,
new installs, own URL upgrade, concurrent entries/reloads/restart, YAML mode,
missing frontend/Lovelace, static failure, vendor hashes, ZIP contents and all
existing recovery/diagnostic/control/privacy regressions. JavaScript checks cover
both script load orders, repeat integrated load, independent instances, unchanged
service payloads, visible footer, numeric modes, confirmation, no automatic heating
and no retries. All HA services and cloud transports are fixtures/mocks.

Pending actual HA UI verification (not performed here): HACS install/update in a
test HA instance; new card picker; old and integrated cards together with existing
entity IDs; desktop/mobile footer readability; resource persistence across a real
restart; YAML resource snippet and browser cache refresh. No actual kettle action
is required for these UI checks. Hassfest/HACS hosted actions were not run locally
because they require unavailable validation tooling/network; CI retains both.

Local results: **195 Python tests passed**, no skips, on HA 2026.10.2 /
cryptography 50.0.1. **33 JavaScript tests passed**, no skips, on Node 22.23.4.
Integrated JS syntax check and `git diff --check` passed. ZIP content tests passed.
No installed-HA/browser UI tests, hassfest or hosted HACS validation were executed.

Changed files: integration `__init__.py`, `manifest.json`, new `frontend.py` and
four frontend vendor files (snapshot, integrated JS, LICENSE, PROVENANCE.json);
`tools/build_zip.py`, new `tools/vendor_integrated_card.py`;
`tests/test_integrated_frontend.py`, `tests/integrated_card.test.mjs`;
`.github/workflows/validate.yml`, `README.md`, `CHANGELOG.md`,
`THIRD_PARTY_NOTICES.md` and this document. Local ignored build artifact:
`dist/aigosmart-ha-0.1.4-beta.5.zip`.

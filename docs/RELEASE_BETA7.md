# v0.1.4-beta.7 — 2026-10-26

Opt-in beta prerelease. Stable v0.1.3 remains Latest.

- Fix Alibaba refresh request wire nesting: credentials belong in `params.request` for `/account/checkOrRefreshSession`; API version remains 1.0.4.
- Carry all issue #12 source: opt-in diagnostic manual refresh button (#9), safe response-shape diagnostics (#10), `application_rejection` distinction (#11), and signed nested refresh-body regression (#12).
- Preserve token expiry/rotation persistence, valid-session handling, bounded retries, bundled integration card, translations, and one-attempt device-write safety. No unrelated card improvements are claimed.
- Privacy: diagnostics retain allowlisted categories/types, not token values, passwords or raw response bodies.

User live evidence on 2026-10-26: one manual refresh with the issue #12 build succeeded (vendor code 200); tokens rotated, expiries advanced, authorization/connection stayed healthy, and cloud/device reads succeeded. Automatic timer refresh with this fixed version is NOT YET proven, including a 20-hour run. Earlier beta.6 rejected 21 automatic attempts and one early manual test.

Enable diagnostics to use the manual refresh diagnostic button. Roll back via HACS Redownload to stable v0.1.3 or beta.6 if needed; beta.6 does not fix refresh. No live cloud requests or appliance actions were performed during packaging.

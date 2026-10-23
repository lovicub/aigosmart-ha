# Changelog

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

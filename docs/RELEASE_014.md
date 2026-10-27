# v0.1.4 — 2026-10-27

- Bundle the native `custom:aigosmart-ha-integrated-card` smart-kettle dashboard with MIT attribution; the separately installed Premium Card remains optional and can coexist.
- Fix automatic Alibaba IoT session/token refresh using `params.request` at API version 1.0.4; owner-confirmed rejected-token recovery on 2026-10-27 restored cloud/device reads. Scheduled proactive renewal before expiry remains separately unverified.
- Improve private diagnostic sensors and manual refresh, Mode descriptions and English/German/Polish translations, and bounded session recovery resilience.
- Preserve entity IDs, token/refreshToken/identityId and expiry persistence, and one-attempt device controls without heating-command replay.

Stable code update to main only; no new tag, GitHub Release or ZIP publication.

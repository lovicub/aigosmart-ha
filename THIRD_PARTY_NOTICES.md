# Third-party licenses and provenance

MIT is used for original code and documentation in this repository. Dependencies
are imported from the user's Home Assistant/Python environment, not vendored.
This license does not replace their own copyright notices or license terms.

| Component | License | Use |
| --- | --- | --- |
| Home Assistant | Apache-2.0 | Host platform and imported helpers/entities |
| cryptography | Apache-2.0 OR BSD-3-Clause | AES-CBC and PKCS7 primitives |
| voluptuous | BSD-3-Clause | Configuration schemas |
| Python standard library | PSF license | Runtime, HTTPS, signing and serialization |

These are permissive dependency licenses; no copyleft dependency was identified
among direct runtime imports. Transitive dependencies are managed by HA and are
not redistributed in this repository or integration ZIP. No dependency binaries,
private APKs or captured account data are included.

Protocol provenance: the existing implementation records a review against
MarcoM1993/ha-aigostar commit 39f7bab1edd36161e41430ed1e01439e4e8b51ab. That project's
current repository identifies an MIT license. The local source states that no
upstream code is imported or executed. This release preserves that attribution
and does not claim ownership of third-party libraries or public app constants.
If upstream source is incorporated later, retain its full applicable copyright
and license notice. The historical commit's license was not independently fetched.

App signing/client constants in protocol.py are part of the existing public app
protocol, not user account credentials. They are retained because the working
protocol depends on them; this does not grant rights to third-party services.

Sources checked:

- https://github.com/home-assistant/core/blob/dev/LICENSE.md
- https://github.com/pyca/cryptography/blob/48.0.1/LICENSE
- https://github.com/pyca/cryptography/blob/48.0.1/LICENSE.BSD
- https://github.com/alecthomas/voluptuous/blob/master/COPYING
- https://github.com/MarcoM1993/ha-aigostar
- https://docs.python.org/3/license.html


The v0.1.2 refresh request envelope was reviewed against
[`refresh_iot_token_sync()` in MarcoM1993/ha-aigostar](https://github.com/MarcoM1993/ha-aigostar/blob/main/custom_components/aigostar/alibaba_api.py).
The implementation here is independent; no upstream module is imported or run.
Alibaba's [OpenAccount guide](https://g.alicdn.com/linkbusiness-fe/iotx-linkbusiness-common/1.0.5/sitedocs/dch3zc.html)
documents `iotTokenExpire` and `refreshTokenExpire` as durations in seconds.
The [Alibaba error code dictionary](https://help.aliyun.com/en/document_detail/127995.html)
provides the reviewed authentication error vocabulary, including 100003 for an
invalid or expired refresh token. Unknown codes and server messages are redacted.


v0.1.4-beta.4 additionally reviews JuanmanDev/aigo-smart commit
66173b5235a70e2b7bf6bf136823d168972ca2c1 (MIT) and the Marco commit above
(MIT verified through GitHub). No source is copied, imported or executed.
The independent recovery changes do not adopt upstream raw-response logging,
credential retention or write retries. See docs/SESSION_REFRESH_BETA4.md for
per-file references and provider documentation. Existing notices are retained.

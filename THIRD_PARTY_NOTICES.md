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

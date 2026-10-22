# Validation results

Preparation date: 2026-10-22. Integration version: 0.1.1.

| Check | Result |
| --- | --- |
| Original source suite, cryptography 48.0.1 | 91 passed |
| Independent publication directory, cryptography 48.0.1 | 91 passed |
| Independent publication directory, cryptography 50.0.1 | 91 passed |
| Runtime Python source comparison | All 13 integration Python files AST-identical; 12 byte-identical, model.py trailing blank lines normalized |
| Script comparison | All four original CLI scripts byte-identical to source |
| JSON / YAML and repository structure | Validated locally |
| Credentials and PII review | See SECURITY_REVIEW.md |
| Official hassfest | Not run locally: Docker/action runtime unavailable |
| Official HACS validation | Not run locally: Docker unavailable and remote repository not published |

The test environment uses Python 3.14.4 and installed Home Assistant 2026.10.2
classes. cryptography 48.0.1 was loaded from a separate target directory; the
base HA package declares 50.0.1. The 48.0.1 run proves these integration tests work
with that library, not that the entire HA dependency set supports an override.
The integration manifest has requirements=[], so it does not replace HA's library.

All tests use mock API transports. No real login, kettle command or running HA
configuration was used. The publication test suite changes fixture paths only:
two tests use tests/fixtures/kettle_capabilities.json, and the CLI dry-run test
passes that fixture explicitly. No private reports are required or distributed.

Official validation actions are configured for the future repository. Their status
is pending, not passed. The separate Premium Card now has its supplied JS and its own validation report.
Screenshots from a real installation have not been supplied.

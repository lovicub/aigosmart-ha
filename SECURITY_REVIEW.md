# Security review

Preparation date: 2026-10-22. This is a publication-content review, not a guarantee
that every possible credential pattern can be detected.

## Scope and findings

Source application files, tests, metadata and reports were inspected with local
pattern checks and detect-secrets 1.5.0. Dependency environments, generated caches,
old build archives and environment-owned directories were inventoried as excluded
material, not treated as publishable application source. All exported text files
were checked for email addresses, IPv4/MAC addresses, account/device identifier
literals, token/password assignments, private keys and environment files.

The source and export scans each produced 11 candidate detections (10 distinct
lines), all reviewed:

- Two detections on the same public APK app-signing constant in protocol.py.
- Four password-field translation labels, not credential values.
- Five synthetic test credential/error fixtures, not real account credentials.

No real account passwords/tokens, email addresses, device iotId, Virtual ID,
MAC addresses or private network addresses were identified in the exported files.
Example email addresses and sentinel strings in offline tests are intentional.
GitHub account lovicub and repository URLs are intentional public attribution.

Public application/client signing constants remain in the existing protocol.
They are not user tokens and removing them would break authentication. They were
reviewed separately from secret-like test strings; the API implementation is
unchanged. The scanner used --no-verify: potential tokens were never sent to
external verification services. Raw scanner output stays outside the repositories.

## Excluded material

No original reports/, old diagnostic README, logs, .env files, .venv, HA .storage,
private HA YAML, .aws, .codex, .agents, __pycache__, old ZIP archives, test.txt,
credentials or binary dependency packages were copied into either repository.
A fresh synthetic TSL fixture contains only known property definitions and no
captured responses or device/account identifiers. Generated cache files created
while testing are ignored and were removed from the publication directories.
The icon is an existing geometric project asset without embedded account metadata.

## Git history

The visible source .git directory is empty and git rev-parse / git log report
that it is not a Git repository. No accessible source history could be audited;
this is not a certification of any history outside the provided workspace view.
No source .git data was copied. Each publication directory has a newly initialized
local main branch with no commits, remotes or inherited objects/history. Only
reviewed files are staged. No commits, remotes, pushes or GitHub repositories
were created. After future commits, scan history again before publication if
additional material is added.

## Runtime observations preserved from source

The client keeps TLS verification, rejects redirects, allows reviewed endpoints
and sanitizes API error reporting. HA stores email/session token in config-entry
storage; password/security code are not persisted by this integration. Heating is
not restored after restart. No live API calls were made during preparation.

## Companion card handoff update

GitHub CLI is now available and the requested read-only user lookup returned
lovicub. The real Premium Card v0.1.0 JS is now included in its own repository,
byte-identical to the supplied file. The two-repository scan covered 58 files:
no additional secret candidates were found in the card. Browser/error-log and
provenance observations are documented in the card's separate security report.
The Python integration was not changed during this handoff update.


## v0.1.2 session handling review (2026-10-23)

Config Entry data now includes IoT/refresh tokens, identityId, API TTLs, absolute
expiry timestamps and the last successful refresh. These are protected by HA's
configuration/backup access controls, not encrypted by this integration. The
new diagnostic export uses an explicit allowlist of three non-sensitive values;
it does not export entry data, device identifiers, email or credentials.
Refresh diagnostics and exceptions use fixed messages/sanitized error codes.
Offline tests assert tokens/identity IDs are absent from debug logs and entity
attributes. Writes remain single-attempt; refresh and read retries cannot invoke
the write path. No credentials were sent to any API for v0.1.2 verification.

# Stable main — v0.1.4

This update prepares and pushes stable code to main only. Build the local archive
with `python tools/build_zip.py`; do not publish it. No Git tag, GitHub Release or
public ZIP upload is part of this update. Validate the merged commit before push.

The instructions below are historical beta/release handoffs, not current main
publication instructions; their branch restrictions describe those past tasks.

---

# Beta.7 publication

Publish only beta/diagnostics-v014 after all five Validate jobs succeed.
Use annotated v0.1.4-beta.7, prerelease=true, latest=false. Never replace tags.
Release notes: docs/RELEASE_BETA7.md. Preserve main and previous releases.

# Beta publication — v0.1.4-beta.6

Publish only `beta/diagnostics-v014`; never merge this release into stable main.
Run the full offline suite with cryptography 48.0.1 and 50.0.1, build with
`python3 tools/build_zip.py`, and verify all GitHub Validate jobs on the exact
commit: tests (48.0.1), tests (50.0.1), hacs, hassfest and native_select_frontend.
Create the unused annotated tag `v0.1.4-beta.6` only after those checks pass;
attach `dist/aigosmart-ha-0.1.4-beta.6.zip`. Create a prerelease with `--latest=false`.
Never replace an existing tag or release, including beta.5. Keep issue #3 open.

Release notes must explain the missing `http` after-dependency fix and preservation
of beta.5 functionality. The production root cause remains unconfirmed; do not
claim the 12–24 hour production failure is resolved. Production verification and
stable-release gates are in docs/SESSION_REFRESH_BETA4.md.

---

Historical handoff follows.

# Publication handoff — v0.1.2

The working tree contains the prepared v0.1.2 changes on top of the local v0.1.1
commit. No push, tag, GitHub release or deployment has been performed for v0.1.2.
Review the diff and [validation results](VALIDATION.md) before publishing.

```sh
python -m unittest discover -s tests -v
python tools/build_zip.py
git diff --check
git status --short
git add custom_components tests README.md CHANGELOG.md VALIDATION.md PUBLISHING.md SECURITY_REVIEW.md THIRD_PARTY_NOTICES.md tools/build_zip.py
git commit -m "fix: refresh IoT sessions automatically (v0.1.2)"
```

The reviewed release archive is `dist/aigosmart-ha-0.1.2.zip`.
The `dist/` directory is ignored; attach the ZIP as a GitHub release asset.
`CHANGELOG.md` contains release notes. Publishing remains a manual step: confirm
the intended remote and branch, push the reviewed commit, then tag `v0.1.2` and
create its release. Run the official hassfest and HACS workflows on GitHub.
No automatic push is included in this handoff.

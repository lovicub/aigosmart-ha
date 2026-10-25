# Beta publication — v0.1.4-beta.4

Publish only `beta/diagnostics-v014`; never merge this release into stable main.
Run the full offline suite with cryptography 48.0.1 and 50.0.1, build with
`python3 tools/build_zip.py`, and verify all GitHub Validate jobs on the exact
commit. Create the unused tag `v0.1.4-beta.4` only after those checks pass; attach
`dist/aigosmart-ha-0.1.4-beta.4.zip`. Create a prerelease with `--latest=false`.
Never replace an existing tag or release. Keep issue #3 open.

Release notes must describe recovery fixes and safe diagnostic instrumentation,
without claiming the 12–24 hour production failure is resolved. Production
verification and stable-release gates are in docs/SESSION_REFRESH_BETA4.md.

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

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

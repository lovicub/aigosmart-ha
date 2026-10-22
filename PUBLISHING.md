# Publication handoff

Nothing has been published. This directory is an independent local Git repository
on branch `main`, with no commits or configured remotes. GitHub CLI is available; the read-only command `gh api user --jq '.login'`
confirmed the authenticated login as `lovicub`. Run these commands yourself only after approving
the reviewed contents and configuring your Git author identity:

```sh
git status --short
git diff --cached --check
git add .
git commit -m "Prepare initial public release"
gh auth login
gh repo create lovicub/aigosmart-ha --public --source=. --remote=origin --push
```

The last command publishes to GitHub. It has **not** been executed. A public
GitHub profile name appears intentionally in README and repository metadata;
no private account email is required in the repository files.

After publication, add a description and the relevant Home Assistant / HACS topics,
check the official validation workflows, and use a custom HACS repository for initial
tests. Do not claim default HACS catalog inclusion. Review screenshots before upload.

For an integration release, run `python tools/build_zip.py` and review the output.
Use version 0.1.1 in the manifest; do not commit your local `dist/` directory or
captured reports. No live kettle command is required by the automated tests.

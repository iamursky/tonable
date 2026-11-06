# Publication preparation

Preparation date: 6 November 2026. This is a source-readiness record, not a
publication or a release. No public repository, remote or package upload was
created. The working tree was clean before preparation; changes were made in the
existing task worktree.

## Source and package review

- Public documentation, CLI text, comments and examples use English. Personal
  assistant instructions and machine-specific storage paths were removed.
- The README banner reuses the existing Tonable logo in a local SVG with an
  English alternative description. No generated service or external image host
  is required.
- Public package, MCP and bridge identifiers are unchanged. No protocol migration
  is needed; see [architecture](plan.md#public-api-stability).
- MIT was already selected in `LICENSE` and package metadata. The author credit
  and third-party MIT notices were preserved. Dependencies retain their own
  licenses; Ableton software and licensed content are not distributed.
- `probe/` remains optional developer diagnostics. It has no network server and
  is useful for real Live API regressions. Personal instructions and fixed disk
  locations were removed; installation uses the configured User Library. Its
  source and tests ship in the source archive, while the installed wheel contains
  only the application and production Remote Script.
- The source archive uses an explicit directory allowlist. Ignore rules cover
  virtual environments, Python caches, builds, local assistant configuration,
  credential files, session discovery, probe reports, logs and Ableton content.
  Ignore rules do not remove files that have already entered git history.

## Checks performed

- `uv sync --locked` and `uv lock --check` succeeded.
- `uv run pytest`: 111 tests passed on macOS arm64, Python 3.13.17. This includes
  loopback bridge tests, fake Live tests, portable probe installation and a real
  MCP stdio subprocess handshake/discovery/disconnected-status check.
- All 111 tests also passed on Python 3.11.17 from the extracted source archive.
  The installed wheel was checked outside the checkout on Python 3.11.17:
  temporary-library script installation/removal, stdio initialization, discovery
  of all 24 tools and disconnected status handling passed.
- The SVG banner was rendered and visually checked; 24 local Markdown links and
  anchors resolved. Legal author credits remain intentional public metadata.
- `uv run ruff check .` and `uv run ruff format --check .` passed.
- `uv build` built the source archive and then the wheel from that archive.
  Archive inspection confirmed the production Remote Script and both license
  files in the wheel, and diagnostic source/tests in the source archive.
- Gitleaks 8.30.1 scanned the publishable working files and all available git refs
  with output redaction: no detected secrets. The checkout is not shallow; 16
  commits and 119 unique historical file blobs were reviewed for branding,
  non-English text, local paths and email addresses.
- `pip-audit` found no known vulnerabilities in 35 installed third-party
  distributions. The local `tonable` package was skipped because it is not in
  the advisory index. This is a scan of the installed Python 3.13 dependency set,
  not every conditional dependency on every Python version or platform.
- Client examples were checked against official documentation linked in
  [client setup](clients.md). Claude Code's local CLI help also confirmed its
  stdio and user-scope flags. No user's client configuration was changed.

Secret detection is heuristic and advisory databases change. Repeat the scans on
the final publication candidate, including any files added after this review.
Do not include virtual environments or build output in a source commit.

## History requires a publication decision

The current source no longer contains the earlier product branding, personal
assistant scenarios, Russian prose or workstation-specific disk paths. The
available git history still contains those materials. They occur in older file
versions and commit messages; author/committer metadata also exposes a personal
email address. These are privacy and presentation findings, not detected leaked
credentials. Legal author and upstream copyright credits are intentionally kept.

Do not publish the existing history unchanged if the public project must exclude
all earlier branding and personal details. Choose one of these approaches:

1. **Recommended: start public history from the approved clean snapshot.** After
   the final source is committed and reviewed, export only that commit's tracked
   files into a separate directory without `.git`, local files or build output.
   Review the export again, initialize a new repository with a neutral branch
   name, and make an initial English commit using an approved public identity
   or a GitHub no-reply email. Keep the original development history private.
2. **Preserve selected history only after a separately approved cleanup.** Back
   up the original repository, review all refs, remove private content from file
   revisions and messages, and review author metadata. Re-run all scans before
   publishing. This changes commit identities and needs coordination with anyone
   using the old history.

Neither export into a new repository nor history rewriting was performed here.
No credentials were detected in history. If a later scan identifies one, revoke
or rotate it first, then plan removal from every affected ref and coordinate
cleanup of copies; history cleanup alone does not make a credential safe again.

## Remaining release steps

- Approve the public-history approach and public commit identity. Recheck the
  final commit created by the workspace manager as well as earlier commits.
- Repeat the read-only connection checks in each intended client, then the
  [manual Live checklist](../tests/manual_checklist.md) in a disposable Set.
  Publication preparation did not install scripts into the user's Live library,
  run the probe in Live or exercise client UIs. Earlier Live 12.4.16 results are
  historical evidence, not a new acceptance run.
- Choose the repository owner/name and add its real source and issue URLs to
  package metadata once known. No destination URLs were invented.
- Rebuild and re-scan the approved snapshot. Create a public repository or publish
  a package only after explicit authorization for that step.

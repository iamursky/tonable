# CI and releases

Tonable uses GitHub Actions in
[iamursky/tonable](https://github.com/iamursky/tonable/actions). CI validates source
changes; the Release workflow publishes the exact distributions it has tested.
No Live installation, client configuration or user library is changed by CI.

## Continuous integration

[ci.yml](https://github.com/iamursky/tonable/blob/main/.github/workflows/ci.yml)
runs on branch pushes, pull requests and manual dispatches. It also runs as a
reusable workflow for releases.

- Locked dependencies, Ruff lint and formatting on Python 3.13.
- Full tests on Linux and macOS, each with Python 3.11 and 3.13.
- A fresh sdist, then a wheel built from that sdist.
- Strict Twine metadata validation and archive composition checks, including
  production Remote Script resources and both MIT notice files.
- Full tests from the extracted sdist on Python 3.11, outside the checkout.
- Clean-environment wheel installation, entry points, temporary-library component
  installation/replacement/removal, `uvx` launch and discovery of 24 MCP tools.
- A `python-distributions` artifact retained for 30 days, uploaded only after all
  checks pass.

Tests use a fake Live API, temporary homes and loopback sockets. They do not prove
Live behavior, audio quality or Windows compatibility. Before a release, repeat
the [manual Live checklist](../tests/manual_checklist.md) in a disposable Set and
verify read-only connections in each intended client. Record the commit, Live,
client and OS versions with the results.

Third-party Actions are pinned to full commit SHAs; uv is pinned to 0.13.5. Normal
CI has a read-only repository token and no PyPI credentials. Keep pins current
through reviewed changes.

## Release a version

[release.yml](https://github.com/iamursky/tonable/blob/main/.github/workflows/release.yml)
runs when a `v*` tag is pushed. Manual dispatch is supported when its selected ref
is a version tag. Dispatching it on a branch fails before publication.

1. Update the package version in `pyproject.toml` and
   `remote_script/Tonable/version.py`; refresh `uv.lock`. Update versioned links
   in the README and client instructions, plus the release notes in
   `.github/release-notes.md`.
2. Merge the reviewed candidate into `main` and wait for CI to pass.
3. Tag that exact commit with `v<version>` and push only that tag. For 0.5.2:

   ```sh
   git tag -a v0.5.2 <approved-commit> -m 'Tonable 0.5.2'
   git push origin refs/tags/v0.5.2
   ```

4. Release checks that the tag equals the package version and its commit is on
   `main`, then runs the complete CI workflow again.
5. The GitHub job downloads the tested wheel and sdist, calculates SHA-256 sums,
   and publishes a release with both files and `SHA256SUMS.txt`. It stages the
   release as a draft until its files are attached. Reruns compare existing
   assets and refuse to replace different bytes.
6. If `PYPI_PUBLISH_ENABLED` is exactly `true`, the PyPI job publishes those same
   wheel/sdist bytes using OIDC. It does not check out or build source. Only this
   job receives `id-token: write`; only the GitHub release job receives
   `contents: write`.
7. A final job compares PyPI's hashes with the tested artifacts, then launches
   `tonable==<version>` from the public registry in a clean temporary home and
   confirms discovery of all 24 tools. No registry-install claim relies only on
   a successful upload response.

Do not move a published tag or replace release assets. Fix a released package by
issuing a new version. After a partial workflow failure, inspect what was already
published before retrying. PyPI version uploads are immutable; the workflow does
not silently skip existing files.

## Enable PyPI once

GitHub release downloads work independently of PyPI. The repository variable
`PYPI_PUBLISH_ENABLED` must stay `false` until the owner has configured the
publisher. The owner confirmed the pending publisher for Tonable on 6 November
2026; the repository variable is now enabled. No long-lived PyPI token is required.

Sign in to the intended PyPI owner account and open
[account publishing](https://pypi.org/manage/account/publishing/). If `tonable`
does not exist, add a pending GitHub publisher using these exact values:

| Field | Value |
|---|---|
| PyPI project name | `tonable` |
| GitHub owner | `iamursky` |
| GitHub repository | `tonable` |
| Workflow filename | `release.yml` |
| Environment | `pypi` |

For an existing project you own, configure the equivalent publisher in its
publishing settings. Use GitHub's `pypi` environment and restrict deployment refs
to version tags. Then enable the repository variable:

```sh
gh variable set PYPI_PUBLISH_ENABLED --repo iamursky/tonable --body true
gh workflow run release.yml --repo iamursky/tonable --ref v0.5.2
```

The dispatch reruns validation and verifies existing GitHub assets before the
first PyPI upload. Use it only after confirming ownership and the publisher
configuration. A pending publisher does not reserve the package name; PyPI may
reject an unavailable name. See the official
[pending-publisher guide](https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/)
and [publishing workflow guide](https://docs.pypi.org/trusted-publishers/using-a-publisher/).

After upload, verify version 0.5.2 at
[PyPI](https://pypi.org/project/tonable/0.5.2/), compare its file hashes with the
GitHub release, and test the registry command from outside the checkout:

```sh
uvx --python 3.11 --from 'tonable==0.5.2' tonable --version
```

Only then advertise registry installation. Until then, use the versioned GitHub
wheel URL in the README and client examples.

## Local reproduction

```sh
uv sync --locked --python 3.13
uv lock --check
uv run ruff check .
uv run ruff format --check .
uv run pytest
uv build
uvx --from twine==7.0.0 twine check --strict dist/*
uv run python scripts/check_sdist.py --python 3.11
uv run python scripts/check_distribution.py \
  --wheel dist/tonable-0.5.2-py3-none-any.whl \
  --sdist dist/tonable-0.5.2.tar.gz --python 3.11
```

Start with a fresh `dist/` containing only the candidate version. Build output is
ignored by Git; CI artifacts and published release files retain the reviewed
outputs. Preserve MIT, upstream notices and the existing author credits. Review
source and distribution contents for credentials and local runtime data before
publishing; never include `~/.tonable/session.json` or raw private reports.

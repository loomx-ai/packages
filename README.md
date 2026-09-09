# LoomX package repositories

Signed APT and RPM repositories for [Steward](https://github.com/loomx-ai/steward).

## Install

Follow the [installation guide](https://loomx.ai/steward/docs/installation).
The repository base is `https://loomx-ai.github.io/packages/steward`.
APT supports amd64 and arm64. RPM supports x86_64 and aarch64.

`gpg.key` is the public package signing key. APT uses signed `InRelease`
metadata; RPM verifies both the package signatures and `repomd.xml` signature.
The original GitHub Release assets are immutable. RPM signing happens only on
the copies hosted here. `checksums.txt.asc` signs the latest release's original
checksum file for users downloading its archives directly.

## Publish

The `Publish signed packages` workflow checks for the latest stable Steward
release every hour and supports manual dispatch. Unchanged releases are skipped;
APT metadata is refreshed weekly and expires after 30 days. GitHub schedules can
be delayed. After a new release, publish immediately with:

```sh
gh workflow run publish.yml --repo loomx-ai/packages
```

Publication verifies upstream SHA-256 hashes, signs packages and indexes, and
tests repository installation, upgrade, server startup, removal, and retained
data in Ubuntu, Debian, Fedora, Rocky Linux, and Amazon Linux containers. Only
then does GitHub Pages deploy the complete repository in one operation. Failed
builds leave the previous site available.

`PACKAGE_SIGNING_KEY` is an Actions secret containing the armored private key
corresponding to `gpg.key`. Build jobs import it into a temporary keyring that is
deleted before uploading artifacts. Deployment jobs have no signing key access.
Never commit a private key or overwrite this secret without a key rotation plan.
To rotate, distribute the new public key and update users' `Signed-By`/`gpgkey`
configuration before removing the old key.

Native package repositories contain the latest stable version. Older versions
remain available as immutable GitHub Release downloads; `releases.json` indexes
up to 30 stable releases for the documentation's version picker.

## Check changes

```sh
python3 -m unittest discover -s scripts -p 'test_*.py'
bash -n scripts/smoke.sh
actionlint .github/workflows/publish.yml
```

Linux builds require apt-utils, RPM, createrepo-c, GnuPG, Python 3, and GitHub CLI.

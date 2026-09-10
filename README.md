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
The release index also accepts additional standalone executables verified by
GitHub's SHA-256 asset digest, so existing release archives and checksums do not
need to be replaced. New releases include executables in their checksum file.

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

Each deployment commits `published.json` as a receipt. Weekly metadata renewal
therefore also maintains repository activity, keeping GitHub's public-repository
inactivity policy from disabling the scheduled publisher. Source comparison uses
the packaging files, so receipt commits do not cause unnecessary rebuilds.

`PACKAGE_SIGNING_KEY` is an Actions secret containing the armored private key
corresponding to `gpg.key`. Build jobs import it into a temporary keyring that is
deleted before uploading artifacts. Deployment jobs have no signing key access.
Never commit a private key or overwrite this secret without a key rotation plan.
To rotate, distribute the new public key and update users' `Signed-By`/`gpgkey`
configuration before removing the old key.

Native package repositories contain the latest stable version. Older versions
remain available as immutable GitHub Release downloads; `releases.json` indexes
all published semantic-version releases, including prereleases, for the download
history and documentation's version picker. Drafts are never published.

## R2 release downloads

The publisher can mirror the indexed GitHub Release assets to the `loomx-downloads`
R2 bucket, served at `https://downloads.loomx.ai/steward/v<VERSION>/<FILE>`.
GitHub remains the release source, and APT/RPM repositories stay on GitHub Pages.
Original release RPM files in R2 retain their upstream checksums; the separately
signed RPM copies continue to live in the package repository.

Enable R2 in the existing Cloudflare account before creating the bucket. Using
the pinned Wrangler installed in the sibling `docs` checkout, run from there:

```sh
npx wrangler r2 bucket create loomx-downloads --location apac
npx wrangler r2 bucket domain add loomx-downloads --domain downloads.loomx.ai --zone-id <LOOMX_ZONE_ID> --min-tls 1.2
npx wrangler r2 bucket cors set loomx-downloads --file ../packages/r2-cors.json
```

Use a dedicated R2 API token with **Object Read & Write** access limited to this
bucket. Store its S3 credentials as the `R2_ACCESS_KEY_ID` and
`R2_SECRET_ACCESS_KEY` GitHub Actions secrets in this repository. Do not use a
personal Wrangler OAuth token in CI. The Ubuntu runner provides the AWS CLI;
manual publication also requires `aws`, `gh`, and Python 3.9 or later.

Deploy the documentation renderer's R2 URL support before switching downloads.
After the custom domain is active and the secrets are configured, set the
repository variable `R2_BUCKET=loomx-downloads` and dispatch `publish.yml`.
Changing this variable also forces publication when the release is unchanged.

`scripts/mirror.py` downloads the indexed releases, checks every asset's size and
SHA-256, uploads the original files and `checksums.txt`, and downloads them from
the public domain to verify their hashes again. Only then does it publish the R2
index and rewrite the GitHub Pages release index to use the verified R2 URLs.
A failed mirror stops publication, leaving the previous Pages index available.
Versioned objects use one-year immutable caching; the R2 index uses a 60-second
TTL. Configure a Cloudflare Cache Rule for `/steward/v*` if extensionless binaries
should be cached at the edge; custom-domain defaults do not cache every type.

Removing `R2_BUCKET` and rerunning publication restores GitHub download URLs.
Mirror uploads never delete older R2 objects. All published versions are indexed
and retained objects count toward R2 storage usage. The hourly publisher detects
new prereleases and assets added to an existing release as well as stable releases.

## Check changes

```sh
python3 -m unittest discover -s scripts -p 'test_*.py'
bash -n scripts/smoke.sh
actionlint .github/workflows/publish.yml
```

Linux builds require apt-utils, RPM, createrepo-c, GnuPG, Python 3, and GitHub CLI.

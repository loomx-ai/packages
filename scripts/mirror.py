#!/usr/bin/env python3
"""Mirror verified release assets to R2 before publishing their download URLs."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import urllib.request

from build import REPO, ROOT, VERSION

DOWNLOADS = "https://downloads.loomx.ai/steward"


def validate(index):
    if not index.get("releases") or index.get("latest") not in [r["version"] for r in index["releases"]]:
        raise ValueError("Missing latest release")
    for release in index["releases"]:
        version = release["version"]
        if not re.fullmatch(VERSION, version) or not release["assets"]:
            raise ValueError("Invalid release")
        for name, asset in release["assets"].items():
            if (not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]*", name)
                    or asset["url"] != f"https://github.com/{REPO}/releases/download/v{version}/{name}"
                    or not re.fullmatch(r"[a-f0-9]{64}", asset["sha256"])
                    or type(asset["size"]) is not int or asset["size"] <= 0):
                raise ValueError(f"Invalid asset: {name}")


def run(*args):
    subprocess.run(args, check=True)


def sha256(source):
    digest = hashlib.sha256()
    for chunk in iter(lambda: source.read(1024 * 1024), b""):
        digest.update(chunk)
    return digest.hexdigest()


def verify_public(url, expected):
    with urllib.request.urlopen(url, timeout=120) as response:
        if sha256(response) != expected:
            raise ValueError(f"Public download checksum mismatch: {url}")


def mirror(index, upload):
    validate(index)
    mirrored = json.loads(json.dumps(index))
    for release in mirrored["releases"]:
        version = release["version"]
        with tempfile.TemporaryDirectory(prefix="steward-r2-") as temp:
            directory = Path(temp)
            args = ["gh", "release", "download", f"v{version}", "--repo", REPO,
                    "--dir", temp, "--pattern", "checksums.txt"]
            for name in release["assets"]:
                args += ["--pattern", name]
            run(*args)
            checksums = {}
            for line in (directory / "checksums.txt").read_text().splitlines():
                digest, name = line.split()
                checksums[name] = digest
            # Validate every download before this version becomes available in R2.
            for name, asset in release["assets"].items():
                file = directory / name
                with file.open("rb") as source:
                    digest = sha256(source)
                if (file.stat().st_size != asset["size"] or digest != asset["sha256"]
                        or checksums.get(name, digest) != digest):
                    raise ValueError(f"Checksum or size mismatch: {name}")
                asset["url"] = f"{DOWNLOADS}/v{version}/{name}"
            upload(directory, f"steward/v{version}/", recursive=True)
            release["checksumsUrl"] = f"{DOWNLOADS}/v{version}/checksums.txt"
            for asset in release["assets"].values():
                verify_public(asset["url"], asset["sha256"])
            verify_public(release["checksumsUrl"], hashlib.sha256((directory / "checksums.txt").read_bytes()).hexdigest())
    return mirrored


def main():
    account = os.environ["CLOUDFLARE_ACCOUNT_ID"]
    bucket = os.environ["R2_BUCKET"]
    if not re.fullmatch(r"[a-f0-9]{32}", account) or not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,61}[a-z0-9]", bucket):
        raise ValueError("Invalid R2 account or bucket")
    for name in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"):
        if not os.environ.get(name):
            raise ValueError(f"Missing {name}")
    # R2's S3 API uses auto and supports the checksums required by S3 operations.
    os.environ["AWS_DEFAULT_REGION"] = "auto"
    os.environ["AWS_REQUEST_CHECKSUM_CALCULATION"] = "WHEN_REQUIRED"
    os.environ["AWS_RESPONSE_CHECKSUM_VALIDATION"] = "WHEN_REQUIRED"
    os.environ["AWS_PAGER"] = ""

    def upload(source, key, recursive=False):
        args = ["aws", "s3", "cp", str(source), f"s3://{bucket}/{key}",
                "--endpoint-url", f"https://{account}.r2.cloudflarestorage.com", "--only-show-errors",
                "--cache-control", "public, max-age=31536000, immutable" if recursive else "public, max-age=60"]
        args += ["--recursive"] if recursive else ["--content-type", "application/json"]
        run(*args)

    path = ROOT / "site" / "steward" / "releases.json"
    index = mirror(json.loads(path.read_text()), upload)
    with tempfile.TemporaryDirectory(prefix="steward-r2-index-") as temp:
        staged = Path(temp) / "releases.json"
        staged.write_text(json.dumps(index, indent=2) + "\n")
        # Both public indexes change only after every release upload succeeds.
        upload(staged, "steward/releases.json")
        path.write_bytes(staged.read_bytes())


if __name__ == "__main__":
    main()

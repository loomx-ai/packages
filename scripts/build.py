#!/usr/bin/env python3
"""Verify published releases, then build signed APT/RPM repositories."""
import datetime as dt
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

ROOT = Path(__file__).resolve().parent.parent
REPO = "loomx-ai/steward"
BASE = "https://loomx-ai.github.io/packages/steward"


def run(*args, cwd=None):
    return subprocess.check_output(args, cwd=cwd, text=True)


def verify(directory):
    checksums = {}
    for line in (directory / "checksums.txt").read_text().splitlines():
        digest, name = line.split()
        if not re.fullmatch(r"[0-9a-f]{64}", digest) or Path(name).name != name:
            raise ValueError("Invalid checksum entry")
        checksums[name] = digest
    for file in directory.iterdir():
        if file.name != "checksums.txt":
            if hashlib.sha256(file.read_bytes()).hexdigest() != checksums.get(file.name):
                raise ValueError(f"Checksum mismatch: {file.name}")
    return checksums


def main():
    latest = json.loads(run("gh", "release", "view", "--repo", REPO, "--json", "tagName"))["tagName"]
    releases = json.loads(run("gh", "api", f"repos/{REPO}/releases?per_page=100"))
    releases = [r for r in releases if not r["draft"] and not r["prerelease"] and re.fullmatch(r"v[0-9]+\.[0-9]+\.[0-9]+", r["tag_name"])]
    if latest not in [r["tag_name"] for r in releases]:
        raise ValueError("Latest stable release is missing")
    releases.sort(key=lambda r: tuple(map(int, r["tag_name"][1:].split("."))), reverse=True)
    output = ROOT / "site" / "steward"
    output.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ROOT / "gpg.key", output / "gpg.key")
    key = os.environ["SIGNING_FINGERPRINT"]
    index = []
    for release in releases[:30]:
        tag = release["tag_name"]
        version = tag[1:]
        incoming = ROOT / "incoming" / version
        incoming.mkdir(parents=True, exist_ok=True)
        args = ["gh", "release", "download", tag, "--repo", REPO, "--dir", str(incoming), "--pattern", "checksums.txt"]
        if tag == latest:
            args += ["--pattern", "*.deb", "--pattern", "*.rpm"]
        run(*args)
        hashes = verify(incoming)
        assets = {a["name"]: {"url": a["browser_download_url"], "sha256": hashes.get(a["name"]), "size": a["size"]} for a in release["assets"] if a["name"] in hashes}
        index.append({"version": version, "url": release["html_url"], "publishedAt": release["published_at"], "assets": assets})
        if tag != latest:
            continue
        # Sign the unchanged upstream checksum file as well as package metadata.
        shutil.copyfile(incoming / "checksums.txt", output / "checksums.txt")
        run("gpg", "--batch", "--yes", "--local-user", key, "--armor", "--detach-sign", str(output / "checksums.txt"))
        for arch, rpm_arch in (("amd64", "x86_64"), ("arm64", "aarch64")):
            deb = f"steward_{version}_linux_{arch}.deb"
            pool = output / "apt" / "pool" / arch
            pool.mkdir(parents=True)
            shutil.copyfile(incoming / deb, pool / deb)
            packages = output / "apt" / "dists" / "stable" / "main" / f"binary-{arch}"
            packages.mkdir(parents=True)
            data = run("apt-ftparchive", "packages", f"pool/{arch}", cwd=output / "apt").encode()
            (packages / "Packages").write_bytes(data)
            (packages / "Packages.gz").write_bytes(gzip.compress(data, mtime=0))
            rpm = f"steward_{version}_linux_{arch}.rpm"
            rpm_dir = output / "rpm" / rpm_arch
            (rpm_dir / "Packages").mkdir(parents=True)
            rpm_file = rpm_dir / "Packages" / rpm
            shutil.copyfile(incoming / rpm, rpm_file)
            run("rpmsign", "--define", f"_gpg_name {key}", "--define", f"_gpg_path {os.environ['GNUPGHOME']}", "--define", "__gpg /usr/bin/gpg", "--addsign", str(rpm_file))
            run("createrepo_c", str(rpm_dir))
            run("gpg", "--batch", "--yes", "--local-user", key, "--armor", "--detach-sign", str(rpm_dir / "repodata" / "repomd.xml"))
        release_dir = output / "apt" / "dists" / "stable"
        metadata = run("apt-ftparchive", "-o", "APT::FTPArchive::Release::Origin=LoomX", "-o", "APT::FTPArchive::Release::Label=Steward", "-o", "APT::FTPArchive::Release::Suite=stable", "-o", "APT::FTPArchive::Release::Codename=stable", "-o", "APT::FTPArchive::Release::Architectures=amd64 arm64", "-o", "APT::FTPArchive::Release::Components=main", "release", ".", cwd=release_dir)
        expires = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=30)).strftime("%a, %d %b %Y %H:%M:%S +0000")
        (release_dir / "Release").write_text(f"Valid-Until: {expires}\n" + metadata)
        run("gpg", "--batch", "--yes", "--local-user", key, "--clearsign", "--output", str(release_dir / "InRelease"), str(release_dir / "Release"))
        run("gpg", "--batch", "--yes", "--local-user", key, "--armor", "--detach-sign", "--output", str(release_dir / "Release.gpg"), str(release_dir / "Release"))
    (output / "releases.json").write_text(json.dumps({"latest": latest[1:], "releases": index}, indent=2) + "\n")
    (output / "steward.repo").write_text(f"[loomx-steward]\nname=LoomX Steward\nbaseurl={BASE}/rpm/$basearch\nenabled=1\ngpgcheck=1\nrepo_gpgcheck=1\ngpgkey={BASE}/gpg.key\n")
    (output / "status.json").write_text(json.dumps({"latest": latest, "source": os.environ["PACKAGE_SOURCE"], "generatedAt": dt.datetime.now(dt.timezone.utc).isoformat()}) + "\n")
    (ROOT / "site" / "index.html").write_text('<!doctype html><html lang="en"><meta charset="utf-8"><title>LoomX packages</title><h1>LoomX packages</h1><p><a href="https://loomx.ai/steward/docs/installation">Install Steward</a></p><p><a href="steward/gpg.key">Package signing key</a></p></html>')


if __name__ == "__main__":
    main()

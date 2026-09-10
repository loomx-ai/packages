import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from build import public_releases, release_assets, release_fingerprint, verify


class VerifyTest(unittest.TestCase):
    def test_complete_history_and_updates(self):
        def release(tag, **extra):
            return {"tag_name": tag, "draft": False, "prerelease": "-" in tag,
                    "published_at": "2026-09-10T00:00:00Z", "assets": [], **extra}
        pages = [[release(f"v0.0.{patch}") for patch in range(100)],
                 [release(tag) for tag in ["v1.0.0-rc.2", "v1.0.0-rc.10", "v1.0.0", "v0.1.0", "nightly"]]
                 + [release("v2.0.0", draft=True)]]
        with patch("build.run", return_value=json.dumps(pages)) as command:
            releases = public_releases()
        self.assertIn("--paginate", command.call_args.args)
        self.assertIn("--slurp", command.call_args.args)
        self.assertEqual(len(releases), 104)
        self.assertEqual([r["tag_name"] for r in releases[:4]], ["v1.0.0", "v1.0.0-rc.10", "v1.0.0-rc.2", "v0.1.0"])
        before = release_fingerprint(releases)
        releases[0]["assets"].append({"name": "binary", "size": 100, "digest": "sha256:" + "a" * 64, "updated_at": "2026-09-10T01:00:00Z"})
        self.assertNotEqual(release_fingerprint(releases), before)
        unchanged = copy.deepcopy(releases)
        unchanged[0]["assets"][0]["download_count"] = 1000
        self.assertEqual(release_fingerprint(releases), release_fingerprint(unchanged))
        unchanged[0]["assets"][0]["digest"] = "sha256:" + "b" * 64
        self.assertNotEqual(release_fingerprint(releases), release_fingerprint(unchanged))

    def test_additive_binaries_use_github_digests_and_archives_keep_original_checksums(self):
        def asset(name, digest="sha256:" + "a" * 64):
            return {"name": name, "digest": digest, "browser_download_url": f"https://github.com/loomx-ai/steward/releases/download/v0.1.0/{name}", "size": 123}
        raw = "steward_0.1.0_linux_arm64"
        windows = "steward_0.1.0_windows_amd64.exe"
        archive = raw + ".tar.gz"
        release = {"tag_name": "v0.1.0", "assets": [asset(raw), asset(windows), asset(archive), asset("unknown"), asset("steward_9.9.9_linux_amd64")]}
        indexed = release_assets(release, {archive: "b" * 64})
        self.assertEqual(set(indexed), {raw, windows, archive})
        self.assertEqual(indexed[raw]["sha256"], "a" * 64)
        self.assertEqual(indexed[archive]["sha256"], "b" * 64)
        release["assets"] = [asset(raw, None), asset(windows, "sha256:invalid")]
        self.assertEqual(release_assets(release, {}), {})

    def test_corrupt_and_unlisted_packages_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            package = root / "steward.deb"
            package.write_bytes(b"upstream package")
            digest = hashlib.sha256(package.read_bytes()).hexdigest()
            (root / "checksums.txt").write_text(f"{digest}  steward.deb\n")
            self.assertEqual(verify(root)["steward.deb"], digest)
            package.write_bytes(b"changed package")
            with self.assertRaises(ValueError):
                verify(root)
            package.unlink()
            (root / "unlisted.rpm").write_bytes(b"package")
            with self.assertRaises(ValueError):
                verify(root)


if __name__ == "__main__":
    unittest.main()

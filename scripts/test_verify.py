import hashlib
from pathlib import Path
import tempfile
import unittest

from build import release_assets, verify


class VerifyTest(unittest.TestCase):
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

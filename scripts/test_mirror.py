import copy
import hashlib
import io
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from mirror import DOWNLOADS, mirror, validate, verify_public


class MirrorTest(unittest.TestCase):
    def setUp(self):
        self.name = "steward_1.2.3_linux_amd64"
        self.payload = b"verified upstream binary"
        self.digest = hashlib.sha256(self.payload).hexdigest()
        self.index = {"latest": "1.2.3", "releases": [{"version": "1.2.3", "assets": {
            self.name: {"url": f"https://github.com/loomx-ai/steward/releases/download/v1.2.3/{self.name}",
                        "size": len(self.payload), "sha256": self.digest}}}]}

    def download(self, *args):
        directory = Path(args[args.index("--dir") + 1])
        (directory / self.name).write_bytes(self.payload)
        (directory / "checksums.txt").write_text(f"{self.digest}  {self.name}\n")

    def test_only_verified_uploads_produce_mirror_urls(self):
        events = []
        original = copy.deepcopy(self.index)
        with patch("mirror.run", side_effect=self.download), patch("mirror.verify_public", side_effect=lambda *args: events.append("verify")):
            result = mirror(self.index, lambda *args, **kwargs: events.append("upload"))
        self.assertEqual(events, ["upload", "verify", "verify"])
        self.assertEqual(self.index, original)
        release = result["releases"][0]
        self.assertEqual(release["assets"][self.name]["url"], f"{DOWNLOADS}/v1.2.3/{self.name}")
        self.assertEqual(release["checksumsUrl"], f"{DOWNLOADS}/v1.2.3/checksums.txt")
        with patch("mirror.run", side_effect=self.download), patch("mirror.verify_public", side_effect=ValueError("Wrong public bytes")):
            with self.assertRaisesRegex(ValueError, "Wrong public bytes"):
                mirror(self.index, lambda *args, **kwargs: None)
        self.assertEqual(self.index, original)

    def test_corrupt_download_and_invalid_index_never_upload(self):
        self.index["releases"][0]["assets"][self.name]["sha256"] = "a" * 64
        upload = Mock()
        with patch("mirror.run", side_effect=self.download):
            with self.assertRaisesRegex(ValueError, "Checksum or size mismatch"):
                mirror(self.index, upload)
        upload.assert_not_called()
        self.index["releases"][0]["assets"][self.name]["url"] = "https://evil.example/file"
        with self.assertRaisesRegex(ValueError, "Invalid asset"):
            validate(self.index)
        self.index["releases"][0]["version"] = "../../escape"
        self.index["latest"] = "../../escape"
        with self.assertRaisesRegex(ValueError, "Invalid release"):
            validate(self.index)

    def test_public_file_bytes_must_match(self):
        with patch("mirror.urllib.request.urlopen", return_value=io.BytesIO(self.payload)):
            verify_public("https://downloads.loomx.ai/file", self.digest)
        with patch("mirror.urllib.request.urlopen", return_value=io.BytesIO(b"corrupt")):
            with self.assertRaisesRegex(ValueError, "Public download checksum mismatch"):
                verify_public("https://downloads.loomx.ai/file", self.digest)


if __name__ == "__main__":
    unittest.main()

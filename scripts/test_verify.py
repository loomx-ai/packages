import hashlib
from pathlib import Path
import tempfile
import unittest

from build import verify


class VerifyTest(unittest.TestCase):
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

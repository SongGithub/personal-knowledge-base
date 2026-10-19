"""Reproducible code-only ZIP checks without installing or executing packages."""
from contextlib import redirect_stdout
import hashlib
from io import StringIO
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from tools.build_cloud_release import build


class CloudBuildTests(unittest.TestCase):
    def test_build_excludes_install_specific_files_and_has_stable_bytes(self):
        def fake_install(command, *, check):
            self.assertTrue(check)
            self.assertIn("--require-hashes", command)
            stage = Path(command[command.index("--target") + 1])
            (stage / "synthetic.dist-info").mkdir(parents=True)
            (stage / "synthetic.dist-info/RECORD").write_text(str(stage))
            (stage / "synthetic.dist-info/METADATA").write_text("Name: synthetic\nVersion: 1\n")
            (stage / "bin").mkdir()
            (stage / "bin/synthetic").write_text(str(stage))
            (stage / "__pycache__").mkdir()
            (stage / "__pycache__/synthetic.pyc").write_bytes(b"synthetic")
            (stage / "synthetic.py").write_text("VALUE = 'synthetic'\n")
        with tempfile.TemporaryDirectory() as directory, patch("tools.build_cloud_release.subprocess.run", side_effect=fake_install), redirect_stdout(StringIO()):
            first, second = Path(directory) / "first.zip", Path(directory) / "second.zip"
            build(first)
            build(second)
            self.assertEqual(hashlib.sha256(first.read_bytes()).digest(), hashlib.sha256(second.read_bytes()).digest())
            with zipfile.ZipFile(first) as archive:
                self.assertIn("cloud_kb/api.py", archive.namelist())
                self.assertIn("synthetic.py", archive.namelist())
                self.assertFalse(any(name.startswith(("bin/", "__pycache__/", "tests/", "vault/")) or name.endswith("/RECORD") for name in archive.namelist()))


if __name__ == "__main__":
    unittest.main()

import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]


class BuildTests(unittest.TestCase):
    def test_build_ignores_source_timestamps_and_uses_fixed_zip_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            copy = Path(directory)
            shutil.copytree(ROOT / "product", copy / "product", ignore=shutil.ignore_patterns("__pycache__"))
            (copy / "scripts").mkdir()
            shutil.copyfile(ROOT / "scripts/build_product.py", copy / "scripts/build_product.py")
            command = [sys.executable, "-I", "-B", str(copy / "scripts/build_product.py")]
            first = subprocess.run(command, cwd=copy, capture_output=True, text=True)
            self.assertEqual(first.returncode, 0, first.stderr)
            artifact = copy / "dist/benchreceipt.pyz"
            before = artifact.read_bytes()
            for path in (copy / "product").rglob("*"):
                if path.is_file():
                    os.utime(path, (946684800, 946684800))
            (copy / "product/benchreceipt/local_notes.py").write_text("PRIVATE_BUILD_CANARY", encoding="utf-8")
            second = subprocess.run(command, cwd=copy, capture_output=True, text=True)
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertEqual(artifact.read_bytes(), before)
            with zipfile.ZipFile(artifact) as archive:
                self.assertNotIn("benchreceipt/local_notes.py", archive.namelist())
                for entry in archive.infolist():
                    self.assertEqual(entry.date_time, (1980, 1, 1, 0, 0, 0))
                    self.assertEqual(entry.external_attr >> 16, 0o100644)


if __name__ == "__main__":
    unittest.main()

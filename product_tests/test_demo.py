import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "product"))
from benchreceipt.demo import demo_bytes


class DemoTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        # Only the standalone artifact enters this directory. No fixture, source
        # package or Vault path is supplied to the isolated child process.
        self.app = self.root / "benchreceipt.pyz"
        shutil.copyfile(ROOT / "dist/benchreceipt.pyz", self.app)

    def run_cli(self, *args):
        return subprocess.run([sys.executable, "-I", "-B", str(self.app), *args],
                              cwd=self.root, capture_output=True, text=True)

    def test_source_and_bundle_use_exact_canonical_fixture(self):
        canonical = (ROOT / "product/examples/synthetic-vllm.json").read_bytes()
        self.assertEqual(demo_bytes(), canonical)
        with zipfile.ZipFile(self.app) as archive:
            self.assertEqual(archive.read("benchreceipt/demo.json"), canonical)

    def test_isolated_demo_generates_json_without_input_or_checkout(self):
        output = self.root / "demo.json"
        result = self.run_cli("--demo", "--format", "json", "--output", str(output))
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(report["data_kind"], "DECLARED_SYNTHETIC")
        self.assertEqual(report["status"], "CHECKED")
        self.assertEqual(report["regression_verdict"], "NOT_EVALUATED")
        self.assertEqual(report["input_sha256"], hashlib.sha256(demo_bytes()).hexdigest())
        self.assertNotIn(str(ROOT), output.read_text(encoding="utf-8") + result.stdout + result.stderr)

    def test_demo_supports_html_and_markdown(self):
        for format, marker in (("html", "DECLARED_SYNTHETIC"), ("markdown", "DECLARED&#95;SYNTHETIC")):
            output = self.root / ("demo-" + format)
            result = self.run_cli("--demo", "--format", format, "--output", str(output))
            self.assertEqual(result.returncode, 0, result.stderr)
            text = output.read_text(encoding="utf-8")
            self.assertIn(marker, text)
            self.assertIn("NOT_EVALUATED", text)

    def test_demo_preserves_existing_output_and_artifact(self):
        output = self.root / "existing.html"
        output.write_text("do not overwrite")
        before = self.app.read_bytes()
        result = self.run_cli("--demo", "--output", str(output))
        self.assertEqual(result.returncode, 3)
        self.assertIn("Output already exists. Choose a new --output path.", result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertEqual(output.read_text(), "do not overwrite")
        self.assertEqual(self.app.read_bytes(), before)

    def test_all_demo_formats_use_crlf_report_line_endings(self):
        for format in ("html", "json", "markdown"):
            with self.subTest(format=format):
                output = self.root / format
                result = self.run_cli("--demo", "--format", format, "--output", str(output))
                self.assertEqual(result.returncode, 0, result.stderr)
                data = output.read_bytes()
                self.assertIn(b"\r\n", data)
                self.assertNotIn(b"\n", data.replace(b"\r\n", b""))

    def test_demo_explains_missing_output_directory(self):
        output = self.root / "Missing Folder" / "Demo Receipt.html"
        result = self.run_cli("--demo", "--output", str(output))
        self.assertEqual(result.returncode, 3)
        self.assertEqual(result.stdout, "")
        self.assertIn("Output directory does not exist. Create it or choose another --output path.", result.stderr)
        self.assertFalse(output.parent.exists())

    def test_input_and_demo_are_mutually_exclusive(self):
        source = self.root / "input.json"
        source.write_bytes(demo_bytes())
        output = self.root / "out.html"
        result = self.run_cli(str(source), "--demo", "--output", str(output))
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(output.exists())
        self.assertEqual(source.read_bytes(), demo_bytes())

    def test_neither_input_nor_demo_is_rejected(self):
        output = self.root / "out.html"
        result = self.run_cli("--output", str(output))
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(output.exists())

    def test_demo_rejects_directory_options_and_bad_limit(self):
        for extra in (("--recursive",), ("--include-paths",), ("--pattern", "x*.json"), ("--max-input-mib", "0")):
            output = self.root / "out.html"
            result = self.run_cli("--demo", "--output", str(output), *extra)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()

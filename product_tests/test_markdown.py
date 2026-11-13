import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "product"))
from benchreceipt import inspect_bytes
from benchreceipt.batch import inspect_directory
from benchreceipt.markdown import cell, render_markdown


class MarkdownTests(unittest.TestCase):
    def setUp(self):
        self.raw = (ROOT / "product/examples/synthetic-vllm.json").read_bytes()
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)

    def test_single_preserves_evidence_boundaries_and_hash(self):
        report = inspect_bytes(self.raw)
        document = render_markdown(report)
        self.assertIn("DECLARED&#95;SYNTHETIC", document)
        self.assertIn(report["input_sha256"], document)
        self.assertIn("NOT_EVALUATED", document)
        self.assertIn("| mean&#95;ttft&#95;ms | 25 |", document)
        self.assertIn("## Limits", document)
        self.assertIn("No content is published automatically", document)

    def test_single_never_echoes_prompts_or_identifiers(self):
        value = json.loads(self.raw)
        value.update(gpu="PRIVATE_CANARY", model_id="PRIVATE_CANARY", prompts=["PRIVATE_CANARY"], errors=["PRIVATE_CANARY"])
        document = render_markdown(inspect_bytes(json.dumps(value).encode()))
        self.assertNotIn("PRIVATE", document)

    def test_unknown_failed_is_not_zero_in_markdown(self):
        value = json.loads(self.raw)
        del value["failed"]
        document = render_markdown(inspect_bytes(json.dumps(value).encode()))
        self.assertIn("| failed | Unknown |", document)
        self.assertIn("INCOMPLETE", document)

    def test_batch_contains_counts_missing_and_per_file_hash(self):
        value = json.loads(self.raw)
        del value["gpu"]
        (self.root / "PRIVATE.json").write_text(json.dumps(value))
        report = inspect_directory(self.root)
        document = render_markdown(report)
        self.assertIn("| gpu | 1 |", document)
        self.assertIn("file-0001", document)
        self.assertIn(report["files"][0]["input_sha256"], document)
        self.assertNotIn("PRIVATE", document)
        self.assertNotIn(str(self.root), document)

    def test_opted_in_filename_is_inert_not_a_link_mention_or_table_break(self):
        (self.root / "run.json").write_bytes(self.raw)
        report = inspect_directory(self.root, include_paths=True)
        report["files"][0]["relative_path"] = '@owner | [link](https://example.invalid) `<script>`\n# heading.json'
        document = render_markdown(report)
        self.assertNotIn("@owner", document)
        self.assertNotIn("[link]", document)
        self.assertNotIn("https://", document)
        self.assertNotIn("<script>", document)
        self.assertNotIn("\n# heading", document)
        row = next(line for line in document.splitlines() if "&#64;owner" in line)
        self.assertEqual(row.count("|"), 5)
        self.assertIn("<br>", row)
        self.assertIn("Relative filenames are included", document)

    def test_escaping_handles_entities_backslashes_and_crlf(self):
        rendered = cell('&lt;tag>\\|`\r\n@all')
        self.assertIn("&amp;lt;tag&gt;", rendered)
        self.assertIn("&#92;&#124;&#96;<br>&#64;all", rendered)
        self.assertNotIn("\r", rendered)

    def test_empty_batch_does_not_imply_all_checked(self):
        document = render_markdown(inspect_directory(self.root))
        self.assertIn("EMPTY", document)
        self.assertIn("No saved results were inspected", document)

    def test_batch_overview_separates_hashes_and_field_specific_explanations(self):
        value = json.loads(self.raw)
        del value["gpu"]
        (self.root / "missing.json").write_text(json.dumps(value))
        (self.root / "metadata.json").write_text('{}')
        report = inspect_directory(self.root)
        document = render_markdown(report)
        overview, details = document.split("## Per-file details and hashes")
        self.assertIn("Not assessed", overview)
        for item in report["files"]:
            self.assertNotIn(item["input_sha256"], overview)
            self.assertIn(item["input_sha256"], details)
        self.assertIn("PROVENANCE&#95;UNKNOWN&#58; gpu", details)

    def run_cli(self, source, output):
        return subprocess.run([sys.executable, "-I", "-B", str(ROOT / "dist/benchreceipt.pyz"),
                               str(source), "--format", "markdown", "--output", str(output)],
                              cwd=self.root, capture_output=True, text=True)

    def test_cli_single_markdown_and_no_overwrite(self):
        source = self.root / "run.json"
        source.write_bytes(self.raw)
        output = self.root / "receipt.md"
        first = self.run_cli(source, output)
        self.assertEqual(first.returncode, 0, first.stderr)
        before = output.read_bytes()
        self.assertTrue(before.startswith(b"# BenchReceipt"))
        self.assertEqual(self.run_cli(source, output).returncode, 3)
        self.assertEqual(before, output.read_bytes())
        self.assertEqual(source.read_bytes(), self.raw)

    def test_cli_mixed_batch_still_writes_markdown_and_error_exit(self):
        (self.root / "run.json").write_bytes(self.raw)
        (self.root / "bad.json").write_text("PRIVATE invalid json")
        output = self.root / "receipt.md"
        result = self.run_cli(self.root, output)
        self.assertEqual(result.returncode, 3)
        document = output.read_text(encoding="utf-8")
        self.assertIn("Selected files: 2", document)
        self.assertIn("| CHECKED | 1 |", document)
        self.assertIn("| ERROR | 1 |", document)
        self.assertNotIn("PRIVATE", document + result.stderr)

    def test_cli_incomplete_keeps_exit_code_and_policy(self):
        value = json.loads(self.raw)
        del value["gpu"]
        source = self.root / "run.json"
        source.write_text(json.dumps(value))
        output = self.root / "receipt.md"
        result = self.run_cli(source, output)
        self.assertEqual(result.returncode, 2)
        document = output.read_text(encoding="utf-8")
        self.assertIn("Maximum input size: 67108864 bytes", document)
        self.assertIn("| gpu | unknown |", document)


if __name__ == "__main__":
    unittest.main()

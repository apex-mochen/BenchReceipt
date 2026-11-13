import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "product"))
from benchreceipt.batch import inspect_directory, render_batch_html


class BatchTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.sample = json.loads((ROOT / "product/examples/synthetic-vllm.json").read_text())

    def write(self, name, value):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value), encoding="utf-8")
        return path

    def test_mixed_statuses_continue_after_first_bad_file_and_preserve_sources(self):
        (self.root / "00-bad.json").write_text("PRIVATE bad json")
        self.write("01-checked.json", self.sample)
        incomplete = copy.deepcopy(self.sample)
        del incomplete["gpu"]
        del incomplete["failed"]
        self.write("02-incomplete.json", incomplete)
        inconsistent = dict(self.sample, mean_ttft_ms=900)
        self.write("03-inconsistent.json", inconsistent)
        self.write("04-config.json", {"secret": "PRIVATE"})
        before = {p.name: p.read_bytes() for p in self.root.iterdir()}
        report = inspect_directory(self.root)
        self.assertEqual(report["status_counts"], {"CHECKED": 1, "INCOMPLETE": 1, "INCONSISTENT": 1, "ERROR": 1, "SKIPPED": 1})
        self.assertEqual(report["total_files"], 5)
        self.assertEqual(report["status"], "ERROR")
        self.assertEqual(report["missing_field_counts"], {"failed": 1, "gpu": 1})
        self.assertEqual(report["files"][0]["input_sha256"], hashlib.sha256(before["00-bad.json"]).hexdigest())
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.root.iterdir()})
        self.assertNotIn("PRIVATE", json.dumps(report))

    def test_empty_and_unrelated_only_do_not_report_checked(self):
        self.assertEqual(inspect_directory(self.root)["status"], "EMPTY")
        self.write("metadata.json", {"gpu": "PRIVATE"})
        self.assertEqual(inspect_directory(self.root)["status"], "NO_RESULTS")

    def test_recursive_and_pattern_selection_are_explicit(self):
        self.write("b.json", self.sample)
        self.write("nested/a.json", self.sample)
        (self.root / "ignored.txt").write_text("not json")
        self.assertEqual(inspect_directory(self.root)["total_files"], 1)
        report = inspect_directory(self.root, recursive=True, pattern="a*.json", include_paths=True)
        self.assertEqual(report["total_files"], 1)
        self.assertEqual(report["files"][0]["relative_path"], "nested/a.json")

    def test_default_projection_hides_filenames_and_absolute_roots(self):
        self.write("PRIVATE_CANARY.json", self.sample)
        report = inspect_directory(self.root)
        self.assertNotIn("PRIVATE_CANARY", json.dumps(report))
        self.assertNotIn(str(self.root), json.dumps(report))
        self.assertEqual(report["files"][0]["file_id"], "file-0001")
        self.assertIn("PRIVATE_CANARY", json.dumps(inspect_directory(self.root, include_paths=True)))

    def test_unreadable_file_is_an_error_but_other_files_are_checked(self):
        self.write("bad.json", self.sample)
        self.write("good.json", self.sample)
        from benchreceipt.input import read_input
        def read(path, limit):
            if path.name == "bad.json":
                raise PermissionError("PRIVATE_PERMISSION_ERROR")
            return read_input(path, limit)
        with patch("benchreceipt.batch.read_input", read):
            report = inspect_directory(self.root)
        self.assertEqual(report["status_counts"]["ERROR"], 1)
        self.assertEqual(report["status_counts"]["CHECKED"], 1)
        self.assertIsNone(report["files"][0]["input_sha256"])
        self.assertNotIn("PRIVATE_PERMISSION_ERROR", json.dumps(report))

    def test_html_escapes_opted_in_filename_and_has_no_script(self):
        self.write("test.json", self.sample)
        report = inspect_directory(self.root, include_paths=True)
        report["files"][0]["relative_path"] = '<script>alert("x")</script>.json'
        document = render_batch_html(report)
        self.assertNotIn("<script>", document)
        self.assertIn("&lt;script&gt;", document)
        self.assertNotIn("https://", document)

    def test_finding_counts_are_per_file_not_duplicate_codes(self):
        value = dict(self.sample, num_prompts=1)
        self.write("one.json", value)
        report = inspect_directory(self.root)
        self.assertEqual(report["finding_file_counts"]["COUNT_MISMATCH"], 1)

    def test_deterministic_file_ids_and_order(self):
        self.write("z.json", self.sample)
        self.write("a.json", self.sample)
        first = inspect_directory(self.root, include_paths=True)
        self.assertEqual(first, inspect_directory(self.root, include_paths=True))
        self.assertEqual([r["relative_path"] for r in first["files"]], ["a.json", "z.json"])

    def test_child_symlink_is_skipped_without_reading_target(self):
        target = self.write("target.json", self.sample)
        try:
            (self.root / "link.json").symlink_to(target)
        except OSError:
            self.skipTest("Platform does not permit symlink creation")
        report = inspect_directory(self.root)
        self.assertEqual(report["status_counts"]["SKIPPED"], 1)
        self.assertEqual(report["status_counts"]["CHECKED"], 1)

    def test_cli_writes_complete_mixed_report_and_returns_error(self):
        (self.root / "bad.json").write_text("PRIVATE bad json")
        self.write("valid.json", self.sample)
        output = self.root / "summary.json"
        result = subprocess.run([sys.executable, "-I", "-B", str(ROOT / "dist/benchreceipt.pyz"),
                                 str(self.root), "--format", "json", "--output", str(output)],
                                cwd=self.root, capture_output=True, text=True)
        self.assertEqual(result.returncode, 3, result.stderr)
        report = json.loads(output.read_text())
        self.assertEqual(report["total_files"], 2)
        self.assertEqual(report["status_counts"]["CHECKED"], 1)
        self.assertNotIn("PRIVATE", output.read_text() + result.stdout + result.stderr)

    def test_invalid_selection_and_directory_flags_on_file_are_rejected(self):
        with self.assertRaises(ValueError):
            inspect_directory(self.root, pattern="../*.json")
        source = self.write("valid.json", self.sample)
        output = self.root / "summary.html"
        result = subprocess.run([sys.executable, "-I", "-B", str(ROOT / "dist/benchreceipt.pyz"),
                                 str(source), "--recursive", "--output", str(output)],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 3)
        self.assertFalse(output.exists())

    def test_empty_cli_writes_receipt_but_returns_error(self):
        output = self.root / "empty.html"
        result = subprocess.run([sys.executable, "-I", "-B", str(ROOT / "dist/benchreceipt.pyz"),
                                 str(self.root), "--output", str(output)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 3)
        self.assertIn("EMPTY", output.read_text(encoding="utf-8"))

    def test_batch_status_escalates_incomplete_then_inconsistent(self):
        self.write("checked.json", self.sample)
        self.write("missing.json", {key: value for key, value in self.sample.items() if key != "gpu"})
        self.assertEqual(inspect_directory(self.root)["status"], "INCOMPLETE")
        self.write("tampered.json", dict(self.sample, mean_ttft_ms=500))
        self.assertEqual(inspect_directory(self.root)["status"], "INCONSISTENT")

    def test_mixed_readable_rows_keep_full_names_hashes_and_unassessed_states(self):
        from html.parser import HTMLParser
        class Cells(HTMLParser):
            def __init__(self):
                super().__init__()
                self.values, self.active = [], False
            def handle_starttag(self, tag, attrs):
                if tag == "td":
                    self.values.append("")
                    self.active = True
            def handle_endtag(self, tag):
                if tag == "td":
                    self.active = False
            def handle_data(self, data):
                if self.active:
                    self.values[-1] += data
        long_name = "01-" + "synthetic-long-name-" * 5 + ".json"
        self.write(long_name, self.sample)
        self.write("02-missing.json", {k: v for k, v in self.sample.items() if k != "gpu"})
        self.write("03-inconsistent.json", dict(self.sample, mean_ttft_ms=999))
        (self.root / "04-invalid.json").write_text("synthetic invalid JSON")
        self.write("05-metadata.json", {"synthetic": True})
        report = inspect_directory(self.root, include_paths=True)
        before = copy.deepcopy(report)
        parser = Cells()
        parser.feed(render_batch_html(report))
        text = " ".join(parser.values)
        self.assertIn(long_name, text)
        self.assertEqual(text.count("Completeness not assessed."), 2)
        for item in report["files"]:
            self.assertIn(item["status"], text)
            self.assertIn(item["input_sha256"], text)
        self.assertIn("Review", render_batch_html(report))
        self.assertEqual(report, before)

    def test_default_batch_reading_never_exposes_filename_in_disclosures(self):
        self.write("PRIVATE_FILENAME.json", self.sample)
        document = render_batch_html(inspect_directory(self.root))
        self.assertNotIn("PRIVATE_FILENAME", document)
        self.assertIn("Filenames are hidden", document)
        self.assertIn("Input SHA256", document)

    def test_zero_inspected_reports_do_not_suggest_complete_evidence(self):
        from benchreceipt.markdown import render_markdown
        for expected in ("EMPTY", "NO_RESULTS"):
            if expected == "NO_RESULTS":
                self.write("metadata.json", {"synthetic": True})
            report = inspect_directory(self.root)
            before = copy.deepcopy(report)
            self.assertEqual(report["status"], expected)
            html = render_batch_html(report)
            self.assertLess(html.index("Completeness was not assessed"), html.index("What to do next"))
            self.assertNotIn("Missing evidence by file count", html)
            self.assertIn(f"Selected files: {report['total_files']}.", html)
            for document in (html, render_markdown(report)):
                self.assertIn("Saved results inspected: 0", document)
                self.assertIn("Completeness was not assessed", document)
                self.assertIn("not a successful result check", document)
                self.assertNotIn("No missing-field findings", document)
                if expected == "EMPTY":
                    self.assertIn("No file entries", document)
                    self.assertIn("new output path", document)
            self.assertEqual(report, before)

    def test_disclosure_names_identify_each_file_and_use_native_summaries(self):
        from html.parser import HTMLParser
        class Summaries(HTMLParser):
            def __init__(self):
                super().__init__()
                self.names, self.active = [], False
            def handle_starttag(self, tag, attrs):
                if tag == "summary":
                    self.names.append("")
                    self.active = True
            def handle_endtag(self, tag):
                if tag == "summary":
                    self.active = False
            def handle_data(self, data):
                if self.active:
                    self.names[-1] += data
        self.write("first.json", self.sample)
        self.write("second.json", {k: v for k, v in self.sample.items() if k != "gpu"})
        parser = Summaries()
        document = render_batch_html(inspect_directory(self.root))
        parser.feed(document)
        self.assertEqual(len(parser.names), len(set(parser.names)))
        self.assertTrue(any("Input SHA256" in text and "file-0001" in text for text in parser.names))
        self.assertTrue(any("Findings" in text and "file-0002" in text for text in parser.names))
        self.assertIn("Shift+Tab", document)
        self.assertNotIn('role="button"', document)


if __name__ == "__main__":
    unittest.main()

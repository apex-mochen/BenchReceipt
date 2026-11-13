import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "product"))
from benchreceipt import inspect_bytes, render_html


class ReceiptTests(unittest.TestCase):
    def setUp(self):
        self.sample = json.loads((ROOT / "product/examples/synthetic-vllm.json").read_text())

    def inspect(self, value):
        return inspect_bytes(json.dumps(value).encode())

    def test_hand_calculated_linear_percentiles_and_synthetic_label(self):
        report = self.inspect(self.sample)
        self.assertEqual(report["status"], "CHECKED")
        self.assertEqual(report["data_kind"], "DECLARED_SYNTHETIC")
        for name, expected in {"mean_ttft_ms": 25, "p50_ttft_ms": 25, "p95_ttft_ms": 38.5, "p99_ttft_ms": 39.7}.items():
            self.assertAlmostEqual(report["recomputed_ttft_ms"][name], expected)
        self.assertEqual(report["regression_verdict"], "NOT_EVALUATED")

    def test_missing_failure_counter_never_becomes_zero(self):
        del self.sample["failed"]
        report = self.inspect(self.sample)
        self.assertIsNone(report["counts"]["failed"])
        self.assertEqual(report["status"], "INCOMPLETE")

    def test_failed_batch_remains_inspectable(self):
        self.sample.update(num_prompts=5, failed=1)
        report = self.inspect(self.sample)
        self.assertEqual(report["counts"]["failed"], 1)
        self.assertEqual(report["status"], "INCOMPLETE")
        self.assertIn("FAILED_REQUESTS", [f["code"] for f in report["findings"]])

    def test_tampered_mean_is_detected(self):
        self.sample["mean_ttft_ms"] = 999
        report = self.inspect(self.sample)
        self.assertEqual(report["status"], "INCONSISTENT")
        self.assertIn("TTFT_AGGREGATE_MISMATCH", [f["code"] for f in report["findings"]])

    def test_missing_gpu_is_unknown_even_when_values_look_valid(self):
        del self.sample["gpu"]
        report = self.inspect(self.sample)
        self.assertEqual(report["provenance"]["gpu"], "unknown")
        self.assertEqual(report["status"], "INCOMPLETE")

    def test_arbitrary_strings_and_identifiers_do_not_leave_input(self):
        canary = 'PRIVATE_CANARY_<script>alert(1)</script>'
        self.sample.update(gpu=canary, model_id=canary, generated_texts=[canary], prompts=[canary], errors=[canary], arbitrary={"secret": canary})
        report = self.inspect(self.sample)
        self.assertNotIn(canary, json.dumps(report))
        document = render_html(report)
        self.assertNotIn(canary, document)
        self.assertNotIn("<script>", document)
        self.assertNotIn("https://", document)

    def test_bool_count_and_huge_metric_are_not_numbers(self):
        self.sample.update(failed=False, mean_tpot_ms=10**400)
        report = self.inspect(self.sample)
        self.assertIsNone(report["counts"]["failed"])
        self.assertEqual(report["status"], "INCONSISTENT")

    def test_completed_exceeds_total_with_unknown_failures(self):
        self.sample.update(num_prompts=1)
        del self.sample["failed"]
        self.assertEqual(self.inspect(self.sample)["status"], "INCONSISTENT")

    def test_nonfinite_json_and_wrong_shape_are_rejected(self):
        for raw in (b'{"completed":1,"num_prompts":1,"x":NaN}', b'[]', b'{"foo":1}'):
            with self.assertRaises(ValueError):
                inspect_bytes(raw)

    def test_array_size_mismatch_is_detected(self):
        self.sample["ttfts"].pop()
        self.assertEqual(self.inspect(self.sample)["status"], "INCONSISTENT")

    def test_zipapp_runs_isolated_and_preserves_existing_files(self):
        app = ROOT / "dist/benchreceipt.pyz"
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "input.json"
            source.write_text(json.dumps(self.sample))
            target = Path(folder) / "report.html"
            command = [sys.executable, "-I", "-B", str(app), str(source), "--output", str(target)]
            first = subprocess.run(command, cwd=folder, capture_output=True, text=True)
            self.assertEqual(first.returncode, 0, first.stderr)
            content = target.read_bytes()
            second = subprocess.run(command, cwd=folder, capture_output=True, text=True)
            self.assertEqual(second.returncode, 3)
            self.assertEqual(target.read_bytes(), content)
            self.assertEqual(json.loads(source.read_text()), self.sample)

    def test_zipapp_error_does_not_echo_bad_input(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "input.json"
            source.write_text('PRIVATE_CANARY bad json')
            result = subprocess.run([sys.executable, "-I", "-B", str(ROOT / "dist/benchreceipt.pyz"), str(source), "--output", str(Path(folder) / "out.json")], capture_output=True, text=True)
            self.assertEqual(result.returncode, 3)
            self.assertNotIn("PRIVATE_CANARY", result.stdout + result.stderr)
            self.assertFalse((Path(folder) / "out.json").exists())

    def test_checked_first_read_explains_boundary_without_changing_receipt(self):
        from benchreceipt.markdown import render_markdown
        report = self.inspect(self.sample)
        original = copy.deepcopy(report)
        for document in (render_html(report), render_markdown(report)):
            self.assertIn("What to do next", document)
            self.assertIn("CHECKED is not a performance approval", document)
            self.assertIn("NOT", document)
        self.assertIn("Demo data, not a GPU measurement", render_html(report))
        self.assertIn("<details><summary>Technical receipt JSON", render_html(report))
        self.assertEqual(report, original)

    def test_incomplete_first_read_preserves_unknown_and_explains_recovery(self):
        from benchreceipt.markdown import render_markdown
        for field in ("failed", "gpu", "num_warmups", "ttfts"):
            del self.sample[field]
        self.sample["prompts"] = ["PRIVATE_READING_CANARY"]
        report = self.inspect(self.sample)
        original = copy.deepcopy(report)
        for document in (render_html(report), render_markdown(report)):
            self.assertIn("Do not fill gaps with guesses", document)
            self.assertIn("unknown does not mean zero", document)
            self.assertIn("summary values cannot recreate samples", document)
            self.assertNotIn("PRIVATE_READING_CANARY", document)
        self.assertEqual(report["status"], "INCOMPLETE")
        self.assertIsNone(report["counts"]["failed"])
        self.assertEqual(report, original)

    def test_batch_first_read_does_not_approve_empty_or_skipped_selection(self):
        from benchreceipt.batch import inspect_directory, render_batch_html
        from benchreceipt.markdown import render_markdown
        with tempfile.TemporaryDirectory() as directory:
            for expected in ("EMPTY", "NO_RESULTS"):
                if expected == "NO_RESULTS":
                    (Path(directory) / "metadata.json").write_text('{}')
                report = inspect_directory(directory)
                original = copy.deepcopy(report)
                self.assertEqual(report["status"], expected)
                for document in (render_batch_html(report), render_markdown(report)):
                    self.assertIn("What to do next", document)
                    self.assertIn("No files matched" if expected == "EMPTY" else "no result was checked", document)
                self.assertEqual(report, original)


if __name__ == "__main__":
    unittest.main()

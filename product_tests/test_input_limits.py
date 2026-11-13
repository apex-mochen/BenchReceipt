import json
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "product"))
from benchreceipt.batch import inspect_directory
from benchreceipt.input import InputTooLarge, read_input


class InputLimitTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.raw = (ROOT / "product/examples/synthetic-vllm.json").read_bytes()

    def test_exact_boundary_accepts_complete_bytes(self):
        source = self.root / "run.json"
        source.write_bytes(self.raw)
        self.assertEqual(read_input(source, len(self.raw)), self.raw)
        with self.assertRaises(InputTooLarge):
            read_input(source, len(self.raw) - 1)

    def test_size_precheck_rejects_before_content_read(self):
        handle = MagicMock()
        handle.__enter__.return_value = handle
        with patch.object(Path, "open", return_value=handle), patch("benchreceipt.input.os.fstat", return_value=SimpleNamespace(st_mode=stat.S_IFREG, st_size=101)):
            with self.assertRaises(InputTooLarge):
                read_input(self.root / "oversized.json", 100)
        handle.read.assert_not_called()

    def test_growth_after_stat_is_bounded_and_never_returned_as_complete(self):
        handle = MagicMock()
        handle.__enter__.return_value = handle
        handle.read.return_value = b"x" * 101
        with patch.object(Path, "open", return_value=handle), patch("benchreceipt.input.os.fstat", return_value=SimpleNamespace(st_mode=stat.S_IFREG, st_size=10)):
            with self.assertRaises(InputTooLarge):
                read_input(self.root / "growing.json", 100)
        handle.read.assert_called_once_with(101)

    def test_non_regular_files_are_rejected_before_read(self):
        handle = MagicMock()
        handle.__enter__.return_value = handle
        with patch.object(Path, "open", return_value=handle), patch("benchreceipt.input.os.fstat", return_value=SimpleNamespace(st_mode=stat.S_IFIFO, st_size=0)):
            with self.assertRaises(ValueError):
                read_input(self.root / "not-regular", 100)
        handle.read.assert_not_called()

    def test_invalid_library_limits_are_rejected_even_for_empty_directory(self):
        for value in (0, -1, True, 1.5):
            with self.assertRaises(ValueError):
                inspect_directory(self.root, max_input_bytes=value)

    def test_large_file_does_not_block_good_file_or_get_partial_hash(self):
        limit = len(self.raw)
        (self.root / "large.json").write_bytes(self.raw + b" ")
        (self.root / "good.json").write_bytes(self.raw)
        report = inspect_directory(self.root, max_input_bytes=limit, include_paths=True)
        self.assertEqual(report["status_counts"]["ERROR"], 1)
        self.assertEqual(report["status_counts"]["CHECKED"], 1)
        large = next(row for row in report["files"] if row["relative_path"] == "large.json")
        self.assertEqual(large["findings"], [{"code": "INPUT_TOO_LARGE"}])
        self.assertIsNone(large["input_sha256"])
        self.assertEqual(report["selection"]["max_input_bytes"], limit)

    def test_batch_decodes_each_selected_json_only_once(self):
        (self.root / "run.json").write_bytes(self.raw)
        (self.root / "metadata.json").write_text('{"unrelated": true}')
        original = json.loads
        with patch("benchreceipt.json.loads", wraps=original) as decoder:
            report = inspect_directory(self.root)
        self.assertEqual(decoder.call_count, 2)
        self.assertEqual(report["status_counts"]["CHECKED"], 1)
        self.assertEqual(report["status_counts"]["SKIPPED"], 1)

    def test_cli_oversize_does_not_write_output_or_echo_input(self):
        source = self.root / "large.json"
        with source.open("wb") as handle:
            handle.write(b"PRIVATE_CANARY")
            handle.truncate(1024 * 1024 + 1)
        output = self.root / "receipt.json"
        command = [sys.executable, "-I", "-B", str(ROOT / "dist/benchreceipt.pyz"), str(source),
                   "--max-input-mib", "1", "--output", str(output)]
        result = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(result.returncode, 3)
        self.assertIn("INPUT_TOO_LARGE", result.stderr)
        self.assertNotIn("PRIVATE_CANARY", result.stdout + result.stderr)
        self.assertFalse(output.exists())

    def test_cli_rejects_invalid_limit_and_preserves_source(self):
        source = self.root / "run.json"
        source.write_bytes(self.raw)
        for limit in ("0", "-1", "1.5", "invalid"):
            output = self.root / "out.json"
            result = subprocess.run([sys.executable, "-I", "-B", str(ROOT / "dist/benchreceipt.pyz"),
                                     str(source), "--max-input-mib", limit, "--output", str(output)],
                                    capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(output.exists())
        self.assertEqual(source.read_bytes(), self.raw)

    def test_cli_batch_limit_is_applied_and_summary_is_written(self):
        source = self.root / "large.json"
        with source.open("wb") as handle:
            handle.truncate(1024 * 1024 + 1)
        (self.root / "good.json").write_bytes(self.raw)
        output = self.root / "out.json"
        result = subprocess.run([sys.executable, "-I", "-B", str(ROOT / "dist/benchreceipt.pyz"),
                                 str(self.root), "--max-input-mib", "1", "--format", "json", "--output", str(output)],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 3)
        report = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(report["status_counts"]["CHECKED"], 1)
        self.assertEqual(report["finding_file_counts"]["INPUT_TOO_LARGE"], 1)


if __name__ == "__main__":
    unittest.main()

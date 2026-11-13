import importlib.util
import hashlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


packager = load("package_product")
verifier = load("verify_bundle")


class BundleTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.source = self.root / "source"
        shutil.copytree(ROOT / "product", self.source / "product", ignore=shutil.ignore_patterns("__pycache__"))
        for name in ("dist/benchreceipt.pyz", "scripts/verify_bundle.py"):
            target = self.source / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / name, target)

    def bundle(self):
        archive = self.root / "candidate.zip"
        packager.package(self.source, archive)
        extracted = self.root / "extracted"
        with zipfile.ZipFile(archive) as source:
            self.assertEqual(set(source.namelist()), {"benchreceipt.pyz", "README.md", "verify.py", "manifest.json", "LICENSE"})
            source.extractall(extracted)
        return archive, extracted

    def test_exact_allowlist_and_repeat_packaging(self):
        (self.source / "PRIVATE-raw.json").write_text("PRIVATE_CANARY")
        first, extracted = self.bundle()
        second = self.root / "candidate-again.zip"
        packager.package(self.source, second)
        self.assertEqual(first.read_bytes(), second.read_bytes())
        with zipfile.ZipFile(first) as archive:
            for entry in archive.infolist():
                self.assertEqual(entry.date_time, (1980, 1, 1, 0, 0, 0))
                self.assertEqual(entry.external_attr >> 16, 0o100644)
                self.assertNotIn(b"PRIVATE_CANARY", archive.read(entry))
        self.assertTrue(verifier.verify(extracted)["passed"])

    def test_complete_license_in_outer_bundle_inner_app_and_manifest(self):
        archive, extracted = self.bundle()
        canonical = (ROOT / "product/LICENSE").read_bytes()
        self.assertEqual(hashlib.sha256(canonical).hexdigest(), packager.APACHE_2_SHA256)
        self.assertEqual((extracted / "LICENSE").read_bytes(), canonical)
        manifest = json.loads((extracted / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["schema"], "benchreceipt-local-bundle-v2")
        self.assertEqual(manifest["license"], "Apache-2.0")
        self.assertEqual(manifest["files"]["LICENSE"]["sha256"], packager.APACHE_2_SHA256)
        with zipfile.ZipFile(archive) as bundle:
            with zipfile.ZipFile(io.BytesIO(bundle.read("benchreceipt.pyz"))) as app:
                self.assertEqual(app.read("benchreceipt/LICENSE"), canonical)

    def test_missing_or_incomplete_source_license_refused_before_output(self):
        path = self.source / "product/LICENSE"
        canonical = path.read_bytes()
        output = self.root / "candidate.zip"
        path.unlink()
        with self.assertRaises(FileNotFoundError):
            packager.package(self.source, output)
        self.assertFalse(output.exists())
        for invalid in (b"", canonical[:100], canonical + b"\nchanged"):
            with self.subTest(length=len(invalid)):
                path.write_bytes(invalid)
                with self.assertRaises(ValueError):
                    packager.package(self.source, output)
                self.assertFalse(output.exists())

    def test_license_missing_tampered_or_rehashed_is_rejected(self):
        _, extracted = self.bundle()
        path = extracted / "LICENSE"
        canonical = path.read_bytes()
        path.unlink()
        self.assertFalse(verifier.verify(extracted)["passed"])
        path.write_bytes(canonical[:100])
        self.assertFalse(verifier.verify(extracted)["passed"])
        manifest_path = extracted / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["files"]["LICENSE"] = {"bytes": path.stat().st_size,
                                       "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        result = verifier.verify(extracted)
        self.assertFalse(result["passed"])
        self.assertEqual(result["checks"]["LICENSE"], "LICENSE_TEXT_MISMATCH")

    def test_old_schema_or_wrong_license_declaration_is_rejected(self):
        _, extracted = self.bundle()
        path = extracted / "manifest.json"
        original = json.loads(path.read_text(encoding="utf-8"))
        for patch in ({"schema": "benchreceipt-local-bundle-v1"}, {"license": "MIT"}, {"license": None},
                      {"publication_status": "UNKNOWN"}):
            path.write_text(json.dumps(dict(original, **patch)), encoding="utf-8")
            self.assertFalse(verifier.verify(extracted)["passed"])

    def test_previous_v2_candidate_status_is_still_accepted(self):
        _, extracted = self.bundle()
        manifest_path = extracted / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["publication_status"] = "LOCAL_CANDIDATE"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        self.assertTrue(verifier.verify(extracted)["passed"])

    def test_artifact_without_embedded_license_is_refused(self):
        artifact = self.source / "dist/benchreceipt.pyz"
        with zipfile.ZipFile(artifact) as app:
            entries = {name: app.read(name) for name in app.namelist() if name != "benchreceipt/LICENSE"}
        with zipfile.ZipFile(artifact, "w") as app:
            for name, data in entries.items():
                app.writestr(name, data)
        output = self.root / "candidate.zip"
        with self.assertRaises(ValueError):
            packager.package(self.source, output)
        self.assertFalse(output.exists())

    def test_extracted_verifier_and_demo_work_without_source(self):
        _, extracted = self.bundle()
        checked = subprocess.run([sys.executable, "-I", "-B", "verify.py"], cwd=extracted, capture_output=True, text=True)
        self.assertEqual(checked.returncode, 0, checked.stderr)
        self.assertTrue(json.loads(checked.stdout)["passed"])
        run = subprocess.run([sys.executable, "-I", "-B", "benchreceipt.pyz", "--demo", "--format", "json", "--output", "demo.json"], cwd=extracted, capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        report = json.loads((extracted / "demo.json").read_text(encoding="utf-8"))
        self.assertEqual(report["data_kind"], "DECLARED_SYNTHETIC")
        self.assertEqual(report["regression_verdict"], "NOT_EVALUATED")
        self.assertTrue(verifier.verify(extracted)["passed"])
        self.assertEqual(verifier.verify(extracted)["unlisted_entry_count"], 1)

    def test_modified_payload_fails_and_is_not_executed(self):
        _, extracted = self.bundle()
        app = extracted / "benchreceipt.pyz"
        app.write_bytes(app.read_bytes() + b"CORRUPTED")
        self.assertFalse(verifier.verify(extracted)["passed"])
        result = subprocess.run([sys.executable, "-I", "-B", "verify.py"], cwd=extracted, capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(json.loads(result.stdout)["checks"]["benchreceipt.pyz"], "MISMATCH")

    def test_missing_payload_fails(self):
        _, extracted = self.bundle()
        (extracted / "README.md").unlink()
        self.assertFalse(verifier.verify(extracted)["passed"])

    def test_manifest_cannot_select_arbitrary_paths_or_empty_set(self):
        _, extracted = self.bundle()
        path = extracted / "manifest.json"
        original = json.loads(path.read_text(encoding="utf-8"))
        for files in ({}, {"../PRIVATE.json": {"bytes": 1, "sha256": "0" * 64}}, None):
            mutated = dict(original, files=files)
            path.write_text(json.dumps(mutated), encoding="utf-8")
            self.assertFalse(verifier.verify(extracted)["passed"])

    def test_linked_payload_is_rejected(self):
        _, extracted = self.bundle()
        readme = extracted / "README.md"
        outside = self.root / "outside.md"
        outside.write_bytes(readme.read_bytes())
        readme.unlink()
        try:
            readme.symlink_to(outside)
        except OSError:
            self.skipTest("Platform does not permit symlink creation")
        self.assertFalse(verifier.verify(extracted)["passed"])

    def test_existing_bundle_is_never_overwritten(self):
        archive, _ = self.bundle()
        before = archive.read_bytes()
        with self.assertRaises(FileExistsError):
            packager.package(self.source, archive)
        self.assertEqual(archive.read_bytes(), before)

    def test_stale_version_or_demo_refused_before_writing_bundle(self):
        output = self.root / "candidate.zip"
        version = self.source / "product/benchreceipt/__init__.py"
        before = version.read_bytes()
        version.write_text('VERSION = "99.0.0"', encoding="utf-8")
        with self.assertRaises(ValueError):
            packager.package(self.source, output)
        self.assertFalse(output.exists())
        version.write_bytes(before)
        example = self.source / "product/examples/synthetic-vllm.json"
        example.write_bytes(example.read_bytes() + b"\n")
        with self.assertRaises(ValueError):
            packager.package(self.source, output)
        self.assertFalse(output.exists())

    def test_same_version_stale_source_and_extra_artifact_entry_are_refused(self):
        output = self.root / "candidate.zip"
        source = self.source / "product/benchreceipt/demo.py"
        original = source.read_bytes()
        source.write_bytes(original + b"\n# source changed without a version change\n")
        with self.assertRaises(ValueError):
            packager.package(self.source, output)
        self.assertFalse(output.exists())
        source.write_bytes(original)
        (self.source / "product/benchreceipt/local_notes.py").write_text("PRIVATE_CANARY", encoding="utf-8")
        with zipfile.ZipFile(self.source / "dist/benchreceipt.pyz", "a") as app:
            app.writestr("benchreceipt/local_notes.py", "PRIVATE_CANARY")
        with self.assertRaises(ValueError):
            packager.package(self.source, output)
        self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()

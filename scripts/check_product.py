"""Portable CPU validation: no Vault data, installed test tools or fixed paths."""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile
import zipfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="New evidence directory; never overwritten")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    def now():
        return datetime.datetime.now(datetime.timezone.utc).isoformat()
    def digest(path):
        return hashlib.sha256(path.read_bytes()).hexdigest()
    sources = {}
    for directory in (root / "product", root / "product_tests"):
        for path in sorted(directory.rglob("*")):
            if path.is_file() and "__pycache__" not in path.parts:
                sources[path.relative_to(root).as_posix()] = digest(path)
    for name in ("build_product.py", "check_product.py", "package_product.py", "verify_bundle.py"):
        sources["scripts/" + name] = digest(root / "scripts" / name)
    (output / "environment.json").write_text(json.dumps({
        "recorded_before_execution_utc": now(), "python": sys.version,
        "executable": sys.executable, "platform": platform.platform(),
        "source_sha256": sources, "level": "Unit/isolated synthetic CLI, not Benchmark",
    }, indent=2), encoding="utf-8")
    steps = []
    def run(name, arguments, cwd):
        command = [sys.executable, "-I", "-B", *map(str, arguments)]
        record = {"command": command, "cwd": str(cwd), "started_utc": now()}
        (output / (name + ".command.json")).write_text(json.dumps(record, indent=2), encoding="utf-8")
        try:
            with (output / (name + ".stdout.log")).open("wb") as stdout, (output / (name + ".stderr.log")).open("wb") as stderr:
                process = subprocess.run(command, cwd=cwd, stdout=stdout, stderr=stderr, timeout=180)
            record.update(exit_code=process.returncode, passed=process.returncode == 0)
        except (OSError, subprocess.TimeoutExpired) as exc:
            record.update(exit_code=None, passed=False, error=type(exc).__name__)
        record["finished_utc"] = now()
        (output / (name + ".execution.json")).write_text(json.dumps(record, indent=2), encoding="utf-8")
        steps.append({"step": name, "passed": record["passed"], "exit_code": record["exit_code"]})
        return record["passed"]
    first_hash = second_hash = bundle_hash = None
    with tempfile.TemporaryDirectory(prefix="benchreceipt-check-") as temporary:
        clean = Path(temporary)
        if run("build", [root / "scripts/build_product.py"], clean):
            app = root / "dist/benchreceipt.pyz"
            first_hash = digest(app)
            if run("tests", ["-m", "unittest", "discover", "-s", root / "product_tests", "-v"], clean):
                copied = clean / "benchreceipt.pyz"
                shutil.copyfile(app, copied)
                for format, suffix in (("html", "html"), ("json", "json"), ("markdown", "md")):
                    if not run("demo-" + format, [copied, "--demo", "--format", format,
                                                 "--output", output / ("demo." + suffix)], clean):
                        break
                if all(step["passed"] for step in steps) and run("rebuild", [root / "scripts/build_product.py"], clean):
                    second_hash = digest(app)
                    steps.append({"step": "repeat-build-identical", "passed": first_hash == second_hash})
                if all(step["passed"] for step in steps):
                    bundle = clean / "candidate.zip"
                    if run("package", [root / "scripts/package_product.py", "--output", bundle], clean):
                        bundle_hash = digest(bundle)
                        extracted = clean / "bundle"
                        with zipfile.ZipFile(bundle) as archive:
                            if (len(archive.namelist()) != 5 or set(archive.namelist()) !=
                                    {"README.md", "benchreceipt.pyz", "verify.py", "LICENSE", "manifest.json"}):
                                raise ValueError("Unexpected bundle members")
                            archive.extractall(extracted)
                        if run("bundle-verify", [extracted / "verify.py"], clean):
                            run("bundle-demo", [extracted / "benchreceipt.pyz", "--demo", "--format", "json",
                                                "--output", output / "bundle-demo.json"], clean)
    passed = len(steps) == 10 and all(step["passed"] for step in steps)
    summary = {"finished_utc": now(), "passed": passed, "steps": steps,
               "artifact_sha256": first_hash, "rebuilt_sha256": second_hash,
               "bundle_sha256": bundle_hash, "license": "Apache-2.0",
               "limits": "Local interpreter/platform only. No GPU, historical benchmark files, remote CI or adoption evidence."}
    (output / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())

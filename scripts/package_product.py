"""Create an Apache-2.0 offline bundle from an explicit allowlist."""
import argparse
import ast
import hashlib
import io
import json
from pathlib import Path
import runpy
import zipfile

artifact_payload = runpy.run_path(str(Path(__file__).with_name("build_product.py")))["artifact_payload"]

APACHE_2_SHA256 = "cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30"


def version(source):
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == "VERSION" for target in node.targets):
            return ast.literal_eval(node.value)
    raise ValueError("Version missing")


def package(root, output):
    root, output = Path(root).resolve(), Path(output).resolve()
    license_bytes = (root / "product/LICENSE").read_bytes()
    if hashlib.sha256(license_bytes).hexdigest() != APACHE_2_SHA256:
        raise ValueError("LICENSE must match the complete adopted Apache-2.0 text")
    artifact = (root / "dist/benchreceipt.pyz").read_bytes()
    with zipfile.ZipFile(io.BytesIO(artifact)) as app:
        expected = artifact_payload(root)
        expected["benchreceipt/LICENSE"] = license_bytes
        if len(app.namelist()) != len(expected) or set(app.namelist()) != set(expected):
            raise ValueError("Artifact contents differ from the source allowlist; rebuild first")
        if any(app.read(name) != data for name, data in expected.items()):
            raise ValueError("Artifact source is stale; rebuild first")
        actual_version = version(app.read("benchreceipt/__init__.py"))
    if actual_version != version((root / "product/benchreceipt/__init__.py").read_bytes()):
        raise ValueError("Artifact version is stale; rebuild first")
    payload = {
        "benchreceipt.pyz": artifact,
        "README.md": (root / "product/PACKAGE-README.md").read_bytes(),
        "verify.py": (root / "scripts/verify_bundle.py").read_bytes(),
        "LICENSE": license_bytes,
    }
    if not all(payload.values()):
        raise ValueError("Empty bundle payload")
    manifest = {"schema": "benchreceipt-local-bundle-v2", "version": actual_version,
                "license": "Apache-2.0",
                "publication_status": "DISTRIBUTABLE",
                "files": {name: {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()} for name, data in sorted(payload.items())}}
    payload["manifest.json"] = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")
    with output.open("xb") as handle:
        with zipfile.ZipFile(handle, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for name, data in sorted(payload.items()):
                info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                info.create_system = 3
                info.external_attr = 0o100644 << 16
                info.compress_type = zipfile.ZIP_DEFLATED
                archive.writestr(info, data, compresslevel=9)
    return {"output": str(output), "sha256": hashlib.sha256(output.read_bytes()).hexdigest(), "members": sorted(payload), "version": actual_version}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="New ZIP file; never overwritten")
    args = parser.parse_args()
    print(json.dumps(package(Path(__file__).resolve().parents[1], args.output), indent=2))


if __name__ == "__main__":
    main()

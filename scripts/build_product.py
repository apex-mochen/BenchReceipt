"""Build a standard-library zipapp with no runtime dependency installation."""
import json
from pathlib import Path
import zipfile

RUNTIME_FILES = {
    "__main__.py": "__main__.py",
    "benchreceipt/__init__.py": "benchreceipt/__init__.py",
    "benchreceipt/__main__.py": "benchreceipt/__main__.py",
    "benchreceipt/batch.py": "benchreceipt/batch.py",
    "benchreceipt/demo.py": "benchreceipt/demo.py",
    "benchreceipt/input.py": "benchreceipt/input.py",
    "benchreceipt/markdown.py": "benchreceipt/markdown.py",
    "benchreceipt/demo.json": "examples/synthetic-vllm.json",
    "benchreceipt/LICENSE": "LICENSE",
}


def artifact_payload(root):
    payload = {name: (root / "product" / source).read_bytes() for name, source in RUNTIME_FILES.items()}
    example = json.loads(payload["benchreceipt/demo.json"])
    if not isinstance(example, dict) or example.get("benchreceipt_data_kind") != "synthetic":
        raise ValueError("The bundled example must be declared synthetic")
    return payload


def main():
    root = Path(__file__).resolve().parents[1]
    payload = artifact_payload(root)
    destination = root / "dist/benchreceipt.pyz"
    destination.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        # Fix timestamp, permissions and entry order instead of inheriting the
        # source checkout's filesystem metadata or local timezone.
        for name, data in payload.items():
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, data, compresslevel=9)
    print(destination)


if __name__ == "__main__":
    main()

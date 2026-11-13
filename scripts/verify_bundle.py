"""Check the bundle's fixed payload against its manifest; execute no payload."""
import argparse
import hashlib
import json
from pathlib import Path
import re

EXPECTED = {"README.md", "benchreceipt.pyz", "verify.py", "LICENSE"}
APACHE_2_SHA256 = "cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30"


def verify(directory):
    root = Path(directory).resolve()
    result = {"passed": False, "checks": {}, "limits": "Integrity against the supplied manifest only; not authenticity, signing or publication approval."}
    try:
        manifest_path = root / "manifest.json"
        if manifest_path.is_symlink() or not manifest_path.is_file() or manifest_path.stat().st_size > 1024 * 1024:
            raise ValueError("manifest unavailable")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        files = manifest["files"]
        if (manifest["schema"] != "benchreceipt-local-bundle-v2"
                or manifest["publication_status"] not in ("LOCAL_CANDIDATE", "DISTRIBUTABLE")
                or manifest["license"] != "Apache-2.0" or set(files) != EXPECTED):
            raise ValueError("manifest schema")
        for name in sorted(EXPECTED):
            metadata = files[name]
            if type(metadata["bytes"]) is not int or metadata["bytes"] <= 0 or not isinstance(metadata["sha256"], str) or not re.fullmatch("[0-9a-f]{64}", metadata["sha256"]):
                raise ValueError("manifest entry")
            path = root / name
            if path.is_symlink() or not path.is_file():
                result["checks"][name] = "MISSING_OR_LINK"
                continue
            digest = hashlib.sha256()
            size = 0
            with path.open("rb") as handle:
                while chunk := handle.read(1024 * 1024):
                    size += len(chunk)
                    digest.update(chunk)
            result["checks"][name] = "MATCH" if size == metadata["bytes"] and digest.hexdigest() == metadata["sha256"] else "MISMATCH"
            if name == "LICENSE" and digest.hexdigest() != APACHE_2_SHA256:
                result["checks"][name] = "LICENSE_TEXT_MISMATCH"
        result["passed"] = all(value == "MATCH" for value in result["checks"].values())
        result["unlisted_entry_count"] = sum(path.name not in EXPECTED | {"manifest.json"} for path in root.iterdir())
        result["unlisted_entry_policy"] = "Not verified or executed; user-created reports may be present."
    except (OSError, ValueError, KeyError, TypeError, UnicodeError):
        result["error"] = "MANIFEST_OR_PAYLOAD_INVALID"
        result["passed"] = False
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=Path(__file__).resolve().parent)
    args = parser.parse_args()
    result = verify(args.directory)
    print(json.dumps(result, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

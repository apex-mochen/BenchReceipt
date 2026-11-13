"""Deterministic, failure-isolated directory receipts. Never follows child links."""
from collections import Counter
import fnmatch
import hashlib
import html
import json
import os
from pathlib import Path

from . import VERSION, inspect_bytes, reading_guide, finding_message, KEYBOARD_HELP, DISCLOSURE_CSS
from .input import DEFAULT_MAX_INPUT_BYTES, InputTooLarge, read_input

EXIT_CODES = {"CHECKED": 0, "INCOMPLETE": 2, "INCONSISTENT": 1,
              "ERROR": 3, "EMPTY": 3, "NO_RESULTS": 3}


def inspect_directory(root, *, pattern="*.json", recursive=False, include_paths=False,
                      max_input_bytes=DEFAULT_MAX_INPUT_BYTES):
    root = Path(root).resolve()
    if not root.is_dir() or not pattern or "/" in pattern or "\\" in pattern:
        raise ValueError("Expected a directory and a filename-only pattern")
    if type(max_input_bytes) is not int or max_input_bytes <= 0:
        raise ValueError("Input size limit must be a positive integer")

    def fail(error):
        raise error

    paths = []
    for directory, folders, files in os.walk(root, followlinks=False, onerror=fail):
        folders[:] = [name for name in folders if not (Path(directory) / name).is_symlink()
                      and not getattr(Path(directory) / name, "is_junction", lambda: False)()]
        paths.extend(Path(directory) / name for name in files if fnmatch.fnmatchcase(name, pattern))
        if not recursive:
            break
    paths.sort(key=lambda path: (path.relative_to(root).as_posix().casefold(), path.relative_to(root).as_posix()))
    rows = []
    missing = Counter()
    findings = Counter()
    for index, path in enumerate(paths, start=1):
        row = {"file_id": f"file-{index:04d}", "status": "ERROR", "input_sha256": None,
               "missing_fields": [], "findings": []}
        if include_paths:
            row["relative_path"] = path.relative_to(root).as_posix()
        try:
            if path.is_symlink():
                row.update(status="SKIPPED", findings=[{"code": "SYMLINK_SKIPPED"}])
            else:
                raw = read_input(path, max_input_bytes)
                row["input_sha256"] = hashlib.sha256(raw).hexdigest()
                # Valid unrelated JSON (configs, metadata, previous receipts) is
                # explicitly skipped. Malformed JSON remains a visible error.
                report = inspect_bytes(raw, allow_unrelated=True)
                if report is None:
                    row.update(status="SKIPPED", findings=[{"code": "UNSUPPORTED_FORMAT"}])
                else:
                    row.update({key: report[key] for key in ("status", "data_kind", "counts", "provenance",
                               "reported_metrics", "recomputed_ttft_ms", "findings")})
                    row["missing_fields"] = sorted({
                        item["field"] for item in report["findings"]
                        if item["code"] in ("COUNT_UNKNOWN", "PROVENANCE_UNKNOWN")
                    } | ({"ttfts"} if any(item["code"] == "TTFT_SAMPLES_MISSING" for item in report["findings"]) else set()))
        except InputTooLarge:
            row.update(status="ERROR", findings=[{"code": "INPUT_TOO_LARGE"}])
        except (OSError, ValueError, UnicodeError, OverflowError, RecursionError):
            row.update(status="ERROR", findings=[{"code": "UNREADABLE_OR_INVALID_INPUT"}])
        missing.update(row["missing_fields"])
        findings.update({item["code"] for item in row["findings"]})
        rows.append(row)
    counts = {key: 0 for key in ("CHECKED", "INCOMPLETE", "INCONSISTENT", "ERROR", "SKIPPED")}
    counts.update(Counter(row["status"] for row in rows))
    status = next((name for name in ("ERROR", "INCONSISTENT", "INCOMPLETE") if counts[name]),
                  "CHECKED" if counts["CHECKED"] else "NO_RESULTS" if rows else "EMPTY")
    return {
        "schema": "benchreceipt-batch-v1", "version": VERSION, "status": status,
        "regression_verdict": "NOT_EVALUATED", "total_files": len(rows),
        "status_counts": counts, "missing_field_counts": dict(sorted(missing.items())),
        "finding_file_counts": dict(sorted(findings.items())), "files": rows,
        "selection": {"filename_pattern": pattern, "recursive": recursive,
                      "max_input_bytes": max_input_bytes},
        "paths_included": include_paths,
        "limits": ["Independent file checks only; no aggregation of performance or regression verdict.",
                   "One bad file does not prevent inspection of the remaining selected files.",
                   "Valid unrelated JSON and symbolic links are explicitly skipped.",
                   "No input text or arbitrary metadata is echoed; numeric metrics remain visible.",
                   "Relative filenames appear only with --include-paths and may be sensitive.",
                   "Each input is size-limited before decoding; this is not a bound on total process memory.",
                   "Oversized inputs have no SHA256; truncated bytes are never reported as complete evidence."],
    }


def render_batch_html(report):
    meaning, action = reading_guide(report["status"])
    def escape(value):
        return html.escape(str(value), quote=True)
    counts = "".join(f"<li>{escape(key)}: {value}</li>" for key, value in report["status_counts"].items())
    missing = "".join(f"<tr><td>{escape(key)}</td><td>{value}</td></tr>" for key, value in report["missing_field_counts"].items())
    rows = []
    for item in report["files"]:
        label = item.get("relative_path", item["file_id"])
        missing_text = ("Completeness not assessed." if item["status"] in ("ERROR", "SKIPPED")
                        else ", ".join(item["missing_fields"]) or "No missing-field findings.")
        findings = "".join(f"<li><strong>{escape(f['code'])}{': ' + escape(f['field']) if 'field' in f else ''}</strong> — {escape(finding_message(f))}</li>" for f in item["findings"])
        finding_detail = (f"<details><summary>Findings ({len(item['findings'])}) — {escape(item['file_id'])}</summary><ul>{findings}</ul></details>"
                          if findings else "<p>No findings in the implemented checks.</p>")
        identity = f"<small>{escape(item['file_id'])}</small>" if report["paths_included"] else ""
        data_note = "<small>Declared synthetic data</small>" if item.get("data_kind") == "DECLARED_SYNTHETIC" else ""
        digest = escape(item["input_sha256"] or "Unavailable — input was not fully read.")
        rows.append(f"<tr><td data-label=\"File\"><span class=\"filename\">{escape(label)}</span>{identity}{data_note}</td><td data-label=\"Status\"><strong>{escape(item['status'])}</strong></td><td data-label=\"Review\"><p><strong>Missing evidence:</strong> {escape(missing_text)}</p>{finding_detail}<details><summary>Input SHA256 — {escape(item['file_id'])}</summary><code>{digest}</code></details></td></tr>")
    inspected = sum(report["status_counts"][status] for status in ("CHECKED", "INCOMPLETE", "INCONSISTENT"))
    zero_notice = ('' if inspected else
                   '<p><strong>Completeness was not assessed.</strong> This is not a successful result check.</p>')
    missing_section = ''
    if inspected:
        missing_rows = missing or '<tr><td>No missing-field findings; skipped/error files were not checked for completeness.</td><td>—</td></tr>'
        missing_section = ('<section><h2>Missing evidence by file count</h2><table><tr><th>Field</th><th>Files</th></tr>'
                           + missing_rows + '</table></section>')
    if rows:
        path_note = ('Relative filenames are included; review before sharing.' if report['paths_included']
                     else 'Filenames are hidden; available Input SHA256 details can match entries to originals.')
        file_content = (f'<p>{path_note}</p><p>Expand findings for explanations and next checks. '
                        'On narrow screens, each entry is a labeled card.</p>'
                        '<table class="results"><thead><tr><th>File</th><th>Status</th><th>Review</th></tr></thead><tbody>'
                        + ''.join(rows) + '</tbody></table>')
    else:
        file_content = '<p>No file entries. Check the directory, --pattern and --recursive options, then run again with a new output path.</p>'
    limits = "".join(f"<li>{escape(item)}</li>" for item in report["limits"])
    encoded = escape(json.dumps(report, indent=2, allow_nan=False))
    return f"""<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'">
<title>BenchReceipt — directory summary</title>
<style>*{{box-sizing:border-box}}body{{font:16px/1.5 system-ui;max-width:1200px;margin:24px auto;padding:0 16px;color:#17283b;background:#f5f7fb;overflow-wrap:anywhere}}section{{background:white;padding:24px;margin:16px 0;border-radius:12px;min-width:0}}h1{{font-size:clamp(24px,4vw,32px)}}td,th{{text-align:left;padding:12px;vertical-align:top;border-bottom:1px solid #ddd;overflow-wrap:anywhere}}table{{border-collapse:collapse;width:100%;table-layout:fixed}}.results th:first-child{{width:32%}}.results th:nth-child(2){{width:18%}}pre,code{{white-space:pre-wrap;overflow-wrap:anywhere}}small{{display:block;margin-top:8px}}.filename{{font-weight:600}}details{{margin:12px 0;min-width:0}}{DISCLOSURE_CSS}li{{margin:8px 0}}.status-counts{{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:8px;padding:0;list-style:none}}.status-counts li{{padding:8px;background:#f5f7fb;margin:0}}.results p{{margin:0 0 12px}}@media(max-width:700px){{body{{padding:0 12px}}section{{padding:16px}}.results,.results tbody,.results tr,.results td{{display:block;width:100%}}.results thead{{display:none}}.results tr{{border:1px solid #ccd4de;border-radius:8px;padding:12px;margin:16px 0}}.results td{{padding:8px 0;border:0}}.results td::before{{content:attr(data-label);display:block;font-weight:700;color:#526579;margin-bottom:4px}}}}</style>
<h1>BenchReceipt — directory summary</h1><section><h2>{escape(report['status'])}</h2><p>{escape(meaning)}</p>{zero_notice}<p>Selected files: {report['total_files']}. Saved results inspected: {inspected}.</p><h3>What to do next</h3><p>{escape(action)}</p><p>Regression verdict: NOT EVALUATED — no cross-run comparison was performed.</p><p>Selected files include skipped and error rows; only CHECKED, INCOMPLETE and INCONSISTENT rows were inspected as saved results. Unknown is not zero.</p><ul class="status-counts">{counts}</ul></section>
<section><p>{KEYBOARD_HELP}</p></section>
{missing_section}
<section><h2>Per-file results</h2>{file_content}</section>
<section><h2>Limits</h2><ul>{limits}</ul></section><section><details><summary>Technical receipt JSON</summary><pre>{encoded}</pre></details></section></html>"""

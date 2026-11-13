"""Shareable Markdown from the existing privacy projection, never raw input."""
from . import reading_guide, finding_message


def cell(value):
    """Keep untrusted relative names inside one inert table cell.

    Entities are parsed as text, not Markdown syntax, links or mentions. Do not
    wrap untrusted values in code spans: embedded backticks can end them.
    """
    text = str(value).replace("\r\n", "\n").replace("\r", "\n")
    entities = {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}
    punctuation = "|`\\[]()*_~:!@#{}"
    return "".join("<br>" if char == "\n" else entities.get(char, f"&#{ord(char)};" if char in punctuation else char)
                   for char in text)


def table(headers, rows):
    lines = ["| " + " | ".join(cell(h) for h in headers) + " |",
             "| " + " | ".join("---" for _ in headers) + " |"]
    lines.extend("| " + " | ".join(cell(v) for v in row) + " |" for row in rows)
    return "\n".join(lines)


def render_markdown(report):
    batch = report.get("schema") == "benchreceipt-batch-v1"
    parts = ["# BenchReceipt" + (" — directory summary" if batch else " — saved-result receipt"),
             "**Status: " + cell(report["status"]) + "**",
             "Regression verdict: **NOT_EVALUATED**. This is evidence inspection, not a performance approval."]
    meaning, action = reading_guide(report["status"])
    parts += [meaning, "## What to do next", action,
              "Unknown means missing or invalid, not zero. Recorded context is available, not independently verified."]
    if batch:
        inspected = sum(report["status_counts"][status] for status in ("CHECKED", "INCOMPLETE", "INCONSISTENT"))
        parts += [f"Selected files: {report['total_files']}.",
                  f"Saved results inspected: {inspected}.",
                  "## Status counts", table(("Status", "Files"), report["status_counts"].items()),
                  "## Missing evidence"]
        if not inspected:
            parts.append("No saved results were inspected. Completeness was not assessed. This is not a successful result check.")
        elif report["missing_field_counts"]:
            parts.append(table(("Field", "Files"), report["missing_field_counts"].items()))
        else:
            parts.append("No missing-field findings. Skipped/error files were not evaluated for completeness.")
        rows = []
        for item in report["files"]:
            label = item["file_id"] + " — " + item["relative_path"] if "relative_path" in item else item["file_id"]
            missing = "Not assessed" if item["status"] in ("ERROR", "SKIPPED") else ", ".join(item["missing_fields"]) or "No missing-field findings"
            rows.append((label, item["status"], missing,
                         ", ".join(sorted({f["code"] for f in item["findings"]})) or "None"))
        parts.append("## Per-file results")
        if rows:
            parts += [table(("File", "Status", "Missing", "Finding codes"), rows),
                      "Relative filenames are included; review before sharing." if report["paths_included"]
                      else "Filenames and absolute root paths are excluded; use SHA256 to match original files."]
        else:
            parts.append("No file entries. Check the directory, --pattern and --recursive options, then run again with a new output path.")
        parts.append(f"Maximum input size per file: {report['selection']['max_input_bytes']} bytes.")
        if rows:
            parts.append("## Per-file details and hashes")
        for item in report["files"]:
            parts += ["### " + cell(item["file_id"]),
                      "Input SHA256: " + cell(item["input_sha256"] or "Unavailable") + "."]
            parts.extend("- " + cell(f["code"] + (": " + f["field"] if "field" in f else "")) + ": " + cell(finding_message(f)) for f in item["findings"])
    else:
        parts += ["Data label: " + cell(report["data_kind"]) + ".",
                  "Input SHA256: " + cell(report["input_sha256"]) + ".",
                  "## Requests", table(("Field", "Count"), ((k, v if v is not None else "Unknown") for k, v in report["counts"].items())),
                  "## Evidence availability", table(("Field", "Evidence"), report["provenance"].items()),
                  "## Reported metrics", table(("Metric", "Value"), report["reported_metrics"].items()),
                  "## Recomputed TTFT", table(("Metric", "Milliseconds"), report["recomputed_ttft_ms"].items()),
                  "## Findings", table(("Finding", "Field", "Meaning and next check"), ((f["code"], f.get("field", "—"), finding_message(f)) for f in report["findings"]))]
        if not report["findings"]:
            parts.append("No discrepancies in the implemented checks.")
        if "input_policy" in report:
            parts.append(f"Maximum input size: {report['input_policy']['max_input_bytes']} bytes.")
    parts += ["## Limits", "\n".join("- " + cell(limit) for limit in report["limits"]),
              "Generated locally. Numeric metrics remain visible; review before sharing. No content is published automatically."]
    return "\n\n".join(parts) + "\n"

"""Local vLLM result receipts. No dependencies, telemetry or causal attribution."""
import hashlib
import html
import json
import math

VERSION = "0.5.0"
METRICS = ("mean_ttft_ms", "p50_ttft_ms", "p95_ttft_ms", "p99_ttft_ms",
           "mean_tpot_ms", "output_throughput", "request_throughput")
KEYBOARD_HELP = "Keyboard: Tab to a detail control; Enter or Space expands or collapses it. Shift+Tab moves back."
DISCLOSURE_CSS = "summary{cursor:pointer;padding:8px 4px;min-height:44px}summary:focus-visible{outline:3px solid #215da8;outline-offset:3px;background:#eaf2ff}"


def number(value):
    try:
        return type(value) in (int, float) and math.isfinite(value) and value >= 0
    except OverflowError:
        return False


def inspect_bytes(raw, *, allow_unrelated=False):
    def reject_constant(_):
        raise ValueError("non-finite JSON constant")
    value = json.loads(raw, parse_constant=reject_constant)
    if not isinstance(value, dict) or not {"completed", "num_prompts"} <= value.keys():
        if allow_unrelated:
            return None
        raise ValueError("Expected a vLLM result object with completed and num_prompts")
    findings = []
    counts = {}
    for field in ("num_prompts", "completed", "failed"):
        val = value.get(field)
        counts[field] = val if type(val) is int and val >= 0 else None
        if counts[field] is None:
            findings.append({"code": "COUNT_UNKNOWN", "field": field})
    if all(v is not None for v in counts.values()):
        if counts["completed"] + counts["failed"] != counts["num_prompts"]:
            findings.append({"code": "COUNT_MISMATCH"})
        if counts["num_prompts"] == 0:
            findings.append({"code": "EMPTY_BATCH"})
    if counts["failed"]:
        findings.append({"code": "FAILED_REQUESTS"})
    if counts["completed"] is not None and counts["num_prompts"] is not None and counts["completed"] > counts["num_prompts"]:
        findings.append({"code": "COUNT_MISMATCH"})
    provenance = {}
    for field in ("gpu", "model_id", "vllm_version", "num_warmups"):
        val = value.get(field)
        valid = (type(val) is int and val >= 0) if field == "num_warmups" else isinstance(val, str) and bool(val.strip())
        provenance[field] = "recorded_unverified" if valid else "unknown"
        if not valid:
            findings.append({"code": "PROVENANCE_UNKNOWN", "field": field})
    metrics = {key: value[key] for key in METRICS if number(value.get(key))}
    for key in METRICS:
        if key in value and key not in metrics:
            findings.append({"code": "METRIC_INVALID", "field": key})
    recomputed = {}
    ttfts = value.get("ttfts")
    if ttfts is not None:
        if not isinstance(ttfts, list) or not ttfts or len(ttfts) != counts["completed"] or not all(number(v) for v in ttfts):
            findings.append({"code": "TTFT_SAMPLES_INVALID"})
        else:
            # Each saved TTFT sample is in seconds; reported aggregates are ms.
            ordered = sorted(ttfts)
            mean = sum(v / len(ordered) for v in ordered) * 1000
            if math.isfinite(mean):
                recomputed["mean_ttft_ms"] = mean
            for p in (50, 95, 99):
                position = (len(ordered) - 1) * p / 100
                lo, hi = math.floor(position), math.ceil(position)
                result = (ordered[lo] * (1 - (position - lo)) + ordered[hi] * (position - lo)) * 1000
                if math.isfinite(result):
                    recomputed[f"p{p}_ttft_ms"] = result
            for key, computed in recomputed.items():
                if key in metrics and not math.isclose(metrics[key], computed, rel_tol=1e-6, abs_tol=1e-6):
                    findings.append({"code": "TTFT_AGGREGATE_MISMATCH", "field": key})
            if len(recomputed) != 4:
                findings.append({"code": "TTFT_NUMERIC_RANGE"})
    else:
        findings.append({"code": "TTFT_SAMPLES_MISSING"})
    issues = {f["code"] for f in findings}
    inconsistent = bool(issues & {"COUNT_MISMATCH", "EMPTY_BATCH", "METRIC_INVALID", "TTFT_SAMPLES_INVALID", "TTFT_AGGREGATE_MISMATCH", "TTFT_NUMERIC_RANGE"})
    status = "INCONSISTENT" if inconsistent else "INCOMPLETE" if findings else "CHECKED"
    return {
        "schema": "benchreceipt-v1", "version": VERSION,
        "data_kind": "DECLARED_SYNTHETIC" if value.get("benchreceipt_data_kind") == "synthetic" else "UNVERIFIED_SAVED_RESULT",
        "status": status, "input_sha256": hashlib.sha256(raw).hexdigest(),
        "input_bytes": len(raw), "counts": counts, "provenance": provenance,
        "reported_metrics": metrics, "recomputed_ttft_ms": recomputed,
        "findings": findings,
        "regression_verdict": "NOT_EVALUATED",
        "limits": ["Single saved file only; no cross-run comparison or root-cause diagnosis.",
                   "Recorded metadata is not verified hardware identity or execution proof.",
                   "TTFT recomputation describes recorded successful requests, not all-request SLO.",
                   "Prompt text, generated text, identifiers, paths and arbitrary metadata are excluded.",
                   "No network, GPU, model, telemetry or paid API is used."],
    }


def reading_guide(status):
    return {
        "CHECKED": ("No discrepancies found in the implemented checks.",
                    "Review the recorded context and numeric values before sharing. CHECKED is not a performance approval."),
        "INCOMPLETE": ("Some evidence is missing, invalid, or includes failed requests.",
                       "Review the findings below. Recover missing fields from the original run records; if unavailable, keep them unknown. Do not fill gaps with guesses."),
        "INCONSISTENT": ("Some counts, samples or reported metrics disagree.",
                         "Compare the findings with the original saved result before relying on its numbers."),
        "ERROR": ("At least one input could not be checked.",
                  "Review error rows and input readability, JSON format or size limit. Other rows may still have useful results."),
        "EMPTY": ("No files matched the selection.", "Check the input directory, filename pattern and recursion option."),
        "NO_RESULTS": ("Selected files were skipped; no result was checked.",
                       "Select saved vLLM result JSON rather than metadata or linked files."),
    }.get(status, ("Review this result's status.", "Read the findings before sharing."))


def finding_message(item):
    return {
        "COUNT_UNKNOWN": "Request count missing or invalid; unknown does not mean zero. Check the original request totals.",
        "COUNT_MISMATCH": "Request totals disagree. Compare requested, completed and failed counts.",
        "EMPTY_BATCH": "No requests were recorded. A zero-request result cannot support a latency claim.",
        "FAILED_REQUESTS": "Failed requests are present; successful-request latency is not an all-request SLO. Review the failures.",
        "PROVENANCE_UNKNOWN": "Run context missing or invalid. Recover it from original run records, or leave it unknown.",
        "METRIC_INVALID": "Reported metric is invalid. Check its value and unit in the original result.",
        "TTFT_SAMPLES_INVALID": "TTFT samples are invalid or their count disagrees with completed requests. Check the saved sample array.",
        "TTFT_SAMPLES_MISSING": "Per-request TTFT samples are unavailable; aggregates cannot be recomputed. Recover detailed results if retained; summary values cannot recreate samples.",
        "TTFT_AGGREGATE_MISMATCH": "Reported TTFT disagrees with recomputed samples. Check sample selection and units (samples: seconds; aggregates: milliseconds).",
        "TTFT_NUMERIC_RANGE": "TTFT arithmetic exceeded the supported numeric range. Review sample values and units.",
        "UNSUPPORTED_FORMAT": "Skipped: valid JSON does not have the supported saved-result shape.",
        "SYMLINK_SKIPPED": "Skipped: linked files are not read.",
        "INPUT_TOO_LARGE": "Input exceeds the configured size limit. Raise it only if resources permit; no truncated hash is provided.",
        "UNREADABLE_OR_INVALID_INPUT": "Input could not be read or parsed. Check permissions and JSON format locally.",
    }.get(item["code"], "Review this finding against the original result.")


def render_html(report):
    def escape(value):
        return html.escape(str(value), quote=True)
    rows = "".join(f"<tr><td>{escape(k)}</td><td>{escape(v)}</td></tr>" for k, v in report["reported_metrics"].items())
    meaning, action = reading_guide(report["status"])
    data_note = "Demo data, not a GPU measurement." if report["data_kind"] == "DECLARED_SYNTHETIC" else "Saved result; historical execution is not verified."
    findings = "".join(f"<li><strong>{escape(item.get('field', item['code']))}</strong>: {escape(finding_message(item))}</li>" for item in report["findings"])
    counts = "".join(f"<tr><td>{escape(k)}</td><td>{escape(v if v is not None else 'Unknown')}</td></tr>" for k, v in report["counts"].items())
    provenance = "".join(f"<tr><td>{escape(k)}</td><td>{'Recorded, not verified' if v == 'recorded_unverified' else 'Unknown — missing or invalid'}</td></tr>" for k, v in report["provenance"].items())
    recomputed = "".join(f"<tr><td>{escape(k)}</td><td>{escape(v)}</td></tr>" for k, v in report["recomputed_ttft_ms"].items())
    limits = "".join(f"<li>{escape(item)}</li>" for item in report["limits"])
    encoded = escape(json.dumps(report, indent=2, allow_nan=False))
    return f"""<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'">
<title>BenchReceipt — offline result check</title>
<style>body{{font:16px system-ui;max-width:960px;margin:40px auto;padding:0 20px;color:#17283b;background:#f5f7fb}}section{{background:white;padding:24px;margin:16px 0;border-radius:12px}}h1{{font-size:32px}}td{{padding:8px;border-bottom:1px solid #ddd}}pre{{white-space:pre-wrap;overflow-wrap:anywhere}}li{{margin:8px 0}}code{{overflow-wrap:anywhere}}{DISCLOSURE_CSS}</style>
<h1>BenchReceipt</h1><p>One saved result. Its evidence and its limits.</p><p>{escape(report['data_kind'])} — {escape(data_note)}</p>
<section><h2>{escape(report['status'])}</h2><p>{escape(meaning)}</p><h3>What to do next</h3><p>{escape(action)}</p><p>Regression verdict: NOT EVALUATED — no cross-run comparison was performed.</p></section>
<section><h2>Findings</h2><ul>{findings or '<li>No discrepancies in the implemented checks.</li>'}</ul></section>
<section><h2>Requests</h2><p>num_prompts: requested; completed: successful; failed: failed when reported. Unknown means missing or invalid, not zero.</p><table><tr><th>Field</th><th>Count</th></tr>{counts}</table><h2>Run context</h2><p>gpu: hardware label; model_id: model label; vllm_version: software version; num_warmups: warmup count. Availability does not verify execution.</p><table><tr><th>Field</th><th>Evidence availability</th></tr>{provenance}</table></section>
<section><h2>Reported metrics</h2><table>{rows or '<tr><td>No valid reported metrics are available.</td></tr>'}</table><h2>Recomputed TTFT (milliseconds)</h2><p>From recorded successful-request samples only.</p><table>{recomputed or '<tr><td>Unavailable — see findings; missing samples cannot be recreated from averages.</td></tr>'}</table></section>
<section><h2>Limits</h2><ul>{limits}</ul></section>
<section><p>{KEYBOARD_HELP}</p><details><summary>Technical receipt JSON and input SHA256</summary><p>Input SHA256: <code>{escape(report['input_sha256'])}</code></p><pre>{encoded}</pre></details></section></html>"""

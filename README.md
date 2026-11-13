# BenchReceipt

**Offline evidence checks for saved vLLM benchmark results.**

Version **0.5.0**, [Apache-2.0](LICENSE).

BenchReceipt helps developers check a saved vLLM-shaped JSON result before sharing its numbers. It preserves failed and unknown request counts, flags missing provenance and checks available TTFT aggregates against successful-request samples. Reports are HTML, JSON or Markdown.

## Download and try

Download the offline ZIP, the three synthetic example reports and `SHA256SUMS` from the [0.5.0 release](https://github.com/apex-mochen/BenchReceipt/releases/tag/v0.5.0). Follow the release notes to verify the download and generate your first report.

## Build from source

**Minimum Python requirement.** Python 3.11 or newer and its standard library.

The offline bundle's recipient workflow was tested on Windows 11 with Python 3.12.14 and 3.13.14, and Ubuntu 24.04 on WSL 2 with Python 3.12.3. The recipient workflow was not tested on Python 3.11 or other environments.

From this source directory, run the following commands.

```shell
python -I -B scripts/build_product.py
python -I -B dist/benchreceipt.pyz --demo --output dist/demo.html
```

Open `dist/demo.html` locally. The example is explicitly **SYNTHETIC**, not a GPU measurement. No model, GPU, server, dependency installation or network access is needed. Existing output files are never overwritten; choose new paths for later runs.

The built `dist/benchreceipt.pyz` can be copied alone to another directory. It includes the synthetic example and full Apache-2.0 license. Its `--demo` and `--help` work without this source tree.

## Check saved results

```shell
python -I -B dist/benchreceipt.pyz result.json --output dist/receipt.html
python -I -B dist/benchreceipt.pyz results --format markdown --output dist/batch.md
python -I -B dist/benchreceipt.pyz results --recursive --pattern "c*-r[0-9].json" --format json --output dist/batch.json
```

Replace `result.json` or `results` with your own input. Quote paths with spaces and create the output directory first. Directory selection defaults to top-level `*.json`. Patterns match filenames and are case-sensitive. Unrelated valid JSON and matching file links are skipped. Child directory links and junctions are excluded from traversal. Invalid files get individual error rows. Traversal failure stops the command.

| Status | Exit | Meaning |
| --- | --- | --- |
| CHECKED | 0 | No discrepancy in the implemented checks. |
| INCONSISTENT | 1 | Counts, samples or aggregates disagree. |
| INCOMPLETE | 2 | Failed requests or evidence gaps require review. |
| ERROR / EMPTY / NO_RESULTS | 3 | An error occurred or no result was checked. |

Batch precedence is ERROR, INCONSISTENT, INCOMPLETE, CHECKED. A batch with file errors still writes its summary when scanning succeeds. A written report prints a JSON status line to stdout, including when the exit code is nonzero. Command syntax errors exit 2 without writing a report. Input/output failures exit 3 with an error on stderr and no successful report. If the output already exists, choose a new `--output` path. In PowerShell use `$LASTEXITCODE` immediately after the command. In Bash or Zsh use `echo $?`.

Every report retains `regression_verdict=NOT_EVALUATED`. A receipt does not prove historical execution, hardware identity, regression, causality or improved performance. Missing samples cannot be recovered. Failed requests do not become successful samples or an all-request SLO.

Start with the status explanation and **What to do next**. CHECKED means the implemented checks found no discrepancy, not performance approval. INCOMPLETE means evidence gaps or failures need review; Unknown never means zero. Recover context from original run records when possible, and leave unavailable fields unknown. HTML keeps the technical receipt JSON collapsed beneath the readable findings.

Batch HTML uses labeled cards on narrow screens. Expand each entry's findings for explanations and its Input SHA256 for the full hash. Long filenames wrap without truncation and appear only when requested with `--include-paths`. Error/skipped rows have completeness **not assessed**. Batch Markdown keeps a compact overview, followed by per-file explanations and full hashes.

Keyboard: use Tab or Shift+Tab to move between detail controls, then Enter or Space to expand or collapse. Each file's control includes its file ID and shows a visible focus outline. EMPTY and NO_RESULTS both exit 3: no saved result was inspected, even though a receipt was written. Check the directory/selection or skipped-entry reasons and use a new output path when trying again.

## Privacy and resource limits

Inputs are read only. Reports omit prompts, generated text, arbitrary metadata and absolute input paths. Batch filenames are hidden by default. A custom `--pattern` is recorded and may itself contain a filename or identifier. `--include-paths` explicitly adds relative filenames. Review counts, hashes, numeric metrics, custom patterns and opted-in filenames before sharing real reports. Use `--demo` to generate a report from the bundled synthetic example. The tool does not upload data or post comments. HTML has no JavaScript or external assets.

Each input read is limited to 64 MiB by default. `--max-input-mib 128` explicitly raises that per-file limit; oversized input is refused without a truncated-content hash. This is not a total process-memory cap.

## Validate and package

```shell
python -I -B scripts/check_product.py --output .validation/run-001
python -I -B scripts/package_product.py --output dist/benchreceipt-local.zip
```

Validation builds the tool, runs Unit/CLI tests, exercises all three demo formats, compares repeat-build hashes, then packages and verifies an extracted bundle and runs its demo. It needs no historical benchmark results. Use a new validation directory and ZIP path each time. Diagnostic logs contain local paths; review them separately before sharing.

The binary ZIP has exactly five files: `benchreceipt.pyz`, `README.md`, `verify.py`, `LICENSE`, `manifest.json`. Extract it into a new directory and run `python -I -B verify.py`, followed by `python -I -B benchreceipt.pyz --demo --output demo.html`. The v2 manifest declares Apache-2.0 and the verifier checks four fixed payloads, including the complete license text. This is integrity checking, not a signature or proof of authenticity. Use the verifier shipped with each bundle.

## Source inventory

`SOURCE-MANIFEST.json` lists every supplied source file's size and SHA256, except the manifest itself. It describes the source snapshot before building. Build outputs, generated reports and validation logs are excluded from the inventory.

See [CONTRIBUTING.md](CONTRIBUTING.md) for focused changes and safe reproductions. The source files are licensed under [Apache-2.0](LICENSE). The build input `product/LICENSE` contains the same full text.

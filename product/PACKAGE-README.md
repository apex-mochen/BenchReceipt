# BenchReceipt 0.5.0

BenchReceipt checks saved vLLM-shaped JSON offline. See the included `LICENSE` for the complete Apache-2.0 terms.

**Minimum Python requirement.** Python 3.11 or newer.

**Tested recipient environments.** Windows 11 with Python 3.12.14 and 3.13.14, and Ubuntu 24.04 on WSL 2 with Python 3.12.3. The recipient workflow was not tested on Python 3.11 or other environments.

Extract this ZIP into a new directory. The ZIP contains the following files.

- `benchreceipt.pyz`: standalone tool, including synthetic demonstration data and an embedded Apache-2.0 `benchreceipt/LICENSE`.
- `verify.py`: standard-library integrity checker; it executes no tool payload.
- `manifest.json`: v2 schema with the Apache-2.0 declaration, SHA256 and size of the four payload files.
- `LICENSE`: complete, unmodified Apache License 2.0 text.
- This README.

## First run

1. Open a terminal in the directory that contains the extracted `verify.py` and `benchreceipt.pyz`. Run `python --version` and check that it shows Python 3.11 or newer. If the command is unavailable, use the full path to an installed Python executable in the commands below.
2. Run the bundle checker:

```text
python -I -B verify.py
```

Continue when it prints `"passed": true` with exit code **0**. If it prints `"passed": false` with exit code **1**, stop and extract a fresh copy of the ZIP into a new directory. The checker reports which files are missing or changed.

3. Generate and open `demo.html` in your browser:

```text
python -I -B benchreceipt.pyz --demo --output demo.html
```

Expect status `CHECKED` and exit code **0**. The report identifies the example as **SYNTHETIC**. No server, GPU, model, fixture download, pip installation or internet access is needed. To run the demo again, choose a new output name such as `demo-2.html`. BenchReceipt preserves existing files.

## View or regenerate the companion examples

You may receive `demo.html`, `demo.json` and `demo.md` alongside the ZIP. These files are example reports. Open the HTML file in a browser and the JSON or Markdown files in a text editor. They are optional. Keep them outside the extracted directory if you want to regenerate reports with the same names.

The program includes the synthetic input. In the extracted directory, use the HTML demo command above or run these commands for the other formats:

```text
python -I -B benchreceipt.pyz --demo --format json --output demo.json
python -I -B benchreceipt.pyz --demo --format markdown --output demo.md
```

Each generated report shows `CHECKED` and marks the input as synthetic. Report files use UTF-8 with CRLF line endings across platforms so regenerated examples can match the companion files byte for byte. For your own checks, use saved vLLM result JSON as input. `demo.json` is the output of the example check.

## Check your own results

Replace `result.json` or `results` with the path to your saved vLLM result or results directory. Quote paths that contain spaces. If you save a report in a subdirectory, create that directory first.

```text
python -I -B benchreceipt.pyz result.json --output receipt.html
python -I -B benchreceipt.pyz results --format markdown --output batch.md
```

### Paths with spaces in Git Bash

Use a path such as `/d/Work/BenchReceipt unpacked` in Git Bash. Replace the example directory and input file with your own paths. If you use the full path to Python, quote that path too.

```bash
cd "/d/Work/BenchReceipt unpacked"
mkdir -p "Report Files"
python -I -B benchreceipt.pyz "Saved Results/Run With Gaps.json" --output "Report Files/Gap Receipt.html"
echo $?
```

HTML, JSON and Markdown are supported. Use `--help` for patterns, recursion, opt-in relative filenames and input-size limits. Input files are read only and existing outputs are never overwritten. Default maximum input size is 64 MiB per file; this is not a total-memory guarantee.

## Read the exit code and check for a report

When BenchReceipt writes a report, it prints a short JSON line with `status` and `regression_verdict`. Open the file named by `--output` even when the exit code is nonzero if that status line appears. If the command prints an error instead, resolve it before using any file at the output path.

| Exit | Report written | What to do |
| --- | --- | --- |
| 0 | Yes, `CHECKED` | Read the findings. The implemented checks found no discrepancy. |
| 1 | Yes, `INCONSISTENT` | Review disagreements in the findings. |
| 2 | Yes, `INCOMPLETE` | Review missing evidence or failed requests. |
| 2 | No, command syntax error | Read the error and run `benchreceipt.pyz --help` through Python. |
| 3 | Yes, `EMPTY`, `NO_RESULTS` or batch `ERROR` | Review the selection or per-file findings. An empty selection or a batch with only skipped files checked zero results. |
| 3 | No successful report, input/output error | Read the error. Check the input and output paths. If the output exists, choose a new one. |

Read the exit code immediately after the tool runs. In PowerShell use `$LASTEXITCODE`. In Bash or Zsh use `echo $?` before running another command. The number alone cannot tell you whether a report was written. Check the JSON status line and the file named by `--output`. Use the `passed` field for the separate bundle checker.

All reports keep `regression_verdict=NOT_EVALUATED`. The checks cover the supplied evidence and do not establish performance approval, root cause, hardware identity or historical execution.

For a shareable example, generate a fresh report with `--demo`. Review reports from your own results before sharing. The projection excludes prompts and arbitrary metadata, while counts, numeric metrics, input hashes and custom batch patterns can remain visible. `--include-paths` also shows relative filenames. Nothing is published or uploaded automatically.

The verifier checks the manifest's **fixed four payload names**, including `LICENSE`. It refuses missing, linked or modified payloads, invalid manifests and a LICENSE that differs from the adopted complete text, even if its manifest hash is updated. Old v1 manifests are rejected; use the checker shipped with each bundle. Extra files (such as generated reports) are counted but neither verified nor executed. A matching manifest proves consistency with that manifest, not authenticity: an attacker able to replace the manifest and checker can replace both. No signature is provided.

## 中文

最低运行要求是 Python 3.11 或更新版本。实际接收方复核覆盖 Windows 11 的 Python 3.12.14、3.13.14，以及 Ubuntu 24.04 WSL 2 的 Python 3.12.3。Python 3.11 接收方流程尚未验证。

1. 解压到新目录，在包含 `verify.py` 的目录打开终端。用 `python --version` 确认 Python 3.11 或更新版本。
2. 执行 `python -I -B verify.py`。看到 `"passed": true` 和退出码 0 再继续。校验失败时先重新解压到新目录。
3. 执行 `python -I -B benchreceipt.pyz --demo --output demo.html`，用浏览器打开生成的合成示例。重复运行时换成 `demo-2.html` 等新文件名。
4. 工具输出带 `status` 的 JSON 行时，报告已经写入，即使退出码是 1、2 或 3。退出码 2 也可能是命令参数写错，3 也可能是输入或输出失败。PowerShell 里用 `$LASTEXITCODE` 查看退出码，Git Bash 里紧接着运行 `echo $?`。结合状态行和输出文件判断报告是否写入。
5. Git Bash 里用双引号括起带空格的目录、输入和输出路径。如果把报告写到子目录，先创建该目录。上面的 Git Bash 示例展示了完整命令。
6. ZIP 旁的 `demo.html`、`demo.json` 和 `demo.md` 是可直接查看的合成报告。用浏览器打开 HTML，用文本编辑器查看 JSON 或 Markdown。把它们留在解压目录外，再按上面的示例命令在解压目录里重生成。`demo.json` 是报告输出，运行示例只需 `--demo`。

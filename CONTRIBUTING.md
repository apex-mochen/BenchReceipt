# Contributing

BenchReceipt is licensed under [Apache-2.0](LICENSE).

For a bug report, use [GitHub Issues](https://github.com/apex-mochen/BenchReceipt/issues). Include the Python and OS versions, exact command, expected behavior, actual status and exit code, and relevant finding. Prefer a minimal synthetic JSON example. Do not include customer data, prompts, generated text, credentials or private paths. Metrics and hashes may also be sensitive.

Keep changes focused. Preserve unknown versus zero, failed requests, synthetic labels, `NOT_EVALUATED`, input read-only behavior and refusal to overwrite outputs. Fixes should include a small reproducer and a relevant regression test. Runtime code uses only the Python standard library.

From the source root, run:

```shell
python -I -B scripts/check_product.py --output .validation/run-001
```

Use a new evidence directory each time. Inspect the summary, stdout, stderr and any platform skips; report untested platforms honestly. No GPU, historical data or external service is required. Generated diagnostic logs can contain local paths and must be reviewed before sharing.

For potential security issues, avoid posting sensitive details in a public issue.

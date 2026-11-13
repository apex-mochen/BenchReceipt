import argparse
import json
from pathlib import Path
import sys
from . import VERSION, inspect_bytes, render_html
from .batch import EXIT_CODES, inspect_directory, render_batch_html
from .input import DEFAULT_MAX_INPUT_BYTES, InputTooLarge, read_input
from .markdown import render_markdown
from .demo import demo_bytes


def positive_mib(value):
    try:
        result = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Expected a positive integer MiB limit") from exc
    if result <= 0:
        raise argparse.ArgumentTypeError("Expected a positive integer MiB limit")
    return result


def main():
    parser = argparse.ArgumentParser(
        description="Offline, privacy-projected vLLM result receipt. No GPU required.",
        epilog=("Report written: 0 CHECKED, 1 INCONSISTENT, 2 INCOMPLETE, or 3 EMPTY, NO_RESULTS or batch ERROR. "
                "Command failures: 2 invalid syntax, 3 input/output failure. "
                "A written report prints its status to stdout."),
    )
    parser.add_argument("--version", action="version", version=VERSION)
    parser.add_argument("input", type=Path, nargs="?")
    parser.add_argument("--demo", action="store_true", help="Use the bundled synthetic example; no input file or GPU needed")
    parser.add_argument("--output", type=Path, required=True, help="New report path; existing files are never overwritten")
    parser.add_argument("--format", choices=("json", "html", "markdown"), default="html")
    parser.add_argument("--pattern", default="*.json", help="Directory mode: filename pattern (default: *.json)")
    parser.add_argument("--recursive", action="store_true", help="Directory mode: include subdirectories, without following links")
    parser.add_argument("--include-paths", action="store_true", help="Include relative filenames in directory reports; review before sharing")
    parser.add_argument("--max-input-mib", type=positive_mib, default=DEFAULT_MAX_INPUT_BYTES // (1024 * 1024),
                        help="Maximum size of each input before JSON decoding (default: 64 MiB)")
    args = parser.parse_args()
    if (args.input is None) == (not args.demo):
        parser.error("Choose exactly one input file/directory or --demo")
    if args.demo and (args.recursive or args.include_paths or args.pattern != "*.json"):
        parser.error("Directory options cannot be used with --demo")
    try:
        if args.input is not None and args.input.resolve() == args.output.resolve():
            raise ValueError("Input and output must differ")
        if args.output.exists():
            raise FileExistsError
        if args.demo:
            report = inspect_bytes(demo_bytes())
            report["input_policy"] = {"max_input_bytes": args.max_input_mib * 1024 * 1024}
            html_renderer = render_html
        elif args.input.is_dir():
            report = inspect_directory(args.input, pattern=args.pattern, recursive=args.recursive,
                                       include_paths=args.include_paths, max_input_bytes=args.max_input_mib * 1024 * 1024)
            html_renderer = render_batch_html
        else:
            if args.recursive or args.include_paths or args.pattern != "*.json":
                raise ValueError("Directory options require directory input")
            report = inspect_bytes(read_input(args.input, args.max_input_mib * 1024 * 1024))
            report["input_policy"] = {"max_input_bytes": args.max_input_mib * 1024 * 1024}
            html_renderer = render_html
        renderers = {"html": html_renderer, "markdown": render_markdown,
                     "json": lambda item: json.dumps(item, indent=2, allow_nan=False)}
        text = renderers[args.format](report)
        try:
            output = args.output.open("x", encoding="utf-8", newline="\r\n")
        except FileNotFoundError:
            print("ERROR: Output directory does not exist. Create it or choose another --output path.", file=sys.stderr)
            return 3
        with output:
            output.write(text)
    except FileExistsError:
        print("ERROR: Output already exists. Choose a new --output path.", file=sys.stderr)
        return 3
    except InputTooLarge:
        print("ERROR: INPUT_TOO_LARGE. Choose a larger --max-input-mib only if resources permit.", file=sys.stderr)
        return 3
    except (OSError, ValueError, UnicodeError, OverflowError, RecursionError):
        print("ERROR: invalid/unreadable input or unavailable output. No input content is echoed.", file=sys.stderr)
        return 3
    print(json.dumps({"status": report["status"], "regression_verdict": "NOT_EVALUATED"}))
    return EXIT_CODES[report["status"]]


if __name__ == "__main__":
    raise SystemExit(main())

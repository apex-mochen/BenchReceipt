"""Load the one canonical synthetic example from a zipapp or source checkout."""
from importlib.resources import files
from pathlib import Path


def demo_bytes():
    try:
        return files("benchreceipt").joinpath("demo.json").read_bytes()
    except FileNotFoundError:
        # Source checkouts keep the canonical fixture outside the package. The
        # builder embeds exactly those bytes; no separate demo data is invented.
        return (Path(__file__).resolve().parents[1] / "examples/synthetic-vllm.json").read_bytes()

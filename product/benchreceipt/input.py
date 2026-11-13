"""Bound saved-file reads before JSON decoding; never returns truncated evidence."""
import os
from pathlib import Path
import stat

DEFAULT_MAX_INPUT_BYTES = 64 * 1024 * 1024


class InputTooLarge(ValueError):
    pass


def read_input(path, max_input_bytes=DEFAULT_MAX_INPUT_BYTES):
    if type(max_input_bytes) is not int or max_input_bytes <= 0:
        raise ValueError("Input size limit must be a positive integer")
    with Path(path).open("rb") as handle:
        info = os.fstat(handle.fileno())
        if not stat.S_ISREG(info.st_mode):
            raise ValueError("Expected a regular saved file")
        if info.st_size > max_input_bytes:
            raise InputTooLarge("Input exceeds configured byte limit")
        raw = handle.read(max_input_bytes + 1)
        if len(raw) > max_input_bytes:
            raise InputTooLarge("Input exceeds configured byte limit")
    return raw

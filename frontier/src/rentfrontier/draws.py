"""Reading a run's kept draws from posterior.npz a block of draws at a time.

`explain.load_run` reads every kept array whole and casts it to float64. On
the served all-scraped run that comes to about 28 GB, 18 GB of it the building
walk, on a machine with 15 GB. The estimate kit reads 250 of the 1000 draws and
two of the walk's 35 knots, and the rent map reads every draw's walk only to
average it over each calendar year. So `read` goes through the archive's
members in order, decompresses `block` draws at a time, keeps the draws asked
for, and hands each block to a function of the caller's before keeping it.

The arrays come out as `explain.load_run` gives them: (draws, ...) with the
chains' draws one after another, in float64 unless the caller asks for another
type.
"""

from __future__ import annotations

import json
import zipfile
from collections.abc import Callable
from pathlib import Path

import numpy as np
from numpy.lib import format as npy

from .run import RUNS

PREFIX = "kept/"


def run(name: str) -> tuple[Path, dict]:
    """The run's directory and its result.json, without its draws."""
    run_dir = RUNS / name
    return run_dir, json.loads((run_dir / "result.json").read_text())


def _header(fh):
    version = npy.read_magic(fh)
    read = npy.read_array_header_1_0 if version == (1, 0) else npy.read_array_header_2_0
    return read(fh)


def shapes(path: Path) -> dict[str, tuple]:
    """Each kept array's stored shape, (chains, draws per chain, ...)."""
    found = {}
    with zipfile.ZipFile(path) as archive:
        for member in archive.namelist():
            if member.startswith(PREFIX):
                with archive.open(member) as fh:
                    found[member[len(PREFIX) : -len(".npy")]] = _header(fh)[0]
    return found


def _fill(fh, view) -> int:
    """Read into `view` a few MB at a time, which glibc serves from its heap
    and reuses, and return the bytes read."""
    filled = 0
    while filled < len(view):
        part = fh.read(min(1 << 22, len(view) - filled))
        if not part:
            break
        view[filled : filled + len(part)] = part
        filled += len(part)
    return filled


def read(
    path: Path,
    keys=None,
    draws=None,
    take: dict[str, Callable] | None = None,
    dtype=np.float64,
    block: int = 20,
) -> dict[str, np.ndarray]:
    """The kept arrays named in `keys` (all of them by default), at the
    increasing draw indexes `draws` (all by default) of the (draws, ...) axis.

    Each block of draws is cast to `dtype` (None keeps the stored type) and
    passed through `take[key]`, when given, before it is kept; the function
    gets and returns arrays with the draws on the first axis.
    """
    take = take or {}
    out = {}
    with zipfile.ZipFile(path) as archive:
        for member in archive.namelist():
            if not member.startswith(PREFIX):
                continue
            key = member[len(PREFIX) : -len(".npy")]
            if keys is not None and key not in keys:
                continue
            with archive.open(member) as fh:
                shape, fortran, stored = _header(fh)
                if fortran or stored.hasobject or len(shape) < 2:
                    raise ValueError(f"{member} is not (chains, draws, ...) in C order")
                n = shape[0] * shape[1]
                rest = tuple(shape[2:])
                index = np.arange(n) if draws is None else np.asarray(draws)
                if index.size and (index[0] < 0 or index[-1] >= n):
                    raise ValueError(f"{member} has {n} draws")
                if np.any(np.diff(index) <= 0):
                    raise ValueError("draws must be increasing")
                per = int(np.prod(rest, dtype=np.int64)) * stored.itemsize
                fn = take.get(key)
                width = min(block, n)
                # The buffers are reused for every block: a fresh array per block
                # faults its pages in again, which on the all-scraped run is most
                # of a step's system time.
                raw = bytearray(per * width)
                picked = np.empty((width, *rest), stored)
                cast = np.empty((width, *rest), dtype) if fn and dtype else None
                kept, filled = None, 0
                for lo in range(0, n, block):
                    hi = min(lo + block, n)
                    if _fill(fh, memoryview(raw)[: per * (hi - lo)]) != per * (hi - lo):
                        raise ValueError(f"{member} ends early")
                    wanted = index[(index >= lo) & (index < hi)]
                    if not len(wanted):
                        continue
                    value = np.frombuffer(raw, stored).reshape(width, *rest)[: hi - lo]
                    if len(wanted) < hi - lo:
                        # mode="clip" writes straight into `picked`; "raise" buffers.
                        sel = picked[: len(wanted)]
                        np.take(value, wanted - lo, axis=0, out=sel, mode="clip")
                        value = sel
                    if fn:
                        if cast is not None:
                            np.copyto(cast[: len(value)], value, casting="unsafe")
                            value = cast[: len(value)]
                        value = fn(value)
                    if kept is None:
                        # The whole array at once, so it is never held twice.
                        kind = value.dtype if fn or dtype is None else dtype
                        kept = np.empty((len(index), *value.shape[1:]), kind)
                    kept[filled : filled + len(value)] = value
                    filled += len(value)
                if kept is None:
                    empty = np.empty((0, *rest), stored if dtype is None else dtype)
                    kept = fn(empty) if fn else empty
                out[key] = kept
    return out

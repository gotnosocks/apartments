"""Observable local NUTS sampling and recoverable binary result publication."""
from __future__ import annotations

from datetime import datetime, UTC
import json
import math
from pathlib import Path
import time

from apartments.corrections import canonical
from apartments.research_pipeline import _verified_bundle, digest

VERSION = 'observable-bayesian-sampling-v2'


def write_status(path, phase, **details):
    path = Path(path)
    value = {'phase': phase, 'updated_at': datetime.now(UTC).isoformat(), **details}
    temporary = path.with_name(path.name+'.tmp')
    temporary.write_text(canonical(value)+'\n')
    temporary.replace(path)
    return value


class SamplingProgress:
    """Nutpie calls this on its background thread; no model mutation occurs."""
    def __init__(self, path, emit_seconds=60):
        self.path = Path(path)
        self.emit_seconds = emit_seconds
        self.last_emit = -math.inf

    def __call__(self, chains):
        rows = []
        for index, chain in enumerate(chains):
            step_size = float(chain.step_size)
            rows.append({'chain': index, 'finished_draws': int(chain.finished_draws),
                'total_draws': int(chain.total_draws), 'divergences': int(chain.divergences),
                'tuning': bool(chain.tuning), 'started': bool(chain.started),
                'latest_num_steps': int(chain.latest_num_steps),
                'total_num_steps': int(chain.total_num_steps),
                'step_size': step_size if math.isfinite(step_size) else None,
                'runtime_seconds': float(chain.runtime_ms)/1000})
        status = write_status(self.path, 'sampling', chains=rows)
        now = time.monotonic()
        if now-self.last_emit >= self.emit_seconds:
            print(canonical(status), flush=True)
            self.last_emit = now


def sample(model, *, draws, tune, chains, seed, adaptation, target_accept, status_path):
    """Use nutpie's public callback interface; retain proper PyMC named coordinates."""
    import nutpie
    write_status(status_path, 'compiling')
    started = time.monotonic()
    try:
        compiled = nutpie.compile_pymc_model(model, backend='numba')
        inference = nutpie.sample(compiled, draws=draws, tune=tune, chains=chains,
            cores=min(chains, 4), seed=seed, adaptation=adaptation, target_accept=target_accept,
            save_warmup=False, store_unconstrained=False, progress_bar=False,
            progress_callback=SamplingProgress(status_path), progress_rate=5000)
        if (inference['posterior'].sizes.get('chain') != chains
                or inference['posterior'].sizes.get('draw') != draws):
            raise ValueError('Sampler returned incomplete chains or draws')
    except BaseException as error:
        write_status(status_path, 'failed', error_type=type(error).__name__, elapsed_seconds=time.monotonic()-started)
        raise
    write_status(status_path, 'sampled', elapsed_seconds=time.monotonic()-started)
    return inference


def publish_fit(directory, *, version, protocol_hash):
    """An interrupted atomic completion write never enters its own checksum set."""
    directory = Path(directory)
    complete = directory/'complete.json'
    if complete.exists():
        manifest, _ = _verified_bundle(directory)
        if manifest.get('version') != version or manifest.get('protocol_sha256') != protocol_hash:
            raise ValueError('Completed fit belongs to another protocol')
        return manifest
    temporary = directory/'complete.json.tmp'
    payloads = [p for p in directory.iterdir() if p.name != temporary.name]
    if not payloads or any(not p.is_file() or p.is_symlink() for p in payloads):
        raise ValueError('Fit payloads must be regular files')
    files = {p.name: digest(p) for p in payloads}
    manifest = {'version': version, 'protocol_sha256': protocol_hash, 'files': files}
    temporary.write_text(canonical(manifest)+'\n')
    temporary.replace(complete)
    _verified_bundle(directory)
    return manifest

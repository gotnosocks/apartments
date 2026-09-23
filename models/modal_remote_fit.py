"""Run an unchanged local fit runner on Modal; the local checkout stays primary.

    uv run --locked --extra model --extra modal python -m models.modal_remote_fit run \\
        --dataset /home/ben/code/apartments/data/model/chelsea-product-scope-analysis-20260921 \\
        --output data/model/modal-runs/spline-smoke -- --draws 50 --tune 50 --chains 4

Inputs go to Volume ``apartments-fit-work`` as SHA-256 blobs (only missing blobs are
uploaded), the worker runs in scratch space, and fit/protocol products come back to a
new local directory after verification. The Volume is a cache: ``clean`` removes a run
and ``clean --unreferenced-blobs`` prunes blobs no remaining run needs.
"""
from __future__ import annotations

import argparse
import io
import json
import sys
import time
from pathlib import Path

import modal
from modal.exception import NotFoundError

from . import remote_fit_sync as sync

REPO = Path(__file__).resolve().parents[1]
VOLUME_NAME = 'apartments-fit-work'
UV_VERSION = '0.12.15'
# Versions of the September 18-19 GPU benchmark environment (docs/analysis/chelsea-sampler-reassessment-2026-09-18.md).
JAX_STACK = ['jax[cuda13]==0.11.1', 'numpyro==0.22.0', 'blackjax==1.6.2']
# Modal list prices recorded 2026-09-08 in docs/model/modal.md; estimates, not bills.
USD_PER_CORE_SECOND = .0000131
USD_PER_GIB_SECOND = .00000222


def volume():
    return modal.Volume.from_name(VOLUME_NAME, create_if_missing=True, version=2)


def image(repo=REPO, jax=False):
    # Same locked scientific stack as local fits; code and data arrive as blobs, not layers.
    result = (modal.Image.debian_slim(python_version='3.12')
              .apt_install('build-essential')
              .uv_sync(str(repo), extras=['model'], frozen=True, uv_version=UV_VERSION))
    if jax:
        # Not in uv.lock: an explicit experiment layer, recorded in each run's request.
        quoted = ' '.join(f'"{p}"' for p in JAX_STACK)
        result = result.run_commands(f'/.uv/uv pip install --python /.uv/.venv/bin/python {quoted}')
    return result.add_local_file(Path(sync.__file__), '/root/models/remote_fit_sync.py')


def present_blobs(store):
    try:
        return {Path(entry.path).name for entry in store.listdir('/blobs')}
    except (FileNotFoundError, NotFoundError):
        return set()


def read_json(store, path):
    return json.loads(b''.join(store.read_file(path)))


GPU_USD_PER_SECOND = {'T4': .000164, 'L4': .000222, 'A10': .000306, 'L40S': .000542, 'A100-40GB': .000583,
                      'A100-80GB': .000694, 'RTX-PRO-6000': .000842, 'H100': .001097, 'H200': .001261,
                      'B200': .001736}  # modal.com/pricing, 2026-09-22


def estimate_usd(result, resources):
    seconds = result['timings']['worker_seconds']
    gpu = GPU_USD_PER_SECOND.get((resources.get('gpu') or '').upper(), 0.)
    return seconds*(resources['cpu']*USD_PER_CORE_SECOND + resources['memory_mib']/1024*USD_PER_GIB_SECOND + gpu)


def submit(args):
    destination = Path(args.output).resolve()
    partial = destination.with_name(destination.name + '.partial')
    if destination.exists() or partial.exists():
        raise SystemExit(f'Output or partial download already exists: {destination}')
    runner_args = args.runner_args[1:] if args.runner_args[:1] == ['--'] else args.runner_args
    jax = args.jax or bool(args.gpu)
    resources = {'cpu': args.cpu, 'memory_mib': args.memory, 'timeout_seconds': args.timeout,
                 'ephemeral_disk_mib': args.ephemeral_disk, 'gpu': args.gpu,
                 'jax_stack': JAX_STACK if jax else None}
    extra_code = {Path(path).resolve().relative_to(REPO).as_posix(): path for path in args.add_code}
    run_id = sync.new_run_id(args.label)
    started = time.monotonic()
    request, sources = sync.build_request(repo=args.code_root, dataset=args.dataset, runner=args.runner,
        runner_args=runner_args, run_id=run_id, inputs=args.input,
        keep_auxiliary=args.keep_auxiliary, resources=resources, extra_code=extra_code,
        returned=args.returned)
    hashing = time.monotonic() - started

    store = volume()
    started = time.monotonic()
    missing = sync.missing_blobs(request, present_blobs(store))
    # Blobs are named by content hash, so a concurrent submit writing the same name is harmless.
    with store.batch_upload(force=True) as batch:
        for sha in missing:
            batch.put_file(sources[sha], f'/blobs/{sha}')
        batch.put_file(io.BytesIO(json.dumps(request, indent=2).encode()), f'/runs/{run_id}/request.json')
    total = {item['sha256']: item['size'] for item in request['files']}
    transfer = {'input_files': len(request['files']), 'input_blobs': len(total),
                'input_bytes': sum(total.values()), 'uploaded_blobs': len(missing),
                'uploaded_bytes': sum(missing.values()), 'hash_seconds': hashing,
                'upload_seconds': time.monotonic() - started}
    print(json.dumps({'run_id': run_id, **transfer}, indent=2), flush=True)

    partial.mkdir(parents=True)
    record = {'run_id': run_id, 'volume': VOLUME_NAME, 'request_git': request['git'],
              'runner': request['runner'], 'runner_args': runner_args, 'dataset': request['dataset'],
              'resources': resources, 'upload': transfer}
    (partial/'remote-submit.json').write_text(json.dumps(record, indent=2) + '\n')

    app = modal.App(f'apartments-fit-{run_id}'.lower()[:64])
    options = {'ephemeral_disk': args.ephemeral_disk} if args.ephemeral_disk else {}
    if args.gpu:
        options['gpu'] = args.gpu
    worker = app.function(image=image(args.code_root, jax), cpu=args.cpu, memory=args.memory, timeout=args.timeout,
        **options, volumes={sync.VOLUME_MOUNT: store}, retries=0,
        max_containers=1, include_source=False)(sync.modal_worker)
    started = time.monotonic()
    with modal.enable_output(), app.run(detach=args.detach):
        if args.detach:
            call = worker.spawn(run_id, VOLUME_NAME)
            print(json.dumps({'run_id': run_id, 'function_call_id': call.object_id,
                              'fetch': f'python -m models.modal_remote_fit fetch --run-id {run_id} --output {args.output}'}, indent=2))
            return
        worker.remote(run_id, VOLUME_NAME)
    remote_seconds = time.monotonic() - started
    fetch_run(store, run_id, destination, remote_seconds=remote_seconds, include_auxiliary=args.keep_auxiliary)


def fetch_run(store, run_id, destination, remote_seconds=None, include_auxiliary=False):
    destination = Path(destination).resolve()
    partial = destination.with_name(destination.name + '.partial')
    result = read_json(store, f'/runs/{sync.safe_id(run_id)}/result.json')
    request = read_json(store, f'/runs/{run_id}/request.json')
    if not result['succeeded']:
        partial.mkdir(parents=True, exist_ok=True)
        (partial/'remote-runner.log').write_bytes(b''.join(store.read_file(f'/runs/{run_id}/runner.log')))
        raise SystemExit(f'Remote runner failed (exit {result["returncode"]}); log in {partial/"remote-runner.log"}')
    include = [*request['returned'], *(sync.AUXILIARY if include_auxiliary else ())]
    started = time.monotonic()
    downloaded = sync.download(result, lambda path: store.read_file(f'/runs/{run_id}/output/{path}'),
                               destination, include=include)
    downloaded['download_seconds'] = time.monotonic() - started
    (destination/'remote-runner.log').write_bytes(b''.join(store.read_file(f'/runs/{run_id}/runner.log')))
    submitted = destination/'remote-submit.json'
    record = json.loads(submitted.read_text()) if submitted.exists() else {'run_id': run_id}
    record.update(result={k: v for k, v in result.items() if k != 'files'}, download=downloaded,
                  remote_call_seconds=remote_seconds,
                  estimated_worker_usd=estimate_usd(result, request['resources']),
                  cost_note='Worker seconds at 2026-09-08 list prices; excludes image builds, startup, storage and egress.')
    (destination/'remote-run.json').write_text(json.dumps(record, indent=2) + '\n')
    print(json.dumps({k: record[k] for k in ('run_id', 'download', 'remote_call_seconds', 'estimated_worker_usd')}
                     | {'timings': result['timings'], 'output': str(destination)}, indent=2))


def clean(args):
    store = volume()
    if args.run_id:
        store.remove_file(f'/runs/{sync.safe_id(args.run_id)}', recursive=True)
    if args.unreferenced_blobs:
        referenced = set()
        for entry in store.listdir('/runs'):
            try:
                referenced |= {item['sha256'] for item in read_json(store, f'{entry.path}/request.json')['files']}
            except (FileNotFoundError, NotFoundError):
                raise SystemExit(f'{entry.path} has no request; refusing to prune blobs')
        stale = present_blobs(store) - referenced
        for sha in sorted(stale):
            store.remove_file(f'/blobs/{sha}')
        print(json.dumps({'removed_blobs': len(stale)}))


def listing(args):
    store = volume()
    try:
        runs = sorted(Path(entry.path).name for entry in store.listdir('/runs'))
    except (FileNotFoundError, NotFoundError):
        runs = []
    for run_id in runs:
        try:
            result = read_json(store, f'/runs/{run_id}/result.json')
            state = 'succeeded' if result['succeeded'] else f'failed ({result["returncode"]})'
        except (FileNotFoundError, NotFoundError):
            state = 'running or never finished'
        print(run_id, state)


def argument_parser():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest='command', required=True)
    run = commands.add_parser('run', help='Upload changed inputs, fit remotely, download results')
    run.add_argument('--dataset', type=Path, required=True)
    run.add_argument('--output', type=Path, required=True, help='New local experiment directory')
    run.add_argument('--runner', default='models.bayesian_floor_spline_experiment')
    run.add_argument('--code-root', type=Path, default=REPO,
                     help='Checkout whose src/models/config and uv.lock are sent (default: this one)')
    run.add_argument('--input', type=Path, action='append', default=[],
                     help='Extra input directory the runner reads (rebuilt at the same absolute path)')
    run.add_argument('--label', default='', help='Suffix for the run ID')
    # The disk sampler runs at most min(chains, 4) nutpie threads; more cores do not help one fit.
    run.add_argument('--cpu', type=float, default=4.0)
    run.add_argument('--memory', type=int, default=16384, help='MiB')
    run.add_argument('--timeout', type=int, default=6*3600, help='Seconds (Modal maximum 86400)')
    run.add_argument('--ephemeral-disk', type=int, default=None,
                     help='MiB of scratch disk; Modal accepts 524288-3145728, omitted uses its default')
    run.add_argument('--gpu', help='Modal GPU type, e.g. A100-80GB or H100; implies --jax')
    run.add_argument('--jax', action='store_true', help='Add the pinned JAX/NumPyro/BlackJAX layer')
    run.add_argument('--add-code', action='append', default=[],
                     help='File in this checkout to add under the same path in --code-root')
    run.add_argument('--returned', nargs='+', default=list(sync.RETURNED),
                     help='Top-level output names to persist and download')
    run.add_argument('--keep-auxiliary', action='store_true',
                     help='Also persist and download raw trace and report cache')
    run.add_argument('--detach', action='store_true', help='Submit and return; fetch later')
    run.add_argument('runner_args', nargs=argparse.REMAINDER, help='Arguments after -- go to the runner')
    fetch = commands.add_parser('fetch', help='Download a finished run (resumes partial downloads)')
    fetch.add_argument('--run-id', required=True)
    fetch.add_argument('--output', type=Path, required=True)
    fetch.add_argument('--include-auxiliary', action='store_true')
    remove = commands.add_parser('clean', help='Delete remote copies; local results are untouched')
    remove.add_argument('--run-id')
    remove.add_argument('--unreferenced-blobs', action='store_true')
    commands.add_parser('list', help='Show remote runs and whether they finished')
    return parser


def main(argv=None):
    args = argument_parser().parse_args(argv)
    if args.command == 'run':
        submit(args)
    elif args.command == 'fetch':
        fetch_run(volume(), args.run_id, args.output, include_auxiliary=args.include_auxiliary)
    elif args.command == 'clean':
        clean(args)
    else:
        listing(args)


if __name__ == '__main__':
    main(sys.argv[1:])

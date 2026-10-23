"""Held-out scores of a downloaded baseline run, from score.py in a Modal CPU container.

    /data1/apartments/venvs/modal/bin/python modal_score.py RUN MODULE OUT.npz -- FIT ARGS...

FIT ARGS are the run's ops/modal-fit arguments: I rebuild its spec with ops/modal/fit.py, sync
its inputs and code to the Volume, upload the run's posterior, and run
docs/notes/conference-followups-2026-10-22/score.py at the run's commit with 64 GiB of memory,
since the kitchen sink's design doesn't fit in thelio's.
"""

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import modal

RUNS = "/data1/apartments/frontier/runs/"
# KS_SCRIPT runs that script in place of score.py, with the same arguments.
SCRIPT = os.environ.get("KS_SCRIPT", "")
OUTNAME = "shares.json" if SCRIPT else "scores.npz"
WORK = "/work/apartments"

if modal.is_local():
    run, module, out = sys.argv[1:4]
    fit_args = sys.argv[sys.argv.index("--") + 1 :]
    os.chdir(
        "/home/ben/code/apartments/.claude/worktrees/bridge-cse_01AQsHUSjwomLWnZjxnozD1d"
    )
    sys.path.insert(0, "ops/modal")
    import fit as F

    args, rest = F.parse(fit_args)
    spec = F.plan(args, rest, args.commit)
    stage = F.stage_code(args.commit)
    os.environ["MODAL_FIT_STAGE"] = str(stage)
    import app as A

    image, volume = A.image, A.volume
else:
    image = modal.Image.debian_slim()
    volume = modal.Volume.from_name("apartments-modal-fits")

app = modal.App("apartments-ks-score", image=image)


@app.function(cpu=8, memory=65536, timeout=3600, volumes={"/vol": volume})
def score(spec, run, module, split, dataset, script=False, outname="scores.npz"):
    started = time.time()
    volume.reload()
    for path in spec["inputs"]:
        src, dst = Path("/vol/inputs") / path.lstrip("/"), Path(path)
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.is_dir():
            shutil.copytree(src, dst, dirs_exist_ok=True)
        else:
            shutil.copy2(src, dst)
    shutil.copytree(f"/vol/code/{spec['commit']}", WORK)
    Path(RUNS, run).mkdir(parents=True, exist_ok=True)
    shutil.copy2(f"/vol/score/{run}/posterior.npz", f"{RUNS}{run}/posterior.npz")
    env = dict(
        os.environ,
        PYTHONPATH=f"{WORK}/frontier/src",
        FRONTIER_DATASET=dataset,
        JAX_PLATFORMS="cpu",
        PYTHONUNBUFFERED="1",
    )
    out = f"/vol/score/{run}/{outname}"
    p = subprocess.run(
        [
            "/venv/bin/python",
            f"/vol/score/{run}/script.py"
            if script
            else f"{WORK}/docs/notes/conference-followups-2026-10-22/score.py",
            module,
            run,
            out,
            split,
            dataset,
        ],
        env=env,
        cwd=WORK,
        capture_output=True,
        text=True,
    )
    volume.commit()
    return {
        "exit": p.returncode,
        "tail": (p.stdout + p.stderr)[-3000:],
        "seconds": round(time.time() - started),
    }


def _main():
    with modal.enable_output(), app.run():
        F.sync(volume, spec, stage)
        with volume.batch_upload(force=True) as b:
            b.put_file(f"{RUNS}{run}/posterior.npz", f"/score/{run}/posterior.npz")
            if SCRIPT:
                b.put_file(SCRIPT, f"/score/{run}/script.py")
        meta = score.remote(
            spec, run, module, args.split, spec["dataset"], bool(SCRIPT), OUTNAME
        )
        print(meta, flush=True)
        if meta["exit"] == 0:
            with open(out, "wb") as f:
                for chunk in volume.read_file(f"/score/{run}/{OUTNAME}"):
                    f.write(chunk)
            print("wrote", out, flush=True)


USD_PER_SECOND = 8 * 0.0000131 + 64 * 0.00000222  # app.py's core and GiB prices

if __name__ == "__main__":
    import cap

    # Charged for the container's whole timeout, then settled at the time it ran.
    launch, left = cap.reserve(
        f"{run}-{OUTNAME.split('.')[0]}",
        "cpu",
        round(3600 * USD_PER_SECOND, 2),
        secs=3600,
    )
    print(f"Modal balance now ${left:.2f}", flush=True)
    t0 = time.time()
    try:
        _main()
    finally:
        cap.settle(launch, round((time.time() - t0) * USD_PER_SECOND, 2))

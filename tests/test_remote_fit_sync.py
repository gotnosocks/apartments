import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from models import remote_fit_sync as sync

RUNNER = """
import argparse, hashlib, json, pathlib
p = argparse.ArgumentParser(); p.add_argument('--dataset'); p.add_argument('--output'); p.add_argument('--draws')
a = p.parse_args(); out = pathlib.Path(a.output)/'fit'; out.mkdir(parents=True)
text = (pathlib.Path(a.dataset)/'observations.jsonl').read_text() + a.draws
(out/'posterior.nc').write_text(text)
(out/'complete.json').write_text(json.dumps({'files': {'posterior.nc': hashlib.sha256(text.encode()).hexdigest()}}))
(pathlib.Path(a.output)/'trace').mkdir(); (pathlib.Path(a.output)/'trace/raw').write_text('big')
"""


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / "repo"
    (root / "models").mkdir(parents=True)
    (root / "models/fake_runner.py").write_text(RUNNER)
    (root / "pyproject.toml").write_text('[project]\nname="x"\n')
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "x"],
        cwd=root,
        check=True,
    )
    dataset = tmp_path / "data/set"
    dataset.mkdir(parents=True)
    (dataset / "observations.jsonl").write_text('{"rent": 1}\n')
    return root, dataset


def upload(request, sources, blobs):
    blobs.mkdir(parents=True, exist_ok=True)
    missing = sync.missing_blobs(request, {p.name for p in blobs.iterdir()})
    for sha in missing:
        (blobs / sha).write_bytes(sources[sha].read_bytes())
    return missing


def test_roundtrip_uploads_only_changes_and_verifies_download(repo, tmp_path):
    root, dataset = repo
    blobs, fs = tmp_path / "volume/blobs", tmp_path / "worker-fs"
    request, sources = sync.build_request(
        repo=root,
        dataset=dataset,
        runner="models.fake_runner",
        runner_args=["--draws", "5"],
        run_id="one",
    )
    assert len(upload(request, sources, blobs)) == len(request["files"])
    run_root, scratch = tmp_path / "volume/runs/one", tmp_path / "scratch"
    scratch.mkdir()
    result = sync.execute(
        request, blob_root=blobs, run_root=run_root, scratch=scratch, filesystem_root=fs
    )
    assert (
        result["succeeded"]
        and (fs / str(dataset).lstrip("/") / "observations.jsonl").is_file()
    )
    assert {f["path"] for f in result["files"]} == {
        "fit/posterior.nc",
        "fit/complete.json",
    }

    local = tmp_path / "local/fit-one"
    stats = sync.download(
        result, lambda p: sync.file_chunks(run_root / "output" / p), local
    )
    assert (
        stats["files"] == 2
        and (local / "fit/posterior.nc").read_text() == '{"rent": 1}\n5'
    )
    assert not local.with_name("fit-one.partial").exists()
    with pytest.raises(ValueError, match="never overwrite"):
        sync.download(
            result, lambda p: sync.file_chunks(run_root / "output" / p), local
        )

    (dataset / "observations.jsonl").write_text('{"rent": 2}\n')
    request2, sources2 = sync.build_request(
        repo=root,
        dataset=dataset,
        runner="models.fake_runner",
        runner_args=["--draws", "5"],
        run_id="two",
    )
    missing = upload(request2, sources2, blobs)
    assert list(missing.values()) == [len('{"rent": 2}\n')]


def test_download_rejects_corruption_and_resumes(repo, tmp_path):
    root, dataset = repo
    blobs = tmp_path / "blobs"
    request, sources = sync.build_request(
        repo=root,
        dataset=dataset,
        runner="models.fake_runner",
        runner_args=["--draws", "1"],
        run_id="r",
    )
    upload(request, sources, blobs)
    run_root, scratch = tmp_path / "runs/r", tmp_path / "scratch"
    scratch.mkdir()
    result = sync.execute(
        request,
        blob_root=blobs,
        run_root=run_root,
        scratch=scratch,
        filesystem_root=tmp_path / "fs",
    )
    local = tmp_path / "out"
    with pytest.raises(ValueError, match="differ from worker inventory"):
        sync.download(result, lambda p: iter([b"tampered"]), local)
    assert not local.exists()
    sync.download(result, lambda p: sync.file_chunks(run_root / "output" / p), local)
    assert (
        json.loads((local / "fit/complete.json").read_text())["files"]["posterior.nc"]
        == hashlib.sha256((local / "fit/posterior.nc").read_bytes()).hexdigest()
    )


def test_materialize_refuses_corrupt_blob_and_rejects_wrapper_arguments(repo, tmp_path):
    root, dataset = repo
    request, sources = sync.build_request(
        repo=root,
        dataset=dataset,
        runner="models.fake_runner",
        runner_args=[],
        run_id="r",
    )
    blobs = tmp_path / "blobs"
    upload(request, sources, blobs)
    victim = next(p for p in blobs.iterdir())
    victim.write_bytes(victim.read_bytes() + b"x")
    with pytest.raises(ValueError, match="integrity"):
        sync.materialize(request, blobs, tmp_path / "fs")
    with pytest.raises(ValueError, match="supplies --dataset"):
        sync.build_request(
            repo=root,
            dataset=dataset,
            runner="models.fake_runner",
            runner_args=["--output", "x"],
            run_id="r",
        )


def test_summary_download_leaves_posterior_remote_until_completed(repo, tmp_path):
    root, dataset = repo
    blobs = tmp_path / "blobs"
    request, sources = sync.build_request(
        repo=root,
        dataset=dataset,
        runner="models.fake_runner",
        runner_args=["--draws", "3"],
        run_id="r",
    )
    upload(request, sources, blobs)
    run_root, scratch = tmp_path / "runs/r", tmp_path / "scratch"
    scratch.mkdir()
    result = sync.execute(
        request,
        blob_root=blobs,
        run_root=run_root,
        scratch=scratch,
        filesystem_root=tmp_path / "fs",
    )
    read = lambda p: sync.file_chunks(run_root / "output" / p)
    local = tmp_path / "summary"
    stats = sync.download(result, read, local, omit=("fit/posterior.nc",))
    assert stats["omitted_files"] == 1 and not (local / "fit/posterior.nc").exists()
    assert (
        json.loads((local / sync.OMITTED_MARKER).read_text())["files"][0]["path"]
        == "fit/posterior.nc"
    )
    sync.complete(local, read)
    assert (local / "fit/posterior.nc").read_text() == '{"rent": 1}\n3'
    assert not (local / sync.OMITTED_MARKER).exists()


def test_clean_refuses_to_drop_draws_that_exist_only_remotely():
    result = {
        "succeeded": True,
        "files": [{"path": "fit/posterior.nc"}, {"path": "fit/summary.json"}],
    }
    assert "result.json" in sync.clean_refusal(None, [])
    assert "no local download" in sync.clean_refusal(result, [])
    assert "complete" in sync.clean_refusal(result, [{"complete": False}])
    assert sync.clean_refusal(result, [{"complete": False}, {"complete": True}]) is None
    assert sync.clean_refusal({"succeeded": False, "files": []}, []) is None

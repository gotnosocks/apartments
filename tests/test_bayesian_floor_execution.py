import copy
import hashlib
import json
from types import SimpleNamespace
import pytest
from apartments.corrections import canonical
from models import bayesian_disk_protocol as protocol
from models import bayesian_floor_execution as execution


def products(options):
    p = {
        "execution_version": protocol.VERSION,
        "storage_policy": protocol.POLICY,
        "storage_versions": dict.fromkeys(("zarr", "obstore", "xarray", "h5py"), "1"),
        "implementation_sha256": dict.fromkeys(protocol.CODE, "a" * 64),
        "chains": 4,
        "draws": 6000,
        "tune": 4000,
        "seed": 3,
        "adaptation": "diag",
        "target_accept": 0.93,
        **options,
    }
    identity = {
        "version": protocol.POLICY["version"],
        "protocol_sha256": hashlib.sha256(canonical(p).encode()).hexdigest(),
        **{
            k: p[k]
            for k in ("chains", "draws", "tune", "seed", "adaptation", "target_accept")
        },
        "contract": {"chains": 4, "draws": 6000, "variables": {"beta": ["feature"]}},
        **options,
    }
    trace = {"identity": identity, "files": {"zarr.json": "a" * 64}}
    storage = {
        "version": protocol.POLICY["version"],
        "posterior_sha256": "b" * 64,
        "trace_manifest_sha256": hashlib.sha256(
            (canonical(trace) + "\n").encode()
        ).hexdigest(),
        "chains": 4,
        "draws": 6000,
        "warmup_exported": False,
        "raw_event_statistics_preserved": True,
        "block_budget_bytes": protocol.POLICY["export_max_array_block_bytes"],
        "maximum_array_block_bytes": 1024,
        "posterior_variables": ["beta"],
        **options,
    }
    return p, storage, trace


@pytest.mark.parametrize("depth", [None, 12, 14])
def test_depth_is_optional_and_bound_to_both_products(depth):
    options = {} if depth is None else {"maxdepth": depth}
    p, s, t = products(options)
    assert execution.verify_products(p, s, t, "b" * 64)
    for target in ("storage", "identity"):
        ss, tt = copy.deepcopy(s), copy.deepcopy(t)
        node = ss if target == "storage" else tt["identity"]
        if depth is None:
            node["maxdepth"] = 10
        else:
            node.pop("maxdepth")
        ss["trace_manifest_sha256"] = hashlib.sha256(
            (canonical(tt) + "\n").encode()
        ).hexdigest()
        with pytest.raises(ValueError):
            execution.verify_products(p, ss, tt, "b" * 64)


@pytest.mark.parametrize("depth", [True, False, 0, -1, 21, 12.0, "12", None])
def test_invalid_explicit_depth_rejected(depth):
    p, _, _ = products({"maxdepth": depth})
    with pytest.raises(ValueError):
        execution.verify_protocol(p)


def test_graph_identity_and_manifest_tampering_rejected():
    graph = {"version": execution.graph.VERSION, "parity_manifest_sha256": "c" * 64}
    p, s, t = products({"execution_graph": graph, "maxdepth": 12})
    assert execution.verify_products(p, s, t, "b" * 64)
    s["execution_graph"] = {**graph, "parity_manifest_sha256": "d" * 64}
    with pytest.raises(ValueError):
        execution.verify_products(p, s, t, "b" * 64)
    p["execution_graph"] = {"version": "invented", "parity_manifest_sha256": "c" * 64}
    with pytest.raises(ValueError):
        execution.verify_protocol(p)


def test_runner_arguments_leave_legacy_settings_absent():
    import argparse

    parser = argparse.ArgumentParser()
    execution.add_arguments(parser)
    assert vars(parser.parse_args([])) == {
        "maxdepth": None,
        "floor_block_graph_validation": None,
    }
    assert parser.parse_args(["--maxdepth", "14"]).maxdepth == 14


@pytest.mark.parametrize("depth", [None, 14])
def test_sampler_forwards_explicit_depth_and_records_intent(
    tmp_path, monkeypatch, depth
):
    import nutpie
    from models import bayesian_disk_sampling as sampler

    model = SimpleNamespace(
        free_RVs=[SimpleNamespace(name="a")],
        deterministics=[],
        named_vars_to_dims={},
        coords={},
    )
    captured = {}
    monkeypatch.setattr(nutpie, "compile_pymc_model", lambda *a, **k: object())

    def stop(*args, **kwargs):
        captured.update(kwargs)
        raise RuntimeError("stop after capturing real sampler arguments")

    monkeypatch.setattr(nutpie, "sample", stop)
    with pytest.raises(RuntimeError, match="stop after"):
        sampler.sample_to_netcdf(
            model,
            output=tmp_path / "posterior.nc",
            trace_root=tmp_path / "trace",
            protocol_hash="a" * 64,
            draws=6000,
            tune=4000,
            chains=4,
            seed=3,
            adaptation="diag",
            target_accept=0.93,
            status_path=tmp_path / "status.json",
            maxdepth=depth,
        )
    intent = json.loads((tmp_path / "trace/intent.json").read_text())
    if depth is None:
        assert "maxdepth" not in captured and "maxdepth" not in intent
    else:
        assert captured["maxdepth"] == intent["maxdepth"] == depth


def frozen_proof():
    from models import bayesian_disk_experiment as runner
    from models import bayesian_feature_experiment_v4 as floor
    from apartments.research_pipeline import digest

    code = {p.name: digest(p) for p in runner.implementation_paths(floor)}
    fields = {
        "source_manifest_sha256": "a" * 64,
        "source_observations_sha256": "b" * 64,
        "specification": "full_half_balance",
        "floor_increment_prior_scale": 0.15,
        "floor_levels": [1, 2, 3],
        "graph_configuration": {},
        "rows": 100,
    }
    p = {"implementation_sha256": code, **fields}
    required = {
        path.name
        for path in floor.previous.implementation_paths()
        if "experiment" not in path.name and path.name != "bayesian_sampling.py"
    } | {
        "bayesian_floor_increment_design.py",
        "bayesian_floor_block_graph.py",
        "verify_floor_block_graph.py",
    }
    proof = {
        **fields,
        "implementation_sha256": {k: code[k] for k in required},
        "version": execution.PARITY_VERSION,
        "passed": True,
        "mode": "NUMBA",
        "fresh_design_matches_saved": True,
    }
    payload = canonical(proof) + "\n"
    manifest = {
        "version": execution.PARITY_VERSION,
        "files": {"parity.json": hashlib.sha256(payload.encode()).hexdigest()},
    }
    raw = canonical(manifest) + "\n"
    sha = hashlib.sha256(raw.encode()).hexdigest()
    p["execution_graph"] = {
        "version": execution.graph.VERSION,
        "parity_manifest_sha256": sha,
    }
    p["graph_verification"] = {
        "manifest_sha256": sha,
        "version": execution.PARITY_VERSION,
        "rows": 100,
    }
    return p, {
        "floor-block-parity.json": payload,
        "floor-block-parity-manifest.json": raw,
    }


def test_archived_proof_binds_exact_original_manifest_and_math():
    p, files = frozen_proof()
    assert execution.verify_archived_proof(p, files)
    files["floor-block-parity.json"] += " "
    with pytest.raises(ValueError):
        execution.verify_archived_proof(p, files)


@pytest.mark.parametrize(
    "damage", ["source", "rows", "prior", "code", "interaction", "not_passed"]
)
def test_proof_semantics_rejected_even_if_container_is_valid(damage):
    p, files = frozen_proof()
    proof = json.loads(files["floor-block-parity.json"])
    manifest = json.loads(files["floor-block-parity-manifest.json"])
    if damage == "source":
        proof["source_observations_sha256"] = "0" * 64
    if damage == "rows":
        proof["rows"] = 99
    if damage == "prior":
        proof["floor_increment_prior_scale"] = 0.25
    if damage == "code":
        proof["implementation_sha256"]["bayesian_floor_block_graph.py"] = "0" * 64
    if damage == "interaction":
        proof["interaction_mode"] = "pooled"
    if damage == "not_passed":
        proof["passed"] = False
    with pytest.raises(ValueError):
        execution.validate_graph_proof(p, proof, manifest)

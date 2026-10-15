import os

# SQLMesh forks workers to load models. In a test process with DuckDB connections open from
# earlier tests, a fork can deadlock, so the tests load models in the main process.
os.environ["MAX_FORK_WORKERS"] = "1"

# Coding standards

Approved by Ben on 2026-10-22. Rules 1 and 2 are enforced by tests and rule 3 by the exclude
list in `ruff.toml`; the rest are checked in review. Nothing here asks for a change that alters how code behaves.

1. **Format with `ops/fmt`** before every commit (Ben, 2026-10-06). `tests/test_formatting.py`
   fails on anything unformatted.
2. **Lint with `ops/lint`.** It runs the pinned ruff with the rules in `ruff.toml`: pyflakes
   (`F`), syntax errors (`E9`), import order (`I`), mutable default arguments (`B006`),
   `raise ... from` inside `except` (`B904`) and `datetime.UTC` (`UP017`). They catch mistakes,
   not style. `tests/test_lint.py` runs `ops/lint --changed`, which checks only the tracked
   files a branch changes since its merge base with `origin/master`, so older code that
   predates the rules doesn't fail an unrelated branch (run `git fetch origin master` first if
   your `origin/master` is stale). `ops/lint --fix --changed`, or `--fix` with paths, applies
   ruff's safe fixes; a repo-wide `--fix` is refused because re-sorting imports can touch files
   a running fit hashes. The backlog in older files is cleaned up in small PRs, and the test
   moves to the whole repo once it is zero.
3. **Never edit a hash-locked file.** Saved fits and datasets record the SHA-256 of the code
   that made them. The list in `ruff.toml`'s `extend-exclude` is the source of truth; both
   `ops/fmt` and `ops/lint` skip those files.
4. **Every module starts with a docstring** that says what it does and why, in plain language.
   Comments explain why, not what. A rule that came from a decision carries its source, as in
   "(Ben, 2026-10-14)".
5. **No stale comments.** A comment that names a run, PR, file or number that has since changed
   is updated in the same PR that changes it.
6. **One-off analysis scripts live in `docs/notes/<topic>-<date>/`.** They are a record, not
   library code, so lint skips them, and `src/`, `models/`, `frontier/` and `ops/` never import
   them.
7. **Library code** uses type hints on public functions, `pathlib.Path` for paths,
   `subprocess.run(..., check=True)` unless the exit code is handled, and no bare `except:`.
8. **Every change to `src/`, `frontier/`, `ops/` or the site comes with a test**, or a line in
   the PR saying why none is needed.
9. **One unit of work per PR**, reviewed by a separate reviewer, squash-merged after an
   annotated `archive/pr-N` tag on the branch head. Delete the branch on GitHub after the merge
   (Ben, 2026-10-22); the tag keeps its commits.
10. **Docs follow the code.** A PR that changes behavior described in `README.md`, `CLAUDE.md`
    or `docs/` updates that text too.

## Branches and worktrees

A nightly maintenance pass (the "Repo maintenance" project thread) removes only what can't
lose work:

- a GitHub branch only when its tip is exactly an `archive/*` tag and no open PR uses it. Each
  deletion is recorded with its commit in `/data1/apartments/tmp/maintenance/` on thelio, and
  `git push origin <sha>:refs/heads/<name>` restores it;
- a worktree on thelio only when it has no changes or untracked files, no process, unit or
  venv uses it, and its commit is in master or on an archive tag. `/data1/apartments/serve/*`
  and the main checkout are never touched.

Branches with unmerged work are left alone.

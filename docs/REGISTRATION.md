# Fleet registration — DONE (kept as the record of how and why)

*Status as of 2026-08-29 (kickoff session): **all registration is complete.** The
`video_gen` group membership landed (the manifest lists `t/paces`), the package was
scaffolded (`pyproject.toml` + wads CI), `priv pkg add-package` ran with it, and the PyPI
name was claimed by an actual publish (paces 0.0.1). The interpreter breakage described at
the bottom turned out to be scoped: the pyenv fallback outside `$HOME` is broken, but the
`p12` env resolves fine from under the projects tree — run ecosystem commands from there.
The sections below are kept as the reasoning of record.*

## Do now — one command

```bash
priv group add video_gen $PP/t/paces
```

That is the whole registration for a docs-only package. It edits the **SSOT**
(`$PP/t/priv/data/groups/video_gen/manifest.json`, git-tracked in `thorwhalen/priv`) and
regenerates the workspace from it.

Then commit the SSOT change in the `priv` repo — it is tracked, so leaving it dirty is drift:

```bash
cd $PP/t/priv && git status --short data/groups/video_gen/manifest.json
```

### Do NOT hand-edit the workspace file

`$PP/vs_workspaces/video_gen.code-workspace` is a **symlink** to
`$PP/t/priv/data/groups/video_gen/video_gen.code-workspace`, which is **generated** by
`_generate_code_workspace()` (`priv/group.py:381`) from the manifest, and is gitignored
(`t/priv/.gitignore:128`). Any hand-edit is destroyed by the next
`priv group materialize video_gen` — the same failure mode `CLAUDE.md` warns about for
`my_packages.pth`.

## Do NOT do yet — `priv pkg add-package`

Deliberately deferred until there is a `pyproject.toml`. It does **not** fail on a docs-only
directory (it warns and skips the editable install), but it costs more than it buys today:

- it appends to `packages.pth.in` and so creates **a standing `priv align` warning** —
  `in manifest, NOT installed: paces` — on every run, until a `pyproject.toml` exists and the
  package is pip-installed. Drift noise in the tool whose job is detecting drift.
- it regenerates the **global** pip constraints file, and `infer_distribution_name()` falls back
  to the directory name, writing `paces @ file:///…/t/paces` — a pin pointing at something pip
  cannot install. Inert in practice (nothing requests `paces`), but wrong.
- there is no dry-run.

**Run it in the same session as the first `pyproject.toml`**, when it will also do the editable
install and write a real pin. It is reversible either way (`priv pkg remove-package paces`).

Nothing imports `paces` yet, so nothing is lost by waiting.

## Also outstanding (optional, and not about `paces`)

`$PP/tt/reelee/docs/video_gen_manifest.json` is a **hand-maintained copy** of the group manifest
and is **6 packages stale** — missing `acture`, `zodal`, `reelee-web`, `burns`, `walkthru`,
`illustration`, `braidio`, and still carrying `t/wrapex`, which the SSOT dropped. Its only
consumer is `resolve_reelee_web_root()` (`reelee/storybook_planner.py:190`), a third-tier
fallback, so the staleness is currently harmless — but regenerating it from the SSOT would fix
that fallback and make the file true again. Worth doing while you are in there; it is a `reelee`
change, not a `paces` one.

## When there is code

From the fleet survey — every member is its own `thorwhalen/*` repo on `main` with a `ci.yml`.
`t/scribed` (9 commits) is the most recent worked example; `git log --reverse` it to see the
initial-commit shape. Creating a GitHub remote is outward-facing — get consent first.

## Why this is pending

The interpreter hosting `priv`
(`~/.pyenv/versions/3.12.12/envs/p12/bin/python`, symlinked from
`~/.pyenv/versions/3.12.12/bin/python`) began failing mid-session: it exits 0 but produces no
output and cannot write files, and the pyenv shim reports
`pyenv-exec: … /Users/thorwhalen/.pyenv/versions/p12/bin/python: Undefined error: 0`.
`/usr/bin/python3` was unaffected, and the disk had 650 GB free, so it is not disk pressure.
On macOS that error usually points at a code-signing / quarantine / dyld problem with the
interpreter binary.

**Check that the interpreter works before running the command above** — if `priv` still cannot
start, fix the environment first rather than working around it by hand-editing generated files.

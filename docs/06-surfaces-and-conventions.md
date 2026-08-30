# 06 — Surfaces & conventions: how this user builds a Python library and exposes it

**What this file is for.** You are about to build a new Python library (working name
`stepped`) that turns instructional video + docs into an "AST" of steps and renders guides
from it. This user has a strongly-opinionated, already-written house style for *how a
library gets built and exposed* — a turn-1 seam table, a single-registry core, and five
surfaces in a fixed default order (CLI → MCP → agent skills → HTTP → frontend). Following it
is not optional; it is what code review will check. This file distils the governing skills
(`architecture-first`, `python-dispatching`, `python-project-structure`, `python-storage`,
`python-iterables`, `app-data-lifecycle`, `skill-package-setup`/`skill-enable`,
`tw-frontend-ux`, `tw-deploy`) and pins each surface to a **real, verified, in-house worked
example** you can copy. Everything with a file path was read on 2026-08-28; everything I ran
is marked VERIFIED.

---

## 0. The one-page version

| Step | Do this | Authority / worked example |
|---|---|---|
| Turn 1 | Write the **seam table** (≤5 rows) + the `NOT seams:` line + the **one-command test**, before code | `~/.claude/skills/architecture-first/SKILL.md` |
| Core | `stepped/tools.py` — plain functions, JSON-able in, JSON-able dict out, **one list** `_dispatch_funcs` | `$PP/i/ir/ir/tools.py` |
| Surface 1 | **CLI** via `argh` in `stepped/__main__.py` over that same list | `$PP/tt/reelee/reelee/__main__.py` |
| Surface 2 | **MCP** via `py2mcp.mk_mcp_from_refs(['stepped.tools:verb', …])` | `py2mcp` README + `t/coact/coact/realize.py:650` |
| Surface 3 | **Shipped agent skills** in `stepped/data/skills/<name>/SKILL.md` | `i/enlace/enlace/data/skills/`, `t/yb/yb/data/skills/` |
| Surface 4 | **HTTP** via `qh.mk_app(routes, config=AppConfig(path_prefix="/api"))` | `$PP/tt/reelee/reelee/server.py:283` |
| Surface 5 | **Frontend** Vite+React+TS, `@zodal/*` collections + `acture` commands | `$PP/tt/reelee-web` |
| Data | Derived media in `media/` **next to the document** (ADR-0005 §1), addressed via the injected store seam; deploy-managed trees inject a non-doc root | `docs/adr/0005-media-derivation.md` |
| Deploy | `tw_platform/deploy.py`, app registered with an `app.toml` + an enlace `server.py` | `~/.claude/skills/tw-deploy/SKILL.md` → `twp-deploy` |

**Build ONE surface in v1.** Ask the other four's question ("would this surface need the core
to change?"), one line each, in the plan. Do not build them.

---

## 1. Turn 1 — the seam table (this governs the first commit)

Source: `~/.claude/skills/architecture-first/SKILL.md`. The load-bearing rules,
verbatim in spirit:

> Ship a working v1 fast, and make every later iteration an **ADD at a boundary that already
> exists.**

**A seam is one keyword argument.** ~1 line. If it needs a base class, a registry, a factory,
a plugin loader, a `plugins/` dir, or a config file — "you have already built version 2.
Delete it and pass an argument."

**A seam's default is never a placeholder.** It is "the best implementation that costs no new
dependency and no real complexity". `str.split` is a real splitter; a `dict` is a real store;
`lambda p: "ok"` is not an answerer. A `NotImplementedError` default fails the speed gate.

**The four tests that gate a seam:**

1. **Evidence, not naming.** Declare a seam only if you can *point at* the replacement — a
   package in `pyproject.toml` or `$PP/my_packages.pth`, an open issue, a line in the user's
   request, code already in this repo. No pointer → write the value directly plus a
   `# seam candidate: <what would change>` comment.
2. **Cost.** One keyword argument.
3. **Cap.** Zero is fine, five is a ceiling. Past seven → stop and ask.
4. **One implementation.** v1 ships exactly one component per seam.

**The `NOT seams:` line matters as much as the table** — it proves you budgeted rather than
generalized.

Template to emit before writing code:

```
| # | Seam (the boundary) | v1 default (no new dependency) | Replacement you can point at |
|---|---|---|---|
| 1 | where step media lands | stdlib `DirStore` at `<doc dir>/media/` (ADR-0005 §1) | dol.Files / s3dol.S3Store injected via `media_store=` |
| 2 | how the video is segmented | <the POC's method>            | <point at it or delete the row>  |

Surface for v1: CLI only (MCP/HTTP/frontend/skills: questions answered, not built)
NOT seams:      arg parsing, log format, the HTML template — written directly, on purpose
```

**The speed gate — this is the definition of v1.** Write the single command that runs the
whole path end to end on real input, with every seam on its default, *before* the seam table:

```
v1 done when: `python -m stepped parse <video-url> --doc aide.html && python -m stepped render out.html`
              produces a page you would actually use.
```

That command is also `tests/test_smoke.py`, and it must still pass after every later seam
swap. Budget: **one working session** from "let's build X" to the first commit. Blowing it
cuts *scope*, never seams. Report both (one-command test passes + the table exists) in the
message announcing v1.

**Where the table lives afterwards** (re-derived means rewritten): a GitHub Discussion if the
repo has a remote; the `## Seams & surfaces` field of a `session-handoff`; or 3 lines at the
top of `.claude/CLAUDE.md`.

**Before the first commit**, five checks: public names you'd be happy to see in someone
else's code; the next known change must not touch a *caller* (if it does, move the seam
now); delete dead seams; no placeholder defaults; delete anything not reachable from the
one-command test.

---

## 2. The core contract — `stepped/tools.py` is the SSOT

Every surface dispatches from **one list of plain functions**. This is the single most
important structural rule, and the ecosystem has both the reference and the cautionary tale.

### The reference: `ir/tools.py` (VERIFIED, quoted from the file)

`$PP/i/ir/ir/tools.py`:

```python
"""Agent-callable tool surface over ``ir`` — plain functions returning JSON-ready
dicts, deliberately MCP/HTTP-agnostic.

``ir`` knows nothing about MCP, HTTP, or any agent host. This module is the SSOT
for "expose ir's retrieval as a single agent-callable tool": a wrapper
(``py2mcp``, ``qh``, a hand-written agent tool) references e.g. ``ir.tools:search``
and gets a clean JSON ``dict`` back. The corpus is a **parameter**, so one
function serves every corpus with no per-corpus code …
"""
```

Note the shape of the signature — flat, serializable, keyword-only past the first arg:

```python
def search(query: str, *, corpus: Any, k: int = 8, mode: str = "hybrid",
           filter: dict | None = None) -> dict:
```

### The list, per `python-dispatching`

```python
# stepped/tools.py
"""Tools with CLI support."""


def parse(video: str, *, doc: str | None = None, prompt: str | None = None) -> dict: ...
def render(ast_path: str, *, renderer: str = "html") -> dict: ...


_dispatch_funcs = [parse, render]  # SSOT — every surface reads this

if __name__ == "__main__":
    import argh

    argh.dispatch_commands(_dispatch_funcs)
```

`reelee` does exactly this at scale: `tt/reelee/reelee/cli.py:941` is a 27-entry
`_dispatch_funcs = [init, import_screenplay, status, …]`, and its docstring states the rule —
*"The CLI dispatches over the **same reelee operations** the MCP server exposes — one source
of truth for 'what reelee can do', two front-ends."*

### The cautionary tale (VERIFIED — read the file, it is real)

`architecture-first` cites `reelee/server.py`. The receipt is
`$PP/tt/reelee/tests/test_http_mcp_parity.py` — **930 lines**,
opening docstring:

> `reelee/server.py` used to claim its HTTP closures and the MCP tools "stay aligned by
> construction". *By construction* was not a mechanism — no test, no shared registry, no
> codegen — and the claim was false for twelve handlers across eight capability families
> (reference locks, characters, supervision, model constraints, shot advice, gotchas, prompt
> assembly, intake). This module is the mechanism.

**The rule that falls out: if you need a parity test between two surfaces, you have two
implementations.** Do not author two lists.

`lookbook` (`$PP/t/lookbook/`) is the full single-module-per-surface
layout (`facade.py`, `registry.py`, `store.py`, thin `http.py`/`mcp.py`/`__main__.py`) and
states the rule as *"wire it once, expose it twice"* (`lookbook/mcp.py` docstring, VERIFIED).
**Its one flaw, confirmed by reading the source:** `lookbook/mcp.py` imports from
`lookbook.http`, which couples MCP to `qh`. Prefer `ir`'s string-ref variant where the core
imports neither.

---

## 3. Surface 1 — CLI (`argh`)

**What it is.** ~20 lines, no deployment, no auth, no client. Written *even for a library
nobody will call from a shell*, because it is the audit of the core and the way you run the
one-command test. Pressure it applies: arguments must be flat, ordered, serializable; no live
object crosses the boundary; nothing in the core may `print` or `sys.exit`.

**Minimal real example** — `$PP/tt/reelee/reelee/__main__.py`,
copied verbatim (VERIFIED, `argh` 'ok' + `argcomplete` importable in the `p12` env):

```python
# PYTHON_ARGCOMPLETE_OK
"""reelee CLI entry point — ``python -m reelee`` / ``reelee`` (after install)."""

from __future__ import annotations

import argh

from .cli import _dispatch_funcs


def main() -> None:
    """Build the argh parser over the reelee commands and dispatch."""
    parser = argh.ArghParser()
    parser.add_commands(_dispatch_funcs)
    try:
        import argcomplete

        argcomplete.autocomplete(parser)
    except ImportError:
        pass
    parser.dispatch()


if __name__ == "__main__":
    main()
```

`pyproject.toml`:

```toml
[project.scripts]
stepped = "stepped.__main__:main"
```

For namespaced sub-commands (`python -m stepped tools parse …`), `python-dispatching` gives
`dispatch_with_namespaces(functions, namespaced_funcs={"tools": tools_funcs})`.

**The one thing that most often goes wrong.** The `# PYTHON_ARGCOMPLETE_OK` marker must be in
the **first 1024 bytes** of `__main__.py` — before the docstring, as above — or global
argcomplete activation silently never sees your CLI and tab completion just doesn't work with
no error. (Second-most-common: putting the marker in but forgetting
`argcomplete.autocomplete(parser)` on a *custom* parser; `argh.dispatch_commands` calls it for
you, `ArghParser` + `parser.dispatch()` does not.)

**Dependency placement.** `reelee` puts `argh>=0.30` and `argcomplete>=3.0` in **core**
`dependencies` (verified, `tt/reelee/pyproject.toml:68-69`) — right for a CLI-first tool.
`architecture-first/references/surface-checks.md` says the opposite for a library with
dependents: surface deps belong in `[project.optional-dependencies]` and must be imported
*inside* the adapter. Decide which `stepped` is before merging.

---

## 4. Surface 2 — MCP (`py2mcp`)

**What it is.** Nearly free after the CLI, and it applies the strictest pressure of the five:
every operation needs a stable name, a typed schema, a side-effect class, and a description.
It kills "just pass a dict" and any function that does two things.

**Where it lives:** `$PP/t/py2mcp` (note: `t/`, not `i/`).
Installed version 0.1.9 resolves to the editable source tree (VERIFIED). Repo is
`i2mint/py2mcp`; only dependency is `fastmcp`.

**Public API** (`py2mcp/__init__.py`, VERIFIED):
`mk_mcp_server`, `mk_mcp_from_store`, `mk_mcp_from_refs`, `mk_input_trans`, `import_object`,
`serve_stdio`, `resolve_server_config`, `load_server_config`, `mk_http_app`, `serve_http`,
`mk_auth_provider`.

**`mk_mcp_from_refs` — the one to use** (real signature, `py2mcp/main.py:91`):

```python
def mk_mcp_from_refs(
    refs: Iterable[str],
    *,
    name: str = "py2mcp Server",
    input_trans: Optional[Callable[[dict], dict]] = None,
    auth: Optional[Any] = None,
    middleware: Optional[Any] = None,
    instructions: Optional[str] = None,
) -> FastMCP:
```

VERIFIED by running it:

```python
>>> from py2mcp import mk_mcp_from_refs
>>> mcp = mk_mcp_from_refs(['os.path:basename', 'os.path:dirname'], name='Paths')
>>> mcp.name
'Paths'          # <class 'fastmcp.server.server.FastMCP'>
```

So for `stepped`:

```python
# stepped/mcp.py  (≤40 lines; the core imports nothing MCP)
from py2mcp import mk_mcp_from_refs


def build_mcp_server(
    *, name: str = "stepped", instructions: str | None = None, middleware=None
):
    return mk_mcp_from_refs(
        ["stepped.tools:parse", "stepped.tools:render"],
        name=name,
        instructions=instructions,
        middleware=middleware,
    )
```

Other builders: `mk_mcp_server(funcs, …)` for callables; `mk_mcp_from_store(store, name='step')`
auto-generates `list_/get_/set_/delete_` CRUD tools from any `MutableMapping` — directly useful
if `stepped`'s AST/step store is a `MutableMapping`. `serve_stdio(refs, name=…)` runs a local
stdio server; `py2mcp.http.mk_http_app(refs, name=…, auth=AUTH)` returns an ASGI app for a
hosted OAuth 2.1 resource-server connector. `middleware=` is the metering/auth/audit seam
(FastMCP middleware) — attach once at construction so a paid tool can't be missed.

**The one thing that most often goes wrong.** Using **string refs** is what keeps the core
MCP-free; the moment `stepped/tools.py` (or `__init__.py`) imports `fastmcp` or `py2mcp`,
every downstream import pays for the MCP stack. `reelee` states this explicitly in
`reelee/mcp/__init__.py`: *"Both `build_mcp_server` and `build_http_app` import
`fastmcp`/`py2mcp` **lazily**, so importing `reelee.mcp` does not require them (the reelee core
is imported by other live apps that must stay MCP-stack-free)."* Verify with check B in §11.

**Flag / precedent worth knowing.** `reelee` does **not** use `py2mcp` for its own server —
`reelee/mcp/server.py:278 build_mcp_server` hand-rolls `FastMCP` because its tools are closures
over a bound project, and `reelee/mcp/http.py` only borrows `py2mcp.http.mk_auth_provider`.
If `stepped`'s operations need per-request bound state, expect the same divergence — but you
then owe a shared registry, not a second hand-authored list (see §2).

---

## 5. Surface 3 — shipped agent skills (this is "AI artifacts on top")

**What the user means by "AI artifacts" (INFERRED, but on strong evidence).** There is no
coined term "AI artifacts" anywhere in `~/.claude/skills` or the projects tree (I grepped —
zero hits in skills, four irrelevant hits in project docs). In this ecosystem the layer
between "Python backend" and "web services / MCPs" is consistently: **SKILL.md files shipped
with the package**, plus the agent-facing repo docs (`AGENTS.md`, `.claude/CLAUDE.md`) and the
model-facing prose attached to tools (`instructions=` on an MCP server, docstrings that
become tool descriptions). `architecture-first` lists exactly this as a surface: *"Agent skills
(shipped, `{pkg}/data/skills/`) — every operation must be describable in prose to a stranger.
Cannot write the trigger sentence → the operation has no name and the API is wrong."*
Confirm with the user, but build to this reading.

**The pattern is real and widespread.** 17 packages in `$PP` have a `{pkg}/data/skills/`
directory (VERIFIED by `find`): `t/scribed`, `t/dn`, `t/toolery`, `t/ge`, `t/creel`, `t/foley`,
`t/inkmap`, `t/ocracy`, `t/yp`, `t/yb`, `t/falaw`, `t/openloops`, `t/xa`, `i/enlace`, `i/wads`,
`i/pdfdol`, `i/vd`.

**Two different `.claude/` things — keep them apart** (`architecture-first`, `dev-skills-workflow`):

| | Dev skills | Shipped / end-user skills |
|---|---|---|
| Audience | the agent building *this* project | the package's `pip` / `gh skill` users |
| Real files | repo-root `skills/<name>/` | `{pkg}/data/skills/<name>/` |
| Naming | `stepped-dev-<topic>` | `stepped-<topic>` |
| Frontmatter | `metadata.audience: developers` | `metadata.audience: users` (or `both`) |
| Ships in the wheel | no | yes |

**Layout (`skill-package-setup` — the authority):**

```
stepped/
├── stepped/data/skills/stepped-quickstart/SKILL.md   ← real files, pip-shipped + gh-skill-discoverable
├── skills/stepped-dev-<topic>/SKILL.md               ← real files, dev-only, not shipped
└── .claude/skills/
    ├── stepped-quickstart -> ../../stepped/data/skills/stepped-quickstart
    └── stepped-dev-<topic> -> ../../skills/stepped-dev-<topic>
```

Rules that get enforced: **real files in exactly ONE non-hidden location** (both → `gh skill`
reports duplicates); `.claude/skills/<name>` is a **relative symlink per skill**, never a
symlink of the whole dir (Claude writes `.system/` files there); folder name == frontmatter
`name`, lowercase `[a-z0-9-]`; only spec top-level keys (`name`, `description`, `license`,
`compatibility`, `metadata`, `allowed-tools`) — **`audience` goes under `metadata:`**, a
top-level `audience:` fails `gh skill publish` validation; `allowed-tools` is a
space-separated *string*, not a YAML list; `description` ≤1024 chars; body <500 lines with
detail pushed to `references/`.

**Packaging.** With hatchling, `{pkg}/data/**` rides along implicitly —
`t/falaw/pyproject.toml` has only `[tool.hatch.build.targets.wheel] packages = ["falaw"]`
(VERIFIED). Explicit form if you want it: `include = ["stepped/data/*"]`. Setuptools:
`[tool.setuptools.package-data] stepped = ["data/skills/**/*"]`. Verify with
`python -m build --wheel && unzip -l dist/*.whl | grep -i skills`.

**The convenience helper + entry point** (from `i/enlace`, the only fleet package that wires
the entry point — VERIFIED, `i/enlace/enlace/__init__.py:68` and `i/enlace/pyproject.toml:52`):

```python
# stepped/__init__.py
def skills_dir() -> Path:
    """Return the path to this package's bundled skills directory."""
    return Path(__file__).parent / "data" / "skills"
```

```toml
[project.entry-points."skill.skill_packs"]
stepped = "stepped:skills_dir"
```

README install line:

```bash
skill link-skills "$(python -c 'from stepped import skills_dir; print(skills_dir())')"
# or, cross-agent + versioned:
gh skill install thorwhalen/stepped stepped-quickstart --agent claude-code
```

**The one thing that most often goes wrong.** The `.claude/skills/` symlink bridge gets
forgotten, so the skills exist and ship but Claude Code never sees them —
`t/yb` currently has `yb/data/skills/{music2video,yb-download,yb-podcast,yb-publish,yb-setup}`
and **no `.claude/skills/` directory at all** (VERIFIED). Second-most-common: a *new* skills
directory needs a **session restart** to be watched (edits inside an already-watched dir
hot-reload) — so verify a new skill is invocable in a **fresh** session before relying on it.

---

## 6. Surface 4 — HTTP (`qh`)

**What it is.** `$PP/i/qh` — "quick http", convention-over-
configuration FastAPI wrapper. Repo `i2mint/qh`. Deps: `fastapi>=0.100`, `uvicorn>=0.23`,
`requests`, `pydantic>=2`, `i2`. Pressure it applies: state must be explicit and per-request;
no module-level mutation, no implicit session; errors need codes. Only build it with a remote
consumer — and note remote MCP *is* HTTP, so if the only remote consumer is an agent you may
already be done.

**Minimal real example — VERIFIED, I ran this:**

```python
from qh import mk_app
from qh.testing import test_app


def add(x: int, y: int) -> int:
    """Add two numbers"""
    return x + y


app = mk_app([add])

with test_app(app) as c:
    r = c.post("/add", json={"x": 3, "y": 5})
    # → 200, 8
```

Run it: `uvicorn your_module:app`. Docs at `/docs`, enhanced OpenAPI at `/openapi.json`.

**Real signature** (`qh/app.py:25`):

```python
def mk_app(funcs, *, app=None, config=None, use_conventions=False,
           async_funcs=None, async_config=None, enhanced_openapi=True, **kwargs) -> FastAPI:
```

`funcs` may be a callable, a list, or a `{callable: RouteConfig|dict}` mapping.
`use_conventions=True` derives RESTful routes from names (`get_user(user_id)` →
`GET /users/{user_id}`). `async_funcs=[…]` adds `?async=true` + a `/tasks/{id}` surface —
**directly relevant to `stepped`**, whose parse phase is long-running:
`GET /tasks/{id}/result?wait=true&timeout=10`. Executors: `ThreadPoolTaskExecutor`,
`ProcessPoolTaskExecutor`, or a custom one via `TaskConfig(executor=…, ttl=…, async_mode='always')`.
Also ships `export_openapi`, `mk_client_from_app`, `export_ts_client` (a generated TS client
is a real option for the frontend instead of hand-written fetch wrappers).

**The in-house production example** —
`$PP/tt/reelee/reelee/server.py:283 build_http_app`. Its module
docstring states the convention: *"Per the saved feedback memory, this is a `qh`-driven app:
we point `qh.mk_app` at our closures and ship."* The shape (VERIFIED):

```python
try:
    from qh import mk_app
    from qh.config import AppConfig
except ImportError as e:
    raise ImportError("The reelee HTTP server needs `qh` — `pip install reelee[web]` …") from e

routes = _build_routes(project, agent=agent, url_fetcher=url_fetcher, identity_scorer=identity_scorer)
app_cfg = AppConfig(title=title, path_prefix="/api", default_methods=["POST"], …)
app = mk_app(routes, config=app_cfg)
```

Note the injectable collaborators as keyword args (`agent=`, `url_fetcher=`,
`identity_scorer=`) — seams, exactly as §1 describes, each documented with what a test injects
and why.

**The one thing that most often goes wrong.** `qh` is an **optional** dependency guarded by a
`try/except ImportError` with an install hint — and then the HTTP tests `importorskip("qh")`
and **silently pass while proving nothing**. `reelee` hit this and wrote the fix into its
pyproject (VERIFIED, `tt/reelee/pyproject.toml:108-112`):

```toml
dev = [
    # The HTTP-surface tests `importorskip("qh")`. Without these in *dev*
    # they skip silently and the suite still reads green — so every
    # endpoint test proves nothing. Mirrors the [web] extra deliberately.
    "qh", "fastapi", …
]
web = ["qh>=0.0.12", "fastapi>=0.110", "uvicorn>=0.27", "httpx>=0.27"]
```

**Stale/confusing in `qh` — flag.** `qh/pyproject.toml` says `version = "0.0.17"` while
`qh/__init__.py` sets `__version__ = "0.5.0"  # Phase 4: Async Task Processing`. The two
disagree; PyPI will show 0.0.x. Pin by feature, not by `__version__`. `qh/__init__.py` also
carries a legacy `py2http`-based import block wrapped in `try/except ImportError` — dead on a
clean install; don't build on `qh.main`/`qh.trans`/`qh.util`. `qh/stores_qh.py` exposes a
mall-of-stores over FastAPI (`GET /` list keys, `GET/PUT/DELETE /{item_key}`) — useful, but
see the media warning in §8: never serve video bytes through a `store[key] -> bytes` route.

---

## 7. Surface 5 — the frontend

**Stack (mandatory federation convention).** From
`$PP/tt/reelee-web/README.md` (VERIFIED) and its `package.json`:

- **Vite 8 + React 19 + TypeScript (strict)**, Tailwind v4 + shadcn/ui.
- **`@zodal/*` + `acture` for the architecture** — *"This is the federation's mandatory
  convention. Data + UI flow through `@zodal` collections derived from JSON Schema; every
  user-actionable behavior is an `acture` dispatch command."* (`acture` replaced
  `command-wrapex` in May 2026.)
- **Zustand + Immer** for store state (a `@zodal/ui` peer). **Zod v4** as the schema language.
- **Vitest + Testing Library**; Playwright for e2e.
- **Zod schemas are codegened from the Python Pydantic SSOT, never hand-written**
  (`schemas/` holds JSON Schema; `npm run codegen`).

**How a FE talks to the Python core.** `reelee-web` has **no backend code of its own**. Its
`server.py` is 5 lines of real work: resolve a project root, then
`app = build_http_app(project_root)` from the *standalone Python package*. Two build-time env
vars injected by the deploy: `VITE_PUBLIC_BASE="/reelee-web/"` and
`VITE_API_BASE="/api/reelee-web"`, the latter read by `getApiBase()` in
`src/store/providers.ts`; every call is `${VITE_API_BASE}/api/<endpoint>`. Local dev: Vite at
:5173 proxies `/api/*` to `127.0.0.1:8787`, backend run with `uvicorn server:app --reload --port 8787`.

**Media on the FE — the part that matters most for `stepped`.** A `<video src>` needs a
**URL**, not bytes. The zodal seam is `ContentRef` (`@zodal/core`,
`zodal/packages/core/src/types.ts:139`, VERIFIED):

```ts
export interface ContentRef {
  readonly _tag: 'ContentRef';
  field: string; itemId: string;
  hash?: string; url?: string; mimeType?: string; size?: number;
}
```

and the provider that resolves it, `@zodal/store-http` (`i/_zodals/zodal-store-http/README.md`,
VERIFIED) — *"`getUrl()` is the reason this package exists."*

```ts
const clips = createHttpBlobProvider({ baseUrl: '/api/stepped/clips', contentFields: ['clip'] });
const provider = createBifurcatedProvider({
  metadataProvider: createHttpProvider({ baseUrl: '/api/stepped/steps' }),
  contentProvider: clips, contentFields: ['clip'],
});
videoEl.src = (await provider.getUrl('block-03.mp4', 'clip'))!;
```

Moving the clips to S3 later changes **one factory call** (`createS3BlobProvider`), not the
component.

**`acture`** (`$PP/tt/acture`) is the command-dispatch layer:
define an operation once as a command and it becomes a palette entry, a hotkey, an AI tool
call, an MCP tool, a macro step, an e2e action, an undo entry, and a telemetry event.
`defineCommand({id, title, category, keybinding, when, params: z.object({…}), execute})`,
registered into a singleton registry; `dispatch(id, params, source)` is the canonical surface.
Important positioning: acture is **a development tool first** — "You can use acture without
adding a single `acture-*` dependency to your project"; the npm packages are an optional
accelerator, and `.claude/skills/` in that repo holds 26 agent skills that write the pattern
into your project. There is also a PyPI `acture` — a thin MCP-*client* facade
(`Mapping[str, Command]` over any `acture-mcp-server`); **it is not a Python command-dispatch
library**, so it is not the tool for `stepped`'s Python core.

**UX contract you will be reviewed against** — `~/.claude/skills/tw-frontend-ux/SKILL.md`,
principle 1: every state change gets *immediate* feedback well under ~400ms (Doherty), and
**never leave stale content on screen while new content loads**. Track load status against the
**new** identity (`key={src}` + `onLoad`/`onError` + a cached-`complete` ref), fade in, add
`aria-busy`, and label honestly (a generic load is a neutral skeleton, not "generating…").
Reference implementation: `reelee-web/src/ui/image-well.tsx`.

**The one thing that most often goes wrong.** Fetching blob bytes and `createObjectURL`-ing
them instead of resolving a URL — it defeats HTTP range requests, so seeking breaks, Safari
refuses to play, and the whole file sits in memory. For a library whose whole output is short
looping video clips, this is *the* failure mode.

---

## 8. Storage & data lifecycle — load-bearing for a media library

`~/.claude/skills/app-data-lifecycle/SKILL.md`. The one rule:

> An app directory contains **only** code + build output. Media → blob store. Runtime state →
> `~/.local/share/{project}/`. Confidential data → a provisioning step. Nothing server-only
> ever lives inside the deploy-managed tree. Then `rsync --delete` is always safe.

Four categories, each with a different source of truth: (1) code/build output — git+CI, the
deploy *should* mirror and `--delete`; (2) large/binary media; (3) confidential data;
(4) mutable runtime state — the deploy must never touch 2–4.

**Where `stepped`'s bytes go** (superseded for *derived media* by ADR-0005 §1: the
default is `media/` next to the user-owned document; the sketch below remains the rule
for the server-side clause — documents inside a deploy-managed tree):

```
~/.local/share/stepped/          # the project data ROOT, never written to directly
    videos/                      # one subfolder per KIND
    clips/
    frames/
    asts/
```

- **One env var overrides the root**: `STEPPED_DATA_DIR`. Never a per-kind env var.
- Resolve cross-platform with `config2py.AppData("stepped").app_folder()` — VERIFIED:
  `config2py.AppData('demo_proj_x').app_folder()` → `~/.local/share/demo_proj_x`.
- **Whose `~`?** It resolves against the home of the user the *server process* runs as, which
  is often not the SSH user. `systemctl show <unit> -p User` before assuming.

**Address it through a store, not a path.** `dol` gives `Mapping[str, bytes]` over local files;
`s3dol` over S3 — same interface, backend injected (VERIFIED: `from dol import Files` →
`dol.filesys.Files`, from `$PP/i/dol`):

```python
def clip_store(directory=None) -> Mapping[str, bytes]:
    """Local files today, S3 tomorrow — callers never know."""
    return Files(str(directory or config.clips_dir()))
    # return S3Store(bucket, prefix)   ← the entire migration, later
```

Business logic takes the store as an argument and never learns where the bytes live. This is
the seam that `architecture-first` says is already worked in full — do not re-derive it.

**Serving media (the traps that will bite a video library):**

- **Never compress a ranged response**, and never compress already-compressed bytes. A gzip
  middleware without a `206 Partial Content` exclusion produces headers that contradict each
  other; ranges are the entire basis of `<video>` streaming and seeking.
- **Test with a realistic range** (a 64KB one). A range below the compression threshold looks
  perfectly clean and hides the bug.
- **Serve media with something that does ranges properly** — `StaticFiles`, a real file
  server, or the blob store's own URL. Never a hand-rolled `store[key] -> bytes` endpoint.
- **Resolve the media base at runtime from the server**, not from a baked-in `VITE_*` var, so
  flipping to S3 is one server env var rather than a rebuild.
- **A data dir that can't be created must not raise at import**, or one app takes down the
  whole shared ASGI process. Guard the mkdir; construct static mounts with the existence check
  disabled. "No videos" degrades better than "no platform".

**Migrations are expand → migrate → contract**, never a flag day: (1) read new, fall back to
old, write new; (2) move bytes idempotently, non-destructively, verified, locally on the
machine holding them; (3) remove the fallback, *then* delete old copies. Finish with a census
(`find <deploy tree> -name '<the data>'` must return zero), not a spot-check — a green deploy
proves nothing.

**Related conventions from `python-storage`:** most storage is key-value; model it as
`Mapping`/`MutableMapping` from `collections.abc`. When a class manages several entity types,
don't build a god-class — build separate stores and group them in a **mall**
(`mall = {'asts': AstStore(...), 'clips': ClipStore(...)}`), optionally supporting
`mall['clips', key]`. `__getitem__` may be enriched (slices, key lists, callable filters,
query dicts). This pairs directly with `py2mcp.mk_mcp_from_store` (§4) and `qh/stores_qh.py`
(§6) — a `MutableMapping` gets an MCP surface and an HTTP surface for free.

---

## 9. Python coding conventions that get enforced in review

From `python-project-structure`, `python-iterables`, `python-storage` and the user's global
`CLAUDE.md`:

- **Keep it minimal by default.** Do NOT auto-create a multi-module package. Single module for
  small projects; a separate `test_{module}.py` once there are more than two tests; **pytest,
  never unittest**. The full package layout (`__init__.py` / `base.py` / `util.py` / `data/` /
  `misc/`) is for when a full package is explicitly asked for. Seams are parameters and
  function boundaries, **not files** — a single-module v1 can hold five seams.
- `__init__.py` **defines the public API**; `base.py` is foundational objects only, no business
  logic; `util.py` internal helpers prefixed `_` unless broadly reusable; `data/` accessed via
  `importlib.resources.files`; `misc/CHANGELOG.md` for major AI-made changes only.
- **Every module needs a top-level docstring** — they're auto-extracted for generated docs
  (`ruff` config in these repos literally selects `D100`; see any fleet `pyproject.toml`).
- **Yield, don't accumulate.** Return `Iterable[T]`/`Iterator[T]`, not `list[T]`, unless the
  caller genuinely needs indexing/mutation/`len`. For dicts, yield `(key, value)` pairs and let
  the consumer call `dict(...)`. This is a return type you cannot widen later, so get it right
  in v1.
- **Arguments beyond the 3rd are keyword-only**; consider keyword-only from the 2nd if it
  reads better. No hardcoded values or magic numbers — keyword-only args or external config.
- **Favor functional over OOP**; when OOP, SOLID, small classes, `collections.abc` interfaces
  and `dataclasses`. Exception: controllers/service classes, which use `functools.cached_property`
  for lazy loading and `lru_cache` / `dol.cache_this` for persisted data.
- **Helper placement:** used by ONE function → inner function; used within the SAME module →
  `_prefixed`; reusable across modules → no prefix.
- **System dependencies** (ffmpeg, opencv, a face-anonymiser — `stepped` will have several):
  mention in the README **and** guide users dynamically via a `check_requirements` function.
  The house pattern returns a report rather than installing:
  `t/foley/foley/requirements.py:94 check_requirements(*, names=None, verbose=False) -> dict[str, bool]`
  plus `verify_and_setup()` returning `{name: {'available','purpose','install','url','probe'}}`
  (VERIFIED). Other instances: `i/vd/vd/requirements.py:191`, `t/ke/ke/registry.py:193`,
  `t/aix/aix/credentials.py:352`. `coact` shows the call-site form:
  `check_requirements({"py2mcp": "py2mcp", "fastmcp": "fastmcp"}, feature="realize(backend='mcp')")`
  — note the signature differs per package; there is **no shared implementation**, pick one and
  copy it.
- **READMEs**: essential in a few lines, then paragraphs, then details; easy examples first.

**Ecosystem plugin pattern, if you need one:** `xdol.Registry` — a typed, dict-backed
`MutableMapping` plugin registry with `on_conflict` policy and `subscribe()`
(`$PP/i/xdol/xdol/registry.py:134`, VERIFIED). The video_gen
workspace overview names it "the ecosystem-wide plugin pattern". Note the tension with
`architecture-first` test 2 (a seam that grew a registry means you over-built) — a Registry is
justified when *third parties* register into it (as genres do in `nw`), not to make your own
two implementations swappable.

---

## 10. Packaging, repo scaffolding, CI

- **Build backend: hatchling.** `[tool.hatch.build.targets.wheel] packages = ["stepped"]`.
- **Dependencies un-versioned by default** (`"dol"`, not `"dol>=1.2"`) unless a constraint is
  genuinely needed — and when you do pin, `reelee`'s pyproject shows the house style: a
  multi-line comment above the pin explaining *which symbol* forced the floor and *how* it
  fails against an older version. Copy that discipline; it is why their pins survive.
- **Scaffolding:** `~/.claude/skills/setup-py-project/SKILL.md` drives `wads.project_setup`
  (`check_names` for PyPI+GitHub availability, `setup_project(...)`, `create_misc_docs`).
  Three documented pitfalls: `proj_rootdir` is the **full package path, not its parent**;
  `tomli_w` must be installed first or populate half-fails; populate needs a `.git/` with an
  `origin` remote or CI generation raises and later steps silently never run.
- **CI is a stub calling a reusable workflow** — `.github/workflows/ci.yml` is
  `uses: i2mint/wads/.github/workflows/uv-ci.yml@master` with `permissions: {contents: write, pages: write}`
  and **explicit** `secrets:` pass-through (not `secrets: inherit` — verified empirically not
  to propagate cross-account). All config lives in `pyproject.toml` under `[tool.wads.ci.*]`
  (see `t/py2mcp/pyproject.toml` for the full block: quality/ruff, testing python_versions,
  coverage, metrics, build, publish, docs builder `epythet`).
- **Merging = releasing.** On these repos a merge to the default branch is usually a PyPI
  upload or a live deploy. A shipped surface is **public API permanently** — a console-script
  name, an MCP tool name, a route path, a skill trigger phrase. That is the real argument for
  building only one surface in v1.

---

## 11. The three checks that prove the core is surface-agnostic

From `architecture-first/references/surface-checks.md`. Run these before merging any surface.

**A — static: no surface library imported below the adapter layer.**

```bash
pkg=stepped
rg -n --type py -g '!*test*' \
  '^\s*(import|from)\s+(argh|click|typer|fastapi|starlette|flask|uvicorn|mcp|fastmcp|qh|uf|gradio|streamlit)\b' \
  "$pkg" | rg -v '__main__\.py|/cli\.py|/tools\.py|/app\.py|/api\.py|/routes\.py|/server\.py|mcp'
# ANY line = a surface library imported below the adapter layer.
```

**B — runtime: importing the core must not drag a surface library into `sys.modules`.**

```bash
python -c "
import sys, importlib; importlib.import_module('stepped')
S = {'argh','click','typer','fastapi','starlette','uvicorn','flask','mcp','fastmcp','qh','uf','gradio','streamlit'}
bad = {m.split('.')[0] for m in sys.modules} & S
assert not bad, f'core import pulls in surface libs: {sorted(bad)}'
print('core is surface-agnostic')"
```

**C — the adapter budget, as a number.** CLI (`argh`) ≤25 lines; MCP server (`py2mcp` over
refs) ≤40 lines; one HTTP route (`qh`/FastAPI) ≤15 lines. Over budget means core logic
migrated into the adapter — move it back, don't refactor the adapter.

**When no adapter exists yet**, A and B pass vacuously — run the inverse: take any core
function and ask whether `argh` could dispatch it **as written** (flat serializable args, one
return value, no printing, no `sys.exit`, no `os.environ` read). Whatever blocks it *is* the
coupling.

**Surface parity of the storage seam:** a seam that is a `Mapping` in Python should be a store
on the JS side too (`ContentRef` / `@zodal/store`), never a REST endpoint invented at the
adapter.

---

## 12. Deployment (short pointer)

`~/.claude/skills/tw-deploy/SKILL.md` is itself a thin pointer to the project-scoped
**`twp-deploy`** skill in `~/Dropbox/py/proj/tt/tw_platform/.claude/skills/twp-deploy/`.
Facts you need up front:

- Production: Hetzner, SSH alias `tw`. Edge is Traefik 3.6 → `enlace-backend.service`
  (gunicorn+uvicorn) on `127.0.0.1:8010`.
- Deploy from the `tw_platform` repo:
  `python deploy.py cmd-deploy --dry-run`, then `--force` (**always `--force` from an agent
  shell** — no TTY means a config-change prompt aborts *before* the backend restart, which
  looks like a silent no-op). Don't pipe to `tail` (masks the exit code); verify with a curl
  that reflects the change.
- **An app reaches the platform as an enlace app**: an `app.toml` + a `server.py` exposing
  `app`. `reelee-web`'s pair is the model (VERIFIED, both read):
  `app.toml` declares `display_name`, `description`, `access = "protected:user"` +
  `allowed_users`, a `[build]` block (`env_vars`, `install = "npm ci"`, `build = "npm run build"`),
  and `[python.requires] reelee = ["agent", "web"]` — which makes `deploy.py` run
  `pip install -e <editable-path>[agent,web]`. `server.py` does nothing but resolve state and
  call `build_http_app(...)`.
- Mounts: frontend at `https://apps.thorwhalen.com/<app>/`, backend at
  `https://apps.thorwhalen.com/api/<app>/`.
- **Secrets:** never in a committed file; the platform's secret-editing helper (see its skill).
- **Privacy in public artifacts:** no absolute local paths, hostnames, or emails in issues,
  PRs, commit messages, or any committed file.

---

## 13. Fleet context you should not re-discover

- The federation overview lives at
  `$PP/t/priv/data/groups/video_gen/workspace_overview.md`
  (note: `t/priv/data/…`, **not** `t/priv/priv/data/…`). It has the ASCII stack diagram,
  ~22 packages with one concern each, and the **prime directive**: *"We work from the top of
  the stack but do as little work as possible in either [app]. Whenever something looks like
  it could be useful to a second application — or already has a natural home in the substrate
  — it goes into the focused package below, not inline in the app. If nothing fits, stop and
  tell the user."* A new focused package (`stepped`) is exactly the sanctioned outcome of that
  last clause — say so explicitly when proposing it.
- Two abstractions the substrate converged on, which a "parse → AST → render" library should
  at minimum evaluate before inventing its own: **`lacing.Annotation`** (typed envelope with
  provenance — the SSOT for "what is" and "what happens when", `$PP/t/lacing`) and
  **`falaw.Plan`** (pure-data plans with honest cost, `$PP/t/falaw`). `nw` (`ProjectGraph`,
  `Transform`, freshness, genres/jobs) is the canonical Python backend for an AV project
  folder. Evaluating these is a different research area — but do not design `stepped`'s AST
  without at least reading `lacing.Annotation`.
- The `$PP/my_packages.pth` manifest is **generated and read-only**. Add packages with
  `priv pkg add-package <path>`; diagnose with `priv align`. Being in the manifest does **not**
  mean importable (imports resolve via per-package `__editable__*.pth`).

---

## Open questions for the next agent

1. **Does "AI artifacts on top" mean shipped SKILL.md files, or something more?** I found no
   coined term for it anywhere in `~/.claude/skills` or the projects tree. My reading (§5) is
   skills + agent-facing docs + model-facing tool prose, and `architecture-first` supports it —
   but it could also mean generated agent *prompts* (there is a `prompts/` dir in `reelee-web`
   and `reelee/data/prompts`), or `coact`-realized agents. **Ask before building.**
2. **Which surface is v1's?** The default order is CLI → MCP → skills → HTTP → frontend, but
   `architecture-first` explicitly inverts it when *the product is a web app* — and the POC's
   deliverable was a deployed web page. If `stepped`'s deliverable is the rendered guide, HTTP
   + frontend are the product and the order flips (write the CLI anyway, as the cheapest proof
   the core isn't fused to the request cycle). Unresolved.
3. **Is `stepped` a `reelee` sibling app, an `nw` genre plugin, or a standalone substrate
   package?** `reelee-web/server.py` loads genre plugins by module name
   (`REELEE_GENRE_PLUGINS`, defaults `muvid.genre`, `muvid.genre_music_video`, `braidio.genre`,
   `an.genre`), which suggests a fourth option: `stepped.genre` registering into `nw`. This
   choice changes the seam table and I could not settle it.
4. **`stepped`'s AST: new type, or `lacing.Annotation`?** Out of scope for this file, but it
   determines whether the storage seam is a `dol` store of blobs plus a lacing graph, or a
   plain `MutableMapping` of JSON.
5. **Is the `stepped` repo scaffolded?** `$PP/pocs/stepped/`
   currently contains **only** `docs/` — no `pyproject.toml`, no package dir, no `.git`. It is
   also under `pocs/`, not a normal `$PP` group (`t/ tt/ i/ c/ misc/`), and is not in the
   manifest. Decide whether it graduates to `$PP/tt/stepped` (and gets `priv pkg add-package`)
   before the first commit — moving it later churns every editable install.
6. **`qh` version confusion.** `pyproject` 0.0.17 vs `__version__` 0.5.0. If `stepped` pins
   `qh`, work out which numbering PyPI actually publishes before writing a floor.
7. **CLI deps in core or extra?** `reelee` puts `argh`/`argcomplete` in core `dependencies`;
   `surface-checks.md` says a library with dependents must put them in extras. `stepped` is
   plausibly both a CLI tool and a library — pick one and write down why.

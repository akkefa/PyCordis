# Phase 0 source audit — 2026-10-03

## Existing repository

/Users/iali/workplace/projects/personal/PyCordis was clean at
`a70acded040c204c8bc30308d1c383000959f658` (Initial commit). It contained .git,
.gitignore (4664 bytes), LICENSE (1066 bytes; MIT, Ikram Ali 2026), and README.md
(10 bytes, only the project title). No source, tests, or Python metadata existed.
The original license and git history are preserved; README is expanded.
No applicable ancestor AGENTS.md was found for PyCordis.

## Reproducible references

Primary: clean local DeepSeek Harness checkout at
`639ed015397290b3745d163aafe02ffee4aa3f84` (2026-09-29).
This is the selected inspected snapshot, not a claim about today's remote HEAD.

- [Vendor manifest and modification log](https://github.com/deepseek-ai/deepseek-harness/blob/639ed015397290b3745d163aafe02ffee4aa3f84/vendor/README.md)
- [Primary core source](https://github.com/deepseek-ai/deepseek-harness/tree/639ed015397290b3745d163aafe02ffee4aa3f84/vendor/cordis/src)
- [Harness lifecycle regression tests](https://github.com/deepseek-ai/deepseek-harness/blob/639ed015397290b3745d163aafe02ffee4aa3f84/packages/extensions/tool-cordis/tests/cordis-lifecycle.spec.ts)
- [Pinned upstream core](https://github.com/cordiverse/cordis/tree/56b3d4f725681cf4556c1a8695a709cc3b6eed74/packages/core)
- [Current upstream inspected snapshot](https://github.com/cordiverse/cordis/tree/f8ea3cd50f1a5724e8e715995bcde131c9c12b2c/packages/core)

Vendor manifest: upstream cordis 4.0.0-rc.7, source commit
`56b3d4f725681cf4556c1a8695a709cc3b6eed74`. Actual scoped Harness manifest:
@deepseek-ai/cordis 4.0.4. These describe different version layers and are not
interchangeable. Current upstream clone HEAD is
`f8ea3cd50f1a5724e8e715995bcde131c9c12b2c` (2026-09-08).

## Comparison method and scope

Read all nine vendored core TypeScript modules, vendor README, manifests,
licenses and selected upstream test bodies (Fiber inertia/failure, effects,
reflection, isolation, events) plus the Harness lifecycle regression suite.
Compared pinned and current upstream core source to vendor source using diffs
with comments, import scopes and .ts suffixes normalized for triage; retained
real import/type differences. The diff is source evidence, not test execution.
No TypeScript suites or live Harness runtime were executed. Loader changes are
classified from the documented patch log, not a full loader implementation audit.

## Harness changes versus its upstream base

| Patch-log entry | Change | Python consequence |
|---|---|---|
| 6 | Register effects before setup; join in-flight cleanup; roll back sync failure | Required ownership semantics |
| 6 | Reject effect creation during UNLOADING; allow PENDING/LOADING | Required state guard |
| 6 | Child owned before publication; resolve observer-added inject; drain pending effects | Required child lifecycle semantics |
| 6 | Skip stale load; isolate teardown observer failures | Required race/failure handling |
| 15 | Raw config retained; internal/config resolution after dependencies, again on activation | Preserve when config phase arrives |
| 21 | Exporter disposer captures registration id | Preserve in any logging adapter |
| 22 | Exports Volatile consumer types; loader commits references | Future config/loader feature; no kernel Fiber change |
| 2–4, 7, 10, 16, 17 | Scope names, packaging, TS import/type rewrites, docs, published src | Python packaging adaptation; not lifecycle behavior |
| 8–14, 18–20, 22 | Include/HMR/Loader changes | Defer to separate loader phase; not kernel scope |

Config and ownership changes were confirmed in core source diffs. Loader fiber
identity patch 20 is in Loader: it stores the original ctx.fiber instead of
mutating the PromiseLike wrapper. That is evidence to keep one Python Fiber
object with __await__, not a reason to add Loader in Phase 0.

## Differences from current upstream

- Upstream now guards duplicate waterfall next calls; Harness retains the
  shared continuation. Do not silently adopt the guard.
- Upstream supports symbol event dispatch, prototype-safe event buckets and
  removes empty buckets; Harness dispatch still assumes a string event name.
  Python dicts naturally avoid JS prototype hazards; arbitrary event keys are
  a separate API decision.
- Upstream latches failed fibers against dependency refresh, canonicalizes
  update/restart to ctx.fiber, and returns observable update completion.
  Harness differs and retains lazy raw-config resolution. Pin failure/update
  expectations to Harness before adapting newer tests.
- Upstream tracing changes distinguish use/definition/caller context and fix
  inherited tracking; Harness retains its older shadow implementation.
- Current upstream orders logger ERROR/WARN/INFO/DEBUG; Harness has
  ERROR/INFO/WARN/DEBUG. Stdlib logging should be an explicit adapter.
- Both have exporter-id capture at current snapshots; the patch was local
  relative to the pinned base. Current upstream does not replace the Harness
  effect/child hardening and lazy-config code observed here.

## Phase 0 repository structure

```text
PyCordis/
├── .gitignore                 # existing, tool caches added
├── .python-version            # Python 3.11 development baseline
├── pyproject.toml             # Hatchling; uv; Python >=3.11
├── uv.lock
├── README.md
├── LICENSE                    # existing MIT notice preserved
├── THIRD_PARTY_NOTICES.md
├── CHANGELOG.md
├── CONTRIBUTING.md
├── src/pycordis/
│   ├── __init__.py            # documentation only; no runtime API
│   └── py.typed
├── tests/test_import.py
└── docs/
    ├── phase-0.md
    ├── architecture.md
    ├── compatibility.md
    └── adr/0001-phase-0-foundation.md
```

Runtime files from the architecture map will be added only in their phases.
No placeholder Context/Fiber/Service implementations or misleading examples.
No CI/release automation until the relevant readiness phase.

## Tooling

Verified installed uv 0.12.2 help before using uv init --lib, explicit Hatch
backend, Python 3.11, no new VCS. Bootstrap uses a src layout, strict mypy,
Ruff targeting py311, pytest and strict pytest-asyncio. Python 3.11.15 is
installed locally. Hatchling is a build dependency, not a kernel dependency.
PyPI /pypi/pycordis/json returned HTTP 404 on 2026-10-03; name not reserved.

## Phase gate

Stop after scaffold verification. Review architecture.md decisions before
Context implementation. Do not claim any runtime compatibility from an import
smoke test. Suggested commit: chore: bootstrap uv project and pin Cordis references.

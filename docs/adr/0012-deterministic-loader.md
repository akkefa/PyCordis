# ADR 0012: explicit ordered loader batches over kernel ownership

Status: accepted for Phase 11.

## Evidence and stability gate

Phase 10 checkout d55997ec6293b47c423ffbb54b2373959154f65e has 321 passing
Python cases. Phase 11 verifies kernel regression coverage plus loader-owned
failure/cancellation/parent teardown and dependency-chain settlement cases before
introducing file watching or loader event hooks.

Inspected DeepSeek Harness 639ed015397290b3745d163aafe02ffee4aa3f84,
vendored loader src/config/entry.ts EntryOptions and Entry._init: explicit IDs,
module/config options, disabled entries, import then mount, and retention of the
original ctx.fiber. config/group.ts uses group ownership and child stop behavior.
index.ts adds configuration interpolation, persistence and publication hooks,
which require APIs the Python kernel intentionally has not implemented.

## Decision

Keep pycordis.loader separate from Context and top-level exports. Use frozen
PluginEntry records, normal importlib module/attribute resolution, strict mapping
rows, input-order mounting, and LoadedPlugins exposing real Fibers. No discovery
or file format dependency is required to configure a deterministic batch.

Preflight all enabled entries before allocation. Give each batch a dedicated
structural owner Fiber and mount every child before settlement. Revisit lifecycle
transitions so consumers preceding providers reach stable states. Missing services
remain PENDING. Failure/cancellation disposes and joins the owner, retaining the
original exception and leaving unrelated ownership alone.

## Compatibility classifications and limits

All loader tests are Python-specific adaptations, not a full port of the source
Loader suite. Python module:attribute references replace JavaScript imports/exports.
Caller-chosen batch order replaces config trees. A dedicated owner replaces source
group machinery without implementing nested serialized groups. Explicit rollback
strengthens source Entry._init import-error logging/return behavior. Imports and
module-level effects cannot be rolled back; only mounted ownership is reversible.

No TypeScript suites or full Harness boot were run. Entry-point discovery, file
includes, interpolation, volatile config, update/persistence, automatic grouping,
watch and HMR remain future work. The loader does not add internal kernel hooks,
proxy identities, destructive import cache clearing or schema dependencies.

# ADR 0013: source-indexed behavioral compatibility evidence

Status: accepted for Phase 12.

## Evidence

Python checkout baseline: 7f7e8d5ed656071f075631b3967adc0508f6bf40, 355 cases.
Primary runtime target: Harness 639ed015397290b3745d163aafe02ffee4aa3f84.
Upstream comparison baseline: 56b3d4f725681cf4556c1a8695a709cc3b6eed74.

Read the pinned 11 upstream core spec files and the Harness tool-cordis lifecycle
regression file. The inventory includes 72 literal source tests. Current upstream
adds other files/cases; the pinned revision, rather than a moving checkout, determines
this phase's catalog. Other Harness integration suites are outside this inventory.

## Decision

Maintain structured source records with commits, exact titles, source paths/lines,
file fingerprints, classifications, coverage scope, Python test references and
specific remaining gaps. Keep a readable table and current feature matrix. Preserve
the Phase 1–11 record separately so old future-work statements do not imply current
support is missing or complete.

Use a compatibility pytest marker for new source-derived ports. Verify behavior
through public Context/Fiber/service/event/effect APIs. Use Event gates instead of
wall-clock sleeps or private scheduler controls. Distinguish catalog integrity checks
from executable behavioral ports and source test counts from Python invocations.

The four classifications are identical semantic behavior, Python-specific adaptation,
not applicable in Python, and future work. Track ported/partial/none separately.
Future source tests can have related partial coverage without being marked complete.
The catalog test ensures provenance/count/identity consistency and verifies evidence
references resolve to test definitions; it cannot prove semantic equivalence by itself.

## Consequences and limits

No kernel changes are needed for the tested ports. Tests clarify diagnostic adaptations:
Python effect trees omit structural child disposers, explicit require differs from
property proxy traps, and native isinstance replaces Context.is branding. Passing
these adaptations does not establish unimplemented source behavior.

Method @Inject, logger exporters, associated proxy properties, Service.extend/tracing,
publication-hook races and Fiber.update remain recorded as future/partial. Source
metadata wording claiming pinned class-decorator tests was corrected: that pinned
file contains the method-decorator test, which remains unimplemented.

No TypeScript suite or full Harness boot was run. The suite runs without TypeScript
checkouts or network access. No release, compatibility percentage or 100% claim is
made. Documentation/examples beyond the compatibility evidence are Phase 13.

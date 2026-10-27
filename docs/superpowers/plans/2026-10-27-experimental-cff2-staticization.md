# Experimental CFF2 Variable-Font Staticization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add explicit, diagnosable CFF2 VF staticization that feeds the existing glyf merge pipeline.

**Architecture:** Extend `instantiate_if_variable` with an opt-in CFF2 path that fully pins axes, requests CFF downgrade, and validates postconditions. Thread the option through the merge APIs and CLI, then add generated-font and real-corpus CI coverage.

**Tech Stack:** Python 3.10+, fontTools 4.65.0+, unittest, GitHub Actions, OTS, HarfBuzz

**Spec:** `docs/superpowers/specs/2026-10-27-experimental-cff2-staticization-design.md`

## Global Constraints

- CFF2 remains rejected unless `experimental_cff2_staticize=True`.
- A successful CFF2 instance contains neither `CFF2` nor `fvar` before outline conversion.
- Upstream failures never fall back and must report source, coordinates, fontTools version, and original error.
- TrueType VF behavior and the static glyf output contract remain unchanged.
- Python 3.10 remains supported with fontTools `>=4.65.0,<4.66`.

## Review Focus

- CFF2 input without the opt-in must still fail before mutation.
- A named instance plus explicit axis must retain the existing explicit-axis precedence.
- A full instance that fails to downgrade must be rejected rather than passed to cu2qu.
- An upstream exception must not leave or publish a partial output file.
- Static CFF and TrueType VF inputs must not receive CFF2-only instancer arguments.

---

### Task 1: Core CFF2 instancing contract

**Files:**
- Modify: `Font_Merger.py`
- Modify: `tests/test_font_merger.py`

**Interfaces:**
- Produces: `instantiate_if_variable(..., experimental_cff2_staticize: bool = False, source_label: str | None = None) -> set[str]`
- Consumes: existing `requested_axes` and `instance_coordinates` precedence rules

- [ ] Write generated CFF2 VF tests for default rejection, default/custom full instances, postconditions, and wrapped upstream errors.
- [ ] Run the focused tests and verify they fail because the opt-in API does not exist or CFF2 is rejected.
- [ ] Implement the minimal opt-in call with `downgradeCFF2=True, static=True`, postcondition checks, and diagnostic wrapping.
- [ ] Run the focused tests and the existing variable-font tests; expect PASS.
- [ ] Commit the task.

### Task 2: End-to-end merge and CLI plumbing

**Files:**
- Modify: `Font_Merger.py`
- Modify: `tests/test_font_merger.py`
- Modify: `scripts/release_e2e.py`
- Modify: `tests/test_release_e2e.py`

**Interfaces:**
- Consumes: Task 1's `experimental_cff2_staticize` parameter
- Produces: matching keyword arguments on `merge_fonts` and `merge_font_family`, plus `--experimental-cff2-staticize`

- [ ] Write failing tests proving the CLI flag is required, the flag reaches every merge path, and default/custom CFF2 outlines differ after a full merge.
- [ ] Run focused tests and verify the missing flag/plumbing failures.
- [ ] Thread the default-false option through CLI and merge APIs; pass source labels to Task 1.
- [ ] Extend release E2E with a generated CFF2 source and explicit experimental flag.
- [ ] Run focused merge/release tests; expect PASS.
- [ ] Commit the task.

### Task 3: Compatibility, real corpus CI, and documentation

**Files:**
- Modify: `pyproject.toml`
- Create: `scripts/cff2_corpus_e2e.py`
- Create: `tests/test_cff2_corpus_e2e.py`
- Modify: `.github/workflows/ci.yml`
- Modify: `README.md`
- Modify: `docs/roadmap.md`

**Interfaces:**
- Consumes: Task 2's CLI flag and static-output contract
- Produces: pinned Adobe corpus smoke test and documented experimental contract

- [ ] Write failing script tests for pinned download verification, source CFF2 detection, merge invocation, and static output validation.
- [ ] Run focused tests and verify failure because the corpus runner is absent.
- [ ] Implement the corpus runner and add it to `font-qa`; upload its diagnostics on failure.
- [ ] Raise the Python 3.10 fontTools floor to 4.65.0 and document the flag, limits, and completed roadmap item in all README languages.
- [ ] Run focused tests, Ruff, `git diff --check`, and the full unit suite; expect PASS (local external-tool/corpus checks may be explicitly skipped when unavailable).
- [ ] Commit the task.

### Task 4: Whole-branch verification and review

**Files:**
- Review all branch changes

**Interfaces:**
- Consumes: Tasks 1-3
- Produces: review-ready branch with evidence

- [ ] Run the generated CFF2 merge at default and custom coordinates and inspect the output tables/outlines.
- [ ] Run the full suite and Ruff from a clean working tree context.
- [ ] Generate a whole-branch review package and perform the required fresh-context review.
- [ ] Resolve Critical/Important findings with RED→GREEN tests; ledger any rulings or deferred minors.
- [ ] Prepare the branch for push and PR without merging it.

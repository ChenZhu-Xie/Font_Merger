# OTS + HarfBuzz CI Validation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Gate merged fonts with OTS structural validation and deterministic HarfBuzz shaping assertions in both pull-request CI and the Linux packaged release build.

**Architecture:** A standalone Python QA runner executes external tools and evaluates a checked-in shaping corpus. The synthetic release fixture supplies stable GSUB/GPOS/MATH/UVS inputs, and both workflows invoke the same runner against their merged output.

**Tech Stack:** Python 3.10+, unittest, fontTools/feaLib, `ots-sanitize`, `hb-shape`, GitHub Actions Ubuntu 22.04

**Spec:** `docs/superpowers/specs/2026-10-27-ots-harfbuzz-ci-design.md`

## Global Constraints

- OTS and HarfBuzz are CI-only dependencies; do not add them to package runtime dependencies.
- All external commands must record command, exit code, stdout, and stderr beneath the requested work directory.
- One corpus manifest and one QA entry point must be reused by source and packaged-executable validation.
- The existing Windows and macOS packaged E2E behavior must remain unchanged.
- CI uses Ubuntu 22.04 packages `opentype-sanitizer` and `libharfbuzz-bin`.

## Review Focus

- A missing external executable must fail with its exact tool name and an actionable message; Task 1 tests this through real PATH lookup behavior.
- A sanitizer rejection must preserve its stderr and never continue silently; Task 1 tests a fake executable returning nonzero.
- Malformed or schema-incompatible HarfBuzz JSON must name the failing corpus case; Task 1 tests invalid JSON and missing fields.
- RTL cluster order and mark offsets must not be normalized away by the assertion layer; Task 2 adds literal Arabic and mark expectations.
- A release work directory containing spaces must still pass exact path arguments; Task 1 uses temporary paths and Task 3 exercises quoted workflow arguments.

---

### Task 1: External QA runner

**Files:**
- Create: `scripts/font_qa.py`
- Create: `tests/test_font_qa.py`
- Create: `tests/data/shaping-corpus.json`

**Interfaces:**
- Consumes: an existing merged font, a writable diagnostics directory, and a JSON corpus path.
- Produces: `run_qa(font_path: Path, work_dir: Path, corpus_path: Path) -> None` and a CLI with `--font`, `--work-dir`, `--corpus`.

- [ ] **Step 1: Write failing tests for tool execution and HarfBuzz semantic validation**

  Add tests named `test_missing_tool_names_executable`, `test_ots_failure_preserves_diagnostics`, `test_invalid_harfbuzz_json_names_case`, `test_glyph_sequence_is_checked`, `test_rtl_clusters_are_checked`, and `test_mark_position_predicate_is_checked`. Each uses executable temporary scripts rather than mocks and literal JSON expectations.

- [ ] **Step 2: Run tests to verify RED**

  Run: `python -m unittest tests.test_font_qa -v`
  Expected: import failure because `scripts.font_qa` does not exist.

- [ ] **Step 3: Implement the minimal runner**

  Implement `find_tool(name: str) -> str`, `run_external(command: list[str], log_path: Path) -> CompletedProcess[str]`, `load_corpus(path: Path) -> list[dict[str, object]]`, `validate_shape(case: dict[str, object], payload: object) -> None`, and `run_qa(...)`. Request HarfBuzz JSON with explicit glyph names and record tool versions in `report.txt`.

- [ ] **Step 4: Run focused and full suites to verify GREEN**

  Run: `python -m unittest tests.test_font_qa -v`
  Expected: all tests pass.

  Run: `python -m unittest discover -s tests -v`
  Expected: all project tests pass.

- [ ] **Step 5: Commit**

  Commit: `test: add reusable OTS and HarfBuzz QA runner`

### Task 2: Deterministic shaping fixture

**Files:**
- Modify: `scripts/release_e2e.py`
- Create: `tests/test_release_e2e.py`
- Modify: `tests/data/shaping-corpus.json`

**Interfaces:**
- Consumes: `create_inputs(work_dir: Path) -> tuple[Path, Path]` and Font_Merger's existing merge CLI.
- Produces: source fonts whose merged output has deterministic Latin ligature, mark positioning, Arabic joining, and Indic conjunct behavior matching the corpus.

- [ ] **Step 1: Write a failing fixture semantics test**

  Add `test_synthetic_inputs_compile_expected_layout_features`, which builds the inputs and proves with fontTools that the expected GSUB/GPOS feature tags and glyph names exist. Add `test_merged_fixture_passes_real_harfbuzz_corpus`, skipped only when `hb-shape` is not installed, to exercise real shaping.

- [ ] **Step 2: Run tests to verify RED**

  Run: `python -m unittest tests.test_release_e2e -v`
  Expected: failure because current fixtures contain no GSUB/GPOS layout tables.

- [ ] **Step 3: Add the minimal layout fixture**

  Extend glyphs/cmap in `create_inputs`, compile deterministic feature text with fontTools feaLib, and populate literal corpus expectations for Latin ligature, combining mark, Arabic joining, and Indic conjunct cases.

- [ ] **Step 4: Run focused and full suites to verify GREEN**

  Run: `python -m unittest tests.test_release_e2e -v`
  Expected: all tests pass (the real-tool test may skip locally when HarfBuzz is absent).

  Run: `python -m unittest discover -s tests -v`
  Expected: all project tests pass.

- [ ] **Step 5: Commit**

  Commit: `test: add deterministic shaping corpus fixture`

### Task 3: Pull-request and packaged-release gates

**Files:**
- Modify: `.github/workflows/ci.yml`
- Modify: `.github/workflows/build-release.yml`
- Modify: `docs/roadmap.md`

**Interfaces:**
- Consumes: `scripts/release_e2e.py`, `scripts/font_qa.py`, and `tests/data/shaping-corpus.json`.
- Produces: an Ubuntu PR QA job and Linux-only post-package QA step using identical commands and corpus.

- [ ] **Step 1: Run both entry points locally before workflow edits**

  Run the source CLI to create `build/qa-source/e2e-merged.ttf`, then run `scripts/font_qa.py` if the external tools are installed. Expected: successful report, or an explicit local missing-tool error that is covered by tests.

- [ ] **Step 2: Add the workflow gates**

  Install `opentype-sanitizer libharfbuzz-bin` in one Ubuntu 22.04 CI job, invoke the source merge fixture, and run QA. In the release matrix, install tools and run QA only when `runner.os == 'Linux'` after packaged E2E.

- [ ] **Step 3: Update roadmap status**

  Mark OTS + HarfBuzz CI as implemented, document the corpus scope, and retain remaining MATH/VORG gaps separately.

- [ ] **Step 4: Verify workflows and repository**

  Run: `python -m unittest discover -s tests -v`
  Expected: all tests pass.

  Run: `ruff check .`
  Expected: no diagnostics.

  Run a YAML parse check for both workflow files.
  Expected: both documents parse successfully.

- [ ] **Step 5: Commit**

  Commit: `ci: gate merged fonts with OTS and HarfBuzz`


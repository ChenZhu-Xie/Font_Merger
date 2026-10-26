# OTS + HarfBuzz CI Validation Design

## Goal

Add a release-quality font validation gate that proves merged fonts are structurally accepted by OTS and retain selected shaping semantics in HarfBuzz, without adding either tool to Font_Merger's runtime dependencies.

## Scope

The gate runs on Ubuntu 22.04, where CI installs `opentype-sanitizer` and `libharfbuzz-bin`. A reusable Python entry point validates any already-merged font, so ordinary pull-request CI and the Linux packaged-executable build exercise the same checks.

The existing synthetic release fixture is extended with deterministic OpenType layout data. Its merged output must cover:

- scalar Latin and CJK cmap entries;
- default and non-default UVS behavior;
- a Latin `liga` substitution;
- combining-mark positioning through GPOS;
- Arabic joining substitutions;
- an Indic conjunct substitution;
- the existing MATH and differing-UPM assertions.

## Architecture

`scripts/font_qa.py` owns external-tool discovery, command execution, log capture, HarfBuzz JSON parsing, and semantic assertions. It accepts `--font`, `--work-dir`, and repeatable corpus definitions from a checked-in JSON manifest. Failures identify the tool and corpus case, retain stdout/stderr, and return a nonzero exit code.

`scripts/release_e2e.py` remains responsible for constructing inputs, invoking Font_Merger, and validating fontTools-visible structure. It gains deterministic GSUB/GPOS fixtures and leaves the merged font at its current stable path.

`tests/data/shaping-corpus.json` is the single source of expected shaping results. Expectations use literal glyph IDs for the deterministic fixture, cluster ordering, and exact mark offsets/advances rather than a complete textual snapshot. Exact offsets distinguish the fixture's GPOS result from HarfBuzz's non-GPOS fallback positioning. Glyph IDs avoid false failures when the merged font's `post` format 3 table intentionally omits glyph names, while still catching lost or corrupted layout behavior.

## CI Integration

Ordinary CI gets one dedicated Ubuntu 22.04 QA job. It installs the package plus the two distro tools, creates and merges the synthetic fixture through the Python CLI, then runs `font_qa.py` on the result. This provides fast pull-request feedback without multiplying the check across the Python-version matrix.

The Linux member of the release matrix installs the same tools after building the executable. After `release_e2e.py` produces `e2e-merged.ttf`, it invokes the same QA script and uploads its logs on failure. Other release platforms continue to run their existing packaged E2E check but do not install Linux-only QA tools.

## Failure Policy

- Missing `ots-sanitize` or `hb-shape` is a hard error with an install-oriented message.
- Any nonzero OTS exit is a hard error; the sanitized copy is kept as a diagnostic artifact but is not used for HarfBuzz assertions.
- Invalid HarfBuzz JSON, missing expected glyphs, wrong substitutions, or failed positioning predicates are hard errors naming the corpus case.
- External tool versions and commands are recorded in the QA report for reproducibility.
- OTS and HarfBuzz remain CI-only dependencies and are not imported or invoked by the end-user application.

## Non-goals

- Rendering screenshots or pixel comparison.
- FontBakery/Fontspector policy checks.
- Exhaustive shaping-engine conformance.
- Installing OTS or HarfBuzz for Windows/macOS release jobs or ordinary users.

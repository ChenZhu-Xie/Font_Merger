# Experimental CFF2 Variable-Font Staticization Design

## Intent

Allow advanced users and CI to opt into CFF2 variable-font instancing without
weakening the default safety policy. A successful input must become a fully
static CFF font before the existing CFF-to-glyf conversion and merge pipeline.

## Goals

- Add an explicit CLI/API opt-in named `--experimental-cff2-staticize`.
- Reuse the existing named-instance, custom-axis, and automatic-weight logic.
- Fully pin every axis and request CFF2-to-CFF downgrade from fontTools.
- Reject any result that still contains `CFF2` or `fvar`.
- On upstream failure, report the source, selected coordinates, fontTools
  version, and original exception; never silently select another instance.
- Cover default/custom locations with a generated CFF2 VF, and exercise an
  Adobe CFF2 VF in CI before describing the feature as non-experimental.

## Non-goals

- Producing a variable merged font.
- Producing CFF/PostScript-outline output; final output remains glyf-based.
- Claiming compatibility with every CFF2 VF or working around upstream
  charstring/VariationStore defects.
- Adding the experimental control to the GUI in this iteration.

## Constraints

- Default behavior continues to reject CFF2 variable fonts.
- Python 3.10 remains supported.
- The supported fontTools floor becomes 4.58.5: downgrade support appeared in
  4.52, while 4.58.1 and 4.58.5 contain relevant CFF2-instancer fixes.
- CFF2 failures are fatal for the current output and leave no partial result.
- Existing TrueType variable-font behavior remains unchanged.

## Approaches

1. **Selected: extend the existing instancer call.** Pass
   `downgradeCFF2=True, static=True` only for opted-in CFF2 inputs, validate the
   postcondition, then reuse CFF-to-glyf. This has the smallest behavioral
   surface and keeps every existing instance-selection rule.
2. Add a separate pre-conversion command or subprocess. This isolates upstream
   failures but duplicates source parsing, instance selection, logging, and
   temporary-file handling.
3. Remove the CFF2 rejection unconditionally. This is simpler but violates the
   experimental boundary and risks exposing upstream failures to all users.

## User-visible behavior

Without the flag, the existing actionable rejection remains. With the flag,
each CFF2 source logs that experimental staticization is active and which axis
coordinates are pinned. Success produces the same glyf-based static output as
other inputs. Failure identifies the source and environment sufficiently for
an issue report.

## Verification

- Generated CFF2 VF tests prove default and custom coordinates create distinct,
  hand-checked outlines and leave no variable/CFF tables in merged output.
- Tests prove the flag is required and upstream exceptions retain diagnostic
  context.
- The normal unit suite runs on Python 3.10, 3.12, and 3.14.
- CI downloads a pinned Adobe Source Serif 4 CFF2 VF, merges selected glyphs,
  and validates the result with OTS and HarfBuzz.

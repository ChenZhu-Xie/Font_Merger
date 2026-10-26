#!/usr/bin/env python3
"""Validate one merged font with OTS and a deterministic HarfBuzz corpus."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import traceback
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from fontTools.ttLib import TTFont


def find_tool(name: str) -> str:
    """Return an external executable path or raise an actionable error."""
    executable = shutil.which(name)
    if executable is None:
        raise FileNotFoundError(
            f"required font QA executable not found on PATH: {name}"
        )
    return executable


def run_external(
    command: list[str], log_path: Path
) -> subprocess.CompletedProcess[str]:
    """Run and log an external command, raising after preserving diagnostics."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    environment = os.environ.copy()
    environment["PYTHONUTF8"] = "1"
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=environment,
        check=False,
    )
    log_path.write_text(
        "command: "
        + subprocess.list2cmdline(command)
        + f"\nexit_code: {result.returncode}\n\nstdout:\n{result.stdout}"
        + f"\nstderr:\n{result.stderr}",
        encoding="utf-8",
    )
    if result.returncode:
        raise RuntimeError(
            f"{Path(command[0]).name} exited with {result.returncode}; "
            f"see {log_path}"
        )
    return result


def load_corpus(path: Path) -> list[dict[str, object]]:
    """Load the checked-in shaping corpus and reject ambiguous schemas."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError(f"shaping corpus must be a JSON array: {path}")
    cases: list[dict[str, object]] = []
    for index, case in enumerate(payload):
        if not isinstance(case, dict):
            raise ValueError(f"shaping corpus case {index} must be an object")
        if not isinstance(case.get("name"), str) or not isinstance(
            case.get("text"), str
        ):
            raise ValueError(f"shaping corpus case {index} needs name and text")
        if not isinstance(case.get("expect"), dict):
            raise ValueError(f"shaping corpus case {index} needs expect")
        cases.append(case)
    return cases


def _shape_error(case_name: str, detail: str) -> AssertionError:
    return AssertionError(f"HarfBuzz case {case_name}: {detail}")


def validate_shape(
    case: dict[str, object],
    payload: object,
    glyph_ids: Mapping[str, int] | None = None,
) -> None:
    """Check one hb-shape JSON payload against literal semantic expectations."""
    case_name = str(case.get("name", "<unnamed>"))
    if not isinstance(payload, list) or not all(
        isinstance(item, dict) for item in payload
    ):
        raise _shape_error(case_name, "invalid HarfBuzz JSON glyph array")

    glyphs = payload
    names_by_id = (
        {glyph_id: name for name, glyph_id in glyph_ids.items()}
        if glyph_ids is not None
        else {}
    )

    def semantic_name(value: object) -> object:
        if isinstance(value, str):
            match = re.fullmatch(r"gid([0-9]+)", value)
            if match:
                return names_by_id.get(int(match.group(1)), value)
        return value

    expected = case.get("expect")
    if not isinstance(expected, dict):
        raise _shape_error(case_name, "invalid expectation JSON object")

    expected_glyphs = expected.get("glyphs")
    if expected_glyphs is not None:
        actual_glyphs = [semantic_name(glyph.get("g")) for glyph in glyphs]
        if actual_glyphs != expected_glyphs:
            raise _shape_error(
                case_name,
                f"glyphs mismatch: expected {expected_glyphs}, got {actual_glyphs}",
            )

    expected_clusters = expected.get("clusters")
    if expected_clusters is not None:
        actual_clusters = [glyph.get("cl") for glyph in glyphs]
        if actual_clusters != expected_clusters:
            raise _shape_error(
                case_name,
                f"clusters mismatch: expected {expected_clusters}, got {actual_clusters}",
            )

    positions = expected.get("positions")
    if positions is None:
        return
    if not isinstance(positions, dict):
        raise _shape_error(case_name, "positions must be an object")
    by_name = {semantic_name(glyph.get("g")): glyph for glyph in glyphs}
    for glyph_name, predicates in positions.items():
        if glyph_name not in by_name:
            raise _shape_error(case_name, f"position glyph missing: {glyph_name}")
        if not isinstance(predicates, dict):
            raise _shape_error(case_name, f"position predicates invalid: {glyph_name}")
        glyph = by_name[glyph_name]
        for predicate, wanted in predicates.items():
            if predicate not in {"dx_nonzero", "dy_nonzero"} or wanted is not True:
                raise _shape_error(
                    case_name, f"unsupported position predicate: {predicate}"
                )
            field = predicate.removesuffix("_nonzero")
            if not isinstance(glyph.get(field), (int, float)) or glyph[field] == 0:
                raise _shape_error(
                    case_name, f"{glyph_name} failed {predicate}: {glyph.get(field)!r}"
                )


def _safe_case_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-") or "case"


def _shape_command(hb_shape: str, font_path: Path, case: dict[str, object]) -> list[str]:
    command = [hb_shape, "--output-format=json"]
    for key in ("direction", "script", "language", "features"):
        value = case.get(key)
        if value is not None:
            command.append(f"--{key}={value}")
    command.extend([str(font_path), str(case["text"])])
    return command


def run_qa(font_path: Path, work_dir: Path, corpus_path: Path) -> None:
    """Run OTS and every HarfBuzz corpus case against an existing font."""
    font_path = font_path.expanduser().resolve()
    corpus_path = corpus_path.expanduser().resolve()
    work_dir = work_dir.expanduser().resolve()
    if not font_path.is_file():
        raise FileNotFoundError(f"font to validate not found: {font_path}")
    work_dir.mkdir(parents=True, exist_ok=True)

    ots_sanitize = find_tool("ots-sanitize")
    hb_shape = find_tool("hb-shape")
    version_lines = []
    for tool_name, executable in (
        ("ots-sanitize", ots_sanitize),
        ("hb-shape", hb_shape),
    ):
        result = run_external(
            [executable, "--version"], work_dir / f"{tool_name}-version.log"
        )
        version = (result.stdout or result.stderr).strip().splitlines()
        version_lines.append(
            f"{tool_name}={version[0] if version else '<unknown>'} ({executable})"
        )

    sanitized = work_dir / "ots-sanitized.ttf"
    run_external(
        [ots_sanitize, str(font_path), str(sanitized)], work_dir / "ots.log"
    )

    cases = load_corpus(corpus_path)
    with TTFont(font_path, lazy=True) as font:
        glyph_ids = {name: index for index, name in enumerate(font.getGlyphOrder())}
    for case in cases:
        case_name = str(case["name"])
        result = run_external(
            _shape_command(hb_shape, font_path, case),
            work_dir / f"harfbuzz-{_safe_case_name(case_name)}.log",
        )
        try:
            payload: Any = json.loads(result.stdout)
        except json.JSONDecodeError as error:
            raise _shape_error(case_name, f"invalid HarfBuzz JSON: {error}") from error
        validate_shape(case, payload, glyph_ids)

    (work_dir / "report.txt").write_text(
        "font QA passed\n"
        + f"font={font_path}\n"
        + f"corpus_cases={len(cases)}\n"
        + "\n".join(version_lines)
        + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--font", required=True, type=Path)
    parser.add_argument("--work-dir", required=True, type=Path)
    parser.add_argument(
        "--corpus",
        type=Path,
        default=Path(__file__).resolve().parents[1]
        / "tests"
        / "data"
        / "shaping-corpus.json",
    )
    args = parser.parse_args()
    try:
        run_qa(args.font, args.work_dir, args.corpus)
    except Exception:
        args.work_dir.mkdir(parents=True, exist_ok=True)
        failure = traceback.format_exc()
        (args.work_dir / "failure.txt").write_text(failure, encoding="utf-8")
        print(failure, file=sys.stderr)
        return 1
    print(f"Font QA passed; report: {args.work_dir / 'report.txt'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

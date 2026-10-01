"""Reports how far our approximate float assertions actually land from their reference.

The wheel builds run this suite on every architecture we ship, so the summary printed
at the end of a run is a per-architecture record of the floating point spread, readable
straight out of the Actions log. See #348, where an aarch64 build differed from the
reference by a single ULP and the whole suite got skipped on that platform in response.

Set CORRECTIONLIB_ULP_REPORT to also collect the report as markdown, which is how
wheels.yml lifts it into the GitHub Actions job summary. It cannot be written to
GITHUB_STEP_SUMMARY directly from here: cibuildwheel overwrites that file once its
own build table is ready, which is after every test run has finished.
"""

import os
import pathlib
import platform
import struct
import sys
import sysconfig
from collections import defaultdict

import pytest


def _ordinal(value: float) -> int:
    """Map a double onto an integer such that adjacent doubles are adjacent integers."""
    (bits,) = struct.unpack("<q", struct.pack("<d", value))
    # negative doubles run backwards when read as signed integers; reflect them so
    # that the ordering is monotonic across zero
    return bits if bits >= 0 else -0x8000000000000000 - bits


def ulp_distance(actual: float, expected: float) -> float:
    """Count the representable doubles between two floats."""
    if actual != actual or expected != expected:  # NaN
        return float("inf")
    if actual in (float("inf"), float("-inf")) or expected in (
        float("inf"),
        float("-inf"),
    ):
        return float("inf")
    if actual == expected:
        return 0
    try:
        return abs(_ordinal(actual) - _ordinal(expected))
    except (OverflowError, struct.error):
        return float("inf")


_measurements: "defaultdict[str, list[tuple[float, float, float]]]" = defaultdict(list)


@pytest.fixture
def ulp_report(request):
    """Assert approximate equality, recording the ULP distance for the run summary.

    Takes the same keyword arguments as pytest.approx; pass ``label`` to name the
    measurement when a test makes more than one.
    """

    def check(actual, expected, label=None, **approx_kwargs):
        name = request.node.name
        if label is not None:
            name = f"{name}[{label}]"
        _measurements[name].append((actual, expected, ulp_distance(actual, expected)))
        assert actual == pytest.approx(expected, **approx_kwargs)

    return check


def _build_tag() -> str:
    """Name this interpreter and platform the way the wheel it came from is named."""
    return f"{sys.implementation.cache_tag}-{sysconfig.get_platform()}"


def _markdown_report_path(host_mount="/host"):
    """Where to collect the markdown report, if anywhere.

    cibuildwheel runs the Linux tests inside a container, where the runner's
    filesystem is mounted at /host, so a path handed to us by the workflow needs
    translating before we can write to it.
    """
    target = os.environ.get("CORRECTIONLIB_ULP_REPORT")
    if not target and not os.environ.get("CIBUILDWHEEL"):
        # outside cibuildwheel nothing overwrites the job summary, so use it directly
        target = os.environ.get("GITHUB_STEP_SUMMARY")
    if not target:
        return None
    path = pathlib.Path(target)
    if path.parent.is_dir():
        return path
    in_container = pathlib.Path(host_mount) / path.relative_to(path.anchor)
    return in_container if in_container.parent.is_dir() else None


def _write_markdown_report(path, rows):
    header = "### Float assertion ULP report"
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    lines = []
    if header not in existing:
        lines += [
            header,
            "",
            "| build | assertion | ulp | actual | expected |",
            "| --- | --- | ---: | --- | --- |",
        ]
    build = _build_tag()
    for name, ulps, actual, expected in rows:
        lines.append(f"| `{build}` | {name} | {ulps} | `{actual!r}` | `{expected!r}` |")
    with path.open("a", encoding="utf-8") as fp:
        fp.write("\n".join(lines) + "\n")


def pytest_terminal_summary(terminalreporter):
    if not _measurements:
        return
    terminalreporter.write_sep("=", "float assertion ULP report")
    terminalreporter.write_line(
        f"{platform.machine()} {sys.platform} "
        f"python {'.'.join(str(v) for v in sys.version_info[:3])}"
        f"{'t' if sysconfig.get_config_var('Py_GIL_DISABLED') else ''}"
    )
    width = max(len(name) for name in _measurements)
    rows = []
    for name, measurements in sorted(_measurements.items()):
        actual, expected, ulps = max(measurements, key=lambda m: m[2])
        detail = "exact" if ulps == 0 else f"{actual!r} vs {expected!r}"
        count = f" (worst of {len(measurements)})" if len(measurements) > 1 else ""
        terminalreporter.write_line(f"{name:<{width}}  {ulps:>4} ulp  {detail}{count}")
        rows.append((name, ulps, actual, expected))

    path = _markdown_report_path()
    if path is None:
        return
    try:
        _write_markdown_report(path, rows)
    except OSError as exc:  # never fail a test run over the report
        terminalreporter.write_line(f"could not write ULP report to {path}: {exc}")

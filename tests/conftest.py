"""Reports how far our approximate float assertions actually land from their reference.

The wheel builds run this suite on every architecture we ship, so the summary printed
at the end of a run is a per-architecture record of the floating point spread, readable
straight out of the Actions log. See #348, where an aarch64 build differed from the
reference by a single ULP and the whole suite got skipped on that platform in response.
"""

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
    if actual == expected:
        return 0
    try:
        return abs(_ordinal(actual) - _ordinal(expected))
    except (OverflowError, struct.error):  # infinities
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
    for name, measurements in sorted(_measurements.items()):
        actual, expected, ulps = max(measurements, key=lambda m: m[2])
        detail = "exact" if ulps == 0 else f"{actual!r} vs {expected!r}"
        count = f" (worst of {len(measurements)})" if len(measurements) > 1 else ""
        terminalreporter.write_line(f"{name:<{width}}  {ulps:>4} ulp  {detail}{count}")

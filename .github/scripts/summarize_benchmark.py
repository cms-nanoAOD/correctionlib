#!/usr/bin/env python3
"""Generate a markdown summary from pytest-benchmark JSON output."""

import json
import pathlib
import sys


def main():
    benchmark_json = pathlib.Path(".benchmarks/cvmfs-benchmark.json")
    output_md = pathlib.Path(".benchmarks/pr-comment.md")

    if not benchmark_json.exists():
        output_md.write_text(
            "### CVMFS benchmarks\n\nNo benchmark JSON was produced in this run."
        )
        return 0

    data = json.loads(benchmark_json.read_text())
    rows = []
    for bench in data.get("benchmarks", []):
        stats = bench.get("stats", {})
        rows.append(
            (
                bench.get("name", "unknown"),
                stats.get("mean", 0.0) * 1000.0,
                stats.get("stddev", 0.0) * 1000.0,
                stats.get("rounds", 0),
            )
        )

    rows.sort(key=lambda row: row[1], reverse=True)
    rows = rows[:25]

    lines = [
        "### CVMFS benchmarks",
        "",
        "Top 25 slowest-loading corrections, sorted by mean time:",
        "",
        "| Benchmark | Mean (ms) | Stddev (ms) | Rounds |",
        "|---|---:|---:|---:|",
    ]

    if rows:
        for name, mean_ms, stddev_ms, rounds in rows:
            lines.append(f"| `{name}` | {mean_ms:.3f} | {stddev_ms:.3f} | {rounds} |")
    else:
        lines.append("| _No benchmark rows found_ | - | - | - |")

    output_md.write_text("\n".join(lines) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Command-line interface to correctionlib

"""
import argparse

from rich.console import Console

from correctionlib.highlevel import model_auto, open_auto


def validate(console: Console, args: argparse.Namespace) -> int:
    """Check if all files are valid"""
    retcode = 0
    for file in args.files:
        try:
            if not args.quiet:
                console.rule(f"[blue]Validating file {file}")
            cset = model_auto(open_auto(file))
            if args.version and cset.schema_version != args.version:
                raise ValueError(
                    f"Schema version {cset.schema_version} does not match the required version {args.version}"
                )
        except Exception as ex:
            if not args.quiet:
                console.print(str(ex))
            retcode = 1
            if args.failfast:
                break
        else:
            if not args.quiet:
                console.print("[green]All OK :heavy_check_mark:")
    return retcode


def setup_validate(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("validate", help=validate.__doc__)
    parser.set_defaults(command=validate)
    parser.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        help="Suppress error printout, only produce a returncode",
    )
    parser.add_argument(
        "--failfast",
        "-f",
        action="store_true",
        help="Fail on first invalid file",
    )
    parser.add_argument(
        "--version",
        "-v",
        type=int,
        default=None,
        help="Validate against specific schema version",
    )
    parser.add_argument("files", nargs="+", metavar="FILE")


def summary(console: Console, args: argparse.Namespace) -> int:
    for file in args.files:
        console.rule(f"[blue]Corrections in file {file}")
        cset = model_auto(open_auto(file))
        console.print(cset)
    return 0


def setup_summary(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "summary", help="Print a summmary of the corrections"
    )
    parser.set_defaults(command=summary)
    parser.add_argument("files", nargs="+", metavar="FILE")


def main() -> int:
    parser = argparse.ArgumentParser(prog="correction", description=__doc__)
    parser.add_argument(
        "--width",
        type=int,
        default=100,
        help="Rich output width",
    )
    parser.add_argument("--html", type=str, help="Save HTML output to a file")
    subparsers = parser.add_subparsers()
    setup_validate(subparsers)
    setup_summary(subparsers)
    args = parser.parse_args()

    console = Console(width=args.width, record=True)
    # py3.7: subparsers has required=True option
    if hasattr(args, "command"):
        retcode: int = args.command(console, args)
        if args.html:
            console.save_html(args.html)
        return retcode

    parser.parse_args(["-h"])
    return 0

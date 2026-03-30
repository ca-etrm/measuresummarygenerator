import sys
import argparse as ap
import datetime as dt

from src.main import start_app
from src.builder import build


def _configure_build_parser(parser: ap.ArgumentParser) -> None:
    """
    Takes in the build (i.e., the CLI mode versus app mode) command line argument 
    and add the other filter arguments (-u, m, a, etc.)
    """
    parser.set_defaults(mode="build") #set mode of "build" (used later in __main__)

    parser.add_argument(
        "-m", "--measures",
        nargs="*",           # NumOfArgs: * = 0 or more values
        default=[],
        help="Specifies the measure or measures to generate a summary for."
    )

    parser.add_argument(
        "-u", "--use-categories",
        nargs="*",
        default=[],
        help="Specifies the use category or categories to generate a summary for."
    )

    parser.add_argument(
        "-o", "--output-file",
        default="POU TRM PDF",
        help="Specifies the name of the generated summary file."
    )

    parser.add_argument(
        "-a", "--all",
        action="store_true",   #a true boolean
        help="Include to generate a summary that includes every measure in each use category."
    )

    parser.add_argument(
        "-l", "--limit",
        type=int,             #require argument to be a type int
        default=None,
        help="Specifies an upper limit of measures to generate a summary from."
    )

    parser.add_argument(
        "--min-start-date",
        type=dt.date.fromisoformat,
        default=None,
        help="Specifies the inclusive minimum start date (in ISO format) to filter measures by."
    )

    parser.add_argument(
        "--max-start-date",
        type=dt.date.fromisoformat,
        default=None,
        help="Specifies the non-inclusive maximum start date (in ISO format) to filter measures by."
    )

    parser.add_argument(
        "--min-end-date",
        type=dt.date.fromisoformat,
        default=None,
        help="Specifies the inclusive minimum end date (in ISO format) to filter measures by."
    )

    parser.add_argument(
        "--max-end-date",
        type=dt.date.fromisoformat,
        default=None,
        help="Specifies the non-inclusive maximum end date (in ISO format) to filter measures by."
    )


def _configure_app_parser(parser: ap.ArgumentParser) -> None:
    parser.set_defaults(mode="app")

    parser.add_argument(
        "-r", "--run-as",
        type=str,
        choices=["client", "dev"],
        default="client",
        help="Specifies which mode to run the app in."
    )


def parse_args() -> ap.Namespace:
    parser = ap.ArgumentParser(
        prog="eTRM Measure Summary Generator",
        description="Generates summaries of eTRM measures."
    )
    subparsers = parser.add_subparsers(help="Modes to run the program in.")

    build_parser = subparsers.add_parser("build")
    _configure_build_parser(build_parser)

    app_parser = subparsers.add_parser("app")
    _configure_app_parser(app_parser)

    return parser.parse_args()


def handle_build(args: ap.Namespace) -> None:
    """
    Take in the fully parsed command line argument passed back to __main__
    Extract the ind value and set them to each attribute field
    """
    build(
        file_name=getattr(args, "output_file", "measure_summary"),  #default needed here when setting default in parser_arg already?
        all_measures=getattr(args, "all", False),
        measure_versions=getattr(args, "measures", None),
        use_categories=getattr(args, "use_categories", None),
        min_start_date=getattr(args, "min_start_date", None),
        max_start_date=getattr(args, "max_start_date", None),
        min_end_date=getattr(args, "min_end_date", None),
        max_end_date=getattr(args, "max_end_date", None)
    )


def handle_app(args: ap.Namespace) -> None:
    start_app(getattr(args, "run_as", "client"))


if __name__ == '__main__':
    args = parse_args()  #full line argument from the CLI
    
    try:
        mode = str(args.mode)
        print("Main args mode = %s" % mode)
    except ValueError | AttributeError:
        print("Usage: ./cli [build | app] ...", file=sys.stderr)
        sys.exit(1)

    match mode:
        case "build":
            handle_build(args)
        case "app":
            handle_app(args)
        case other:
            raise RuntimeError(f"Unknown run mode: {other}")

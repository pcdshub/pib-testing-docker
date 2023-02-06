import argparse
import logging
from typing import Optional

from .. import build

logger = logging.getLogger(__name__)


def main(paths: list[str], include_deps: bool = True, skip: Optional[list[str]] = None) -> None:
    skip = list(skip or [])
    specs = build.Specifications.from_spec_files(paths)
    build.download(specs, include_deps=include_deps, skip=skip)


def build_arg_parser(argparser=None) -> argparse.ArgumentParser:
    if argparser is None:
        argparser = argparse.ArgumentParser()
    argparser.add_argument("paths", nargs="+", type=str, help="Path to module specification")
    argparser.add_argument("--skip", type=str, nargs="*", help="Skip these modules")
    argparser.add_argument("--no-deps", action="store_false", dest="include_deps", help="Do not download dependencies")
    return argparser


def _main(args=None):
    """Independent CLI entrypoint."""
    parser = build_arg_parser()
    return main(**vars(parser.parse_args(args=args)))


if __name__ == "__main__":
    _main()

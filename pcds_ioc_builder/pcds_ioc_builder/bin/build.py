import argparse
import logging
from typing import Optional

from .. import build

logger = logging.getLogger(__name__)


def main(
    paths: list[str],
    sync: bool = False,
    stop_on_failure: bool = True,
    skip: Optional[list[str]] = None,
) -> None:
    specs = build.Specifications.from_spec_files(paths)
    if sync:
        build.sync(specs)
    build.build(specs, stop_on_failure=stop_on_failure, skip=skip)


def build_arg_parser(argparser=None) -> argparse.ArgumentParser:
    if argparser is None:
        argparser = argparse.ArgumentParser()
    argparser.add_argument("paths", nargs="+", type=str, help="Path to module specification")
    argparser.add_argument("--sync", action="store_true", help="Synchronize makefile variables first")
    argparser.add_argument("--skip", type=str, nargs="*", help="Skip these modules")
    argparser.add_argument("--continue", action="store_false", dest="stop_on_failure", help="Do not stop builds on the first failure")
    return argparser


def _main(args=None):
    """Independent CLI entrypoint."""
    parser = build_arg_parser()
    return main(**vars(parser.parse_args(args=args)))


if __name__ == "__main__":
    _main()

import argparse
import logging

from ..build import build
from .sync import Specifications

logger = logging.getLogger(__name__)


def main(
    paths: list[str],
    sync: bool = False,
    stop_on_failure: bool = True,
) -> None:
    specs = Specifications(paths)
    if sync:
        specs.sync()
    build(specs, stop_on_failure=stop_on_failure)


def build_arg_parser(argparser=None) -> argparse.ArgumentParser:
    if argparser is None:
        argparser = argparse.ArgumentParser()
    argparser.add_argument("paths", nargs="+", type=str, help="Path to module specification")
    argparser.add_argument("--sync", action="store_true", help="Synchronize makefile variables first")
    argparser.add_argument("--continue", action="store_false", dest="stop_on_failure", help="Do not stop builds on the first failure")
    return argparser


def _main(args=None):
    """Independent CLI entrypoint."""
    parser = build_arg_parser()
    return main(**vars(parser.parse_args(args=args)))


if __name__ == "__main__":
    _main()

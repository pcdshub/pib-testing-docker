import argparse

from ..build import Specifications

import logging

logger = logging.getLogger(__name__)


def main(paths: list[str]) -> None:
    specs = Specifications(paths)

    logger.info(
        "Synchronizing dependencies with these paths:\n    %s",
        "\n    ".join(f"{var}={value}" for var, value in specs.variable_name_to_string.items())
    )
    specs.sync()


def build_arg_parser(argparser=None) -> argparse.ArgumentParser:
    if argparser is None:
        argparser = argparse.ArgumentParser()
    argparser.add_argument("paths", nargs="+", type=str, help="Path to module specification")
    return argparser


def _main(args=None):
    """Independent CLI entrypoint."""
    parser = build_arg_parser()
    return main(**vars(parser.parse_args(args=args)))


if __name__ == "__main__":
    _main()

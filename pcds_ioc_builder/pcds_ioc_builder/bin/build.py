import argparse
import pathlib

from whatrecord.makefile import Dependency, Makefile

from ..makefile import patch_makefile
from ..module import (BaseSettings, get_dependency_group_for_module)
from ..spec import Module, SpecificationFile

from .sync import Specifications

import logging

logger = logging.getLogger(__name__)


def main(base_spec_path: str, paths: list[str], sync: bool = False) -> None:
    specs = Specifications(base_spec_path, paths)

    logger.info(
        "Synchronizing dependencies with these paths:\n    %s",
        "\n    ".join(f"{var}={value}" for var, value in specs.variable_name_to_string.items())
    )
    if sync:
        specs.sync()

    # TODO one-by-one building
    for module in specs.modules:
        group = get_dependency_group_for_module(module, specs.settings, recurse=True)


def build_arg_parser(argparser=None) -> argparse.ArgumentParser:
    if argparser is None:
        argparser = argparse.ArgumentParser()
    argparser.add_argument("base_spec_path", type=str, help="Path to base specification")
    argparser.add_argument("paths", nargs="+", type=str, help="Path to module specification")
    argparser.add_argument("--sync", action="store_true", help="Synchronize makefile variables first")
    return argparser


def _main(args=None):
    """Independent CLI entrypoint."""
    parser = build_arg_parser()
    return main(**vars(parser.parse_args(args=args)))


if __name__ == "__main__":
    _main()

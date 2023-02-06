import apischema
import pathlib
import argparse
import json

from typing import Union

from ..spec import Requirements, SpecificationFile
from ..module import BaseSettings, Inspector, VersionInfo
from whatrecord.makefile import DependencyGroup, Makefile

from .sync import Specifications


def main(paths: list[str], requirements: bool = False) -> None:
    specs = Specifications(paths)

    if requirements:
        reqs = apischema.serialize(Requirements, specs.requirements)
        print(json.dumps(reqs, indent=2))


def build_arg_parser(argparser=None) -> argparse.ArgumentParser:
    if argparser is None:
        argparser = argparse.ArgumentParser()
    argparser.add_argument("paths", nargs="+", type=str, help="Path to module specification")
    argparser.add_argument("--requirements", action="store_true", help="Summarize requirements")
    return argparser


def _main(args=None):
    """Independent CLI entrypoint."""
    parser = build_arg_parser()
    return main(**vars(parser.parse_args(args=args)))


if __name__ == "__main__":
    _main()

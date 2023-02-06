import argparse
import json

import apischema

from ..build import Specifications
from ..spec import Requirements


def main(paths: list[str], requirements: bool = False) -> None:
    specs = Specifications.from_spec_files(paths)

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
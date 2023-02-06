import argparse
import json

import apischema

from ..spec import SpecificationFile


def main(spec_filename: str) -> None:
    spec = SpecificationFile.from_filename(spec_filename)
    serialized = apischema.serialize(SpecificationFile, spec)
    print(json.dumps(serialized, indent=2))


def build_arg_parser(argparser=None) -> argparse.ArgumentParser:
    if argparser is None:
        argparser = argparse.ArgumentParser()
    argparser.add_argument("spec_filename", type=str)
    return argparser


def _main(args=None):
    """Independent CLI entrypoint."""
    parser = build_arg_parser()
    return main(**vars(parser.parse_args(args=args)))


if __name__ == "__main__":
    _main()

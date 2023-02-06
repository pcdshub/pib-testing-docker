import argparse

from whatrecord.makefile import Dependency

from ..module import (BaseSettings, download_module,
                      get_dependency_group_for_module)
from ..spec import SpecificationFile
from ..build import Specifications


def main(paths: list[str], include_deps: bool = True) -> None:
    specs = Specifications(paths)

    for module in specs.modules:
        download_module(module, specs.settings)

    if not include_deps:
        return

    variable_to_dep = specs.get_variable_to_dependency()
    print("Overall dependencies:")
    for variable, dep in variable_to_dep.items():
        print(f"{variable}: {dep.path}")

    # TODO: this does not yet handle downloading detected dependencies
    #       that are not in spec files, right?  that is a goal of this tool
    #       after all... Needs testing/work


def build_arg_parser(argparser=None) -> argparse.ArgumentParser:
    if argparser is None:
        argparser = argparse.ArgumentParser()
    argparser.add_argument("paths", nargs="+", type=str, help="Path to module specification")
    argparser.add_argument("--no-deps", action="store_false", dest="include_deps", help="Do not download dependencies")
    return argparser


def _main(args=None):
    """Independent CLI entrypoint."""
    parser = build_arg_parser()
    return main(**vars(parser.parse_args(args=args)))


if __name__ == "__main__":
    _main()

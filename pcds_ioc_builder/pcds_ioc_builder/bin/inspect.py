import apischema
import pathlib
import argparse
import json

from typing import Union

from ..spec import SpecificationFile
from ..module import BaseSettings, Inspector, VersionInfo
from whatrecord.makefile import DependencyGroup, Makefile


def main(path: Union[pathlib.Path, str], recurse: bool = True) -> None:
    path = pathlib.Path(path)
    settings = BaseSettings(
        epics_base=pathlib.Path("~/Repos/epics-base"),
        support=pathlib.Path("~/Repos/"),
        extra_variables={},
    )
    inspector = Inspector.from_path(path, settings=settings, recurse=recurse)
    print(list(inspector.group.all_modules))
    print(list(inspector.find_all_dependencies()))
    print(list(inspector.find_all_missing_dependencies()))
    # root = group.all_modules[group.root]
    # root.missing_paths
    # for path, module in group.all_modules.items():
    #     version = VersionInfo.from_path(path)
    #     print(path, version)

    # 'tool inspect' -> configuration file
    # 'tool download' -> download missing dependencies
    # 'tool build' -> build dependency or dependencies


def build_arg_parser(argparser=None) -> argparse.ArgumentParser:
    if argparser is None:
        argparser = argparse.ArgumentParser()
    argparser.add_argument("path", type=str, help="Path to module or IOC")
    argparser.add_argument("--no-recurse", action="store_false", dest="recurse", help="Path to module or IOC")
    # argparser.add_argument("--name", type=str, default="TODO", help="Variable name for what is being inspected")
    return argparser


def _main(args=None):
    """Independent CLI entrypoint."""
    parser = build_arg_parser()
    return main(**vars(parser.parse_args(args=args)))


if __name__ == "__main__":
    _main()

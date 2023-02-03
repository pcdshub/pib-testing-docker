import argparse
import pathlib

from whatrecord.makefile import Dependency, Makefile

from pcds_ioc_builder.util import call_make

from ..makefile import patch_makefile
from ..module import (BaseSettings, get_build_order, get_dependency_group_for_module)
from ..spec import MakeOptions, Module, SpecificationFile

from .sync import Specifications

import logging

logger = logging.getLogger(__name__)


def main(base_spec_path: str, paths: list[str], sync: bool = False, stop_on_failure: bool = True) -> None:
    specs = Specifications(base_spec_path, paths)

    logger.info(
        "Synchronizing dependencies with these paths:\n    %s",
        "\n    ".join(f"{var}={value}" for var, value in specs.variable_name_to_string.items())
    )
    if sync:
        specs.sync()

    variable_to_dep: dict[str, Dependency] = {}
    for module in specs.all_modules:
        group = get_dependency_group_for_module(module, specs.settings, recurse=True)
        for module in group.all_modules.values():
            if module.variable_name is None:
                logger.warning("Unset variable name? %s", module)
                continue

            variable_to_dep[module.variable_name] = module

    default_make_opts = MakeOptions()
    order = get_build_order(list(variable_to_dep.values()), skip=[])
    logger.info("Build order defined: %s", order)
    for variable in order:
        if variable == "EPICS_BASE":
            # TODO base not required to skip
            continue

        dep = variable_to_dep[variable]
        logger.info("Building: %s from %s", variable, dep.path)
        spec = specs.variable_name_to_module[variable]
        logger.info("Specification file calls for: %s", spec)
        make_opts = spec.make or default_make_opts

        if call_make(*make_opts.args, path=dep.path, parallel=make_opts.parallel) != 0:
            logger.error("Failed to build: %s", variable)
            if stop_on_failure:
                raise RuntimeError(f"Failed to build {variable}")


def build_arg_parser(argparser=None) -> argparse.ArgumentParser:
    if argparser is None:
        argparser = argparse.ArgumentParser()
    argparser.add_argument("base_spec_path", type=str, help="Path to base specification")
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

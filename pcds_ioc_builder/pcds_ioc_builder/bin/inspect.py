import argparse
import io
import logging
import sys

import apischema
import yaml
from whatrecord.makefile import pathlib

from .. import build
from ..spec import Application, SpecificationFile

logger = logging.getLogger(__name__)


def main(
    ioc: str,
    paths: list[str],
    output: io.TextIOBase,
    sync: bool = False,
    download: bool = True,
    recurse: bool = True,
    name: str = "",
    variable_name: str = "",
) -> None:
    ioc_path = pathlib.Path(ioc).expanduser().resolve()

    specs = build.Specifications.from_spec_files(paths)
    specs.check_settings()

    app = Application()
    extra_modules = []
    specs.applications[ioc_path] = app

    if sync:
        logger.debug("Synchronizing paths in dependencies...")
        build.sync(specs)

    logger.debug("Checking for makefile in path: %s", ioc_path)
    logger.debug("EPICS base path for introspection: %s (%s)", specs.settings.epics_base, specs.settings)

    inspector = build.RecursiveInspector.from_path(ioc_path, specs)
    inspector.download_missing_dependencies()

    for variable, version in inspector.variable_to_version.items():
        if variable in specs.variable_name_to_module:
            app.standard_modules.append(variable)
        else:
            extra_modules.append(version.to_module(variable))

    file = SpecificationFile(
        application=app,
        modules=extra_modules,
    )
    serialized = apischema.serialize(SpecificationFile, file, exclude_defaults=True, exclude_none=True)
    result = yaml.dump(serialized, indent=2, sort_keys=False)

    logger.debug("Writing to %s:\n'''\n%s\n'''", output, result)
    output.write(result)

    if output is not sys.stdout:
        output.flush()
        output.close()


def build_arg_parser(argparser=None) -> argparse.ArgumentParser:
    if argparser is None:
        argparser = argparse.ArgumentParser()
    argparser.add_argument("ioc", type=str, help="Path to IOC (or module) to inspect")
    argparser.add_argument("paths", nargs="+", type=str, help="Path to module specification")
    # argparser.add_argument("--download", action="store_true", help="Synchronize makefile variables first")
    argparser.add_argument("--no-recurse", action="store_false", dest="recurse", help="Synchronize makefile variables first")
    argparser.add_argument("--no-download", action="store_false", dest="download", help="Do not download required dependencies for recursive introspection")
    argparser.add_argument("--sync", action="store_true", help="Synchronize makefile variables first")
    argparser.add_argument("--name", type=str, default="ioc", help="Name for this module or IOC")
    argparser.add_argument("--variable-name", type=str, default="ioc", help="If inspecting a module, specify its common variable name")
    argparser.add_argument("-o", "--output", type=argparse.FileType(mode="wt"), default=sys.stdout, help="Output inspection result to this file")
    return argparser


def _main(args=None):
    """Independent CLI entrypoint."""
    parser = build_arg_parser()
    return main(**vars(parser.parse_args(args=args)))


if __name__ == "__main__":
    _main()

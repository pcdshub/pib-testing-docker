import argparse
import io
import logging
import sys

import apischema
import yaml
from whatrecord.makefile import DependencyGroup, pathlib

from .. import build
from ..makefile import get_makefile_for_path
from ..module import VersionInfo, download_module, find_missing_dependencies
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
    makefile = get_makefile_for_path(ioc_path, epics_base=specs.settings.epics_base)

    group = DependencyGroup.from_makefile(makefile, name=name, variable_name=variable_name)

    # TODO, this needs to recurse newly-downloaded dependencies (optionally?)
    missing = list(find_missing_dependencies(group.all_modules[group.root]))
    logger.debug("Found %d missing dep(s)", len(missing))

    for missing_dep in missing:
        if missing_dep.variable in specs.variable_name_to_module:
            logger.info("Found existing module; using packaged version: %s", missing_dep.variable)
            app.standard_modules.append(missing_dep.variable)
            continue

        if missing_dep.version is None:
            continue

        # TODO: the other possibility is a mistaken variable name, where we might
        # need VersionInfo to grab the repository name and correct the variable
        # name

        module = missing_dep.version.to_module(name)
        target_path = specs.settings.get_path_for_module(module)
        logger.debug("Installing to %s %s", target_path, module)
        if not target_path.exists():
            if not download:
                logger.warning("Not downloading dependency %s due to --no-download flag", module)
            else:
                module.install_path = target_path
                download_module(module, specs.settings)

        extra_modules.append(module)

    for path, dep in group.all_modules.items():
        if path == group.root:
            # Skip the IOC itself
            continue

        # Paths that already exist (already fixed Makefile?)
        if dep.variable_name in specs.variable_name_to_module:
            logger.info("Found existing module; using packaged version: %s", dep.variable_name)
            app.standard_modules.append(dep.variable_name)
        else:
            version = VersionInfo.from_path(path)
            if version is None:
                logger.warning(
                    "Existing path that does not follow known versioning standards: %s; skipping.",
                    path
                )
                continue

            assert dep.variable_name is not None
            module = version.to_module(dep.variable_name)
            extra_modules.append(module)

    file = SpecificationFile(
        application=app,
        modules=extra_modules,
    )
    serialized = apischema.serialize(SpecificationFile, file, exclude_defaults=True, exclude_none=True)
    result = yaml.dump(serialized, indent=2, sort_keys=False)
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

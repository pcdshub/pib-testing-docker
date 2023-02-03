import argparse
import pathlib

from whatrecord.makefile import Dependency, Makefile

from ..makefile import patch_makefile
from ..module import (BaseSettings, get_dependency_group_for_module)
from ..spec import Module, SpecificationFile


import logging

logger = logging.getLogger(__name__)


def update_related_makefiles(
    base_path: pathlib.Path,
    makefile: Makefile,
    variable_to_value: dict[str, str],
):
    """
    Update makefiles found during the introspection step that exist in ``base_path``.

    Updates module dependency paths based.

    Parameters
    ----------
    base_path : pathlib.Path
        The path to update makefiles under.
    makefile : Makefile
        The primary Makefile that contains paths of relevant included makefiles.
    """
    for makefile_relative in makefile.makefile_list:
        makefile_path = (base_path / makefile_relative).resolve()
        try:
            makefile_path.relative_to(base_path)
        except ValueError:
            # logger.debug(
            #     "Skipping makefile: %s (not relative to %s)",
            #     makefile_path,
            #     base_path,
            # )
            continue

        try:
            patch_makefile(makefile_path, variable_to_value)
        except PermissionError:
            logger.error("Failed to patch makefile due to permissions: %s", makefile_path)
        except Exception:
            logger.exception("Failed to patch makefile: %s", makefile_path)


class Specifications:
    settings: BaseSettings
    specs: dict[pathlib.Path, SpecificationFile]
    modules: list[Module]

    def __init__(self, base_spec_path: str, paths: list[str]):
        base_spec = SpecificationFile.from_filename(base_spec_path)
        base = base_spec.modules_by_name["epics-base"]
        self.settings = BaseSettings.from_base_version(base)

        if not self.settings.epics_base.exists():
            raise RuntimeError(
                f"epics-base required to introspect and download dependencies.  "
                f"Path is {self.settings.epics_base} from {base_spec_path} module 'epics-base'"
            )

        self.modules = []
        for path in paths:
            spec = SpecificationFile.from_filename(path)
            for module in spec.modules:
                self.modules.append(module)

        self.modules.append(base)

    @property
    def variable_name_to_path(self) -> dict[str, pathlib.Path]:
        return {
            module.variable: self.settings.get_path_for_module(module)
            for module in self.modules
        }

    @property
    def variable_name_to_string(self) -> dict[str, str]:
        return {
            var: str(value)
            for var, value in self.variable_name_to_path.items()
        }

    def sync(self):
        variables = self.variable_name_to_string

        # TODO where do things like this go?
        variables["RE2C"] = "re2c"

        for module in self.modules:
            group = get_dependency_group_for_module(module, self.settings, recurse=True)
            dep = group.all_modules[group.root]
            logger.debug("Updating makefiles in %s", group.root)
            update_related_makefiles(group.root, dep.makefile, variable_to_value=variables)


def main(base_spec_path: str, paths: list[str]) -> None:
    specs = Specifications(base_spec_path, paths)

    logger.info(
        "Synchronizing dependencies with these paths:\n    %s",
        "\n    ".join(f"{var}={value}" for var, value in specs.variable_name_to_string.items())
    )
    specs.sync()


def build_arg_parser(argparser=None) -> argparse.ArgumentParser:
    if argparser is None:
        argparser = argparse.ArgumentParser()
    argparser.add_argument("base_spec_path", type=str, help="Path to base specification")
    argparser.add_argument("paths", nargs="+", type=str, help="Path to module specification")
    return argparser


def _main(args=None):
    """Independent CLI entrypoint."""
    parser = build_arg_parser()
    return main(**vars(parser.parse_args(args=args)))


if __name__ == "__main__":
    _main()

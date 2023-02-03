import argparse
import pathlib

from whatrecord.makefile import Dependency, Makefile

from ..makefile import get_makefile_for_path, patch_makefile
from ..module import (BaseSettings, get_dependency_group_for_module)
from ..spec import Application, Module, Requirements, SpecificationFile


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
    makefiles = set(makefile.makefile_list)

    # TODO: introspection of some makefiles can error out due to $(error dep not found)
    # which means we can't check the makefiles to update, which means it's
    # entirely broken...
    for path in [
        "configure/RELEASE",
        "configure/RELEASE.local",
    ]:
        if (base_path / path).exists():
            makefiles.add(path)

    for makefile_relative in sorted(makefiles):
        makefile_path = (base_path / makefile_relative).resolve()
        try:
            makefile_path.relative_to(base_path)
        except ValueError:
            logger.debug(
                "Skipping makefile: %s (not relative to %s)",
                makefile_path,
                base_path,
            )
            continue

        try:
            patch_makefile(makefile_path, variable_to_value)
        except PermissionError:
            logger.error("Failed to patch makefile due to permissions: %s", makefile_path)
        except Exception:
            logger.exception("Failed to patch makefile: %s", makefile_path)


def add_requirements(reqs: Requirements, to_add: Requirements):
    for req in to_add.apt:
        if req not in reqs.apt:
            reqs.apt.append(req)

    for req in to_add.yum:
        if req not in reqs.yum:
            reqs.yum.append(req)

    for req in to_add.conda:
        if req not in reqs.conda:
            reqs.conda.append(req)


class Specifications:
    settings: BaseSettings
    specs: dict[pathlib.Path, SpecificationFile]
    modules: list[Module]
    applications: dict[pathlib.Path, Application]
    requirements: Requirements

    def __init__(self, base_spec_path: str, paths: list[str]):
        base_spec = SpecificationFile.from_filename(base_spec_path)
        base = base_spec.modules_by_name["epics-base"]
        self.requirements = Requirements()
        self.settings = BaseSettings.from_base_version(base)

        if not self.settings.epics_base.exists():
            raise RuntimeError(
                f"epics-base required to introspect and download dependencies.  "
                f"Path is {self.settings.epics_base} from {base_spec_path} module 'epics-base'"
            )

        self.modules = []
        self.applications = {}
        for path in paths:
            filename = pathlib.Path(path).expanduser().resolve()
            spec = SpecificationFile.from_filename(filename)
            for module in spec.modules:
                self.modules.append(module)
                if module.requires is not None:
                    add_requirements(self.requirements, module.requires)
            if spec.application is not None:
                self.applications[filename] = spec.application
                if spec.application.requires is not None:
                    add_requirements(self.requirements, spec.application.requires)

        self.modules.append(base)

    @property
    def all_modules(self):
        # TODO application-level overrides? shouldn't be possible, right?
        # so raise/warn/remove extra modules that are redefined
        yield from self.modules
        for app in self.applications.values():
            yield from app.extra_modules

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

    @property
    def variable_name_to_module(self) -> dict[str, Module]:
        return {
            module.variable: module
            for module in self.all_modules
        }

    def sync(self):
        variables = self.variable_name_to_string

        # TODO where do things like this go?
        variables["RE2C"] = "re2c"

        for module in self.all_modules:
            group = get_dependency_group_for_module(module, self.settings, recurse=True)
            dep = group.all_modules[group.root]
            logger.info("Updating makefiles in %s", group.root)
            update_related_makefiles(group.root, dep.makefile, variable_to_value=variables)

        for path in self.applications:
            makefile = get_makefile_for_path(path.parent, epics_base=self.settings.epics_base)
            # TODO introspection at 2 levels? 'modules' may be the wrong abstraction?
            # or is (base / modules between / app) not too many layers?
            #
            # group = DependencyGroup.from_makefile(
            #     makefile,
            #     recurse=recurse,
            #     variable_name=variable_name or module.variable,
            #     name=name or module.name,
            #     keep_os_env=keep_os_env
            # )
            update_related_makefiles(path.parent, makefile, variable_to_value=variables)


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

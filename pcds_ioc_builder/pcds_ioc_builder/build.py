import logging
import pathlib
import pprint
from typing import Optional, Union

from whatrecord.makefile import Dependency

from pcds_ioc_builder.exceptions import (EpicsBaseMissing, EpicsBaseOnlyOnce,
                                         InvalidSpecification)

from .makefile import get_makefile_for_path, update_related_makefiles
from .module import (BaseSettings, download_module, get_build_order,
                     get_dependency_group_for_module)
from .spec import (Application, MakeOptions, Module, Requirements,
                   SpecificationFile)
from .util import call_make

logger = logging.getLogger(__name__)


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
    base_spec: Optional[Module] = None

    def __init__(self, paths: list[str]):
        self.modules = []
        self.applications = {}
        self.requirements = Requirements()
        self.settings = BaseSettings()
        self.base_spec = None

        for path in paths:
            self.add_spec(path)

    def check_settings(self) -> None:
        if self.base_spec is None:
            raise InvalidSpecification(
                "EPICS_BASE not found in specification file list; "
                f"Found modules: {self.variable_name_to_module}"
            )

        if not self.settings.epics_base.exists():
            raise EpicsBaseMissing(
                f"epics-base required to introspect and download dependencies.  "
                f"Path is {self.settings.epics_base} from specification file "
                f"module 'epics-base'"
            )

    def add_spec(self, spec_filename: Union[str, pathlib.Path]) -> SpecificationFile:
        spec_filename = pathlib.Path(spec_filename).expanduser().resolve()
        spec = SpecificationFile.from_filename(spec_filename)

        base = spec.modules_by_name.get("epics-base", None)
        if base is not None:
            if self.base_spec is not None:
                raise EpicsBaseOnlyOnce(
                    f"epics-base may only be specified once.  Found "
                    f"second time in: {spec_filename}"
                )

            self.settings = BaseSettings.from_base_version(base)
            self.base_spec = base

        for module in spec.modules:
            self.modules.append(module)
            if module.requires is not None:
                add_requirements(self.requirements, module.requires)

        if spec.application is not None:
            self.applications[spec_filename] = spec.application
            if spec.application.requires is not None:
                add_requirements(self.requirements, spec.application.requires)

        return spec

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

    def get_variable_to_dependency(self) -> dict[str, Dependency]:
        # TODO multiple version specification handling required
        # allow override, etc?
        variable_to_dep: dict[str, Dependency] = {}
        for module in self.all_modules:
            group = get_dependency_group_for_module(module, self.settings, recurse=True)
            for module in group.all_modules.values():
                if module.variable_name is None:
                    logger.warning("Unset variable name? %s", module)
                    continue

                variable_to_dep[module.variable_name] = module

        return variable_to_dep


def download(
    specs: Specifications, include_deps: bool = True, skip: Optional[list[str]] = None
) -> None:
    skip = list(skip or [])

    for module in specs.modules:
        if module.variable in skip or module.name in skip:
            logger.debug("Skipping module: %s", module.name)
            continue

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


def sync(specs: Specifications, skip: Optional[list[str]] = None):
    skip = list(skip or [])
    variables = specs.variable_name_to_string

    # TODO where do things like this go?
    variables["RE2C"] = "re2c"
    logger.debug(
        "Updating makefiles with the following variables:\n %s",
        pprint.pformat(variables),
    )

    for module in specs.all_modules:
        if module.variable in skip or module.name in skip:
            continue

        group = get_dependency_group_for_module(module, specs.settings, recurse=True)
        dep = group.all_modules[group.root]
        logger.info("Updating makefiles in %s", group.root)
        update_related_makefiles(group.root, dep.makefile, variable_to_value=variables)

    for path in specs.applications:
        makefile = get_makefile_for_path(path.parent, epics_base=specs.settings.epics_base)
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


def build(specs: Specifications, stop_on_failure: bool = True, skip: Optional[list[str]] = None):
    skip = list(skip or [])
    specs.check_settings()

    # TODO: what is my plan here? methods on Specifications or
    # actions outside of it?  (-> Specifications.sync() vs build(Specifications()))
    variable_to_dep = specs.get_variable_to_dependency()

    default_make_opts = MakeOptions()
    order = get_build_order(list(variable_to_dep.values()), skip=[])
    logger.info("Build order defined: %s", order)
    for variable in order:
        dep = variable_to_dep[variable]
        if variable in skip or dep.name in skip:
            continue

        logger.info("Building: %s from %s", variable, dep.path)
        spec = specs.variable_name_to_module[variable]
        logger.info("Specification file calls for: %s", spec)
        make_opts = spec.make or default_make_opts

        if call_make(*make_opts.args, path=dep.path, parallel=make_opts.parallel) != 0:
            logger.error("Failed to build: %s", variable)
            if stop_on_failure:
                raise RuntimeError(f"Failed to build {variable}")

    # finally, applications
    for spec_path, app in specs.applications.items():
        path = spec_path.parent
        logger.info("Building application in %s from %s", path, app)
        make_opts = app.make or default_make_opts

        if call_make(*make_opts.args, path=path, parallel=make_opts.parallel) != 0:
            logger.error("Failed to build application in %s", path)
            if stop_on_failure:
                raise RuntimeError(f"Failed to build {path}")

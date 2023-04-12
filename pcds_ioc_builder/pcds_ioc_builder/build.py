from __future__ import annotations

import logging
import os
import pathlib
import pprint
import textwrap
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional, Union

from whatrecord.makefile import Dependency, DependencyGroup

from .exceptions import (
    EpicsBaseMissingError,
    EpicsBaseOnlyOnceError,
    EpicsModuleNotFoundError,
    InvalidSpecificationError,
    TargetDirectoryAlreadyExistsError,
)
from .makefile import call_make, get_makefile_for_path, update_related_makefiles
from .module import (
    BaseSettings,
    MissingDependency,
    VersionInfo,
    download_module,
    find_missing_dependencies,
    get_build_order,
    get_dependency_group_for_module,
)
from .spec import (
    Application,
    MakeOptions,
    Module,
    Patch,
    Requirements,
    SpecificationFile,
)

if TYPE_CHECKING:
    from collections.abc import Generator

    try:
        from typing import Self
    except ImportError:
        from typing_extensions import Self


BUILD_MARKER_FILE = ".pcds_builder.built"

logger = logging.getLogger(__name__)


def add_requirements(reqs: Requirements, to_add: Requirements) -> None:
    for req in to_add.apt:
        if req not in reqs.apt:
            reqs.apt.append(req)

    for req in to_add.yum:
        if req not in reqs.yum:
            reqs.yum.append(req)

    for req in to_add.conda:
        if req not in reqs.conda:
            reqs.conda.append(req)


@dataclass
class Specifications:
    """Specifications file."""

    settings: BaseSettings = field(default_factory=BaseSettings)
    specs: dict[pathlib.Path, SpecificationFile] = field(default_factory=dict)
    modules: list[Module] = field(default_factory=list)
    applications: dict[pathlib.Path, Application] = field(default_factory=dict)
    requirements: Requirements = field(default_factory=Requirements)
    base_spec: Optional[Module] = None

    @classmethod
    def from_spec_files(
        cls: type[Self],
        paths: list[Union[pathlib.Path, str]],
    ) -> Self:
        inst = cls()
        for path in paths:
            inst.add_spec(path)
        return inst

    def check_settings(self) -> None:
        if self.base_spec is None:
            raise InvalidSpecificationError(
                "EPICS_BASE not found in specification file list; "
                f"Found modules: {self.variable_name_to_module}",
            )

        if not self.settings.epics_base.exists():
            raise EpicsBaseMissingError(
                f"epics-base required to introspect and download dependencies.  "
                f"Path is {self.settings.epics_base} from specification file "
                f"module 'epics-base'",
            )

    def add_spec(self, spec_filename: Union[str, pathlib.Path]) -> SpecificationFile:
        spec_filename = pathlib.Path(spec_filename).expanduser().resolve()
        spec = SpecificationFile.from_filename(spec_filename)

        base = spec.modules_by_name.get("epics-base", None)
        if base is not None:
            if self.base_spec is not None:
                raise EpicsBaseOnlyOnceError(
                    f"epics-base may only be specified once.  Found "
                    f"second time in: {spec_filename}",
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
    def all_modules(self) -> Generator[Module, None, None]:
        # TODO application-level overrides? shouldn't be possible, right?
        # so raise/warn/remove extra modules that are redefined
        yield from self.modules
        # for app in self.applications.values():
        #     yield from app.extra_modules

    @property
    def variable_name_to_path(self) -> dict[str, pathlib.Path]:
        return {
            module.variable: self.settings.get_path_for_module(module)
            for module in self.modules
        }

    @property
    def name_to_module(self) -> dict[str, Module]:
        return {module.name: module for module in self.all_modules}

    @property
    def variable_name_to_module(self) -> dict[str, Module]:
        return {module.variable: module for module in self.all_modules}

    @property
    def variables_to_rename(self) -> dict[str, str]:
        # TODO
        return {}

    @property
    def variables_to_sync(self) -> dict[str, str]:
        variables = dict(self.settings.variables)
        for var, path in self.variable_name_to_path.items():
            variables[var] = str(path)

        return variables

    def get_name_to_dependency(self) -> dict[str, Dependency]:
        name_to_dep: dict[str, Dependency] = {}
        for module in self.all_modules:
            # module_path = self.settings.get_path_for_module(module)
            # module_version = VersionInfo.from_path(module_path)
            # if module_version is None:
            #     raise ValueError(
            #         f"Dependency is not in a recognized path; version unknown. "
            #         f"{module.name}: {module_path}",
            #     )
            group = get_dependency_group_for_module(
                module,
                self.settings,
                recurse=True,
                # name=module_version.name,
            )
            for submodule in group.all_modules.values():
                name_to_dep[submodule.name] = submodule

        return name_to_dep

    # def get_variable_to_dependency(self) -> dict[str, Dependency]:
    #     # TODO multiple version specification handling required
    #     # allow override, etc?
    #     variable_to_dep: dict[str, Dependency] = {}
    #     for module in self.all_modules:
    #         group = get_dependency_group_for_module(module, self.settings, recurse=True)
    #         for submodule in group.all_modules.values():
    #             if submodule.variable_name is None:
    #                 logger.warning("Unset variable name? %s", submodule)
    #                 continue
    #
    #             variable_to_dep[submodule.variable_name] = submodule
    #
    #     return variable_to_dep

    def find_module_by_name(self, name: str) -> Module:
        """
        Find a module by case-insensitive variable name or repository name.

        Parameters
        ----------
        name : str
            The variable name or repository name.

        Returns
        -------
        Module

        Raises
        ------
        EpicsModuleNotFoundError
            If the module is not found.
        """
        for module in self.all_modules:
            if name.lower() == module.name.lower():
                return module
            if name.lower() == module.variable.lower():
                return module
        raise EpicsModuleNotFoundError(f"Specified module not found: {name}")


def create_release_site(
    specs: Specifications,
    extra_variables: Optional[dict[str, str]] = None,
    path: Optional[pathlib.Path] = None,
) -> pathlib.Path:
    """
    Create a RELEASE_SITE file.

    Parameters
    ----------
    specs : Specifications
    extra_variables: dict[str, str], optional
    path: pathlib.Path, optional

    Returns
    -------
    pathlib.Path
    """
    release_site = path or specs.settings.support / "RELEASE_SITE"

    variables = {
        "EPICS_BASE": str(specs.settings.epics_base),
        "SUPPORT": str(specs.settings.support),
        "EPICS_MODULES": str(specs.settings.support),
    }
    if extra_variables:
        variables.update(extra_variables)

    with open(release_site, mode="w") as fp:
        for variable, value in variables.items():
            print(f"{variable}={value}", file=fp)

    return release_site


def should_include(module: Module, only: list[str], skip: list[str]) -> bool:
    if only and module.variable not in only and module.name not in only:
        return False

    if module.variable in skip or module.name in skip:
        return False

    return True


def apply_patch_to_module(module: Module, settings: BaseSettings, patch: Patch) -> None:
    logger.info("Applying patch to module %s: %s", module.name, patch.description)
    module_path = settings.get_path_for_module(module)
    if patch.method == "replace":
        if patch.contents is None:
            raise ValueError(f"No contents in patch: {patch.description}")
        file_path = module_path / patch.dest_file
        contents = textwrap.dedent(patch.contents)
        with open(file_path, "w") as fp:
            print(contents, file=fp)
        if patch.mode is not None:
            os.chmod(file_path, patch.mode)
        logger.debug(
            "File %s replaced with contents:\n----\n%s\n----\n",
            file_path,
            contents,
        )
    else:
        raise ValueError(f"Unsupported patch method: {patch.method}")


def patch_module(module: Module, settings: BaseSettings) -> None:
    for patch in module.patches:
        apply_patch_to_module(module, settings, patch)


def download_spec_modules(
    specs: Specifications,
    # include_deps: bool = True,
    skip: Optional[list[str]] = None,
    only: Optional[list[str]] = None,
    exist_ok: bool = True,
) -> None:
    """Download modules with the versions listed in the specifications files."""
    skip = list(skip or [])
    only = list(only or [])

    for module in specs.modules:
        if not should_include(module, only, skip):
            logger.debug("Skipping module: %s", module.name)

        download_module(module, specs.settings, exist_ok=exist_ok)

    # variable_to_dep = specs.get_variable_to_dependency()
    # print("Dependencies from specification files:")
    # for variable, dep in variable_to_dep.items():
    #     print(f"{variable}: {dep.path}")


def sync_module(specs: Specifications, module: Module) -> None:
    group = get_dependency_group_for_module(module, specs.settings, recurse=True)
    dep = group.all_modules[group.root]
    logger.info("Updating makefiles in %s", group.root)
    update_related_makefiles(
        group.root, dep.makefile, variable_to_value=specs.variables_to_sync,
    )


def sync_path(
    specs: Specifications, path: pathlib.Path, extras: Optional[dict[str, str]] = None,
) -> None:
    makefile = get_makefile_for_path(path, epics_base=specs.settings.epics_base)
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
    variables = dict(specs.variables_to_sync)
    variables.update(extras or {})
    update_related_makefiles(path, makefile, variable_to_value=variables)


def sync(specs: Specifications, skip: Optional[list[str]] = None) -> None:
    skip = list(skip or [])

    logger.debug(
        "Updating makefiles with the following variables:\n %s",
        pprint.pformat(specs.variables_to_sync),
    )

    for module in specs.all_modules:
        if module.variable in skip or module.name in skip:
            continue

        sync_module(specs, module)

    for app_spec_path in specs.applications:
        sync_path(specs, app_spec_path.parent)


def build(  # noqa: C901 TODO
    specs: Specifications,
    *,
    stop_on_failure: bool = True,
    only: Optional[list[str]] = None,
    skip: Optional[list[str]] = None,
    mark_as_built: bool = True,
    rebuild: bool = False,
    clean: bool = True,
) -> None:
    skip = list(skip or [])
    only = list(only or [])
    specs.check_settings()

    # TODO: what is my plan here? methods on Specifications or
    # actions outside of it?  (-> Specifications.sync() vs build(Specifications()))
    name_to_dep = specs.get_name_to_dependency()

    default_make_opts = MakeOptions()
    order = get_build_order(list(name_to_dep.values()), skip=[])
    logger.info("Build order defined: %s", order)
    for dep_name in order:
        dep = name_to_dep[dep_name]
        spec = specs.name_to_module[dep.name]
        if not should_include(spec, only, skip):
            logger.debug("Skipping dependency: %s", dep_name)
            continue

        build_marker_file = dep.path / BUILD_MARKER_FILE
        # External `make clean` could interrupt this mechanism; do we care?
        # Not intended to be an interactive tool but rather used from containers,
        # so I think the answer is no...
        # Alternatively put it in the build artifact directory which will be
        # automatically cleaned by the EPICS build system:
        # build_marker_file = dep.path / "configure" / "O.Common" / BUILD_MARKER_FILE
        if build_marker_file.exists() and not rebuild:
            logger.info(
                "Skipping dependency %s from %s as it has already been built",
                dep_name,
                dep.path,
            )
            continue

        logger.info("Building: %s from %s", dep_name, dep.path)
        logger.info("Specification file calls for: %s", spec)
        make_opts = spec.make or default_make_opts

        res = call_make(
            make_opts.args,
            path=dep.path,
            parallel=make_opts.parallel,
            output_fd=None,
        )
        if res.exit_code == 0:
            if mark_as_built:
                with open(build_marker_file, "w") as fp:
                    # More build info here?
                    print('{"built":true}', file=fp)
        else:
            logger.debug("Make output: %s", res.log)
            logger.error("Failed to build: %s", dep_name)
            if stop_on_failure:
                raise RuntimeError(f"Failed to build {dep_name}")

        if clean:
            res = call_make(["clean"], path=dep.path, output_fd=None)
            if res.exit_code != 0:
                logger.warning("Failed to clean: %s", dep_name)

    # finally, applications
    for spec_path, app in specs.applications.items():
        path = spec_path.parent
        logger.info("Building application in %s from %s", path, app)
        make_opts = app.make or default_make_opts

        res = call_make(
            make_opts.args,
            path=path,
            parallel=make_opts.parallel,
            output_fd=None,
        )
        if res.exit_code != 0:
            logger.debug("Make output: %s", res.log)
            logger.error("Failed to build application in %s", path)
            if stop_on_failure:
                raise RuntimeError(f"Failed to build {path}")


@dataclass
class RecursiveInspector:
    """
    Recursive inspector tool.

    Inspector tool which can:
    1. Introspect modules/IOCs for missing dependencies
    2. Download missing dependencies
    3. Recurse to (1)
    """

    specs: Specifications
    new_specs: Specifications
    inspect_path: pathlib.Path
    group: DependencyGroup
    aliased_deps: dict[str, list[str]] = field(default_factory=dict)

    @classmethod
    def from_path(
        cls: type[Self],
        path: pathlib.Path,
        specs: Specifications,
    ) -> Self:
        path = path.expanduser().resolve()
        if path.parts[-1] == "Makefile":
            path = path.parent

        inspector = cls(
            specs=specs,
            inspect_path=path,
            group=DependencyGroup(root=path),
            new_specs=Specifications(settings=specs.settings),
        )
        inspector.add_dependency(
            name="ioc",
            variable_name="",
            path=path,
        )
        return inspector

    @property
    def target_dependency(self) -> Dependency:
        return self.group.all_modules[self.group.root]

    @property
    def makefile_path(self) -> pathlib.Path:
        return self.inspect_path / "Makefile"

    def add_dependency(
        self,
        name: str,
        variable_name: str,
        path: pathlib.Path,
        # reset_configure: bool = True,
    ) -> Dependency:
        """
        Add a dependency identified by its variable name and version tag.

        Parameters
        ----------
        variable_name : str
            The Makefile-defined variable for the dependency.
        version : VersionInfo
            The version information for the dependency, either derived by way
            of introspection or manually.
        reset_configure : bool, optional
            Reset module/configure/* to the git HEAD, if changed.
            (TODO) also reset modules/RELEASE.local

        Returns
        -------
        Dependency
            The whatrecord-generated :class:`Dependency`.
        """
        logger.info("Adding dependency %s: %s", variable_name, path)

        logger.debug("Synchronizing dependency variables")
        sync_path(self.specs, path, extras=self.new_specs.variables_to_sync)

        logger.debug(
            "Introspecting dependency makefile, adding it to the DependencyGroup",
        )
        makefile = get_makefile_for_path(
            path,
            epics_base=self.specs.settings.epics_base,
            variables=self.specs.settings.variables,
        )
        return Dependency.from_makefile(
            makefile,
            recurse=True,
            name=name,
            variable_name=variable_name,
            root=self.group,  # <-- NOTE: this implicitly adds the dep to self.group
        )

    def find_all_dependencies(self) -> Generator[Dependency, None, None]:
        """
        Iterate over all dependencies.

        The caller is allowed to mutate the "all_modules" dictionary between
        each iteration.  Dependencies are keyed on variable names.
        """
        checked = set()

        def done() -> bool:
            return all(
                dep.variable_name in checked for dep in self.group.all_modules.values()
            )

        while not done():
            deps = list(self.group.all_modules.values())
            for dep in deps:
                if dep.variable_name in checked:
                    continue
                checked.add(dep.variable_name)
                yield dep

    def find_dependencies_to_download(self) -> Generator[MissingDependency, None, None]:
        for dep in self.find_all_dependencies():
            logger.debug(
                (
                    "Checking module %s for all dependencies. \n"
                    "\nExisting dependencies:\n"
                    "    %s"
                    "\nMissing paths: \n"
                    "    %s"
                ),
                dep.variable_name or "this IOC",
                "\n    ".join(
                    f"{var}={value}" for var, value in dep.dependencies.items()
                ),
                "\n    ".join(
                    f"{var}={value}" for var, value in dep.missing_paths.items()
                ),
            )

            for missing_dep in find_missing_dependencies(dep):
                yield missing_dep

    def download_missing_dependencies(self) -> None:
        """
        Download missing dependencies.

        Using module path conventions, find all dependencies and check them
        out to the cache directory.

        See Also
        --------
        :func:`VersionInfo.from_path`
        """
        logger.debug(
            (
                "Checking the primary target for dependencies using EPICS build system. \n"
                "\nExisting dependencies:\n"
                "    %s"
                "\nMissing paths: \n"
                "    %s"
            ),
            "\n    ".join(
                f"{var}={value}"
                for var, value in self.target_dependency.dependencies.items()
            ),
            "\n    ".join(
                f"{var}={value}"
                for var, value in self.target_dependency.missing_paths.items()
            ),
        )
        self.specs.check_settings()

        # spec_variable_to_dep = self.specs.get_variable_to_dependency()
        # 1. We need to download missing dependencies
        # 2. We need to inspect those dependencies
        # 3. We need to add those dependencies (and sub-deps) to the new_specs list
        for missing_dep in self.find_dependencies_to_download():
            if missing_dep.version is None:
                # logger.warning("Dependency %s doesn't match version standards...", missing_dep)
                continue

            module = missing_dep.version.to_module(missing_dep.variable)

            try:
                module_path = download_module(module, self.specs.settings)
            except TargetDirectoryAlreadyExistsError as ex:
                logger.info(
                    "%s already exists on disk. Assuming it's up-to-date", module.name,
                )
                module_path = ex.path

            self.add_dependency(module.name, module.variable, module_path)

    @property
    def variable_to_version(self) -> dict[str, VersionInfo]:
        res = {}
        for path, dep in self.group.all_modules.items():
            if not dep.variable_name:
                continue

            # We downloaded these to the correct paths; they must match...
            res[dep.variable_name] = VersionInfo.from_path(path)
        return res

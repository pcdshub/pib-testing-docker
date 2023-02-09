from __future__ import annotations

import logging
import pathlib
import re
import shlex
from dataclasses import dataclass, field
from typing import ClassVar, Generator, Optional

from whatrecord.makefile import Dependency, DependencyGroup, Makefile

from . import git
from .exceptions import DownloadFailure
from .makefile import get_makefile_for_path
from .spec import GitSource, Module

logger = logging.getLogger(__name__)

# Despite trying to get away from AFS/WEKA/network share paths, I think
# it's best to replicate them in the containers for the time being.
EPICS_SITE_TOP = pathlib.Path("/cds/group/pcds/epics")


@dataclass
class BaseSettings:
    epics_base: pathlib.Path = field(default_factory=pathlib.Path)
    support: pathlib.Path = field(default_factory=pathlib.Path)
    extra_variables: dict[str, str] = field(default_factory=dict)

    def __post_init__(self):
        self.epics_base = self.epics_base.expanduser().resolve()
        self.support = self.support.expanduser().resolve()

    @classmethod
    def from_base_version(
        cls, base: Module, extra_variables: Optional[dict[str, str]] = None
    ):
        base_path = base.install_path or EPICS_SITE_TOP / "base" / base.version
        if base.install_path is not None:
            # TODO get rid of this inconsistency
            support = EPICS_SITE_TOP / base.install_path.parts[-1] / "modules"
        else:
            support = EPICS_SITE_TOP / base.version / "modules"

        return cls(
            epics_base=base_path,
            support=support,
            extra_variables=dict(extra_variables or {}),
            # epics_site_top=pathlib.Path("/cds/group/pcds/"),
        )

    def get_path_for_module(self, module: Module) -> pathlib.Path:
        if module.install_path is not None:
            return module.install_path

        tag = module.version
        if "-branch" in tag:
            tag = tag.replace("-branch", "")
        return self.support / module.name / tag

    def get_path_for_version_info(self, version: VersionInfo) -> pathlib.Path:
        """
        Get the cache path for the provided dependency with version
        information.

        Parameters
        ----------
        version : VersionInfo
            The version information for the dependency, either derived by way
            of introspection or manually.

        Returns
        -------
        pathlib.Path

        """
        tag = version.tag
        if "-branch" in tag:
            tag = tag.replace("-branch", "")
        return self.support / version.name / tag

    @property
    def variables(self) -> dict[str, str]:
        variables = {
            "EPICS_BASE": str(self.epics_base),
            # TODO where do things like this go?
            # "EPICS_MODULES": str(self.support),
            # "SUPPORT": str(self.support),
            "RE2C": "re2c",
        }
        variables.update(self.extra_variables)
        return variables


@dataclass
class VersionInfo:
    name: str
    base: str
    tag: str

    _module_path_regexes_: ClassVar[list[re.Pattern]] = [
        re.compile(
            base_path + "/"
            r"(?P<base>[^/]+)/"
            r"modules/"
            r"(?P<name>[^/]+)/"
            r"(?P<tag>[^/]+)/?"
        )
        for base_path in ("/cds/group/pcds/epics", "/reg/g/pcds/epics")
    ]

    @property
    def path(self) -> pathlib.Path:
        if self.name == "epics-base":
            return EPICS_SITE_TOP / "base" / self.tag
        return EPICS_SITE_TOP / self.tag / "modules"

    def to_module(self, variable_name: str) -> Module:
        return Module(
            name=self.name,
            variable=variable_name,
            # install_path=self.path,  # if include_path
            git=GitSource(
                url=f"https://github.com/slac-epics/{self.name}",
                tag=self.tag,
            ),
        )

    @classmethod
    def from_path(cls, path: pathlib.Path) -> Optional[VersionInfo]:
        path_str = str(path.resolve())
        # TODO some sort of configuration
        for regex in cls._module_path_regexes_:
            match = regex.match(path_str)
            if match is None:
                continue
            return cls(**match.groupdict())
        return None


@dataclass
class MissingDependency:
    variable: str
    path: pathlib.Path
    version: Optional[VersionInfo]


def get_build_order(
    dependencies: list[Dependency],
    build_first: Optional[list[str]] = None,
    skip: Optional[list[str]] = None,
) -> list[str]:
    """
    Get the build order by variable name.

    Returns
    -------
    list of str
        List of Makefile-defined variable names, in order of how they
        should be built.
    """
    # TODO: order based on dependency graph could/should be done efficiently
    skip = list(skip or [])
    build_order = list(build_first or ["EPICS_BASE"])
    variable_to_dependency = {str(dep.variable_name): dep for dep in dependencies}
    remaining = set(variable_to_dependency) - set(build_order) - set(skip)
    last_remaining = None
    remaining_requires = {
        dep: list(
            var
            for var in variable_to_dependency[dep].dependencies
            if var != dep
        )
        for dep in remaining
    }
    logger.debug(
        "Trying to determine build order based on these requirements: %s",
        remaining_requires
    )
    while remaining:
        for to_check_name in sorted(remaining):
            dep = variable_to_dependency[to_check_name]
            if all(subdep in build_order for subdep in dep.dependencies):
                build_order.append(to_check_name)
                remaining.remove(to_check_name)
        if last_remaining == remaining:
            remaining_requires = {
                dep: list(variable_to_dependency[dep].dependencies)
                for dep in remaining
            }
            logger.warning(
                f"Unable to determine build order.  Determined build order:\n"
                f"{build_order}\n"
                f"\n"
                f"Remaining:\n"
                f"{remaining}\n"
                f"\n"
                f"which require:\n"
                f"{remaining_requires}"
            )
            for remaining_dep in remaining:
                build_order.append(remaining_dep)
            break

        last_remaining = set(remaining)

    logger.debug("Determined build order: %s", ", ".join(build_order))
    return build_order


def get_makefile_for_module(module: Module, settings: BaseSettings) -> Makefile:
    path = settings.get_path_for_module(module)
    return get_makefile_for_path(path, epics_base=settings.epics_base)


def get_dependency_group_for_module(
    module: Module,
    settings: BaseSettings,
    recurse: bool = True,
    name: Optional[str] = None,
    variable_name: Optional[str] = None,
    keep_os_env: bool = False,
) -> DependencyGroup:
    makefile = get_makefile_for_module(module, settings)
    return DependencyGroup.from_makefile(
        makefile,
        recurse=recurse,
        variable_name=variable_name or module.variable,
        name=name or module.name,
        keep_os_env=keep_os_env
    )


def download_module(module: Module, settings: BaseSettings, exist_ok: bool = False) -> pathlib.Path:
    if module.install_path is not None:
        path = module.install_path
    else:
        path = settings.get_path_for_module(module)

    if path.exists():
        if not path.is_dir():
            raise RuntimeError(f"File exists where module should go: {path}")
        if not exist_ok:
            raise RuntimeError(f"Directories must be empty prior to the download step: {path}")

        # raise NotImplementedError("Checking / updating existing download (TODO)?")
        return path

    if module.git is None:
        raise NotImplementedError("only git-backed modules supported at the moment")

    logger.info("Downloading module %s to %s", module.name, path)
    if git.clone(
        module.git.url,
        to_path=path,
        depth=module.git.depth,
        recursive=module.git.recursive,
        args=shlex.split(module.git.args or ""),
    ):
        raise DownloadFailure(
            f"Failed to download {module.git.url}; git returned a non-zero exit code"
        )

    return path


def find_missing_dependencies(dep: Dependency) -> Generator[MissingDependency, None, None]:
    """
    Using module path conventions, find all missing dependencies.

    ``missing_paths`` is allowed to be mutated during iteration.

    See Also
    --------
    :func:`VersionInfo.from_path`
    """
    for var, path in list(dep.missing_paths.items()):
        logger.debug("Checking missing path: %s", path)
        version_info = VersionInfo.from_path(path)
        missing = MissingDependency(
            variable=var,
            path=path,
            version=version_info,
        )
        if version_info is None:
            logger.debug("Dependency path for %s=%s does not match known patterns", var, path)
        else:
            logger.debug("Missing path matches version information: %s", version_info)
        yield missing

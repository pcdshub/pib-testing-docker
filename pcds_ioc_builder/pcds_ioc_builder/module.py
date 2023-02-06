from __future__ import annotations

import dataclasses
import logging
import pathlib
import shlex
import re
from dataclasses import field, dataclass
from typing import ClassVar, Optional, Generator

from whatrecord.makefile import Dependency, DependencyGroup, Makefile
from .exceptions import DownloadFailure
from . import git
from .spec import GitSource, Module
from .makefile import get_makefile_for_path
from .util import call_make

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
            variable=variable_name,
            install_path=self.path,
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

    # def to_cue(self, variable_name: str) -> dict[str, Any]:
    #     prefix_name = variable_name
    #     default_owner = cue.setup.get("REPOOWNER", "slac-epics")
    #     res = {
    #         "": self.tag or "master",
    #         "_DIRNAME": self.name,
    #         "_REPONAME": repo_name_overrides.get(self.name, self.name),
    #         "_REPOOWNER": repo_owner_overrides.get(default_owner, default_owner),
    #         "_VARNAME": variable_name,  # for RELEASE.local
    #         "_RECURSIVE": "YES",
    #         "_DEPTH": "-1",
    #     }
    #     res["_REPOURL"] = "https://github.com/{_REPOOWNER}/{_REPONAME}.git".format(
    #         **res
    #     )
    #     return {
    #         f"{prefix_name}{key}": value
    #         for key, value in res.items()
    #     }


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


def download_module(module: Module, settings: BaseSettings) -> pathlib.Path:
    if module.install_path is not None:
        path = module.install_path
    else:
        path = settings.get_path_for_module(module)

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


@dataclasses.dataclass
class Inspector:
    group: DependencyGroup
    settings: BaseSettings
    variable_to_dependency: dict[str, Dependency] = dataclasses.field(default_factory=dict)

    def add_dependency(
        self,
        name: str,
        variable_name: str,
        path: pathlib.Path,
        reset_configure: bool = True,
        build: bool = False,
    ) -> Optional[Dependency]:
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
        # cue_variable_name = cue_set_name_overrides.get(variable_name, variable_name)
        logger.info("Updating cue settings for dependency %s: %s", variable_name, path)
        # self.update_settings(version.to_cue(cue_variable_name), overwrite=True)
        # self.variable_to_version[variable_name] = version
        # self._cue.add_dependency(cue_variable_name)

        if reset_configure:
            git.reset_repo_directory(variable_name, "configure")

        makefile = get_makefile_for_path(
            path,
            epics_base=self.settings.epics_base,
            variables=self.settings.variables,
        )
        dep = Dependency.from_makefile(
            makefile,
            recurse=True,
            name=name,
            variable_name=variable_name,
            root=self.group,
        )
        self.variable_to_dependency[variable_name] = dep

        if build:
            # self.module_release_local.touch(exist_ok=True)
            # setup_for_build(CueOptions())
            call_make(path=path, parallel=4, silent=True)

        return dep

    def use_epics_base_by_path(self, path: pathlib.Path, build: bool = True, reset_configure: bool = True):
        """
        Add EPICS_BASE as a dependency given its path.
        """
        # version_info = VersionInfo.from_path(path)
        self.add_dependency("EPICS_BASE", path, reset_configure=reset_configure)
        # base_path = self.settings.get_path_for_version_info(base_version)
        if build:
            # self.module_release_local.touch(exist_ok=True)
            # setup_for_build(CueOptions())
            call_make(path=path, parallel=4, silent=True)

    def use_epics_base_tag(self, tag: str, build: bool = True, reset_configure: bool = True):
        """
        Add EPICS_BASE as a dependency given the provided tag.

        Parameters
        ----------
        tag : str
            The epics-base tag to use.
        build : bool, optional
            Build epics-base now.  Defaults to False.
        reset_configure : bool, optional
            Reset epics-base/configure/* to the git HEAD, if changed.
        """
        # with open(self.cache_path / "RELEASE_SITE", "wt") as fp:
        #     print(f"EPICS_SITE_TOP={cache_base}", file=fp)
        #     print(f"BASE_MODULE_VERSION={tag}", file=fp)
        #     print("EPICS_MODULES=$(EPICS_SITE_TOP)/modules", file=fp)

        # tagged_base_path = self.cache_path / "base" / tag
        # if tagged_base_path.exists() and tagged_base_path.is_symlink():
        #     tagged_base_path.unlink()

        # os.symlink(
        #     # modules/epics-base-... ->
        #     self.get_path_for_version_info(base_version),
        #     # base/tag/...
        #     tagged_base_path
        # )
        base_version = VersionInfo(
            name="epics-base",
            base=tag,
            tag=tag,
        )
        self.use_epics_base_by_path(
            path=base_version.path, build=build, reset_configure=reset_configure
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
                dep.variable_name in checked
                for dep in self.group.all_modules.values()
            )

        while not done():
            deps = list(self.group.all_modules.values())
            for dep in deps:
                if dep.variable_name in checked:
                    continue
                checked.add(dep.variable_name)
                yield dep

    def find_all_missing_dependencies(self):
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
                "\n    ".join(f"{var}={value}" for var, value in dep.dependencies.items()),
                "\n    ".join(f"{var}={value}" for var, value in dep.missing_paths.items()),
            )

            for var, _, version_info in find_missing_dependencies(dep):
                yield dep, var, version_info

    def add_all_dependencies(self):
        """
        Using module path conventions, find all dependencies and check them
        out to the cache directory.

        See Also
        --------
        :func:`VersionInfo.from_path`
        """
        all_deps = {}

        for dep, var, version_info in self.find_all_missing_dependencies():
            sub_dep = self.add_dependency(variable_name=var, version=version_info)
            if sub_dep is None:
                continue

            dep.missing_paths.pop(var, None)
            dep.dependencies[var] = self.settings.get_path_for_version_info(
                version_info
            )
            logger.info(
                "Set dependency of %s: %s=%s",
                dep.variable_name or "the IOC",
                var,
                dep.dependencies[var],
            )

        for dep, var, version_info in self.find_all_missing_dependencies():
            dep.dependencies[var] = all_deps[var]

    @classmethod
    def from_path(cls, path: pathlib.Path, settings: BaseSettings, recurse: bool = True):
        path = path.expanduser().resolve()
        if path.parts[-1] == "Makefile":
            makefile_path = path
            path = path.parent
        else:
            makefile_path = path / "Makefile"

        inspector.use_epics_base(VersionInfo.from_path())
        self.group = self._create_dependency_group()
        dep = self.group.all_modules[self.group.root]
        logger.debug(
            (
                "Checking the primary target for dependencies after epics-base installation. \n"
                "\nExisting dependencies:\n"
                "    %s"
                "\nMissing paths: \n"
                "    %s"
            ),
            "\n    ".join(f"{var}={value}" for var, value in dep.dependencies.items()),
            "\n    ".join(f"{var}={value}" for var, value in dep.missing_paths.items()),
        )

        makefile = Makefile.from_file(makefile_path)
        group = DependencyGroup.from_makefile(makefile, recurse=recurse)
        inspector = cls(
            group=group,
            settings=settings,
        )
        return inspector


def find_missing_dependencies(dep: Dependency) -> Generator[tuple[str, pathlib.Path, VersionInfo], None, None]:
    """
    Using module path conventions, find all missing dependencies.

    ``missing_paths`` is allowed to be mutated during iteration.

    See Also
    --------
    :func:`VersionInfo.from_path`
    """
    for var, path in list(dep.missing_paths.items()):
        print("checking missing path", path)
        version_info = VersionInfo.from_path(path)
        if version_info is None:
            logger.debug(
                "Dependency path for %s=%s does not match known patterns", var, path
            )
        else:
            yield var, path, version_info


class CueShim:
    """
    A shim around epics-cue so I can keep it in one place and refactor if need
    be.
    """

    #: Cache path where all dependencies go.
    cache_path: pathlib.Path
    #: whatrecord dependency information keyed by build variable name.
    variable_to_dependency: dict[str, Dependency]
    #: epics-base to use in the initial setup stage with whatrecord, required
    #: for the GNU make-based build system
    introspection_paths: PcdsBuildPaths
    #: The top-level whatrecord dependency group which gets updated as we
    #: check out more dependencies.
    group: Optional[DependencyGroup]
    #: The subdirectory of the cache path where modules are stored.  Kept this
    #: way for SLAC EPICS to have RELEASE_SITE there (TODO)
    module_cache_path: pathlib.Path
    #: The default repository organization for modules.
    repo_owner: str
    #: Where generated cue.py 'set' files are to be stored.
    set_path: pathlib.Path
    #: Version information by variable name, derived from whatrecord-provided
    #: makefile introspection.
    variable_to_version: dict[str, VersionInfo]

    # def __init__(
    #     self,
    #     target_path: pathlib.Path,
    #     set_path: pathlib.Path = MODULE_PATH / "cache" / "sets",
    #     cache_path: pathlib.Path = MODULE_PATH / "cache",
    #     local: bool = False,
    #     github_org: str = "slac-epics",
    # ):
    #     self.cache_path = cache_path
    #     self.module_cache_path = cache_path / "modules"
    #     self.variable_to_dependency = {}
    #     self.variable_to_version = {}
    #     self.introspection_paths = PcdsBuildPaths()
    #     self.target_path = target_path
    #     self.group = None
    #     self.set_path = set_path
    #     self.local = local
    #     self.github_org = github_org
    #     self._import_cue()

    # def _patch_cue(self) -> None:
    #     """
    #     Monkeypatch cue to do what we expect:

    #     *. Patch `call_git` to insert `--template` in git clone, allowing
    #         us to intercept invalid AFS submodules
    #     """

    #     def call_git(args: List[str], **kwargs):
    #         if args and args[0] == "clone":
    #             git_template_path = MODULE_PATH / "git-template"
    #             args.insert(1, f"--template={git_template_path}")
    #         return orig_call_git(args, **kwargs)

    #     orig_call_git = self._cue.call_git
    #     self._cue.call_git = call_git

    def create_set_text(self) -> str:
        """
        Generate the .set file contents based on the configured versions.

        Returns
        -------
        str
            The .set file contents.
        """
        result = []
        for variable in ["EPICS_BASE"] + self.get_build_order():
            version = self.variable_to_version[variable]
            cue_set_name = cue_set_name_overrides.get(variable, variable)
            for key, value in version.to_cue(cue_set_name).items():
                result.append(f"{key}={value}")
        return "\n".join(result)

    def write_set_to_file(self, name: str) -> pathlib.Path:
        """
        Write a cue .set file to the setup directory.

        Parameters
        ----------
        name : str
            The name of the .set file to write.

        Returns
        -------
        pathlib.Path
            The path to the file that was written.
        """
        self.set_path.mkdir(parents=True, exist_ok=True)
        set_filename = self.set_path / f"{name}.set"
        with open(set_filename, "wt") as fp:
            print(self.create_set_text(), file=fp)
        return set_filename

    def _create_dependency_group(self) -> DependencyGroup:
        """
        Set the primary target - IOC or module - path.

        Returns
        -------
        DependencyGroup
            The top-level `DependencyGroup` which is what whatrecord uses
            to track dependencies.
        """
        # TODO: RELEASE_SITE may need to be generated if unavailable;
        # see eco-tools
        # release_site = path / "RELEASE_SITE"
        # if release_site.exists():
        #     shutil.copy(release_site, self.cache_path)

        # Make sure any previous modifications don't change our introspection efforts:
        # TODO: instead, make the path matcher accept the cache directory, and
        # match {cache_path}/modules/{module}-{version}
        self.git_reset_repo_directory(None, "configure")

        makefile = self.get_makefile_for_path(self.target_path)
        return DependencyGroup.from_makefile(makefile)

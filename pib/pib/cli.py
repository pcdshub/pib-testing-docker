"""`pib` is the top-level command for accessing various subcommands."""

from __future__ import annotations

import json
import logging
import os
import pathlib
import sys
import typing
from typing import Optional, TypedDict, cast

import apischema
import click
import yaml

from . import build
from .exceptions import EpicsModuleNotFoundError
from .spec import Application, Module, Requirements, SpecificationFile

if typing.TYPE_CHECKING:
    import io
    from collections.abc import Generator

DESCRIPTION = __doc__
AUTO_ENVVAR_PREFIX = "BUILDER"

logger = logging.getLogger(__name__)


class CliContext(TypedDict):
    """Click CLI context dictionary."""

    specs: build.Specifications
    exclude_modules: list[str]
    only_modules: list[str]


def get_included_modules(ctx: click.Context) -> Generator[Module, None, None]:
    info = cast(CliContext, ctx.obj)

    for module in info["specs"].modules:
        if build.should_include(module, info["only_modules"], info["exclude_modules"]):
            yield module
        else:
            logger.debug("Skipping module: %s", module.name)


def print_version(
    ctx: click.Context,
    param: click.Parameter,  # noqa: ARG001
    value: bool,
) -> None:
    if not value or ctx.resilient_parsing:
        return

    from . import __version__
    print(__version__)  # noqa: T201
    ctx.exit()


@click.group(chain=True)
@click.pass_context
@click.option(
    "-l",
    "--log",
    "log_level",
    type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR"], case_sensitive=False),
    default="INFO",
)
@click.option(
    "--version",
    is_flag=True,
    callback=print_version,
    expose_value=False,
    is_eager=True,
)
@click.option(
    "-s",
    "--spec",
    "spec_files",  # -> env: BUILDER_SPEC_FILES with [semi]colon delimiter
    help="Spec filenames to load",
    type=click.Path(
        exists=True,
        dir_okay=False,
        readable=True,
        resolve_path=True,
        allow_dash=True,  # <-- TODO support stdin
        path_type=pathlib.Path,
    ),
    multiple=True,
    required=True,
)
@click.option(
    "--exclude",
    "exclude_modules",
    help=(
        "Exclude these modules when performing actions, "
        "by variable name or spec-defined name"
    ),
    type=str,
    multiple=True,
    required=False,
)
@click.option(
    "--exclude-from",
    "exclude_from",
    help="Exclude modules from this file when performing actions",
    type=click.Path(
        exists=True,
        dir_okay=False,
        readable=True,
        resolve_path=True,
        allow_dash=False,  # <-- TODO support stdin
        path_type=pathlib.Path,
    ),
    multiple=True,
    required=False,
)
@click.option(
    "--only",
    "only_modules",
    help="Include only these modules (by variable name or spec-defined name)",
    type=str,
    multiple=True,
    required=False,
)
# @click.option(
#     "--only-from",
#     "only_from",
#     help="Include modules from this file when performing actions",
#     type=click.Path(
#         exists=True,
#         dir_okay=False,
#         readable=True,
#         resolve_path=True,
#         allow_dash=False,  # <-- TODO support stdin
#         path_type=pathlib.Path,
#     ),
#     multiple=True,
#     required=False,
# )
def cli(
    ctx: click.Context,
    *,
    log_level: str,
    spec_files: list[str | pathlib.Path],
    exclude_modules: list[str],
    exclude_from: list[str | pathlib.Path],
    only_modules: list[str],
    # only_from: list[str | pathlib.Path],
) -> None:
    logger.info(
        f"Main: {log_level=} {spec_files=} {exclude_modules=} "
        f"{only_modules=} {exclude_from=}",
    )
    ctx.ensure_object(dict)

    module_logger = logging.getLogger("pib")
    module_logger.setLevel(log_level)
    logging.basicConfig()

    spec_files = list(spec_files)
    exclude_modules = list(exclude_modules)

    # NOTE: gather env vars and add them to the list
    # TODO: this is not what click would do normally; is this OK?
    env_paths = os.environ.get(f"{AUTO_ENVVAR_PREFIX}_SPEC_FILES", "")
    if env_paths:
        for path_str in reversed(
            env_paths.split(os.pathsep),
        ):
            path = pathlib.Path(path_str).expanduser().resolve()
            if path not in spec_files:
                logger.debug("Adding spec file from environment: %s", path)
                spec_files.insert(0, path)
            else:
                logger.debug("Spec file from environment already in list: %s", path)

    logger.debug("Spec file list: %s", spec_files)
    specs = build.Specifications.from_spec_files(spec_files)

    for name in exclude_modules:
        try:
            module = specs.find_module_by_name(name)
        except EpicsModuleNotFoundError:
            logger.warning("Excluded modules: %s", exclude_modules)
        else:
            logger.debug("Excluding module: %s", module)

    exclude_from_specs = build.Specifications.from_spec_files(exclude_from)

    if exclude_from_specs.modules:
        logger.debug("Excluding modules from files: %s", exclude_from)
        for module in exclude_from_specs.all_modules:
            if module.name not in exclude_modules and module.variable not in exclude_modules:
                logger.debug("Excluding module: %s", module)
                exclude_modules.append(module.name)

    ctx.obj["specs"] = specs
    ctx.obj["exclude_modules"] = exclude_modules
    ctx.obj["only_modules"] = only_modules


@cli.command(
    "build",
    help="Recursively build everything in the spec",
)
@click.option(
    "--stop-on-failure/--continue-on-failure",
    default=True,
    help="Stop builds on the first failure",
)
@click.pass_context
def cli_build(ctx: click.Context, stop_on_failure: bool = False) -> None:
    logger.info(f"Build: {stop_on_failure=}")
    info = cast(CliContext, ctx.obj)
    return build.build(
        info["specs"],
        stop_on_failure=stop_on_failure,
        skip=info["exclude_modules"],
    )


@cli.command(
    "download",
    help="Download modules listed in the spec files, optionally ",
)
# @click.option(
#     "--include-deps/--exclude-deps",
#     default=True,
#     help="Do not download dependencies",
# )
@click.pass_context
def cli_download(
    ctx: click.Context,
    # include_deps: bool,
    # release_site: bool,
) -> None:
    logger.info("Download")
    info = cast(CliContext, ctx.obj)

    build.download_spec_modules(
        info["specs"],
        # include_deps=include_deps,
        skip=info["exclude_modules"],
        only=info["only_modules"],
        exist_ok=True,
    )


@cli.command(
    "release_site",
    help="Create a RELEASE_SITE file.",
)
@click.option(
    "--output",
    help="Path to write release_site file to",
    type=click.Path(
        dir_okay=False,
        path_type=pathlib.Path,
    ),
    default=None,
    required=False,
)
@click.pass_context
def cli_release_site(ctx: click.Context, output: Optional[pathlib.Path]) -> None:
    logger.info("RELEASE_SITE")
    info = cast(CliContext, ctx.obj)
    build.create_release_site(info["specs"], path=output)


@cli.command(
    "patch",
    help="Apply patches from spec files",
)
@click.pass_context
def cli_patch(ctx: click.Context) -> None:
    logger.info("Patch")
    info = cast(CliContext, ctx.obj)
    specs = info["specs"]
    for module in get_included_modules(ctx):
        build.patch_module(module, specs.settings)


@cli.command(
    "inspect",
    help="Introspect an IOC/module and [optionally] recursively download dependencies",
)
@click.argument(
    "ioc_path",
    type=click.Path(
        exists=True,
        dir_okay=True,
        file_okay=False,
        readable=True,
        resolve_path=True,
        allow_dash=False,
        path_type=pathlib.Path,
    ),
    required=True,
)
@click.option(
    "-o",
    "--output",
    # help="Path to write to (stdout by default)",
    type=click.File(
        mode="wt",
        lazy=True,
    ),
    default=sys.stdout,
)
@click.option(
    "--download/--no-download",
    default=True,
    help="Download missing dependencies and recursively inspect them",
)
@click.pass_context
def cli_inspect(
    ctx: click.Context,
    ioc_path: pathlib.Path,
    output: io.TextIOBase,
    download: bool = True,
    # recurse: bool = True,
    # name: str = "",
    # variable_name: str = "",
) -> None:
    logger.info(
        "Inspect: ioc_path=%s output=%s download=%s",
        ioc_path, output, download,
    )

    info = cast(CliContext, ctx.obj)
    specs = info["specs"]
    specs.check_settings()

    app = Application()
    extra_modules = []
    specs.applications[ioc_path] = app

    logger.debug("Checking for makefile in path: %s", ioc_path)
    logger.debug(
        "EPICS base path for introspection: %s (%s)",
        specs.settings.epics_base,
        specs.settings,
    )

    inspector = build.RecursiveInspector.from_path(ioc_path, specs)
    if download:
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
    serialized = apischema.serialize(
        SpecificationFile,
        file,
        exclude_defaults=True,
        exclude_none=True,
    )
    result = yaml.dump(serialized, indent=2, sort_keys=False)

    logger.debug("Writing to %s:\n'''\n%s\n'''", output, result)
    output.write(result)

    if output is not sys.stdout:
        output.flush()
        output.close()


@cli.command(
    "parse",
    help="Parse the spec files and output a JSON summary",
)
@click.pass_context
def cli_parse(ctx: click.Context) -> None:
    # TODO: remove?
    logger.info("Parse")
    info = cast(CliContext, ctx.obj)

    specs = info["specs"]
    serialized = apischema.serialize(build.Specifications, specs)
    print(json.dumps(serialized, indent=2))  # noqa: T201


@cli.command(
    "requirements",
    help="Summarize all requirements and list them",
)
@click.argument(
    "source",
    required=False,
    type=click.Choice(["yum", "apt", "conda"]),
    default=None,
)
@click.pass_context
def cli_requirements(ctx: click.Context, source: Optional[str] = None) -> None:
    logger.info("Requirements: source=%s", source)
    info = cast(CliContext, ctx.obj)
    specs = info["specs"]

    if source is None:
        reqs = apischema.serialize(Requirements, specs.requirements)
        print(json.dumps(reqs, indent=2))  # noqa: T201
    else:
        for req in getattr(specs.requirements, source):
            print(req)  # noqa: T201


@cli.command(
    "sync",
    help="Synchronize paths for all dependencies (RELEASE file variables)",
)
@click.pass_context
def cli_sync(ctx: click.Context) -> None:
    logger.info("Sync")
    info = cast(CliContext, ctx.obj)
    specs = info["specs"]

    logger.info(
        "Synchronizing dependencies with these paths:\n    %s",
        "\n    ".join(
            f"{var}={value}" for var, value in specs.variable_name_to_path.items()
        ),
    )
    build.sync(specs, skip=info["exclude_modules"])


def main() -> None:
    return cli(auto_envvar_prefix=AUTO_ENVVAR_PREFIX)


if __name__ == "__main__":
    main()

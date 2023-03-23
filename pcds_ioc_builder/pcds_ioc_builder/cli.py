"""
`pcds-ioc-builder` is the top-level command for accessing various subcommands.
"""

import io
import json
import logging
import os
import pathlib
import sys
from collections.abc import Generator
from typing import Optional, TypedDict, cast

import apischema
import click
import yaml

import pcds_ioc_builder

from . import build
from .spec import Application, Module, Requirements, SpecificationFile

DESCRIPTION = __doc__
AUTO_ENVVAR_PREFIX = "BUILDER"

logger = logging.getLogger(__name__)


class CliContext(TypedDict):
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


def print_version(ctx: click.Context, param: click.Parameter, value: bool):
    if not value or ctx.resilient_parsing:
        return
    print(pcds_ioc_builder.__version__)
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
    help="Exclude these modules (by variable name or spec-defined name)",
    type=str,
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
def cli(
    ctx: click.Context,
    log_level: str,
    spec_files: list[str | pathlib.Path],
    exclude_modules: list[str],
    only_modules: list[str],
):
    logger.info(f"Main: {log_level=} {spec_files=} {exclude_modules=} {only_modules=}")
    ctx.ensure_object(dict)

    module_logger = logging.getLogger("pcds_ioc_builder")
    module_logger.setLevel(log_level)
    logging.basicConfig()

    spec_files = list(spec_files)

    # NOTE: gather env vars and add them to the list
    # TODO: this is not what click would do normally; is this OK?
    for path in reversed(
        os.environ[f"{AUTO_ENVVAR_PREFIX}_SPEC_FILES"].split(os.pathsep)
    ):
        path = pathlib.Path(path).expanduser().resolve()
        if path not in spec_files:
            logger.debug("Adding spec file from environment: %s", path)
            spec_files.insert(0, path)
        else:
            logger.debug("Spec file from environment already in list: %s", path)

    logger.debug("Spec file list: %s", spec_files)
    specs = build.Specifications.from_spec_files(spec_files)
    ctx.obj["specs"] = specs
    ctx.obj["exclude_modules"] = exclude_modules
    ctx.obj["only_modules"] = only_modules


@cli.command("build")
@click.option(
    "--continue-on-failure/--stop-on-failure",
    help="Stop builds on the first failure",
)
@click.pass_context
def cli_build(ctx: click.Context, continue_on_failure: bool = False):
    logger.info(f"Build: {continue_on_failure=}")
    info = cast(CliContext, ctx.obj)
    print(continue_on_failure)
    return build.build(
        info["specs"],
        stop_on_failure=not continue_on_failure,
        skip=info["exclude_modules"],
    )


@cli.command("download")
@click.option(
    "--include-deps/--exclude-deps",
    default=True,
    help="Do not download dependencies",
)
@click.option(
    "--release-site/--no-release-site",
    default=True,
    help="Create a RELEASE_SITE file",
)
@click.pass_context
def cli_download(
    ctx: click.Context,
    include_deps: bool,
    release_site: bool,
):
    logger.info(f"Download: {include_deps=} {release_site=}")
    info = cast(CliContext, ctx.obj)

    build.download_spec_modules(
        info["specs"],
        include_deps=include_deps,
        skip=info["exclude_modules"],
        only=info["only_modules"],
        exist_ok=True,
    )

    if release_site:
        build.create_release_site(info["specs"])


@cli.command("patch")
@click.pass_context
def cli_patch(ctx: click.Context):
    logger.info("Patch")
    info = cast(CliContext, ctx.obj)
    specs = info["specs"]
    for module in get_included_modules(ctx):
        build.patch_module(module, specs.settings)


@cli.command("inspect")
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
):
    logger.info(f"Inspect: {ioc_path=} {output=}")

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


@cli.command("parse")
@click.pass_context
def cli_parse(ctx: click.Context):
    logger.info("Parse")
    info = cast(CliContext, ctx.obj)

    specs = info["specs"]
    serialized = apischema.serialize(build.Specifications, specs)
    print(json.dumps(serialized, indent=2))


@cli.command("requirements")
@click.argument(
    "source",
    required=False,
    type=click.Choice(["yum", "apt", "conda"]),
    default=None,
)
@click.pass_context
def cli_requirements(ctx: click.Context, source: Optional[str] = None):
    logger.info(f"Requirements: {source=}")
    info = cast(CliContext, ctx.obj)
    specs = info["specs"]

    if source is None:
        reqs = apischema.serialize(Requirements, specs.requirements)
        print(json.dumps(reqs, indent=2))
    else:
        for req in getattr(specs.requirements, source):
            print(req)


@cli.command("sync")
@click.pass_context
def cli_sync(ctx: click.Context):
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


def main():
    return cli(auto_envvar_prefix=AUTO_ENVVAR_PREFIX)


if __name__ == "__main__":
    main()

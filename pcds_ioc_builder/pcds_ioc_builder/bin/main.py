"""
`pcds-ioc-builder` is the top-level command for accessing various subcommands.
"""

import json
import logging
from collections.abc import Generator
from typing import Optional, TypedDict, cast

import apischema
import click

import pcds_ioc_builder

from .. import build
from ..spec import Module, Requirements

DESCRIPTION = __doc__

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
    "spec_files",  # -> env: IOC_BUILDER_SPEC_FILES with comma delimiter
    help="Spec filenames to load",
    type=click.Path(
        exists=True,
        dir_okay=False,
        readable=True,
        resolve_path=True,
        allow_dash=True,  # <-- TODO support stdin
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
    spec_files: list[str],
    exclude_modules: list[str],
    only_modules: list[str],
):
    ctx.ensure_object(dict)

    logger = logging.getLogger("pcds_ioc_builder")
    logger.setLevel(log_level)
    logging.basicConfig()

    specs = build.Specifications.from_spec_files(spec_files)
    ctx.obj["specs"] = specs
    ctx.obj["exclude_modules"] = exclude_modules
    ctx.obj["only_modules"] = exclude_modules


@cli.command("build")
@click.option(
    "--continue-on-failure/--stop-on-failure",
    help="Stop builds on the first failure",
)
@click.pass_context
def cli_build(ctx: click.Context, continue_on_failure: bool = False):
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
    info = cast(CliContext, ctx.obj)
    specs = info["specs"]
    for module in get_included_modules(ctx):
        build.patch_module(module, specs.settings)


@cli.command("inspect")
@click.pass_context
def cli_inspect(ctx: click.Context):
    cast(CliContext, ctx.obj)
    print("inspect")


@cli.command("parse")
@click.pass_context
def cli_parse(ctx: click.Context):
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
    return cli(auto_envvar_prefix="IOC_BUILDER")


if __name__ == "__main__":
    main()

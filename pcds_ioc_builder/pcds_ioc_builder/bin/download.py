import argparse
import logging
from typing import Optional

from .. import build

logger = logging.getLogger(__name__)


def main(
    paths: list[str],
    include_deps: bool = True,
    release_site: bool = True,
    patch: bool = True,
    build_modules: bool = False,
    only: Optional[list[str]] = None,
    skip: Optional[list[str]] = None,
) -> None:
    specs = build.Specifications.from_spec_files(paths)
    build.download_spec_modules(
        specs,
        include_deps=include_deps,
        skip=skip,
        only=only,
        exist_ok=True,
    )

    if release_site:
        build.create_release_site(specs)

    if build_modules:
        build.sync(specs)
        build.build(specs, stop_on_failure=True, only=only, skip=skip)


def build_arg_parser(argparser=None) -> argparse.ArgumentParser:
    if argparser is None:
        argparser = argparse.ArgumentParser()
    argparser.add_argument(
        "paths",
        nargs="+",
        type=str,
        help="Path to module specification",
    )
    argparser.add_argument(
        "--only",
        type=str,
        nargs="*",
        help="Include only these modules",
    )
    argparser.add_argument("--skip", type=str, nargs="*", help="Skip these modules")
    argparser.add_argument(
        "--no-deps",
        action="store_false",
        dest="include_deps",
        help="Do not download dependencies",
    )
    argparser.add_argument(
        "--no-release-site",
        action="store_false",
        dest="release_site",
        help="Do not create a RELEASE_SITE file",
    )
    argparser.add_argument(
        "--no-patches",
        action="store_false",
        dest="patch",
        help="Do not apply patches",
    )
    argparser.add_argument(
        "--build",
        action="store_true",
        dest="build_modules",
        help="Build downloaded modules",
    )
    return argparser


def _main(args=None):
    """Independent CLI entrypoint."""
    parser = build_arg_parser()
    return main(**vars(parser.parse_args(args=args)))


if __name__ == "__main__":
    _main()

"""
`pcds-ioc-builder` is the top-level command for accessing various subcommands.

Try:

"""

import argparse
import asyncio
import importlib
import logging
from inspect import iscoroutinefunction

import pcds_ioc_builder

from ..util import MODULE_PATH

DESCRIPTION = __doc__


command_to_module = {
    module.stem.replace("_", "-"): module.stem
    for module in (MODULE_PATH / "bin").glob("*.py")
    if module.stem not in ("__init__", "main")
}


def _try_import(module):
    relative_module = f".{module}"
    return importlib.import_module(relative_module, "pcds_ioc_builder.bin")


def _build_commands():
    global DESCRIPTION
    result = {}
    unavailable = []

    for command, module in sorted(command_to_module.items()):
        try:
            mod = _try_import(module)
        except Exception as ex:
            unavailable.append((command, ex))
        else:
            result[command] = (mod.build_arg_parser, mod.main)
            DESCRIPTION += f"\n    $ pcds-ioc-builder {command} --help"

    if unavailable:
        DESCRIPTION += "\n\n"

        for module, ex in unavailable:
            DESCRIPTION += (
                f'\nWARNING: "pcds-ioc-builder {module}" is unavailable due to:'
                f"\n\t{ex.__class__.__name__}: {ex}"
            )

    return result


COMMANDS = _build_commands()


def main():
    top_parser = argparse.ArgumentParser(
        prog="pcds-ioc-builder",
        description=DESCRIPTION,
        formatter_class=argparse.RawTextHelpFormatter,
    )

    top_parser.add_argument(
        "--version",
        "-V",
        action="version",
        version=pcds_ioc_builder.__version__,
        help="Show the pcds-ioc-builder version number and exit.",
    )

    top_parser.add_argument(
        "--log",
        "-l",
        dest="log_level",
        default="INFO",
        type=str,
        help="Python logging level (e.g. DEBUG, INFO, WARNING)",
    )

    subparsers = top_parser.add_subparsers(help="Possible subcommands")
    for command_name, (build_func, main) in COMMANDS.items():
        sub = subparsers.add_parser(command_name)
        build_func(sub)
        sub.set_defaults(func=main)

    args = top_parser.parse_args()
    kwargs = vars(args)
    log_level = kwargs.pop("log_level")

    logger = logging.getLogger("pcds_ioc_builder")
    logger.setLevel(log_level)
    logging.basicConfig()

    if hasattr(args, "func"):
        func = kwargs.pop("func")
        logger.debug("%s(**%r)", func.__name__, kwargs)
        if iscoroutinefunction(func):
            asyncio.run(func(**kwargs))
        else:
            func(**kwargs)
    else:
        top_parser.print_help()


if __name__ == "__main__":
    main()

import argparse

from whatrecord.makefile import Dependency

from ..module import (BaseSettings, download_module,
                      get_dependency_group_for_module)
from ..spec import SpecificationFile


def main(base_spec_path: str, paths: list[str], include_deps: bool = True) -> None:
    base_spec = SpecificationFile.from_filename(base_spec_path)
    base = base_spec.modules_by_name["epics-base"]

    settings = BaseSettings.from_base_version(base)

    for path in paths:
        spec = SpecificationFile.from_filename(path)
        for module in spec.modules:
            download_module(module, settings)

    if not include_deps:
        return

    if not settings.epics_base.exists():
        raise RuntimeError(
            f"epics-base required to introspect and download dependencies.  "
            f"Path is {settings.epics_base} from {base_spec_path} module 'epics-base'"
        )

    deps: dict[str, Dependency] = {}
    for path in paths:
        spec = SpecificationFile.from_filename(path)
        for module in spec.modules:
            group = get_dependency_group_for_module(module, settings, recurse=True)
            for path, dep in group.all_modules.items():
                assert dep.variable_name is not None
                deps[dep.variable_name] = dep
                # TODO multiple versions

    print("Overall dependencies:")
    for variable, dep in deps.items():
        print(f"{variable}: {dep.path}")


def build_arg_parser(argparser=None) -> argparse.ArgumentParser:
    if argparser is None:
        argparser = argparse.ArgumentParser()
    argparser.add_argument("base_spec_path", type=str, help="Path to base specification")
    argparser.add_argument("paths", nargs="+", type=str, help="Path to module specification")
    argparser.add_argument("--no-deps", action="store_false", dest="include_deps", help="Do not download dependencies")
    return argparser


def _main(args=None):
    """Independent CLI entrypoint."""
    parser = build_arg_parser()
    return main(**vars(parser.parse_args(args=args)))


if __name__ == "__main__":
    _main()

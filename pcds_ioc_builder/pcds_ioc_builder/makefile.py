import logging
import pathlib
from typing import Any, Optional

from whatrecord.makefile import Makefile

logger = logging.getLogger(__name__)


def get_makefile_for_path(
    path: pathlib.Path,
    epics_base: pathlib.Path,
    variables: Optional[dict[str, str]] = None,
) -> Makefile:
    """
    Get a whatrecord :class:`Makefile` for the provided path.

    Parameters
    ----------
    path : pathlib.Path
        The path to search for a Makefile, or a path to the makefile
        itself.

    Returns
    -------
    Makefile
    """
    variables = dict(variables or {})
    variables["EPICS_BASE"] = str(epics_base)
    return Makefile.from_file(
        Makefile.find_makefile(path),
        keep_os_env=False,
        variables=variables,
    )


def patch_makefile(makefile: pathlib.Path, variables: dict[str, Any]) -> set[str]:
    """
    Patch Makefile variable declarations with those provided in ``variables``.

    Parameters
    ----------
    makefile : pathlib.Path
        Path to the Makefile.
    variables : Dict[str, Any]
        Variable-to-value dictionary.

    Returns
    -------
    Set[str]
        Set of updated variables.
    """
    updated = set()

    def fix_line(line: str) -> str:
        if not line:
            return line
        if line[0] in " \t#":
            return line

        for separator in ("?=", ":=", "="):
            if separator in line:
                line = line.rstrip()
                var, _ = line.split(separator, 1)
                var = var.strip()
                if var in variables:
                    fixed = f"{var}{separator}{variables[var]}"
                    updated.add(var)
                    return fixed

        return line

    with open(makefile, "rt") as fp:
        lines = fp.read().splitlines()

    output_lines = [fix_line(line) for line in lines]
    if updated:
        logger.warning(
            "Patching makefile %s variables %s", makefile, ", ".join(updated)
        )
        with open(makefile, "wt") as fp:
            print("\n".join(output_lines), file=fp)
    else:
        logger.debug("Makefile left unchanged: %s", makefile)
    return updated


def update_related_makefiles(
    base_path: pathlib.Path,
    makefile: Makefile,
    variable_to_value: dict[str, str],
):
    """
    Update makefiles found during the introspection step that exist in ``base_path``.

    Updates module dependency paths based.

    Parameters
    ----------
    base_path : pathlib.Path
        The path to update makefiles under.
    makefile : Makefile
        The primary Makefile that contains paths of relevant included makefiles.
    """
    makefiles = set(makefile.makefile_list)

    # TODO: introspection of some makefiles can error out due to $(error dep not found)
    # which means we can't check the makefiles to update, which means it's
    # entirely broken...
    for path in [
        "configure/RELEASE",
        "configure/RELEASE.local",
    ]:
        if (base_path / path).exists():
            makefiles.add(path)

    for makefile_relative in sorted(makefiles):
        makefile_path = (base_path / makefile_relative).resolve()
        try:
            makefile_path.relative_to(base_path)
        except ValueError:
            logger.debug(
                "Skipping makefile: %s (not relative to %s)",
                makefile_path,
                base_path,
            )
            continue

        try:
            patch_makefile(makefile_path, variable_to_value)
        except PermissionError:
            logger.error("Failed to patch makefile due to permissions: %s", makefile_path)
        except Exception:
            logger.exception("Failed to patch makefile: %s", makefile_path)

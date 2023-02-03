import pathlib
import logging
import subprocess
import shlex
import sys
from typing import Optional, Union

from . import util


logger = logging.getLogger(__name__)


def reset_repo_directory(repo_root: pathlib.Path, directory: str):
    """
    Run git reset (or git checkout --) on a specific subdirectory of a
    dependency.

    Parameters
    ----------
    directory : str
        The subdirectory of that dependency, relative to its root.
    """
    run_git("checkout", "--", directory, cwd=repo_root)


# call_git(['clone', '--quiet'] + deptharg + recursearg + ['--branch', tag, setup[dep + '_REPOURL'], dirname],
#  cwd=ci['cachedir'])
def clone(
    repository: str,
    to_path: pathlib.Path,
    depth: int = 1,
    recursive: bool = True,
    insert_template: bool = True,
    args: Optional[list[str]] = None,
) -> int:
    template_args = []
    if insert_template:
        git_template_path = util.MODULE_PATH / "git-template"
        template_args = [f"--template={git_template_path}"]

    return run_git(
        "clone",
        repository,
        "--depth",
        str(depth),
        *(["--recursive"] if recursive else []),
        *template_args,
        *(args or []),
        str(to_path.expanduser().resolve()),
    )


def run_git(*args, cwd: Optional[Union[pathlib.Path, str]] = None, **call_kwargs) -> int:
    call_kwargs["cwd"] = str(cwd or pathlib.Path.cwd())
    shell_cmd = shlex.join(["git", *args])
    logger.debug("Running '%s' in %s", shell_cmd, cwd)
    sys.stdout.flush()
    exit_code = subprocess.call(['git', *args], **call_kwargs)
    logger.debug("Ran '%s' in %s; exit code=%d", shell_cmd, cwd, exit_code)
    return exit_code


def run_git_check_output(*args, cwd: Optional[Union[pathlib.Path, str]] = None, **call_kwargs) -> str:
    call_kwargs["cwd"] = str(cwd or pathlib.Path.cwd())
    shell_cmd = shlex.join(["git", *args])
    logger.debug("Running '%s' in %s", shell_cmd, cwd)
    sys.stdout.flush()
    raw_output = subprocess.check_output(['git', *args], **call_kwargs)
    output = raw_output.decode()
    logger.debug("Ran '%s' in %s; output=\n%s", shell_cmd, cwd, output)
    return output


def get_git_hash(path: pathlib.Path) -> str:
    return run_git_check_output('log', '-n1', '--pretty=format:%H', cwd=path)

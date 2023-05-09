from __future__ import annotations

import datetime
import logging
import pathlib

MODULE_PATH = pathlib.Path(__file__).resolve().parent


logger = logging.getLogger(__name__)


def dt_now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc).astimezone()


# def apply_patch(file, **kws):
#     place = kws.get('cwd', os.getcwd())
#     logger.info('Applying patch %s in %s', file, place)
#     command = ['patch', '-p1', '-i', file]
#     logger.debug("Running '%s' in %s", shlex.join(command), place)
#     sys.stdout.flush()
#     subprocess.check_call(command, cwd=place)
#     logger.debug('Ran %s', shlex.join(command))


# def extract_archive(file, **kws):
#     place = kws.get('cwd', os.getcwd())
#     print('Extracting archive {0} in {1}'.format(file, place))
#     logger.debug("EXEC '%s' in %s", ' '.join(['7z', 'x', '-aoa', '-bd', file]), place)
#     sys.stdout.flush()
#     sp.check_call(['7z', 'x', '-aoa', '-bd', file], cwd=place)
#     logger.debug('EXEC DONE')


def normalize_path(path: pathlib.Path) -> pathlib.Path:
    """Normalize paths to use /cds/group/pcds instead of /reg/g/pcds."""
    last_path = None
    while path != last_path:
        last_path = path
        path = path.expanduser().resolve()
        if path.parts[:4] == ("/", "reg", "g", "pcds"):
            path = pathlib.Path("/cds/group/pcds") / pathlib.Path(*path.parts[4:])

    return path

import logging
import pathlib
import shlex
import subprocess
import sys
import threading
from typing import Optional

MODULE_PATH = pathlib.Path(__file__).resolve().parent

logger = logging.getLogger(__name__)


def call_make(
    *args: str,
    timeout: Optional[float] = None,
    path: Optional[pathlib.Path] = None,
    parallel: int = 1,
    silent: bool = False,
    is_make3: bool = False,
    **popen_kwargs
) -> int:
    global make_timeout
    if path is None:
        path = pathlib.Path.cwd()

    # no parallel make for Base 3.14
    if parallel <= 1:  # or is_base314:
        makeargs = []
    else:
        makeargs = [f'-j{parallel}']
        if not is_make3:
            makeargs += ['-Otarget']
    if silent:
        makeargs += ['-s']
    # if use_extra:
    #     makeargs += extra_makeargs

    command = ['make', *makeargs, *args]
    logger.debug("Running '%s' in %s", shlex.join(command), path)
    sys.stdout.flush()
    sys.stderr.flush()

    child = subprocess.Popen(command, cwd=path, **popen_kwargs)
    timer = None
    if timeout is not None:
        def expire(child):
            logger.error('Timeout when running make')
            child.terminate()
        timer = threading.Timer(timeout, expire, args=(child,))
        timer.start()

    code = child.wait()
    if timer is not None:
        timer.cancel()
    if code == 0:
        logger.debug('Ran %s successfully', shlex.join(command))
    else:
        logger.error('Ran %s unsuccessfully (code %d)', shlex.join(command), code)
    return code


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

import pathlib


class DownloadFailureError(Exception):
    """Download failure."""

    ...


class SpecificationError(Exception):
    """Specification file error."""

    ...


class EpicsModuleNotFoundError(ValueError):
    """User-specified module name was not found."""

    ...


class TargetDirectoryAlreadyExistsError(RuntimeError):
    """Target directory already exists."""

    path: pathlib.Path


class InvalidSpecificationError(SpecificationError):
    """Invalid specification."""

    ...


class EpicsBaseOnlyOnceError(SpecificationError):
    """epics-base specified multiple times."""

    ...


class EpicsBaseMissingError(Exception):
    """epics-base missing from specification."""

    ...

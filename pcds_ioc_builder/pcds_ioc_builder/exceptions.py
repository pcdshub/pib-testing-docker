import pathlib


class DownloadFailure(Exception):
    ...


class SpecificationError(Exception):
    ...


class TargetDirectoryAlreadyExists(RuntimeError):
    path: pathlib.Path


class InvalidSpecification(SpecificationError):
    ...


class EpicsBaseOnlyOnce(SpecificationError):
    ...


class EpicsBaseMissing(Exception):
    ...

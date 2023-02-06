class DownloadFailure(Exception):
    ...


class SpecificationError(Exception):
    ...


class InvalidSpecification(SpecificationError):
    ...


class EpicsBaseOnlyOnce(SpecificationError):
    ...


class EpicsBaseMissing(Exception):
    ...

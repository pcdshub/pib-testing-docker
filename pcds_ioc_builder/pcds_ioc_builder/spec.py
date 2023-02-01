from __future__ import annotations

import pathlib
import yaml

from dataclasses import dataclass, field
from typing import Optional

import apischema


@dataclass
class MakeOptions:
    args: Optional[str] = ""
    parallel: int = 1


@dataclass
class GitSource:
    url: str
    tag: str
    args: Optional[str] = ""


@dataclass
class Module:
    variable: str
    install_path: Optional[pathlib.Path] = None
    git: Optional[GitSource] = None
    make: Optional[MakeOptions] = field(default_factory=MakeOptions)


@dataclass
class SpecificationFile:
    modules: dict[str, Module]

    @classmethod
    def from_filename(cls, filename: pathlib.Path | str) -> SpecificationFile:
        with open(filename) as fp:
            contents = fp.read()

        serialized = yaml.load(contents, Loader=yaml.Loader)
        return apischema.deserialize(cls, serialized)

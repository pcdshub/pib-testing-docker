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
    depth: int = 5
    recursive: bool = True


@dataclass
class Module:
    name: str
    variable: str = ""
    install_path: Optional[pathlib.Path] = None
    git: Optional[GitSource] = None
    make: Optional[MakeOptions] = field(default_factory=MakeOptions)

    def __post_init__(self):
        if not self.variable:
            self.variable = self.name.replace("-", "_").upper()

    @property
    def version(self) -> str:
        if self.git is not None:
            return self.git.tag
        raise NotImplementedError()


@dataclass
class Application:
    binary: str


@dataclass
class SpecificationFile:
    modules: list[Module] = field(default_factory=list)
    applications: Optional[list[Application]] = None

    @property
    def modules_by_name(self) -> dict[str, Module]:
        return {module.name: module for module in self.modules}

    @classmethod
    def from_filename(cls, filename: pathlib.Path | str) -> SpecificationFile:
        with open(filename) as fp:
            contents = fp.read()

        serialized = yaml.load(contents, Loader=yaml.Loader)
        return apischema.deserialize(cls, serialized)

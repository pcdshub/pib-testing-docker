from __future__ import annotations

import pathlib
from dataclasses import dataclass, field
from typing import Optional

import apischema
import yaml


@dataclass
class MakeOptions:
    args: list[str] = field(default_factory=list)
    parallel: int = 1


@dataclass
class GitSource:
    url: str
    tag: str
    args: Optional[str] = ""
    depth: int = 5
    recursive: bool = True


@dataclass
class Requirements:
    yum: list[str] = field(default_factory=list)
    apt: list[str] = field(default_factory=list)
    conda: list[str] = field(default_factory=list)


@dataclass
class Module:
    name: str
    variable: str = ""
    install_path: Optional[pathlib.Path] = None
    git: Optional[GitSource] = None
    make: Optional[MakeOptions] = field(default_factory=MakeOptions)
    requires: Optional[Requirements] = field(default_factory=Requirements)

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
    standard_modules: list[str] = field(default_factory=list)
    requires: Optional[Requirements] = field(default_factory=Requirements)
    make: Optional[MakeOptions] = field(default_factory=MakeOptions)
    # extra modules just go top-level?
    # extra_modules: list[Module] = field(default_factory=list)


@dataclass
class SpecificationFile:
    modules: list[Module] = field(default_factory=list)
    application: Optional[Application] = None

    @property
    def modules_by_name(self) -> dict[str, Module]:
        return {module.name: module for module in self.modules}

    @classmethod
    def from_filename(cls, filename: pathlib.Path | str) -> SpecificationFile:
        with open(filename) as fp:
            contents = fp.read()

        serialized = yaml.load(contents, Loader=yaml.Loader)
        return apischema.deserialize(cls, serialized)

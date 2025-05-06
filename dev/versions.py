from dataclasses import dataclass
from typing import List, Tuple, Union, Optional, Any
from enum import Enum



class VersionSpecifier:
    Latest : type['LatestVersionSpecifier'] = None # type: ignore

@dataclass
class GithubReference(VersionSpecifier):
    # "github:myorg/myrepo#mybranch"
    owner: str
    repo: str
    ref: str

@dataclass
class TarballReference(VersionSpecifier):
    # "https://example.com/mytarball.tar.gz"
    url: str

@dataclass
class LocalReference(VersionSpecifier):
    # "file:///path/to/myproject"
    path: str

@dataclass
class LatestVersionSpecifier(VersionSpecifier):
    pass

@dataclass
class VersionRangeSpecifier(VersionSpecifier):
    min_version: Version | None
    max_version: Version | None

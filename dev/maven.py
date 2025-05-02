from typing import Any, List, Optional, Tuple
import re
from dataclasses import dataclass
from enum import Enum

##################################################################################################
# Maven Coordinates
##################################################################################################

# Regex pattern for Maven coordinates
MAVEN_COORDINATE_PATTERN = r'''
    ^                                       # Start of string
    ([a-zA-Z_\$][a-zA-Z\d_\$\-\.]+)         # Group ID
    :                                       # Separator
    ([a-zA-Z\d_\$\-\.]+)                    # Artifact ID
    :                                       # Separator
    (.+)                                    # Version
    $                                       # End of string
'''
MAVEN_COORDINATE_RE = re.compile(MAVEN_COORDINATE_PATTERN, re.VERBOSE)

class VersionAxis(Enum):
    ALPHA = 'alpha'
    BETA = 'beta'
    MILESTONE = 'milestone'
    RC = 'rc'
    SNAPSHOT = 'snapshot'
    NUMBER = 'number'
    FINAL = 'final'
    SECURITY_PATCH = 'sp'
    UNKNOWN = 'unk'

@dataclass
class MavenVersionCoordinate:
    axis: VersionAxis
    version: int | str

    @staticmethod
    def from_string(s: str) -> 'MavenVersionCoordinate':
        if all(c.isdigit() for c in s):
            return MavenVersionCoordinate(axis=VersionAxis.NUMBER, version=int(s))

        upper_s = s.upper()

        if upper_s == 'ALPHA':
            return MavenVersionCoordinate(axis=VersionAxis.ALPHA, version=0)
        elif upper_s.startswith('ALPHA'):
            return MavenVersionCoordinate(axis=VersionAxis.ALPHA, version=int(s[5:]))
        # a1, a2, a3, etc. are also valid alpha versions
        elif upper_s.startswith('A'):
            return MavenVersionCoordinate(axis=VersionAxis.ALPHA, version=int(s[1:]))

        if upper_s == 'BETA':
            return MavenVersionCoordinate(axis=VersionAxis.BETA, version=0)
        elif upper_s.startswith('BETA'):
            return MavenVersionCoordinate(axis=VersionAxis.BETA, version=int(s[4:]))
        # b1, b2, b3, etc. are also valid beta versions
        elif upper_s.startswith('B'):
            return MavenVersionCoordinate(axis=VersionAxis.BETA, version=int(s[1:]))

        if upper_s == 'MILESTONE':
            return MavenVersionCoordinate(axis=VersionAxis.MILESTONE, version=0)
        elif upper_s.startswith('MILESTONE'):
            return MavenVersionCoordinate(axis=VersionAxis.MILESTONE, version=int(s[9:]))
        elif upper_s.startswith('M'):
            return MavenVersionCoordinate(axis=VersionAxis.MILESTONE, version=int(s[1:]))

        if upper_s == 'RC':
            return MavenVersionCoordinate(axis=VersionAxis.RC, version=0)
        elif upper_s.startswith('RC'):
            return MavenVersionCoordinate(axis=VersionAxis.RC, version=int(s[2:]))

        if upper_s == 'SNAPSHOT':
            return MavenVersionCoordinate(axis=VersionAxis.SNAPSHOT, version=0)
        elif upper_s == 'FINAL' or upper_s == 'RELEASE' or upper_s == 'GA':
            return MavenVersionCoordinate(axis=VersionAxis.FINAL, version=0)

        if upper_s == 'SP' or upper_s == 'SEC':
            return MavenVersionCoordinate(axis=VersionAxis.SECURITY_PATCH, version=0)

        return MavenVersionCoordinate(axis=VersionAxis.UNKNOWN, version=s)

    def __str__(self):
        match self.axis:
            case VersionAxis.NUMBER:         return str(self.version)
            case VersionAxis.ALPHA:          return 'alpha' if self.version == 0 else f'alpha{self.version}'
            case VersionAxis.BETA:           return 'beta' if self.version == 0 else f'beta{self.version}'
            case VersionAxis.RC:             return 'RC' if self.version == 0 else f'RC{self.version}'
            case VersionAxis.SNAPSHOT:       return 'SNAPSHOT' if self.version == 0 else f'SNAPSHOT{self.version}'
            case VersionAxis.FINAL:          return 'FINAL' if self.version == 0 else f'FINAL{self.version}'
            case VersionAxis.SECURITY_PATCH: return 'SP' if self.version == 0 else f'SP{self.version}'
            case VersionAxis.UNKNOWN:        return str(self.version)
            case VersionAxis.MILESTONE:      return f'M{self.version}'
            case _:                          assert False, f"Unknown version axis: {self.axis}"

    def num_repr(self) -> Tuple[int, int | str]:
        match self.axis:
            case VersionAxis.ALPHA:          return (1, self.version)
            case VersionAxis.BETA:           return (2, self.version)
            case VersionAxis.MILESTONE:      return (3, self.version)
            case VersionAxis.RC:             return (4, self.version)
            case VersionAxis.SNAPSHOT:       return (5, self.version)
            case VersionAxis.SECURITY_PATCH: return (6, self.version)
            case VersionAxis.NUMBER:         return (7, self.version)
            case VersionAxis.FINAL:          return (7, self.version)
            case VersionAxis.UNKNOWN:        return (99, self.version)
            case _:                          assert False, f"Unknown version axis: {self.axis}"

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, MavenVersionCoordinate):
            return False
        return self.num_repr() == other.num_repr()

    def __lt__(self, other: 'MavenVersionCoordinate') -> bool:
        return self.num_repr() < other.num_repr()


@dataclass
class MavenVersion:
    components: List[MavenVersionCoordinate]

    @property
    def major(self) -> int:
        assert len(self.components) > 0, "No major version component"
        assert self.components[0].axis == VersionAxis.NUMBER, "Major version is not a number"
        return int(self.components[0].version)

    @property
    def minor(self) -> int:
        if len(self.components) < 2:
            return 0
        assert self.components[1].axis == VersionAxis.NUMBER, "Minor version is not a number"
        return int(self.components[1].version)

    @property
    def is_snapshot(self) -> bool:
        if not self.components:
            return False
        return self.components[-1].axis == VersionAxis.SNAPSHOT

    @classmethod
    def parse(cls, version_str: str) -> 'MavenVersion':
        components = []

        split_re = re.compile(r'[\._-]')

        for part in split_re.split(version_str):
            components.append(MavenVersionCoordinate.from_string(part))

        return cls(components=components)

    def __str__(self):
        version_str = '.'.join(str(c) for c in self.components)
        return version_str

    def _version_tuple(self) -> Tuple:
        return tuple(self.components)

    def __lt__(self, other: 'MavenVersion') -> bool:
        v1 = self._version_tuple()
        v2 = other._version_tuple()
        for i in range(max(len(v1), len(v2))):
            c1 = v1[i] if i < len(v1) else MavenVersionCoordinate(axis=VersionAxis.NUMBER, version=0)
            c2 = v2[i] if i < len(v2) else MavenVersionCoordinate(axis=VersionAxis.NUMBER, version=0)
            if c1 < c2:
                return True
            if c1 > c2:
                return False
        return False

    def __eq__(self, other: 'MavenVersion') -> bool:
        v1 = self._version_tuple()
        v2 = other._version_tuple()
        for i in range(max(len(v1), len(v2))):
            c1 = v1[i] if i < len(v1) else MavenVersionCoordinate(axis=VersionAxis.NUMBER, version=0)
            c2 = v2[i] if i < len(v2) else MavenVersionCoordinate(axis=VersionAxis.NUMBER, version=0)
            if c1 != c2:
                return False
        return True

    def approx_eq(self, other: 'MavenVersion') -> bool:
        v1 = self._version_tuple()
        v2 = other._version_tuple()
        for i in range(max(len(v1), len(v2))):
            c1 = v1[i] if i < len(v1) else MavenVersionCoordinate(axis=VersionAxis.NUMBER, version=0)
            c2 = v2[i] if i < len(v2) else MavenVersionCoordinate(axis=VersionAxis.NUMBER, version=0)
            if c1 != c2:
                return False
        return True


@dataclass
class MavenCoordinate:
    group_id: str
    artifact_id: str
    version: str

    def __str__(self):
        return f"{self.group_id}:{self.artifact_id}:{self.version}"

    @classmethod
    def parse(cls, coordinate: str) -> 'MavenCoordinate':
        match = MAVEN_COORDINATE_RE.match(coordinate)
        if not match:
            raise ValueError(f"Invalid Maven coordinate: {coordinate}")

        group_id, artifact_id, version_str = match.groups()
        version = version_str # Version.parse(version_str)

        return cls(group_id=group_id, artifact_id=artifact_id, version=version)

def is_valid_maven_coordinate(coordinate: str) -> bool:
    return bool(MAVEN_COORDINATE_RE.match(coordinate))


@dataclass
class MavenMetadata:
    latest: str
    release: str | None
    versions: List[str]
    last_updated: str

    @classmethod
    def parse(cls, xml: str) -> 'MavenMetadata':
        import xml.etree.ElementTree as ET
        root = ET.fromstring(xml.strip())

        latest_tag = root.find("versioning/latest")
        release_tag = root.find("versioning/release")

        return MavenMetadata(
            latest = latest_tag.text if latest_tag is not None else None,
            release = release_tag.text if release_tag is not None else None,
            versions = [v.text for v in root.findall("versioning/versions/version")],
            last_updated = root.find("versioning/lastUpdated").text
        )

from dev.caching import cache

@cache(path=".dev.cache.db")
def fetch_raw_metadata(repo_base_url: str, group_id: str, artifact_id: str) -> str:
    import requests
    url = f"{repo_base_url}{group_id.replace('.', '/')}/{artifact_id}/maven-metadata.xml"
    response = requests.get(url)
    response.raise_for_status()
    return response.text

@cache(path=".dev.cache.db")
def fetch_metadata(repo_base_url: str, group_id: str, artifact_id: str) -> MavenMetadata:
    response = fetch_raw_metadata(repo_base_url, group_id, artifact_id)
    return MavenMetadata.parse(response)


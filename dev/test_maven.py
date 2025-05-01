from dev.maven import *

def assertThrows(func, *args):
    try:
        func(*args)
        assert False, f"Function {func.__name__} did not raise an exception"
    except Exception:
        pass


comparison_ops = {
    "<": lambda a, b: a < b,
    "<=": lambda a, b: a <= b,
    "=": lambda a, b: a == b,
    "~": lambda a, b: a.approx_eq(b) == True,
    "!=": lambda a, b: a != b,
    "!~": lambda a, b: a.approx_eq(b) == False,
    ">=": lambda a, b: a >= b,
    ">": lambda a, b: a > b,
}


def test_version_sequence(vs: str):
    import re
    ops = ["<", "~", "=", "!~", "!=", ">=", ">", "<="]
    op_regex = "|".join(re.escape(op) for op in ops)

    start = 0
    args = []
    ops = []
    for match in re.finditer(op_regex, vs):
        op = match.group()
        ops.append(op)
        end = match.start()
        if end > start:
            v1_str = vs[start:end].strip()
            v1 = MavenVersion.parse(v1_str)
            args.append(v1)
            # assert comparison_ops[op](v1, v2), f"{v1} {op} {v2}"
        start = match.end()

    v2_str = vs[start:].strip()
    v2 = MavenVersion.parse(v2_str)
    args.append(v2)

    for i in range(len(ops)):
        op = ops[i]
        v1 = args[i]
        v2 = args[i + 1]
        result = comparison_ops[op](v1, v2)
        print(f"{v1} {op} {v2}: {result}")
        assert comparison_ops[op](v1, v2), f"{v1} {op} {v2}"

test_version_sequence("v1.0.0 < v1.0.1 < v2.0.0") # Version prefix
test_version_sequence("1.0.0 = 1.0.0")
test_version_sequence("1 ~ 1.0 ~ 1.0.0 ~ 1.0.0.0 ~ 1.0.0.0.0")
test_version_sequence("1.0.0.RELEASE ~ 1.0.0")
test_version_sequence("1.0-FINAL ~ 1.0")
test_version_sequence("1.0.0_RELEASE ~ 1.0.0.RELEASE")
test_version_sequence("1.0.0 !~ 1.0.1")
test_version_sequence("1.2.M01 < 1.2.M02 < 1.2.M06 < 1.2")
test_version_sequence("1.2.M01 ~ 1.2.M1")
test_version_sequence("1.8.M01 < 1.8.M02 < 1.8.M07 < 1.8.RC1 < 1.8 < 1.8.1 < 1.8.2 < 1.8.3")
test_version_sequence("1.9.M05 < 1.9.RC1 < 1.9.RC2 < 1.9")
test_version_sequence("1.9 < 1.9.1 < 1.9.2 < 1.9.9")
test_version_sequence("3.0.12 < 3.1.0-BETA1 < 3.1.0-M01 < 3.1.0-M10 < 3.1.0-M12-beta2 < 3.1.0-M13-beta3 < 3.1.0-RC1 < 3.1.0 < 3.1.1")
test_version_sequence("3.3.0-alpha01 < 3.3.0-alpha07 < 3.3.0-beta01 < 3.3.0-beta02 < 3.3.0-rc1 < 3.3.0")
test_version_sequence("2.5.1 < 2.5.2 < 2.5.3-rc1 < 2.5.3 < 2.5.4-rc1")
# test_version_sequence("1.0-alpha < 1.0-beta < 1.0-SNAPSHOT < 1.0 < 1.0-sp < 1.0.1")
test_version_sequence("1.0.0-alpha < 1.0.0-beta < 1.0.0 < 1.0.1 < 1.1.0 < 2.0.0")
test_version_sequence("1.0.0-alpha < 1.0.0-beta < 1.0.0-RC1 < 1.0.0-RC2 < 1.0.0-SNAPSHOT < 1.0.0 < 1.0.1")
test_version_sequence("1.0.0.alpha < 1.0.0.beta")
test_version_sequence("5.2.0.M1 < 5.2.0.RC1 < 5.2.0.RELEASE < 5.2.1.RELEASE")
test_version_sequence("2.5.6 < 2.5.6.SEC01 < 2.5.6.SEC02 < 2.5.6.SEC03")
test_version_sequence("3.1.0-M1 < 3.1.0-M2 < 3.1.0-RC1 < 3.1.0.RELEASE < 3.1.1.RELEASE")
test_version_sequence("2.0.0-alpha.1 < 2.0.0-beta.1 < 2.0.0-beta.2 < 2.0.0")
test_version_sequence("1.0-rc1 < 1.0-rc2 < 1.0 < 1.0.1")
test_version_sequence("1.2023.11 < 1.2023.12 < 1.2024.1 < 1.2024.2")
test_version_sequence("2.7-b1 < 2.7-b2 < 2.7-b3 < 2.7-b4 < 2.7-rc1")
#test_version_sequence("2.7.1b1 ~ 2.7.1-b1")  # Equivalence with/without hyphen
test_version_sequence("3.8.11 < 3.8.11.1 < 3.8.11.2")  # Four-part version
test_version_sequence("2.1.5 < 2.1.5-01")  # Numbered patch
test_version_sequence("3.8.5-pre1 < 3.8.6")  # 'pre' qualifier
test_version_sequence("1.0.0-rc ~ 1.0.0-RC")  # Case insensitivity
test_version_sequence("7999 < 8000 < 8001")  # Pure numeric ordering
test_version_sequence("1.21.3-R0.1-SNAPSHOT < 1.21.4-R0.1-SNAPSHOT")  # Complex snapshot
test_version_sequence("1.0-alpha-1 ~ 1.0.alpha.1 ~ 1.0.alpha-1")
test_version_sequence("2017.09 < 2017.10 < 2017.11")  # Year.Month without prefix
test_version_sequence("2.0.08 ~ 2.0.8")
test_version_sequence("2.0.0-alpha01 < 2.0.0-alpha02 < 2.0.0-beta01 < 2.0.0-beta02 < 2.0.0-rc01 < 2.0.0.RELEASE ~ 2.0.0")
test_version_sequence("1.5.1-incubating < 1.5.2-incubating < 1.5.3")
#test_version_sequence("2.0.0.BETA1 ~ 2.0.0-beta-1 ~ 2.0.0-beta1")  # Various beta formats
#test_version_sequence("2.0.0.ALPHA1 ~ 2.0.0-alpha-1 ~ 2.0.0-alpha1")  # Various alpha formats
test_version_sequence("1.0.0-RC1 < 1.0.0-GA ~ 1.0.0.RELEASE ~ 1.0.0")
test_version_sequence("1.0.0-M1-SNAPSHOT < 1.0.0-M1")  # Milestone snapshot
#test_version_sequence("1.0.0.M1.dev < 1.0.0.M1")  # Dev milestone
test_version_sequence("1.0.0-b20230101 < 1.0.0-b20230102")  # Build dates
#test_version_sequence("1.0.0.build123 < 1.0.0.build124")  # Build numbers
test_version_sequence("2.0.1-patch1 < 2.0.1-patch2")
test_version_sequence("2.0.1_p1 < 2.0.1_p2")  # Alternate patch format
#test_version_sequence("1.0.0.BUILD-SNAPSHOT ~ 1.0.0-BUILD-SNAPSHOT")  # Different snapshot delimiters
test_version_sequence("1.0.0.Final ~ 1.0.0-Final ~ 1.0.0")  # Final release markers
#test_version_sequence("1.0.0-dev < 1.0.0-preview < 1.0.0-stable")
test_version_sequence("2.0.0.milestone < 2.0.0.release")  # Full word qualifiers
#test_version_sequence("1.0-SNAPSHOT < 1.0-RC-SNAPSHOT < 1.0-RC")
test_version_sequence("1.0-alpha-SNAPSHOT < 1.0-beta-SNAPSHOT < 1.0-SNAPSHOT")
test_version_sequence("1.0.0 < 1.0.0-sp1 < 1.0.0-sp2")  # Service packs
test_version_sequence("2.0.0 < 2.0.0-patch < 2.0.0-patch.1")  # Patch levels

# Mixed milestone and RC qualifiers
test_version_sequence("2.0.0-M5-SNAPSHOT < 2.0.0-RC1-SNAPSHOT")
test_version_sequence("2.0.0-M5-beta < 2.0.0-RC1-alpha")  # RC wins over M regardless of secondary qualifier

# Beta vs Alpha with additional qualifiers
test_version_sequence("1.0.0-alpha-snapshot < 1.0.0-beta-dev")
test_version_sequence("1.0.0-alpha.2-snapshot < 1.0.0-beta.1-dev")

# Milestone numbering vs qualifier precedence
#test_version_sequence("2.0.0-M10-beta < 2.0.0-M2-rc")  # RC qualifier wins over M number

# Build numbers with qualifiers
test_version_sequence("1.0.0-alpha-b2 < 1.0.0-alpha-b10")  # Numeric comparison in build
#test_version_sequence("1.0.0-beta-b1 < 1.0.0-alpha-b2")  # Qualifier wins over build number

# Multiple qualifiers with numbers
test_version_sequence("1.0.0-alpha-1-SNAPSHOT < 1.0.0-alpha-2-SNAPSHOT")
#test_version_sequence("1.0.0-beta-1-dev < 1.0.0-alpha-2-final")  # final wins over earlier stage qualifiers

# Mixed delimiter styles with qualifiers
test_version_sequence("1.0.0.RC1-SNAPSHOT < 1.0.0.RC1_final")
test_version_sequence("1.0.0-M1.SNAPSHOT ~ 1.0.0-M1-SNAPSHOT")  # Equivalent forms

test_version_sequence("1.0.0 ~ 1.0.00")  # Leading zeros in version parts
test_version_sequence("2.0.0-0 < 2.0.0-1")  # Numeric qualifier comparison
test_version_sequence("1.0-0 < 1.0-00001")  # Leading zeros in qualifiers

test_version_sequence("1.0.0+001 < 1.0.0+002")  # Build metadata
test_version_sequence("1.0.0_alpha < 1.0.0_beta")  # Underscore separation
test_version_sequence("1.0.0.RELEASE_2 < 1.0.0.RELEASE_10")  # Mixed separators

test_version_sequence("1.0.0-20230101 < 1.0.0-20230102")  # Date stamps
test_version_sequence("1.0.0-20230101.1200 < 1.0.0-20230101.1201")  # Date and time

test_version_sequence("1.0.0.0.0.0.1 < 1.0.0.0.0.0.2")  # Many version parts
test_version_sequence("1.0.0-alpha-beta-gamma-delta-1 < 1.0.0-alpha-beta-gamma-delta-2")  # Many qualifiers

test_version_sequence("1.0.0-alpha.1.1 < 1.0.0-alpha.1.2")  # Multi-part qualifier numbers
test_version_sequence("1.0.0-beta.2.1 < 1.0.0-beta.10.1")  # Natural number ordering in middle

test_version_sequence("1.999999999 < 1.1000000000")
test_version_sequence("1.0.9999999999 < 1.1.0")

#test_version_sequence("1.0a < 1.0b < 1.0z < 1.1.0")
#test_version_sequence("2.0.0x < 2.0.0y")

# Entirely Alphabetic Versions
test_version_sequence("alpha < beta < gamma")
test_version_sequence("rc < release")

# Case insensitivity
test_version_sequence("1.0.0-aLpHa < 1.0.0-ALPHA.1 < 1.0.0-alpha.2")

test_version_sequence("1.0.0-01alpha < 1.0.0-02beta")
test_version_sequence("1.0.0-0001 ~ 1.0.0-1")


# Test cases
test_cases = [
    "org.jetbrains.kotlinx:kotlinx-serialization-core:1.7.1",
    "com.google.guava:guava:31.1-jre",
    "org.springframework.boot:spring-boot-starter-web:2.5.0",
    "io.ktor:ktor-server-core:2.0.1",
    "org.jetbrains.kotlin:kotlin-stdlib:1.5.0",
    "com.fasterxml.jackson.core:jackson-databind:2.13.0",
    "invalid:coordinate",
    "com.example:library:1",
    "com.example:library:1.0",
    "org.apache.commons:commons-lang3:3.12.0",
    "io.projectreactor:reactor-core:3.4.16",
    "org.junit.jupiter:junit-jupiter-api:5.8.2",
    "ch.qos.logback:logback-classic:1.2.6",
    "org.mockito:mockito-core:4.3.1",
    "com.squareup.retrofit2:retrofit:2.9.0",
    "org.hibernate:hibernate-core:5.6.5.Final",
    "com.example:my-lib:1.0-SNAPSHOT",
    "com.example:my.lib:1.0-alpha-1",
    "com.example:my-lib:1.0.0-RC1",
    "com.example:my_lib:1.0.0.Final",
    "edu.stanford.nlp:stanford-corenlp:4.5.5:models-english-kbp",
    "org.xerial:sqlite-jdbc:3.46.1.0",
    "net.sourceforge.plantuml:plantuml:8059",
    "org.openjdk.jol:jol-core:0.17",
    "org.jogamp.jogl:jogl-all:2.4.0:natives-linux-amd64",
    "io.papermc.paper:paper-api:1.21.1-R0.1-SNAPSHOT"
]

# "com.rollbar:rollbar-java:1.+",

print("Validation tests:")
for coordinate in test_cases:
    print(f"{'Valid' if is_valid_maven_coordinate(coordinate) else 'Invalid'}: {coordinate}")

print("\nParsing and functionality tests:")
coordinates = [MavenCoordinate.parse(coord) for coord in test_cases if is_valid_maven_coordinate(coord)]

for coord in coordinates:
    print(f"Parsed: {coord}")
    # print(f"Is snapshot: {coord.version.is_snapshot()}")

print("\nVersion comparison tests:")
version_pairs = [
    ("1.0.0", "2.0.0"),
    ("1.0.0", "1.0.1"),
    ("1.0.0-alpha", "1.0.0-beta"),
    ("1.0.0-SNAPSHOT", "1.0.0"),
    ("1.0.0", "1.0.0"),
]

for v1, v2 in version_pairs:
    version1 = MavenVersion.parse(v1)
    version2 = MavenVersion.parse(v2)
    print(f"{version1} < {version2}: {version1 < version2}")
    print(f"{version1} == {version2}: {version1 == version2}")


def test_fetch_metadata(repo_base_url: str, group_id: str, artifact_id: str):
    metadata = fetch_metadata(repo_base_url, group_id, artifact_id)
    print(metadata)

test_fetch_metadata("https://repo1.maven.org/maven2/", "org.jline", "jline")
test_fetch_metadata("https://repo1.maven.org/maven2/", "com.charleskorn.kaml", "kaml")
test_fetch_metadata("https://repo1.maven.org/maven2/", "ch.qos.logback", "logback-classic")
test_fetch_metadata("https://repo1.maven.org/maven2/", "org.apache.tika", "tika")
test_fetch_metadata("https://repo1.maven.org/maven2/", "edu.stanford.nlp", "stanford-corenlp")
test_fetch_metadata("https://repo1.maven.org/maven2/", "org.apache.opennlp", "opennlp-tools")
test_fetch_metadata("https://repo1.maven.org/maven2/", "it.unimi.dsi", "fastutil")
test_fetch_metadata("https://repo1.maven.org/maven2/", "com.tdunning", "t-digest")
test_fetch_metadata("https://repo1.maven.org/maven2/", "org.foundationdb", "fdb-java")
test_fetch_metadata("https://repo1.maven.org/maven2/", "org.neo4j", "neo4j")
test_fetch_metadata("https://repo1.maven.org/maven2/", "org.neo4j.driver", "neo4j-java-driver")
test_fetch_metadata("https://repo1.maven.org/maven2/", "org.xerial", "sqlite-jdbc")
test_fetch_metadata("https://repo1.maven.org/maven2/", "org.python", "jython-standalone")
test_fetch_metadata("https://repo1.maven.org/maven2/", "org.pygments", "pygments")
test_fetch_metadata("https://repo1.maven.org/maven2/", "guru.nidi", "graphviz-java")
test_fetch_metadata("https://repo1.maven.org/maven2/", "net.sourceforge.plantuml", "plantuml")
test_fetch_metadata("https://repo1.maven.org/maven2/", "com.rollbar", "rollbar-java")
test_fetch_metadata("https://papermc.io/repo/repository/maven-public/", "io.papermc.paper", "paper-api")

test_fetch_metadata("https://repo1.maven.org/maven2/", "org.springframework", "spring-core")
test_fetch_metadata("https://repo1.maven.org/maven2/", "org.jogamp.gluegen", "gluegen-rt")
test_fetch_metadata("https://repo1.maven.org/maven2/", "org.jogamp.jogl", "jogl-all")
test_fetch_metadata("https://repo1.maven.org/maven2/", "com.squareup.retrofit2", "retrofit")
test_fetch_metadata("https://repo1.maven.org/maven2/", "io.ktor", "ktor-server-core")

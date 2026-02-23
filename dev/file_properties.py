from __future__ import annotations
from typing import List, Tuple, Optional, Dict, Set, Iterable
from dataclasses import dataclass
from pathlib import Path
import os
import stat


@dataclass(frozen=True, order=True)
class ExpectedFileProperties:
    is_executable: bool = False
    is_plain_text: bool = False
    is_configuration: bool = False
    is_code: bool = False
    is_binary: bool = False
    is_security_sensitive: bool = False
    is_crlf_native: bool = False

    @property
    def is_text(self) -> bool:
        # Text includes plain text, structured config, and code
        return self.is_plain_text or self.is_configuration or self.is_code


# ============================================================
# Properties by MIME Type (authoritative)
# ============================================================
PROPERTIES_BY_MIME: Dict[str, ExpectedFileProperties] = {}


def _def_mime(mime: str, **kwargs) -> None:
    # register a MIME with its expected properties
    PROPERTIES_BY_MIME[mime] = ExpectedFileProperties(**kwargs)


# --- Text / Documentation ---
_def_mime("text/plain", is_plain_text=True)
_def_mime("text/markdown", is_plain_text=True)
_def_mime("text/x-rst", is_plain_text=True)
_def_mime("text/x-asciidoc", is_plain_text=True)
_def_mime("text/x-latex", is_plain_text=True)
_def_mime("text/csv", is_plain_text=True)
_def_mime("text/tab-separated-values", is_plain_text=True)
_def_mime("text/x-diff", is_plain_text=True)
_def_mime("text/x-patch", is_plain_text=True)
_def_mime("text/x-gettext-translation", is_plain_text=True)
_def_mime("text/x-gettext-template", is_plain_text=True)
_def_mime("text/vtt", is_plain_text=True)
_def_mime("application/x-subrip", is_plain_text=True)  # .srt
_def_mime("text/calendar", is_plain_text=True)

# --- Configuration formats ---
_def_mime("application/json", is_configuration=True)
_def_mime("application/yaml", is_configuration=True)
_def_mime("application/xml", is_configuration=True)
_def_mime("application/toml", is_configuration=True)
_def_mime("text/x-ini", is_configuration=True)
_def_mime("text/x-properties", is_configuration=True)
_def_mime("application/x-plist+xml", is_configuration=True)
_def_mime("application/x-plist-binary", is_binary=True)  # ambiguous vs XML plist
_def_mime("text/x-hcl", is_configuration=True)
_def_mime("application/x-tfvars", is_configuration=True, is_security_sensitive=True)
_def_mime("application/manifest+json", is_configuration=True)
_def_mime("application/x-systemd-unit", is_configuration=True)
_def_mime("application/x-desktop", is_configuration=True)
_def_mime("text/x-dotenv", is_configuration=True, is_security_sensitive=True)
_def_mime("text/x-dotenv-example", is_configuration=True, is_security_sensitive=False)
_def_mime("text/x-gitignore", is_configuration=True)
_def_mime("text/x-gitattributes", is_configuration=True)
_def_mime("text/x-gitmodules", is_configuration=True)
_def_mime("text/x-editorconfig", is_configuration=True)
_def_mime("text/x-pylintrc", is_configuration=True)
_def_mime("text/x-flake8", is_configuration=True)
_def_mime("application/x-docker-compose-yaml", is_configuration=True)
_def_mime("text/x-procfile", is_configuration=True)
_def_mime("text/x-htaccess", is_configuration=True)
_def_mime("text/x-robots-txt", is_plain_text=True)
_def_mime("text/x-netrc", is_configuration=True, is_security_sensitive=True)
_def_mime("text/x-requirements-txt", is_configuration=True)

# --- Web / Code ---
_def_mime("text/html", is_code=True)
_def_mime("text/css", is_code=True)
_def_mime("text/x-scss", is_code=True)
_def_mime("text/x-sass", is_code=True)
_def_mime("text/x-less", is_code=True)
_def_mime("text/x-stylus", is_code=True)
_def_mime("application/javascript", is_code=True)
_def_mime("text/javascript", is_code=True)
_def_mime("text/jsx", is_code=True)
_def_mime("application/mjs", is_code=True)
_def_mime("application/cjs", is_code=True)
_def_mime("text/typescript", is_code=True)
_def_mime("text/tsx", is_code=True)
_def_mime("text/x-vue", is_code=True)
_def_mime("text/x-svelte", is_code=True)
_def_mime("text/x-php", is_code=True)
_def_mime("text/x-phtml", is_code=True)
_def_mime("text/x-asp", is_code=True)
_def_mime("application/x-aspx", is_code=True)
_def_mime("text/x-jsp", is_code=True)
_def_mime("application/graphql", is_code=True)
_def_mime("text/x-graphql", is_code=True)
_def_mime("image/svg+xml", is_code=True)  # XML-based vector graphics

# --- Programming Languages ---
_def_mime("text/x-python", is_code=True)
_def_mime("text/x-ruby", is_code=True)
_def_mime("text/x-java-source", is_code=True)
_def_mime("text/x-kotlin", is_code=True)
_def_mime("text/x-scala", is_code=True)
_def_mime("text/x-swift", is_code=True)
_def_mime("text/x-csrc", is_code=True)
_def_mime("text/x-chdr", is_code=True)
_def_mime("text/x-c++src", is_code=True)
_def_mime("text/x-c++hdr", is_code=True)
_def_mime("text/x-objcsrc", is_code=True)
_def_mime("text/x-objc++src", is_code=True)
_def_mime("text/x-csharp", is_code=True)
_def_mime("text/x-vb", is_code=True)
_def_mime("text/x-fsharp", is_code=True)
_def_mime("text/x-go", is_code=True)
_def_mime("text/x-rust", is_code=True)
_def_mime("text/x-haskell", is_code=True)
_def_mime("text/x-literate-haskell", is_code=True)
_def_mime("text/x-erlang", is_code=True)
_def_mime("text/x-elixir", is_code=True)
_def_mime("text/x-clojure", is_code=True)
_def_mime("text/x-lisp", is_code=True)
_def_mime("text/x-scheme", is_code=True)
_def_mime("text/x-racket", is_code=True)
_def_mime("text/x-elisp", is_code=True)
_def_mime("text/x-vim", is_code=True)
_def_mime("text/x-lua", is_code=True)
_def_mime("text/x-perl", is_code=True)
_def_mime("text/x-dart", is_code=True)
_def_mime("text/x-groovy", is_code=True)
_def_mime("text/x-gradle", is_code=True)
_def_mime("application/x-terraform", is_code=True)
_def_mime("text/x-sql", is_code=True)
_def_mime("application/sql", is_code=True)
_def_mime("application/x-powershell", is_code=True)
_def_mime("text/x-shellscript", is_code=True)  # executability depends on fs permissions
_def_mime("text/x-awk", is_code=True)
_def_mime("text/x-applescript", is_code=True)
_def_mime("application/x-applescript-binary", is_binary=True)
_def_mime("text/x-coffeescript", is_code=True)
_def_mime("text/x-purescript", is_code=True)
_def_mime("text/x-elm", is_code=True)
_def_mime("text/x-r", is_code=True)
_def_mime("text/x-rmarkdown", is_code=True)
_def_mime("text/x-julia", is_code=True)
_def_mime("text/x-nim", is_code=True)
_def_mime("text/x-crystal", is_code=True)
_def_mime("text/x-verilog", is_code=True)
_def_mime("text/x-systemverilog", is_code=True)
_def_mime("text/x-vhdl", is_code=True)
_def_mime("text/x-zig", is_code=True)
_def_mime("text/x-odin", is_code=True)
_def_mime("text/x-d", is_code=True)
_def_mime("text/x-fortran", is_code=True)
_def_mime("text/x-ada", is_code=True)
_def_mime("text/x-cobol", is_code=True)
_def_mime("text/x-pascal", is_code=True)
_def_mime("text/x-asm", is_code=True)
_def_mime("text/x-protobuf", is_code=True)
_def_mime("text/x-thrift", is_code=True)
_def_mime("text/x-capnp", is_code=True)
_def_mime("text/x-mustache", is_code=True)
_def_mime("text/x-handlebars", is_code=True)
_def_mime("text/x-pug", is_code=True)
_def_mime("text/x-haml", is_code=True)
_def_mime("text/x-slim", is_code=True)
_def_mime("text/x-erb", is_code=True)
_def_mime("text/x-jinja2", is_code=True)
_def_mime("text/x-twig", is_code=True)
_def_mime("text/x-makefile", is_code=True)
_def_mime("text/x-dockerfile", is_code=True)
_def_mime("text/x-cmake", is_code=True)
_def_mime("text/x-cmake-list", is_code=True)

# --- Notebooks ---
_def_mime("application/x-ipynb+json", is_code=True)

# --- Binary / compiled / packages ---
_def_mime("application/x-python-bytecode", is_binary=True)
_def_mime("application/x-python-optimized-bytecode", is_binary=True)
_def_mime("application/x-python-extension", is_binary=True)
_def_mime("application/x-sharedlib", is_binary=True)
_def_mime("application/x-dylib", is_binary=True)
_def_mime("application/x-dll", is_binary=True)
_def_mime("application/x-archive", is_binary=True)
_def_mime("application/x-object", is_binary=True)
_def_mime("application/java-vm", is_binary=True)
_def_mime("application/java-archive", is_binary=True)
_def_mime("application/x-jar", is_binary=True)
_def_mime("application/x-war", is_binary=True)
_def_mime("application/x-ear", is_binary=True)
_def_mime("application/x-aar", is_binary=True)
_def_mime("application/x-msdownload", is_binary=True, is_executable=True)
_def_mime("application/x-msdos-program", is_binary=True, is_executable=True)
_def_mime("text/x-batch", is_code=True, is_executable=True, is_crlf_native=True)
_def_mime("text/x-cmd", is_code=True, is_executable=True, is_crlf_native=True)
_def_mime("application/x-msi", is_binary=True)
_def_mime("application/vnd.debian.binary-package", is_binary=True)
_def_mime("application/x-rpm", is_binary=True)
_def_mime("application/x-apple-installer-package", is_binary=True)
_def_mime("application/x-iso9660-image", is_binary=True)
_def_mime("application/vnd.apple.diskimage", is_binary=True)
_def_mime("application/vnd.android.package-archive", is_binary=True)
_def_mime("application/x-ios-ipa", is_binary=True)
_def_mime("application/x-macos-app-bundle", is_binary=True)
_def_mime("application/x-sqlite3", is_binary=True)
_def_mime("application/x-feather", is_binary=True)
_def_mime("application/x-parquet", is_binary=True)
_def_mime("application/avro", is_binary=True)
_def_mime("application/vnd.apache.orc", is_binary=True)
_def_mime("application/x-npy", is_binary=True)
_def_mime("application/x-npz", is_binary=True)
_def_mime("application/x-pickle", is_binary=True)
_def_mime("application/x-joblib", is_binary=True)
_def_mime("application/x-hdf5", is_binary=True)
_def_mime("application/x-spss-sav", is_binary=True)
_def_mime("application/x-stata-dta", is_binary=True)
_def_mime("application/x-sas7bdat", is_binary=True)
_def_mime("application/x-gettext-translation-mo", is_binary=True)
_def_mime("application/pdf", is_binary=True)
_def_mime("application/msword", is_binary=True)
_def_mime(
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    is_binary=True,
)
_def_mime("application/rtf", is_plain_text=True)
_def_mime("application/vnd.oasis.opendocument.text", is_binary=True)
_def_mime("application/vnd.ms-excel", is_binary=True)
_def_mime("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", is_binary=True)
_def_mime("application/vnd.oasis.opendocument.spreadsheet", is_binary=True)
_def_mime("application/vnd.ms-powerpoint", is_binary=True)
_def_mime(
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    is_binary=True,
)
_def_mime("application/vnd.oasis.opendocument.presentation", is_binary=True)
_def_mime("application/x-iwork-keynote-sffkey", is_binary=True)
_def_mime("application/x-iwork-numbers-sffnumbers", is_binary=True)
_def_mime("application/x-iwork-pages-sffpages", is_binary=True)
_def_mime("application/zip", is_binary=True)
_def_mime("application/octet-stream", is_binary=True)
_def_mime("application/x-tar", is_binary=True)
_def_mime("application/gzip", is_binary=True)
_def_mime("application/x-bzip2", is_binary=True)
_def_mime("application/x-xz", is_binary=True)
_def_mime("application/x-lzma", is_binary=True)
_def_mime("application/zstd", is_binary=True)
_def_mime("application/x-7z-compressed", is_binary=True)
_def_mime("application/x-rar-compressed", is_binary=True)
_def_mime("application/x-virtualbox-vdi", is_binary=True)
_def_mime("application/x-vmdk", is_binary=True)
_def_mime("application/x-ovf", is_configuration=True)  # XML
_def_mime("application/x-ova", is_binary=True)
_def_mime("application/x-python-wheel", is_binary=True)

# --- Images ---
_def_mime("image/jpeg", is_binary=True)
_def_mime("image/png", is_binary=True)
_def_mime("image/gif", is_binary=True)
_def_mime("image/bmp", is_binary=True)
_def_mime("image/tiff", is_binary=True)
_def_mime("image/webp", is_binary=True)
_def_mime("image/x-icon", is_binary=True)
_def_mime("image/icns", is_binary=True)
_def_mime("image/vnd.adobe.photoshop", is_binary=True)
_def_mime("image/vnd.adobe.illustrator", is_binary=True)
_def_mime("application/postscript", is_binary=True)

# --- CAD / vector ---
_def_mime("image/svg+xml", is_code=True)
_def_mime("image/vnd.dxf", is_plain_text=True)
_def_mime("image/vnd.dwg", is_binary=True)
_def_mime("image/x-xcf", is_binary=True)

# --- Audio ---
_def_mime("audio/mpeg", is_binary=True)
_def_mime("audio/wav", is_binary=True)
_def_mime("audio/ogg", is_binary=True)
_def_mime("audio/flac", is_binary=True)
_def_mime("audio/aac", is_binary=True)
_def_mime("audio/mp4", is_binary=True)
_def_mime("audio/x-ms-wma", is_binary=True)
_def_mime("audio/aiff", is_binary=True)
_def_mime("audio/opus", is_binary=True)

# --- Video ---
_def_mime("video/mp4", is_binary=True)
_def_mime("video/x-matroska", is_binary=True)
_def_mime("video/quicktime", is_binary=True)
_def_mime("video/x-msvideo", is_binary=True)
_def_mime("video/x-ms-wmv", is_binary=True)
_def_mime("video/x-flv", is_binary=True)
_def_mime("video/webm", is_binary=True)
_def_mime("video/mpeg", is_binary=True)
_def_mime("video/ogg", is_binary=True)
_def_mime("video/3gpp", is_binary=True)
_def_mime("video/x-m4v", is_binary=True)

# --- Fonts ---
_def_mime("font/ttf", is_binary=True)
_def_mime("font/otf", is_binary=True)
_def_mime("font/woff", is_binary=True)
_def_mime("font/woff2", is_binary=True)
_def_mime("application/vnd.ms-fontobject", is_binary=True)

# --- Security sensitive ---
_def_mime("application/x-pem-key", is_plain_text=True, is_security_sensitive=True)
_def_mime("application/x-pem-cert", is_plain_text=True, is_security_sensitive=False)
_def_mime("application/x-x509-cert", is_plain_text=True, is_security_sensitive=False)
_def_mime("application/x-der", is_binary=True, is_security_sensitive=False)
_def_mime("application/x-pkcs12", is_binary=True, is_security_sensitive=True)
_def_mime("application/x-pkcs7-certificates", is_plain_text=True, is_security_sensitive=False)  # .p7b
_def_mime("application/x-pkcs7-mime", is_binary=True, is_security_sensitive=False)  # .p7c
_def_mime("application/x-java-keystore", is_binary=True, is_security_sensitive=True)
_def_mime("application/pgp-keys", is_plain_text=True, is_security_sensitive=False)
_def_mime("application/pgp-signature", is_plain_text=True, is_security_sensitive=False)
_def_mime("application/pgp-encrypted", is_plain_text=True, is_security_sensitive=True)
_def_mime("application/x-ssh-public-key", is_plain_text=True, is_security_sensitive=False)
_def_mime("application/x-ssh-private-key", is_plain_text=True, is_security_sensitive=True)
_def_mime("application/x-keepass2", is_binary=True, is_security_sensitive=True)
_def_mime("text/x-shell-history", is_plain_text=True, is_security_sensitive=True)
_def_mime("text/x-python-history", is_plain_text=True, is_security_sensitive=True)
_def_mime("text/x-htpasswd", is_plain_text=True, is_security_sensitive=True)

# --- Derived/specialized JSON/YAML configs for names ---
_def_mime("application/x-json-config", is_configuration=True)
_def_mime("application/x-yaml-secrets", is_configuration=True, is_security_sensitive=True)
_def_mime("application/x-json-credentials", is_configuration=True, is_security_sensitive=True)
_def_mime("text/x-yarn-lock", is_plain_text=True)
_def_mime("text/x-go-mod", is_configuration=True)
_def_mime("text/x-toml-lock", is_configuration=True)
_def_mime("application/x-source-map+json", is_code=True)


# ============================================================
# Mappings from names and extensions to possible MIME types.
# Names are case-sensitive. Extensions are case-insensitive.
# ============================================================
NAME_TO_MIMES: Dict[str, Set[str]] = {}
EXT_TO_MIMES: Dict[str, Set[str]] = {}


def _reg_name(names: Iterable[str], *mimes: str) -> None:
    for n in names:
        NAME_TO_MIMES.setdefault(n, set()).update(mimes)


def _reg_ext(exts: Iterable[str], *mimes: str) -> None:
    for e in exts:
        EXT_TO_MIMES.setdefault(e.lower(), set()).update(mimes)


# --- Common Project Metadata ---
_reg_name(
    [
        "README",
        "LICENSE",
        "COPYING",
        "CHANGELOG",
        "CONTRIBUTING",
        "AUTHORS",
        "TODO",
        "HISTORY",
        "NEWS",
        "UPGRADE",
        "UPGRADING",
        "INSTALL",
        "NOTICE",
        "CODE_OF_CONDUCT",
    ],
    "text/plain",
    "text/markdown",
)
_reg_name(["robots.txt"], "text/x-robots-txt")
_reg_name(["security.txt", "humans.txt"], "text/plain")

# --- Build & Task Runners ---
_reg_name(["Makefile", "makefile", "GNUmakefile"], "text/x-makefile")
_reg_name(["Rakefile"], "text/x-ruby")
_reg_name(["Gemfile"], "text/x-ruby")
_reg_name(["Podfile"], "text/x-ruby")
_reg_name(["Gruntfile.js", "gulpfile.js"], "application/javascript")
_reg_name(["Jenkinsfile"], "text/x-groovy")
_reg_name(["Vagrantfile"], "text/x-ruby")
_reg_name(["Procfile"], "text/x-procfile")

# --- Containerization ---
_reg_name(["Dockerfile", "dockerfile"], "text/x-dockerfile")
_reg_name(["compose.yaml", "compose.yml"], "application/x-docker-compose-yaml")

# --- VCS ---
_reg_name([".gitignore"], "text/x-gitignore")
_reg_name([".gitattributes"], "text/x-gitattributes")
_reg_name([".gitmodules"], "text/x-gitmodules")
_reg_name([".gitconfig"], "text/x-ini")
_reg_name(
    [
        ".hgignore",
        ".hgsub",
        ".hgsubstate",
        ".svnignore",
        ".npmignore",
        ".eslintignore",
        ".prettierignore",
    ],
    "text/plain",
)  # treat as plain

# --- Linters / editors ---
_reg_name([".pylintrc"], "text/x-pylintrc")
_reg_name([".flake8"], "text/x-flake8")
_reg_name([".editorconfig"], "text/x-editorconfig")

# --- Env / Secrets ---
_reg_name([".env"], "text/x-dotenv")
_reg_name([".env.example"], "text/x-dotenv-example")
_reg_name([".flaskenv"], "text/x-dotenv")
_reg_name([".netrc"], "text/x-netrc")
_reg_name([".htpasswd"], "text/x-htpasswd")
_reg_name([".htaccess"], "text/x-htaccess")
_reg_name(["secrets.yaml", "secrets.yml"], "application/x-yaml-secrets")
_reg_name(["credentials.json"], "application/x-json-credentials")
_reg_name([".bash_history", ".zsh_history"], "text/x-shell-history")
_reg_name([".python_history"], "text/x-python-history")

# --- Package mgmt ---
_reg_name(
    ["package.json", "package-lock.json", "composer.json", "Pipfile.lock"],
    "application/json",
    "application/x-json-config",
)
_reg_name(["yarn.lock"], "text/x-yarn-lock")
_reg_name(["composer.lock"], "application/json", "application/x-json-config")
_reg_name(["requirements.txt"], "text/x-requirements-txt")
_reg_name(["Pipfile", "pyproject.toml", "Cargo.toml"], "application/toml")
_reg_name(["Cargo.lock"], "text/x-toml-lock")
_reg_name(["go.mod"], "text/x-go-mod")
_reg_name(["go.sum"], "text/plain")
_reg_name(["now.json", "vercel.json"], "application/x-json-config")
_reg_name(["netlify.toml"], "application/toml")
_reg_name(
    [".babelrc", ".eslintrc", ".prettierrc", ".stylelintrc"],
    "application/json",
    "application/yaml",
)
_reg_name([".travis.yml", ".gitlab-ci.yml"], "application/yaml")

# --- Build system specifics ---
_reg_name(["CMakeLists.txt"], "text/x-cmake")

# --- Misc ---
_reg_name([".mailmap"], "text/plain")
_reg_name([".DS_Store"], "application/octet-stream")

# --- Extensions (Plain text & docs) ---
_reg_ext([".txt"], "text/plain")
_reg_ext([".md", ".markdown"], "text/markdown")
_reg_ext([".rst"], "text/x-rst")
_reg_ext([".adoc", ".asciidoc"], "text/x-asciidoc")
_reg_ext([".tex"], "text/x-latex")
_reg_ext([".log", ".sig", ".pid"], "text/plain")
_reg_ext([".csv"], "text/csv")
_reg_ext([".tsv"], "text/tab-separated-values")
_reg_ext([".diff"], "text/x-diff")
_reg_ext([".patch"], "text/x-patch")
_reg_ext([".po"], "text/x-gettext-translation")
_reg_ext([".pot"], "text/x-gettext-template")
_reg_ext([".srt"], "application/x-subrip")
_reg_ext([".vtt"], "text/vtt")
_reg_ext([".bib"], "text/plain")
_reg_ext([".ics"], "text/calendar")

# --- Config formats ---
_reg_ext([".json"], "application/json")
_reg_ext([".yaml", ".yml"], "application/yaml")
_reg_ext([".xml"], "application/xml")
_reg_ext([".toml"], "application/toml")
_reg_ext([".ini", ".cfg", ".conf", ".cnf"], "text/x-ini")
_reg_ext([".properties", ".prefs", ".settings"], "text/x-properties")
_reg_ext([".plist"], "application/x-plist+xml", "application/x-plist-binary")
_reg_ext([".xcconfig"], "text/x-ini")
_reg_ext([".env"], "text/x-dotenv")
_reg_ext([".hcl"], "text/x-hcl")
_reg_ext([".tfvars"], "application/x-tfvars")
_reg_ext([".webmanifest"], "application/manifest+json")
_reg_ext(
    [
        ".service",
        ".socket",
        ".timer",
        ".target",
        ".mount",
        ".automount",
        ".path",
        ".scope",
        ".slice",
    ],
    "application/x-systemd-unit",
)
_reg_ext([".desktop"], "application/x-desktop")
_reg_ext([".xsd", ".xsl", ".xslt", ".dtd"], "application/xml")

# --- Web development ---
_reg_ext([".html", ".htm"], "text/html")
_reg_ext([".css"], "text/css")
_reg_ext([".scss"], "text/x-scss")
_reg_ext([".sass"], "text/x-sass")
_reg_ext([".less"], "text/x-less")
_reg_ext([".styl"], "text/x-stylus")
_reg_ext([".js"], "application/javascript")
_reg_ext([".jsx"], "text/jsx")
_reg_ext([".mjs"], "application/mjs")
_reg_ext([".cjs"], "application/cjs")
_reg_ext([".ts"], "text/typescript")
_reg_ext([".tsx"], "text/tsx")
_reg_ext([".vue"], "text/x-vue")
_reg_ext([".svelte"], "text/x-svelte")
_reg_ext([".php"], "text/x-php")
_reg_ext([".phtml"], "text/x-phtml")
_reg_ext([".asp"], "text/x-asp")
_reg_ext([".aspx"], "application/x-aspx")
_reg_ext([".jsp"], "text/x-jsp")
_reg_ext([".map"], "application/x-source-map+json")
_reg_ext([".webmanifest"], "application/manifest+json")
_reg_ext([".graphql", ".gql"], "text/x-graphql", "application/graphql")

# --- Programming languages (source) ---
_reg_ext([".py"], "text/x-python")
_reg_ext([".rb"], "text/x-ruby")
_reg_ext([".java"], "text/x-java-source")
_reg_ext([".kt", ".kts"], "text/x-kotlin")
_reg_ext([".scala"], "text/x-scala")
_reg_ext([".swift"], "text/x-swift")
_reg_ext([".c"], "text/x-csrc")
_reg_ext([".h"], "text/x-chdr")
_reg_ext([".cpp", ".cc", ".cxx"], "text/x-c++src")
_reg_ext([".hpp", ".hh", ".hxx"], "text/x-c++hdr")
_reg_ext([".m"], "text/x-objcsrc")
_reg_ext([".mm"], "text/x-objc++src")
_reg_ext([".cs"], "text/x-csharp")
_reg_ext([".vb"], "text/x-vb")
_reg_ext([".fs", ".fsi", ".fsx"], "text/x-fsharp")
_reg_ext([".go"], "text/x-go")
_reg_ext([".rs"], "text/x-rust")
_reg_ext([".hs"], "text/x-haskell")
_reg_ext([".lhs"], "text/x-literate-haskell")
_reg_ext([".erl", ".hrl"], "text/x-erlang")
_reg_ext([".ex", ".exs"], "text/x-elixir")
_reg_ext([".clj", ".cljs", ".cljc", ".edn"], "text/x-clojure")
_reg_ext([".lisp", ".lsp", ".el"], "text/x-lisp")
_reg_ext([".scm", ".ss"], "text/x-scheme")
_reg_ext([".rkt"], "text/x-racket")
_reg_ext([".vim"], "text/x-vim")
_reg_ext([".lua"], "text/x-lua")
_reg_ext([".pl", ".pm", ".t"], "text/x-perl")
_reg_ext([".dart"], "text/x-dart")
_reg_ext([".groovy", ".gvy"], "text/x-groovy")
_reg_ext([".gradle"], "text/x-gradle")
_reg_ext([".tf"], "application/x-terraform")
_reg_ext([".sql", ".ddl", ".dml"], "text/x-sql", "application/sql")
_reg_ext([".ps1", ".psm1"], "application/x-powershell")
_reg_ext([".psd1"], "text/x-ini")  # PowerShell Data file (manifest)
_reg_ext([".sh", ".bash", ".zsh", ".ksh", ".csh", ".fish"], "text/x-shellscript")
_reg_ext([".awk"], "text/x-awk")
_reg_ext([".applescript"], "text/x-applescript")
_reg_ext([".scpt"], "application/x-applescript-binary")
_reg_ext([".coffee", ".litcoffee"], "text/x-coffeescript")
_reg_ext([".purs"], "text/x-purescript")
_reg_ext([".elm"], "text/x-elm")
_reg_ext([".r"], "text/x-r")
_reg_ext([".rmd"], "text/x-rmarkdown")
_reg_ext([".jl"], "text/x-julia")
_reg_ext([".nim"], "text/x-nim")
_reg_ext([".cr"], "text/x-crystal")
_reg_ext([".v"], "text/x-verilog")
_reg_ext([".vh"], "text/x-verilog")
_reg_ext([".sv"], "text/x-systemverilog")
_reg_ext([".svh"], "text/x-systemverilog")
_reg_ext([".vhd", ".vhdl"], "text/x-vhdl")
_reg_ext([".zig"], "text/x-zig")
_reg_ext([".odin"], "text/x-odin")
_reg_ext([".d"], "text/x-d")
_reg_ext([".f", ".f90", ".f95", ".f03", ".f08", ".for"], "text/x-fortran")
_reg_ext([".ada", ".adb", ".ads"], "text/x-ada")
_reg_ext([".cob", ".cbl"], "text/x-cobol")
_reg_ext([".pas", ".pp", ".inc"], "text/x-pascal")
_reg_ext([".asm", ".s"], "text/x-asm")
_reg_ext([".S"], "text/x-asm")
_reg_ext([".proto"], "text/x-protobuf")
_reg_ext([".thrift"], "text/x-thrift")
_reg_ext([".capnp"], "text/x-capnp")
_reg_ext([".mustache"], "text/x-mustache")
_reg_ext([".hbs"], "text/x-handlebars")
_reg_ext([".pug"], "text/x-pug")
_reg_ext([".haml"], "text/x-haml")
_reg_ext([".slim"], "text/x-slim")
_reg_ext([".erb"], "text/x-erb")
_reg_ext([".j2", ".jinja2"], "text/x-jinja2")
_reg_ext([".twig"], "text/x-twig")

# --- Build system specific ---
_reg_ext([".pom"], "application/xml")
_reg_ext([".csproj", ".vbproj", ".fsproj", ".vcxproj", ".xproj", ".build"], "application/xml")
_reg_ext([".sln"], "text/plain")
_reg_ext([".sbt"], "text/x-gradle")  # treat like build script
_reg_ext([".cmake"], "text/x-cmake")
# Name handled for CMakeLists.txt above

# --- Python compiled / binary data / packages ---
_reg_ext([".pyc"], "application/x-python-bytecode")
_reg_ext([".pyo"], "application/x-python-optimized-bytecode")
_reg_ext([".pyd"], "application/x-python-extension")
_reg_ext([".so"], "application/x-sharedlib")
_reg_ext([".dylib"], "application/x-dylib")
_reg_ext([".dll"], "application/x-dll")
_reg_ext([".a", ".lib"], "application/x-archive")
_reg_ext([".o", ".obj"], "application/x-object")
_reg_ext([".class"], "application/java-vm")
_reg_ext([".jar"], "application/java-archive", "application/x-jar")
_reg_ext([".war"], "application/x-war")
_reg_ext([".ear"], "application/x-ear")
_reg_ext([".aar"], "application/x-aar")
_reg_ext([".exe"], "application/x-msdownload")
_reg_ext([".com"], "application/x-msdos-program")
_reg_ext([".bat"], "text/x-batch")
_reg_ext([".cmd"], "text/x-cmd")
_reg_ext([".msi"], "application/x-msi")
_reg_ext([".deb"], "application/vnd.debian.binary-package")
_reg_ext([".rpm"], "application/x-rpm")
_reg_ext([".pkg"], "application/x-apple-installer-package")
_reg_ext([".dmg"], "application/vnd.apple.diskimage")
_reg_ext([".iso"], "application/x-iso9660-image")
_reg_ext([".img"], "application/octet-stream")
_reg_ext([".vmdk"], "application/x-vmdk")
_reg_ext([".vdi"], "application/x-virtualbox-vdi")
_reg_ext([".ova"], "application/x-ova")
_reg_ext([".ovf"], "application/x-ovf")
_reg_ext([".apk"], "application/vnd.android.package-archive")
_reg_ext([".ipa"], "application/x-ios-ipa")
_reg_ext([".app"], "application/x-macos-app-bundle")
_reg_ext([".bin", ".dat", ".db", ".sqlitedb"], "application/octet-stream")
_reg_ext([".sqlite", ".sqlite3"], "application/x-sqlite3")
_reg_ext([".dbf"], "application/octet-stream")
_reg_ext([".mdb", ".accdb"], "application/octet-stream")
_reg_ext([".feather"], "application/x-feather")
_reg_ext([".parquet"], "application/x-parquet")
_reg_ext([".avro"], "application/avro")
_reg_ext([".orc"], "application/vnd.apache.orc")
_reg_ext([".npy"], "application/x-npy")
_reg_ext([".npz"], "application/x-npz")
_reg_ext([".pkl", ".pickle"], "application/x-pickle")
_reg_ext([".joblib"], "application/x-joblib")
_reg_ext([".h5", ".hdf5"], "application/x-hdf5")
_reg_ext([".ipynb"], "application/x-ipynb+json")
_reg_ext([".rdata", ".rda", ".rds"], "application/octet-stream")
_reg_ext([".sav"], "application/x-spss-sav")
_reg_ext([".dta"], "application/x-stata-dta")
_reg_ext([".sas7bdat"], "application/x-sas7bdat")
_reg_ext([".mo"], "application/x-gettext-translation-mo")

# --- Document formats ---
_reg_ext([".pdf"], "application/pdf")
_reg_ext([".doc"], "application/msword")
_reg_ext([".docx"], "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
_reg_ext([".rtf"], "application/rtf")
_reg_ext([".odt"], "application/vnd.oasis.opendocument.text")
_reg_ext([".wpd"], "application/octet-stream")
_reg_ext([".xls"], "application/vnd.ms-excel")
_reg_ext([".xlsx"], "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
_reg_ext([".ods"], "application/vnd.oasis.opendocument.spreadsheet")
_reg_ext([".ppt"], "application/vnd.ms-powerpoint")
_reg_ext(
    [".pptx"],
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
)
_reg_ext([".odp"], "application/vnd.oasis.opendocument.presentation")
_reg_ext([".key"], "application/x-iwork-keynote-sffkey")
_reg_ext([".numbers"], "application/x-iwork-numbers-sffnumbers")
_reg_ext([".pages"], "application/x-iwork-pages-sffpages")

# --- Images ---
_reg_ext([".jpg", ".jpeg"], "image/jpeg")
_reg_ext([".png"], "image/png")
_reg_ext([".gif"], "image/gif")
_reg_ext([".bmp"], "image/bmp")
_reg_ext([".tiff", ".tif"], "image/tiff")
_reg_ext([".webp"], "image/webp")
_reg_ext([".ico"], "image/x-icon")
_reg_ext([".icns"], "image/icns")
_reg_ext([".psd"], "image/vnd.adobe.photoshop")
_reg_ext([".ai"], "image/vnd.adobe.illustrator")
_reg_ext([".eps"], "application/postscript")
_reg_ext([".svg"], "image/svg+xml")
_reg_ext([".dxf"], "image/vnd.dxf")
_reg_ext([".dwg"], "image/vnd.dwg")
_reg_ext([".xcf"], "image/x-xcf")

# --- Audio ---
_reg_ext([".mp3"], "audio/mpeg")
_reg_ext([".wav"], "audio/wav")
_reg_ext([".ogg"], "audio/ogg")
_reg_ext([".flac"], "audio/flac")
_reg_ext([".aac"], "audio/aac")
_reg_ext([".m4a"], "audio/mp4")
_reg_ext([".wma"], "audio/x-ms-wma")
_reg_ext([".aiff"], "audio/aiff")
_reg_ext([".opus"], "audio/opus")

# --- Video ---
_reg_ext([".mp4"], "video/mp4")
_reg_ext([".mkv"], "video/x-matroska")
_reg_ext([".mov"], "video/quicktime")
_reg_ext([".avi"], "video/x-msvideo")
_reg_ext([".wmv"], "video/x-ms-wmv")
_reg_ext([".flv"], "video/x-flv")
_reg_ext([".webm"], "video/webm")
_reg_ext([".mpeg", ".mpg"], "video/mpeg")
_reg_ext([".ogv"], "video/ogg")
_reg_ext([".3gp"], "video/3gpp")
_reg_ext([".m4v"], "video/x-m4v")

# --- Archives ---
_reg_ext([".zip"], "application/zip")
_reg_ext([".tar"], "application/x-tar")
_reg_ext([".gz"], "application/gzip")
_reg_ext([".tgz"], "application/gzip", "application/x-tar")
_reg_ext([".bz2"], "application/x-bzip2")
_reg_ext([".tbz", ".tbz2"], "application/x-bzip2", "application/x-tar")
_reg_ext([".xz"], "application/x-xz")
_reg_ext([".txz"], "application/x-xz", "application/x-tar")
_reg_ext([".lzma"], "application/x-lzma")
_reg_ext([".tlz"], "application/x-lzma", "application/x-tar")
_reg_ext([".7z"], "application/x-7z-compressed")
_reg_ext([".rar"], "application/x-rar-compressed")
_reg_ext([".whl"], "application/x-python-wheel")

# --- Fonts ---
_reg_ext([".ttf"], "font/ttf")
_reg_ext([".otf"], "font/otf")
_reg_ext([".woff"], "font/woff")
_reg_ext([".woff2"], "font/woff2")
_reg_ext([".eot"], "application/vnd.ms-fontobject")

# --- Security sensitive ---
_reg_ext([".pem"], "application/x-pem-key", "application/x-pem-cert")
_reg_ext([".key"], "application/x-pem-key", "application/x-ssh-private-key")
_reg_ext([".crt", ".cer"], "application/x-x509-cert")
_reg_ext([".der"], "application/x-der")
_reg_ext([".p12", ".pfx"], "application/x-pkcs12")
_reg_ext([".p7b"], "application/x-pkcs7-certificates")
_reg_ext([".p7c"], "application/x-pkcs7-mime")
_reg_ext([".jks"], "application/x-java-keystore")
_reg_ext([".pub"], "application/x-ssh-public-key")
_reg_ext(
    [".asc"],
    "application/pgp-keys",
    "application/pgp-signature",
    "application/pgp-encrypted",
)
_reg_ext([".gpg"], "application/pgp-encrypted")
_reg_ext([".kdbx"], "application/x-keepass2")

# --- Misc ---
_reg_ext([".bak", ".tmp", ".swp", ".swo"], "application/octet-stream")
_reg_ext([".lock"], "text/plain")


def _lower_bound_properties(mime_types: Iterable[str]) -> ExpectedFileProperties:
    """Compute the lower bound (intersection) of properties across the given MIME types.
    A property is True only if it is True for *all* MIME types in the set.
    """
    mime_types = list(mime_types)
    if not mime_types:
        return ExpectedFileProperties()
    props_list = [PROPERTIES_BY_MIME[m] for m in mime_types if m in PROPERTIES_BY_MIME]
    if not props_list:
        return ExpectedFileProperties()

    # For each boolean field, AND across all props
    def AND(field: str) -> bool:
        return all(getattr(p, field) for p in props_list)

    return ExpectedFileProperties(
        is_executable=AND("is_executable"),
        is_plain_text=AND("is_plain_text"),
        is_configuration=AND("is_configuration"),
        is_code=AND("is_code"),
        is_binary=AND("is_binary"),
        is_security_sensitive=AND("is_security_sensitive"),
        is_crlf_native=AND("is_crlf_native"),
    )


def infer_mime_types_from_extension(filepath: Path) -> Set[str]:
    """
    Infer candidate MIME types purely from the file extension (lowercased).
    This intentionally ignores the filename mapping (NAME_TO_MIMES) to keep
    extension-based inference explicit for callers that require it.
    """
    ext = filepath.suffix.lower()
    return set(EXT_TO_MIMES.get(ext, set()))


def infer_candidate_mime_types(filepath: Path) -> Set[str]:
    """
    Infer candidate MIME types using filename (if known) otherwise extension.
    This is a more general helper than infer_mime_types_from_extension().
    """
    name = filepath.name
    ext = filepath.suffix.lower()
    if name in NAME_TO_MIMES:
        return set(NAME_TO_MIMES[name])
    return set(EXT_TO_MIMES.get(ext, set()))


def get_expected_file_properties(filepath: Path) -> Optional[ExpectedFileProperties]:
    name = filepath.name
    ext = filepath.suffix.lower()  # Ensure extension is lower case for lookup

    # Prefer name-based MIME mapping (more specific); fall back to extension-based mapping.
    candidate_mimes: Set[str] = set()
    if name in NAME_TO_MIMES:
        candidate_mimes.update(NAME_TO_MIMES[name])
    elif ext in EXT_TO_MIMES:
        candidate_mimes.update(EXT_TO_MIMES[ext])

    if not candidate_mimes:
        return None

    # Compute conservative (lower-bound) expected properties across candidates
    return _lower_bound_properties(candidate_mimes)


# ============================================================
# Comment handling (configurable, reusable) — based on MIME
# ============================================================


@dataclass(frozen=True)
class CommentStyle:
    """
    Defines how comments work for a given file type.
    - line_markers: start of a line comment to EOL (e.g. "#", "//", "--", ";")
    - block_markers: pairs of (start, end) for block comments (e.g. "/*", "*/")
    """

    line_markers: Tuple[str, ...] = ()
    block_markers: Tuple[Tuple[str, str], ...] = ()


COMMENT_STYLES_BY_MIME: Dict[str, CommentStyle] = {}


def _def_comment(mime: str, line: Tuple[str, ...] = (), block: Tuple[Tuple[str, str], ...] = ()) -> None:
    COMMENT_STYLES_BY_MIME[mime] = CommentStyle(line_markers=line, block_markers=block)


# --- Hash-style / config-like ---
_def_comment("text/x-python", line=("#",), block=(('"""', '"""'), ("'''", "'''")))
_def_comment("text/x-shellscript", line=("#",))
_def_comment("text/x-ruby", line=("#",))
_def_comment("application/yaml", line=("#",))
_def_comment("application/toml", line=("#",))
_def_comment("text/x-ini", line=(";", "#"))
_def_comment("text/x-properties", line=("#", "!"))

# --- C / Java / Scala / Kotlin / Go / JS / TS & friends ---
for _mime in (
    "text/x-csrc",
    "text/x-chdr",
    "text/x-c++src",
    "text/x-c++hdr",
    "text/x-java-source",
    "text/x-kotlin",
    "text/x-kotlin-script",
    "text/x-scala",
    "text/x-go",
    "application/javascript",
    "text/javascript",
    "text/jsx",
    "application/mjs",
    "application/cjs",
    "text/typescript",
    "text/tsx",
    "text/x-php",
    "text/x-phtml",
):
    _def_comment(_mime, line=("//",), block=(("/*", "*/"),))

# --- SQL / Haskell / Lisp / Clojure ---
_def_comment("application/sql", line=("--",), block=(("/*", "*/"),))
_def_comment("text/x-sql", line=("--",), block=(("/*", "*/"),))
_def_comment("text/x-haskell", line=("--",), block=(("{-", "-}"),))
for _mime in (
    "text/x-lisp",
    "text/x-elisp",
    "text/x-scheme",
    "text/x-clojure",
    "text/x-racket",
):
    _def_comment(_mime, line=(";",))

# (Optional) Others that commonly support C-style comments
for _mime in (
    "text/x-verilog",
    "text/x-systemverilog",
    "text/x-vhdl",
    "text/x-swift",
    "text/x-csharp",
    "text/x-groovy",
):
    _def_comment(_mime, line=("//",), block=(("/*", "*/"),))


def _merge_comment_styles(styles: Iterable[CommentStyle]) -> CommentStyle:
    """Union the markers across styles; deduplicate while preserving a stable order."""
    line_seen: Dict[str, None] = {}
    block_seen: Dict[Tuple[str, str], None] = {}
    for s in styles:
        for m in s.line_markers:
            line_seen.setdefault(m, None)
        for b in s.block_markers:
            block_seen.setdefault(b, None)
    return CommentStyle(
        line_markers=tuple(line_seen.keys()),
        block_markers=tuple(block_seen.keys()),
    )


def get_comment_style_for_file(filepath: Path, *, prefer_extension: bool = True) -> Optional[CommentStyle]:
    """
    Return a CommentStyle for the given file.
    If multiple MIME candidates exist (e.g., ambiguous extension), we merge markers across them.
    By default, style inference uses extension-based MIME mapping as requested.
    """
    if prefer_extension:
        candidate_mimes = infer_mime_types_from_extension(filepath)
    else:
        candidate_mimes = infer_candidate_mime_types(filepath)

    styles = [COMMENT_STYLES_BY_MIME[m] for m in candidate_mimes if m in COMMENT_STYLES_BY_MIME]
    if not styles:
        return None
    return _merge_comment_styles(styles)

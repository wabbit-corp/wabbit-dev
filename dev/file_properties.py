from __future__ import annotations
from typing import List, Tuple, Optional, Dict
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
    is_security_sensitive: bool = False # Added this flag
    is_crlf_native: bool = False # Added this flag

    @property
    def is_text(self) -> bool:
        # Text includes plain text, structured config, and code
        return self.is_plain_text or self.is_configuration or self.is_code

# ============================================================
# Properties by Specific Filename (Case Sensitive by Default)
# ============================================================
PROPERTIES_BY_NAME: Dict[str, ExpectedFileProperties] = {
    # -- Common Project Metadata --
    "README":       ExpectedFileProperties(is_plain_text=True),
    "LICENSE":      ExpectedFileProperties(is_plain_text=True),
    "COPYING":      ExpectedFileProperties(is_plain_text=True),
    "CHANGELOG":    ExpectedFileProperties(is_plain_text=True),
    "CONTRIBUTING": ExpectedFileProperties(is_plain_text=True),
    "AUTHORS":      ExpectedFileProperties(is_plain_text=True),
    "TODO":         ExpectedFileProperties(is_plain_text=True),
    "HISTORY":      ExpectedFileProperties(is_plain_text=True),
    "NEWS":         ExpectedFileProperties(is_plain_text=True),
    "UPGRADE":      ExpectedFileProperties(is_plain_text=True),
    "UPGRADING":    ExpectedFileProperties(is_plain_text=True),
    "INSTALL":      ExpectedFileProperties(is_plain_text=True),
    "NOTICE":       ExpectedFileProperties(is_plain_text=True),
    "CODE_OF_CONDUCT": ExpectedFileProperties(is_plain_text=True), # Often Markdown, but treat as plain text info

    # -- Build & Task Runners --
    "Makefile":     ExpectedFileProperties(is_code=True), # Makefile syntax is code-like
    "makefile":     ExpectedFileProperties(is_code=True),
    "GNUmakefile":  ExpectedFileProperties(is_code=True),
    "Rakefile":     ExpectedFileProperties(is_code=True), # Ruby code
    "Gemfile":      ExpectedFileProperties(is_configuration=True), # Ruby DSL for deps
    "Podfile":      ExpectedFileProperties(is_configuration=True), # Ruby DSL for CocoaPods deps
    "Gruntfile.js": ExpectedFileProperties(is_code=True), # JS Code
    "gulpfile.js":  ExpectedFileProperties(is_code=True), # JS Code

    # -- Containerization --
    "Dockerfile":   ExpectedFileProperties(is_code=True), # Dockerfile syntax is code-like
    "dockerfile":   ExpectedFileProperties(is_code=True),
    ".dockerignore": ExpectedFileProperties(is_configuration=True),
    "compose.yaml": ExpectedFileProperties(is_configuration=True), # Docker Compose
    "compose.yml":  ExpectedFileProperties(is_configuration=True), # Docker Compose

    # -- Version Control & Ignore Files --
    ".gitignore":       ExpectedFileProperties(is_configuration=True),
    ".gitattributes":   ExpectedFileProperties(is_configuration=True),
    ".gitmodules":      ExpectedFileProperties(is_configuration=True),
    ".gitconfig":       ExpectedFileProperties(is_configuration=True), # Local repo config
    ".hgignore":        ExpectedFileProperties(is_configuration=True),
    ".hgsub":           ExpectedFileProperties(is_configuration=True),
    ".hgsubstate":      ExpectedFileProperties(is_configuration=True),
    ".svnignore":       ExpectedFileProperties(is_configuration=True), # SVN specific property name, less common
    ".npmignore":       ExpectedFileProperties(is_configuration=True),
    ".eslintignore":    ExpectedFileProperties(is_configuration=True),
    ".prettierignore":  ExpectedFileProperties(is_configuration=True),
    ".pylintrc":        ExpectedFileProperties(is_configuration=True), # Ini format
    ".flake8":          ExpectedFileProperties(is_configuration=True), # Ini format
    ".editorconfig":    ExpectedFileProperties(is_configuration=True), # Ini format

    # -- Environment & Secrets (Often security sensitive!) --
    ".env":             ExpectedFileProperties(is_configuration=True, is_security_sensitive=True),
    ".env.example":     ExpectedFileProperties(is_configuration=True, is_security_sensitive=False), # Example, not sensitive
    ".flaskenv":        ExpectedFileProperties(is_configuration=True, is_security_sensitive=True), # Flask specific
    ".netrc":           ExpectedFileProperties(is_configuration=True, is_security_sensitive=True), # FTP/HTTP credentials
    ".htpasswd":        ExpectedFileProperties(is_plain_text=True, is_security_sensitive=True), # Apache basic auth users
    ".htaccess":        ExpectedFileProperties(is_configuration=True), # Apache config
    "secrets.yaml":     ExpectedFileProperties(is_configuration=True, is_security_sensitive=True), # Common convention
    "secrets.yml":      ExpectedFileProperties(is_configuration=True, is_security_sensitive=True), # Common convention
    "credentials.json": ExpectedFileProperties(is_configuration=True, is_security_sensitive=True), # Common convention

    # -- Shell History (Potentially sensitive) --
    ".bash_history":    ExpectedFileProperties(is_plain_text=True, is_security_sensitive=True),
    ".zsh_history":     ExpectedFileProperties(is_plain_text=True, is_security_sensitive=True),
    ".python_history":  ExpectedFileProperties(is_plain_text=True, is_security_sensitive=True),

    # -- Package Management & Dependencies --
    "package.json":       ExpectedFileProperties(is_configuration=True), # Node.js
    "package-lock.json":  ExpectedFileProperties(is_configuration=True), # Node.js lockfile
    "yarn.lock":          ExpectedFileProperties(is_plain_text=True),    # Yarn lockfile (custom format)
    "composer.json":      ExpectedFileProperties(is_configuration=True), # PHP/Composer
    "composer.lock":      ExpectedFileProperties(is_configuration=True), # PHP/Composer lockfile
    "requirements.txt":   ExpectedFileProperties(is_configuration=True), # Python/pip
    "Pipfile":            ExpectedFileProperties(is_configuration=True), # Python/pipenv (TOML format)
    "Pipfile.lock":       ExpectedFileProperties(is_configuration=True), # Python/pipenv lockfile (JSON format)
    "pyproject.toml":     ExpectedFileProperties(is_configuration=True), # Python build system/deps (TOML)
    "Cargo.toml":         ExpectedFileProperties(is_configuration=True), # Rust/Cargo (TOML)
    "Cargo.lock":         ExpectedFileProperties(is_configuration=True), # Rust/Cargo lockfile (TOML)
    "go.mod":             ExpectedFileProperties(is_configuration=True), # Go modules
    "go.sum":             ExpectedFileProperties(is_plain_text=True),    # Go module checksums

    # -- Config Files for Specific Tools --
    ".babelrc":           ExpectedFileProperties(is_configuration=True), # Babel config (JSON)
    ".eslintrc":          ExpectedFileProperties(is_configuration=True), # ESLint config (can be JSON/YAML)
    ".prettierrc":        ExpectedFileProperties(is_configuration=True), # Prettier config (can be JSON/YAML/JS)
    ".stylelintrc":       ExpectedFileProperties(is_configuration=True), # Stylelint config
    ".travis.yml":        ExpectedFileProperties(is_configuration=True), # Travis CI config
    ".gitlab-ci.yml":     ExpectedFileProperties(is_configuration=True), # GitLab CI config
    "Jenkinsfile":        ExpectedFileProperties(is_code=True),          # Jenkins pipeline (Groovy)
    "Vagrantfile":        ExpectedFileProperties(is_code=True),          # Vagrant config (Ruby)
    "Procfile":           ExpectedFileProperties(is_configuration=True), # Heroku process types
    "now.json":           ExpectedFileProperties(is_configuration=True), # Vercel config (legacy)
    "vercel.json":        ExpectedFileProperties(is_configuration=True), # Vercel config
    "netlify.toml":       ExpectedFileProperties(is_configuration=True), # Netlify config

    # -- Misc --
    ".mailmap":         ExpectedFileProperties(is_plain_text=True), # Git author mapping
    "robots.txt":       ExpectedFileProperties(is_plain_text=True), # Web crawler instructions
    "humans.txt":       ExpectedFileProperties(is_plain_text=True), # Site credits
    "security.txt":     ExpectedFileProperties(is_plain_text=True), # Security policy reporting (RFC 9116)
}

# ============================================================
# Properties by File Extension (Case Insensitive - MUST be lower case)
# ============================================================
PROPERTIES_BY_EXTENSION: Dict[str, ExpectedFileProperties] = {
    # -- Plain Text & Documentation --
    ".txt":         ExpectedFileProperties(is_plain_text=True),
    ".md":          ExpectedFileProperties(is_plain_text=True), # Markdown is text, not typically "code" to lint line length strictly
    ".markdown":    ExpectedFileProperties(is_plain_text=True),
    ".rst":         ExpectedFileProperties(is_plain_text=True), # ReStructuredText
    ".adoc":        ExpectedFileProperties(is_plain_text=True), # AsciiDoc
    ".asciidoc":    ExpectedFileProperties(is_plain_text=True), # AsciiDoc
    ".tex":         ExpectedFileProperties(is_plain_text=True), # LaTeX source
    ".log":         ExpectedFileProperties(is_plain_text=True),
    ".csv":         ExpectedFileProperties(is_plain_text=True), # Comma Separated Values
    ".tsv":         ExpectedFileProperties(is_plain_text=True), # Tab Separated Values
    ".diff":        ExpectedFileProperties(is_plain_text=True), # Diff output
    ".patch":       ExpectedFileProperties(is_plain_text=True), # Patch file
    ".po":          ExpectedFileProperties(is_plain_text=True), # Gettext Portable Object (localization)
    ".pot":         ExpectedFileProperties(is_plain_text=True), # Gettext Template
    ".srt":         ExpectedFileProperties(is_plain_text=True), # SubRip subtitles
    ".vtt":         ExpectedFileProperties(is_plain_text=True), # WebVTT subtitles
    ".bib":         ExpectedFileProperties(is_plain_text=True), # BibTeX bibliography
    ".ics":         ExpectedFileProperties(is_plain_text=True), # iCalendar

    # -- Configuration Formats --
    ".json":        ExpectedFileProperties(is_configuration=True),
    ".yaml":        ExpectedFileProperties(is_configuration=True),
    ".yml":         ExpectedFileProperties(is_configuration=True),
    ".xml":         ExpectedFileProperties(is_configuration=True), # Often config, sometimes data or markup
    ".toml":        ExpectedFileProperties(is_configuration=True),
    ".ini":         ExpectedFileProperties(is_configuration=True),
    ".cfg":         ExpectedFileProperties(is_configuration=True),
    ".conf":        ExpectedFileProperties(is_configuration=True),
    ".cnf":         ExpectedFileProperties(is_configuration=True), # e.g. MySQL config
    ".properties":  ExpectedFileProperties(is_configuration=True), # Java properties
    ".prefs":       ExpectedFileProperties(is_configuration=True),
    ".settings":    ExpectedFileProperties(is_configuration=True),
    ".plist":       ExpectedFileProperties(is_configuration=True), # Apple Property List (XML or binary)
    ".xcconfig":    ExpectedFileProperties(is_configuration=True), # Xcode config
    ".env":         ExpectedFileProperties(is_configuration=True, is_security_sensitive=True), # Environment variables
    ".hcl":         ExpectedFileProperties(is_configuration=True), # HashiCorp Configuration Language
    ".tfvars":      ExpectedFileProperties(is_configuration=True, is_security_sensitive=True), # Terraform variables

    # -- Web Development --
    ".html":        ExpectedFileProperties(is_code=True), # Markup is code-like
    ".htm":         ExpectedFileProperties(is_code=True),
    ".css":         ExpectedFileProperties(is_code=True), # Stylesheets are code
    ".scss":        ExpectedFileProperties(is_code=True), # SASS/SCSS
    ".sass":        ExpectedFileProperties(is_code=True), # SASS (indented)
    ".less":        ExpectedFileProperties(is_code=True), # LESS CSS preprocessor
    ".styl":        ExpectedFileProperties(is_code=True), # Stylus CSS preprocessor
    ".js":          ExpectedFileProperties(is_code=True), # JavaScript
    ".jsx":         ExpectedFileProperties(is_code=True), # JavaScript React/JSX
    ".mjs":         ExpectedFileProperties(is_code=True), # JavaScript ES Module
    ".cjs":         ExpectedFileProperties(is_code=True), # JavaScript CommonJS Module
    ".ts":          ExpectedFileProperties(is_code=True), # TypeScript
    ".tsx":         ExpectedFileProperties(is_code=True), # TypeScript React/JSX
    ".vue":         ExpectedFileProperties(is_code=True), # Vue.js Single File Components
    ".svelte":      ExpectedFileProperties(is_code=True), # Svelte components
    ".php":         ExpectedFileProperties(is_code=True), # PHP code
    ".phtml":       ExpectedFileProperties(is_code=True), # PHP templated HTML
    ".asp":         ExpectedFileProperties(is_code=True), # Classic ASP
    ".aspx":        ExpectedFileProperties(is_code=True), # ASP.NET
    ".jsp":         ExpectedFileProperties(is_code=True), # Java Server Pages
    ".map":         ExpectedFileProperties(is_code=True), # Source Maps (JSON format, but relates to code)
    ".webmanifest": ExpectedFileProperties(is_configuration=True), # Web App Manifest (JSON format)
    ".graphql":     ExpectedFileProperties(is_code=True), # GraphQL query language
    ".gql":         ExpectedFileProperties(is_code=True), # GraphQL query language

    # -- Programming Languages (Source Code) --
    ".py":          ExpectedFileProperties(is_code=True), # Python
    ".rb":          ExpectedFileProperties(is_code=True), # Ruby
    ".java":        ExpectedFileProperties(is_code=True), # Java
    ".kt":          ExpectedFileProperties(is_code=True), # Kotlin
    ".kts":         ExpectedFileProperties(is_code=True), # Kotlin Script
    ".scala":       ExpectedFileProperties(is_code=True), # Scala
    ".swift":       ExpectedFileProperties(is_code=True), # Swift
    ".c":           ExpectedFileProperties(is_code=True), # C
    ".h":           ExpectedFileProperties(is_code=True), # C/C++/Objective-C Header
    ".cpp":         ExpectedFileProperties(is_code=True), # C++
    ".hpp":         ExpectedFileProperties(is_code=True), # C++ Header
    ".cc":          ExpectedFileProperties(is_code=True), # C++
    ".hh":          ExpectedFileProperties(is_code=True), # C++ Header
    ".cxx":         ExpectedFileProperties(is_code=True), # C++
    ".hxx":         ExpectedFileProperties(is_code=True), # C++ Header
    ".m":           ExpectedFileProperties(is_code=True), # Objective-C
    ".mm":          ExpectedFileProperties(is_code=True), # Objective-C++
    ".cs":          ExpectedFileProperties(is_code=True), # C#
    ".vb":          ExpectedFileProperties(is_code=True), # Visual Basic .NET
    ".fs":          ExpectedFileProperties(is_code=True), # F#
    ".fsi":         ExpectedFileProperties(is_code=True), # F# Signature
    ".fsx":         ExpectedFileProperties(is_code=True), # F# Script
    ".go":          ExpectedFileProperties(is_code=True), # Go
    ".rs":          ExpectedFileProperties(is_code=True), # Rust
    ".rlib":        ExpectedFileProperties(is_binary=True), # Rust Library (metadata + native code)
    ".hs":          ExpectedFileProperties(is_code=True), # Haskell
    ".lhs":         ExpectedFileProperties(is_code=True), # Literate Haskell
    ".erl":         ExpectedFileProperties(is_code=True), # Erlang
    ".hrl":         ExpectedFileProperties(is_code=True), # Erlang Header
    ".ex":          ExpectedFileProperties(is_code=True), # Elixir
    ".exs":         ExpectedFileProperties(is_code=True), # Elixir Script
    ".clj":         ExpectedFileProperties(is_code=True), # Clojure
    ".cljs":        ExpectedFileProperties(is_code=True), # ClojureScript
    ".cljc":        ExpectedFileProperties(is_code=True), # Clojure/ClojureScript common
    ".edn":         ExpectedFileProperties(is_configuration=True), # Extensible Data Notation (Clojure data format)
    ".lisp":        ExpectedFileProperties(is_code=True), # Common Lisp
    ".lsp":         ExpectedFileProperties(is_code=True), # Lisp variant
    ".scm":         ExpectedFileProperties(is_code=True), # Scheme
    ".ss":          ExpectedFileProperties(is_code=True), # Scheme
    ".rkt":         ExpectedFileProperties(is_code=True), # Racket
    ".el":          ExpectedFileProperties(is_code=True), # Emacs Lisp
    ".vim":         ExpectedFileProperties(is_code=True), # Vim Script
    ".lua":         ExpectedFileProperties(is_code=True), # Lua
    ".pl":          ExpectedFileProperties(is_code=True), # Perl
    ".pm":          ExpectedFileProperties(is_code=True), # Perl Module
    ".t":           ExpectedFileProperties(is_code=True), # Perl Test file
    ".dart":        ExpectedFileProperties(is_code=True), # Dart
    ".groovy":      ExpectedFileProperties(is_code=True), # Groovy
    ".gvy":         ExpectedFileProperties(is_code=True), # Groovy
    ".gradle":      ExpectedFileProperties(is_code=True), # Gradle build script (Groovy or Kotlin)
    ".tf":          ExpectedFileProperties(is_code=True), # Terraform (HCL code)
    ".sql":         ExpectedFileProperties(is_code=True), # SQL code (queries, DDL, DML)
    ".ddl":         ExpectedFileProperties(is_code=True), # SQL Data Definition Language
    ".dml":         ExpectedFileProperties(is_code=True), # SQL Data Manipulation Language
    ".ps1":         ExpectedFileProperties(is_code=True), # PowerShell Script
    ".psm1":        ExpectedFileProperties(is_code=True), # PowerShell Module
    ".psd1":        ExpectedFileProperties(is_configuration=True), # PowerShell Data File (Manifest)
    ".sh":          ExpectedFileProperties(is_code=True), # Shell script (Bash, Zsh, etc.) - NOTE: Executable status depends on permissions/shebang
    ".bash":        ExpectedFileProperties(is_code=True),
    ".zsh":         ExpectedFileProperties(is_code=True),
    ".ksh":         ExpectedFileProperties(is_code=True),
    ".csh":         ExpectedFileProperties(is_code=True),
    ".fish":        ExpectedFileProperties(is_code=True),
    ".awk":         ExpectedFileProperties(is_code=True), # AWK script
    ".applescript": ExpectedFileProperties(is_code=True), # AppleScript
    ".scpt":        ExpectedFileProperties(is_binary=True), # Compiled AppleScript
    ".coffee":      ExpectedFileProperties(is_code=True), # CoffeeScript
    ".litcoffee":   ExpectedFileProperties(is_code=True), # Literate CoffeeScript
    ".purs":        ExpectedFileProperties(is_code=True), # PureScript
    ".elm":         ExpectedFileProperties(is_code=True), # Elm
    ". R":          ExpectedFileProperties(is_code=True), # R script (case sensitive on some systems)
    ".r":           ExpectedFileProperties(is_code=True), # R script
    ".rmd":         ExpectedFileProperties(is_code=True), # R Markdown (mix of text and code)
    ".jl":          ExpectedFileProperties(is_code=True), # Julia
    ".nim":         ExpectedFileProperties(is_code=True), # Nim
    ".cr":          ExpectedFileProperties(is_code=True), # Crystal
    ".v":           ExpectedFileProperties(is_code=True), # Verilog / V / Coq
    ".vh":          ExpectedFileProperties(is_code=True), # Verilog Header
    ".sv":          ExpectedFileProperties(is_code=True), # SystemVerilog
    ".svh":         ExpectedFileProperties(is_code=True), # SystemVerilog Header
    ".vhd":         ExpectedFileProperties(is_code=True), # VHDL
    ".vhdl":        ExpectedFileProperties(is_code=True), # VHDL
    ".zig":         ExpectedFileProperties(is_code=True), # Zig
    ".odin":        ExpectedFileProperties(is_code=True), # Odin
    ".d":           ExpectedFileProperties(is_code=True), # D language
    ".f":           ExpectedFileProperties(is_code=True), # Fortran (fixed-form)
    ".f90":         ExpectedFileProperties(is_code=True), # Fortran (free-form)
    ".f95":         ExpectedFileProperties(is_code=True), # Fortran
    ".f03":         ExpectedFileProperties(is_code=True), # Fortran
    ".f08":         ExpectedFileProperties(is_code=True), # Fortran
    ".for":         ExpectedFileProperties(is_code=True), # Fortran (fixed-form)
    ".ada":         ExpectedFileProperties(is_code=True), # Ada
    ".adb":         ExpectedFileProperties(is_code=True), # Ada Body
    ".ads":         ExpectedFileProperties(is_code=True), # Ada Specification
    ".cob":         ExpectedFileProperties(is_code=True), # COBOL
    ".cbl":         ExpectedFileProperties(is_code=True), # COBOL
    ".pas":         ExpectedFileProperties(is_code=True), # Pascal
    ".pp":          ExpectedFileProperties(is_code=True), # Pascal / Puppet Manifest
    ".inc":         ExpectedFileProperties(is_code=True), # Include file (Pascal, PHP, Assembly etc.)
    ".asm":         ExpectedFileProperties(is_code=True), # Assembly language
    ".S":           ExpectedFileProperties(is_code=True), # Assembly language (often needs preprocessing)
    ".proto":       ExpectedFileProperties(is_code=True), # Protocol Buffers definition
    ".thrift":      ExpectedFileProperties(is_code=True), # Apache Thrift definition
    ".capnp":       ExpectedFileProperties(is_code=True), # Cap'n Proto definition
    ".idl":         ExpectedFileProperties(is_code=True), # Interface Definition Language (various)
    ".mustache":    ExpectedFileProperties(is_code=True), # Mustache templates
    ".hbs":         ExpectedFileProperties(is_code=True), # Handlebars templates
    ".pug":         ExpectedFileProperties(is_code=True), # Pug templates (formerly Jade)
    ".haml":        ExpectedFileProperties(is_code=True), # Haml templates
    ".slim":        ExpectedFileProperties(is_code=True), # Slim templates
    ".erb":         ExpectedFileProperties(is_code=True), # Embedded Ruby templates
    ".j2":          ExpectedFileProperties(is_code=True), # Jinja2 templates
    ".jinja2":      ExpectedFileProperties(is_code=True), # Jinja2 templates
    ".twig":        ExpectedFileProperties(is_code=True), # Twig templates

    # -- Build System Specific --
    ".pom":         ExpectedFileProperties(is_configuration=True), # Maven POM (XML)
    ".csproj":      ExpectedFileProperties(is_configuration=True), # C# Project (XML)
    ".vbproj":      ExpectedFileProperties(is_configuration=True), # VB.NET Project (XML)
    ".fsproj":      ExpectedFileProperties(is_configuration=True), # F# Project (XML)
    ".vcxproj":     ExpectedFileProperties(is_configuration=True), # C++ Project (Visual Studio, XML)
    ".sln":         ExpectedFileProperties(is_plain_text=True), # Visual Studio Solution (custom text format)
    ".xproj":       ExpectedFileProperties(is_configuration=True), # Old .NET Core Project (JSON)
    ".build":       ExpectedFileProperties(is_configuration=True), # MSBuild file (XML)
    ".sbt":         ExpectedFileProperties(is_code=True), # Scala Build Tool definition (Scala code)
    ".cmake":       ExpectedFileProperties(is_code=True), # CMake script
    "CMakeLists.txt": ExpectedFileProperties(is_code=True), # CMake script (handle by name too)

    # -- Binary / Compiled / Data Formats --
    ".pyc":         ExpectedFileProperties(is_binary=True), # Python compiled bytecode
    ".pyo":         ExpectedFileProperties(is_binary=True), # Python optimized bytecode
    ".pyd":         ExpectedFileProperties(is_binary=True), # Python extension module (Windows DLL)
    ".so":          ExpectedFileProperties(is_binary=True), # Shared Object library (Linux/Unix)
    ".dylib":       ExpectedFileProperties(is_binary=True), # Dynamic Library (macOS)
    ".dll":         ExpectedFileProperties(is_binary=True), # Dynamic Link Library (Windows)
    ".a":           ExpectedFileProperties(is_binary=True), # Static Library archive (Unix)
    ".lib":         ExpectedFileProperties(is_binary=True), # Static Library or Import Library (Windows)
    ".o":           ExpectedFileProperties(is_binary=True), # Compiled object file (Unix)
    ".obj":         ExpectedFileProperties(is_binary=True), # Compiled object file (Windows)
    ".class":       ExpectedFileProperties(is_binary=True), # Java compiled bytecode
    ".jar":         ExpectedFileProperties(is_binary=True), # Java Archive (ZIP format)
    ".war":         ExpectedFileProperties(is_binary=True), # Web Application Archive (ZIP format)
    ".ear":         ExpectedFileProperties(is_binary=True), # Enterprise Application Archive (ZIP format)
    ".aar":         ExpectedFileProperties(is_binary=True), # Android Archive (ZIP format)
    ".exe":         ExpectedFileProperties(is_binary=True, is_executable=True), # Windows Executable
    ".com":         ExpectedFileProperties(is_binary=True, is_executable=True), # MS-DOS Executable (less common now)
    ".bat":         ExpectedFileProperties(is_code=True, is_executable=True, is_crlf_native=True), # Windows Batch script (text, but primarily executable)
    ".cmd":         ExpectedFileProperties(is_code=True, is_executable=True, is_crlf_native=True), # Windows Command script (text, but primarily executable)
    ".msi":         ExpectedFileProperties(is_binary=True), # Microsoft Installer package
    ".deb":         ExpectedFileProperties(is_binary=True), # Debian package (ar archive)
    ".rpm":         ExpectedFileProperties(is_binary=True), # RPM package
    ".pkg":         ExpectedFileProperties(is_binary=True), # macOS Installer package
    ".dmg":         ExpectedFileProperties(is_binary=True), # macOS Disk Image
    ".iso":         ExpectedFileProperties(is_binary=True), # ISO Disk Image
    ".img":         ExpectedFileProperties(is_binary=True), # Disk Image
    ".vmdk":        ExpectedFileProperties(is_binary=True), # Virtual Machine Disk (VMware)
    ".vdi":         ExpectedFileProperties(is_binary=True), # Virtual Disk Image (VirtualBox)
    ".ova":         ExpectedFileProperties(is_binary=True), # Open Virtualization Archive (TAR format)
    ".ovf":         ExpectedFileProperties(is_configuration=True), # Open Virtualization Format (XML)
    ".apk":         ExpectedFileProperties(is_binary=True), # Android Package (ZIP format)
    ".ipa":         ExpectedFileProperties(is_binary=True), # iOS App Store Package (ZIP format)
    ".app":         ExpectedFileProperties(is_binary=True), # macOS Application Bundle (directory, but often treated as a single unit)
    ".bin":         ExpectedFileProperties(is_binary=True), # Generic binary data
    ".dat":         ExpectedFileProperties(is_binary=True), # Generic data file (often binary)
    ".db":          ExpectedFileProperties(is_binary=True), # Generic database file
    ".sqlite":      ExpectedFileProperties(is_binary=True), # SQLite Database
    ".sqlite3":     ExpectedFileProperties(is_binary=True), # SQLite Database
    ".dbf":         ExpectedFileProperties(is_binary=True), # dBase database file
    ".mdb":         ExpectedFileProperties(is_binary=True), # Microsoft Access Database (legacy)
    ".accdb":       ExpectedFileProperties(is_binary=True), # Microsoft Access Database
    ".sqlitedb":    ExpectedFileProperties(is_binary=True), # SQLite Database
    ".feather":     ExpectedFileProperties(is_binary=True), # Feather data format (Apache Arrow)
    ".parquet":     ExpectedFileProperties(is_binary=True), # Parquet data format
    ".avro":        ExpectedFileProperties(is_binary=True), # Avro data format
    ".orc":         ExpectedFileProperties(is_binary=True), # ORC data format
    ".npy":         ExpectedFileProperties(is_binary=True), # NumPy array data (binary)
    ".npz":         ExpectedFileProperties(is_binary=True), # NumPy zipped archive (binary)
    ".pkl":         ExpectedFileProperties(is_binary=True), # Python Pickle file (often binary)
    ".pickle":      ExpectedFileProperties(is_binary=True), # Python Pickle file
    ".joblib":      ExpectedFileProperties(is_binary=True), # Joblib dump file (Python)
    ".h5":          ExpectedFileProperties(is_binary=True), # HDF5 data file
    ".hdf5":        ExpectedFileProperties(is_binary=True), # HDF5 data file
    ".ipynb":       ExpectedFileProperties(is_code=True), # Jupyter Notebook (JSON format, but treated as code/document)
    ".RData":       ExpectedFileProperties(is_binary=True), # R data file
    ".rda":         ExpectedFileProperties(is_binary=True), # R data file (compressed)
    ".rds":         ExpectedFileProperties(is_binary=True), # R single object data file
    ".syd":         ExpectedFileProperties(is_binary=True), # SPSS System Data File
    ".sav":         ExpectedFileProperties(is_binary=True), # SPSS Saved Data File
    ".dta":         ExpectedFileProperties(is_binary=True), # Stata Data File
    ".sas7bdat":    ExpectedFileProperties(is_binary=True), # SAS Data Set
    ".mo":          ExpectedFileProperties(is_binary=True), # Gettext Machine Object (compiled localization)

    # -- Document Formats (Often Binary) --
    ".pdf":         ExpectedFileProperties(is_binary=True),
    ".doc":         ExpectedFileProperties(is_binary=True), # MS Word (legacy)
    ".docx":        ExpectedFileProperties(is_binary=True), # MS Word (OOXML)
    ".rtf":         ExpectedFileProperties(is_plain_text=True), # Rich Text Format (text, but complex) -> Changed to plain_text based on common understanding, though technically markup.
    ".odt":         ExpectedFileProperties(is_binary=True), # OpenDocument Text (ZIP format)
    ".wpd":         ExpectedFileProperties(is_binary=True), # WordPerfect Document
    ".xls":         ExpectedFileProperties(is_binary=True), # MS Excel (legacy)
    ".xlsx":        ExpectedFileProperties(is_binary=True), # MS Excel (OOXML)
    ".ods":         ExpectedFileProperties(is_binary=True), # OpenDocument Spreadsheet (ZIP format)
    ".ppt":         ExpectedFileProperties(is_binary=True), # MS PowerPoint (legacy)
    ".pptx":        ExpectedFileProperties(is_binary=True), # MS PowerPoint (OOXML)
    ".odp":         ExpectedFileProperties(is_binary=True), # OpenDocument Presentation (ZIP format)
    ".key":         ExpectedFileProperties(is_binary=True), # Apple Keynote Presentation (ZIP format)
    ".numbers":     ExpectedFileProperties(is_binary=True), # Apple Numbers Spreadsheet (ZIP format)
    ".pages":       ExpectedFileProperties(is_binary=True), # Apple Pages Document (ZIP format)

    # -- Image Formats (Binary) --
    ".jpg":         ExpectedFileProperties(is_binary=True),
    ".jpeg":        ExpectedFileProperties(is_binary=True),
    ".png":         ExpectedFileProperties(is_binary=True),
    ".gif":         ExpectedFileProperties(is_binary=True),
    ".bmp":         ExpectedFileProperties(is_binary=True),
    ".tiff":        ExpectedFileProperties(is_binary=True),
    ".tif":         ExpectedFileProperties(is_binary=True),
    ".webp":        ExpectedFileProperties(is_binary=True),
    ".ico":         ExpectedFileProperties(is_binary=True), # Icon file
    ".icns":        ExpectedFileProperties(is_binary=True), # Apple Icon Image format
    ".psd":         ExpectedFileProperties(is_binary=True), # Photoshop Document
    ".ai":          ExpectedFileProperties(is_binary=True), # Adobe Illustrator (often PDF-based)
    ".eps":         ExpectedFileProperties(is_binary=True), # Encapsulated PostScript
    ".svg":         ExpectedFileProperties(is_code=True), # Scalable Vector Graphics (XML based, so text/code)
    ".dxf":         ExpectedFileProperties(is_plain_text=True), # Drawing Exchange Format (CAD, often text)
    ".dwg":         ExpectedFileProperties(is_binary=True), # AutoCAD Drawing (binary)
    ".xcf":         ExpectedFileProperties(is_binary=True), # GIMP image format

    # -- Audio Formats (Binary) --
    ".mp3":         ExpectedFileProperties(is_binary=True),
    ".wav":         ExpectedFileProperties(is_binary=True),
    ".ogg":         ExpectedFileProperties(is_binary=True), # Ogg Vorbis audio
    ".flac":        ExpectedFileProperties(is_binary=True), # Free Lossless Audio Codec
    ".aac":         ExpectedFileProperties(is_binary=True), # Advanced Audio Coding
    ".m4a":         ExpectedFileProperties(is_binary=True), # Apple Lossless Audio / AAC audio
    ".wma":         ExpectedFileProperties(is_binary=True), # Windows Media Audio
    ".aiff":        ExpectedFileProperties(is_binary=True), # Audio Interchange File Format
    ".opus":        ExpectedFileProperties(is_binary=True), # Opus audio codec

    # -- Video Formats (Binary) --
    ".mp4":         ExpectedFileProperties(is_binary=True),
    ".mkv":         ExpectedFileProperties(is_binary=True), # Matroska Video
    ".mov":         ExpectedFileProperties(is_binary=True), # QuickTime Movie
    ".avi":         ExpectedFileProperties(is_binary=True), # Audio Video Interleave
    ".wmv":         ExpectedFileProperties(is_binary=True), # Windows Media Video
    ".flv":         ExpectedFileProperties(is_binary=True), # Flash Video
    ".webm":        ExpectedFileProperties(is_binary=True), # WebM Video (VP8/VP9/AV1 + Vorbis/Opus)
    ".mpeg":        ExpectedFileProperties(is_binary=True),
    ".mpg":         ExpectedFileProperties(is_binary=True),
    ".ogv":         ExpectedFileProperties(is_binary=True), # Ogg Video
    ".3gp":         ExpectedFileProperties(is_binary=True), # 3GPP multimedia format
    ".m4v":         ExpectedFileProperties(is_binary=True), # M4V video format (often for Apple devices)

    # -- Archive Formats (Binary) --
    ".zip":         ExpectedFileProperties(is_binary=True),
    ".tar":         ExpectedFileProperties(is_binary=True), # Tarball (uncompressed archive)
    ".gz":          ExpectedFileProperties(is_binary=True), # Gzip compressed file
    ".tgz":         ExpectedFileProperties(is_binary=True), # Gzipped Tarball (.tar.gz)
    ".bz2":         ExpectedFileProperties(is_binary=True), # Bzip2 compressed file
    ".tbz":         ExpectedFileProperties(is_binary=True), # Bzipped Tarball (.tar.bz2)
    ".tbz2":        ExpectedFileProperties(is_binary=True), # Bzipped Tarball (.tar.bz2)
    ".xz":          ExpectedFileProperties(is_binary=True), # XZ compressed file
    ".txz":         ExpectedFileProperties(is_binary=True), # XZ compressed Tarball (.tar.xz)
    ".lzma":        ExpectedFileProperties(is_binary=True), # LZMA compressed file
    ".tlz":         ExpectedFileProperties(is_binary=True), # LZMA compressed Tarball (.tar.lzma)
    ".7z":          ExpectedFileProperties(is_binary=True), # 7-Zip archive
    ".rar":         ExpectedFileProperties(is_binary=True), # RAR archive
    ".z":           ExpectedFileProperties(is_binary=True), # compress (Unix legacy)
    ".zst":         ExpectedFileProperties(is_binary=True), # Zstandard compressed file
    ".whl":         ExpectedFileProperties(is_binary=True), # Python Wheel package (ZIP format)

    # -- Font Formats (Binary) --
    ".ttf":         ExpectedFileProperties(is_binary=True), # TrueType Font
    ".otf":         ExpectedFileProperties(is_binary=True), # OpenType Font
    ".woff":        ExpectedFileProperties(is_binary=True), # Web Open Font Format
    ".woff2":       ExpectedFileProperties(is_binary=True), # Web Open Font Format 2
    ".eot":         ExpectedFileProperties(is_binary=True), # Embedded OpenType

    # -- Security Sensitive Files (Often certificates/keys) --
    ".pem":         ExpectedFileProperties(is_plain_text=True, is_security_sensitive=True), # Privacy-Enhanced Mail cert/key (Base64 text)
    ".key":         ExpectedFileProperties(is_plain_text=True, is_security_sensitive=True), # Private Key (often PEM format)
    ".crt":         ExpectedFileProperties(is_plain_text=True, is_security_sensitive=False), # Certificate (often PEM format, usually public)
    ".cer":         ExpectedFileProperties(is_plain_text=True, is_security_sensitive=False), # Certificate (alternative extension)
    ".der":         ExpectedFileProperties(is_binary=True, is_security_sensitive=False), # Distinguished Encoding Rules cert/key (binary)
    ".p12":         ExpectedFileProperties(is_binary=True, is_security_sensitive=True), # PKCS#12 key/cert bundle (binary)
    ".pfx":         ExpectedFileProperties(is_binary=True, is_security_sensitive=True), # Personal Information Exchange (like .p12)
    ".p7b":         ExpectedFileProperties(is_plain_text=True, is_security_sensitive=False), # PKCS#7 cert bundle (text)
    ".p7c":         ExpectedFileProperties(is_binary=True, is_security_sensitive=False), # PKCS#7 cert bundle (binary)
    ".jks":         ExpectedFileProperties(is_binary=True, is_security_sensitive=True), # Java KeyStore
    ".pub":         ExpectedFileProperties(is_plain_text=True, is_security_sensitive=False), # Public key file (e.g., SSH)
    ".asc":         ExpectedFileProperties(is_plain_text=True, is_security_sensitive=False), # PGP armored file (key, signature, or encrypted data)
    ".gpg":         ExpectedFileProperties(is_binary=True, is_security_sensitive=True), # PGP encrypted file (binary)
    ".kdbx":        ExpectedFileProperties(is_binary=True, is_security_sensitive=True), # KeePass password database

    # -- Misc --
    ".bak":         ExpectedFileProperties(is_binary=True), # Backup file (could be text or binary) -> Defaulting to binary as a safe guess
    ".tmp":         ExpectedFileProperties(is_binary=True), # Temporary file (could be anything) -> Defaulting to binary
    ".swp":         ExpectedFileProperties(is_binary=True), # Vim swap file
    ".swo":         ExpectedFileProperties(is_binary=True), # Vim swap file
    ".lock":        ExpectedFileProperties(is_plain_text=True), # Lock file (often empty or simple text)
    ".pid":         ExpectedFileProperties(is_plain_text=True), # Process ID file
    ".service":     ExpectedFileProperties(is_configuration=True), # Systemd service unit file (INI-like)
    ".socket":      ExpectedFileProperties(is_configuration=True), # Systemd socket unit file
    ".timer":       ExpectedFileProperties(is_configuration=True), # Systemd timer unit file
    ".target":      ExpectedFileProperties(is_configuration=True), # Systemd target unit file
    ".mount":       ExpectedFileProperties(is_configuration=True), # Systemd mount unit file
    ".automount":   ExpectedFileProperties(is_configuration=True), # Systemd automount unit file
    ".path":        ExpectedFileProperties(is_configuration=True), # Systemd path unit file
    ".scope":       ExpectedFileProperties(is_configuration=True), # Systemd scope unit file (runtime)
    ".slice":       ExpectedFileProperties(is_configuration=True), # Systemd slice unit file
    ".desktop":     ExpectedFileProperties(is_configuration=True), # Linux Desktop entry file (INI-like)
    ".xsd":         ExpectedFileProperties(is_configuration=True), # XML Schema Definition (XML)
    ".xsl":         ExpectedFileProperties(is_code=True), # XSL Transformation (XML code)
    ".xslt":        ExpectedFileProperties(is_code=True), # XSL Transformation (XML code)
    ".dtd":         ExpectedFileProperties(is_configuration=True), # Document Type Definition (SGML/XML schema)
    ".mod":         ExpectedFileProperties(is_code=True), # Module file (various langs like Go, Fortran)
    ".sig":         ExpectedFileProperties(is_plain_text=True), # Signature file (e.g., F#, or GPG .asc)
    ".sym":         ExpectedFileProperties(is_binary=True), # Debug symbols (binary)
    ".pdb":         ExpectedFileProperties(is_binary=True), # Program Database (debug symbols, Windows binary)
    ".DS_Store":    ExpectedFileProperties(is_binary=True), # macOS Finder metadata
    "Thumbs.db":    ExpectedFileProperties(is_binary=True), # Windows Explorer thumbnail cache

}

# Function remains the same
def get_expected_file_properties(filepath: Path) -> Optional[ExpectedFileProperties]:
    name = filepath.name
    ext = filepath.suffix.lower() # Ensure extension is lower case for lookup

    # Prioritize lookup by full name (case sensitive based on dict keys)
    if name in PROPERTIES_BY_NAME:
        return PROPERTIES_BY_NAME[name]

    # Fallback to lookup by extension (case insensitive due to .lower())
    if ext in PROPERTIES_BY_EXTENSION:
        return PROPERTIES_BY_EXTENSION[ext]

    # Return None if no match found
    return None

# Example Usage (Optional)
# if __name__ == "__main__":
#     test_files = [
#         Path("README.md"), Path("src/main.py"), Path("config.yaml"),
#         Path("Makefile"), Path(".env"), Path("archive.zip"),
#         Path("my_script.sh"), Path("document.pdf"), Path("image.jpg"),
#         Path("private.key"), Path("app.exe"), Path("unknown.xyz"),
#         Path("Dockerfile"), Path(".gitignore")
#     ]
#     for f in test_files:
#         props = get_expected_file_properties(f)
#         print(f"File: {f.name:<20} -> Properties: {props}")
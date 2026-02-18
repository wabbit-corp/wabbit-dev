(git-user "Test User" "test@example.invalid")

(python-defaults
    :line-length "120"
    :target-version "py310"
    :coverage-fail-under "80"
    :coverage-precision "0"
    :coverage-branch true
    :coverage-show-missing true
    :coverage-skip-empty true
    :coverage-xml-output "coverage.xml")

(python "app-wabbit-dev"
    :version "1.1.0"
    :name "wabbit-dev"
    :description "Development utilities for the Wabbit project"
    :authors ["Sir Wabbit"]
    :requires-python "^3.12"
    :dependencies [
        "beautifulsoup4>=4.12.3,<5.0.0"
        "aiohttp>=3.11.11,<4.0.0"
        "aiodns>=3.2.0,<4.0.0"
        "requests>=2.32.3,<3.0.0"
        "crossrefapi>=1.6.0,<2.0.0"
        "arxiv>=2.1.3,<3.0.0"
        "semanticscholar>=0.9.0,<2.0.0"
        "jinja2>=3.1.5,<4.0.0"
        "pathspec>=0.12.1,<2.0.0"
        "pygithub>=2.5.0,<3.0.0"
        "gitpython>=3.1.44,<4.0.0"
        "graphviz>=0.20.3,<1.0.0"
        "anthropic>=0.44.0,<2.0.0"
        "openai>=1.60.0,<2.0.0"
        "fastembed>=0.7.0,<1.0.0"
    ]
    :dev-dependencies [
        "pytest>=8.2.2,<9.0.0"
        "pyinstaller>=6.9.0,<7.0.0"
    ]
    :scripts ["wabbit-dev=dev.cli:main"]
    :repo "wabbit-corp/wabbit-dev")

(python "python-easytime"
    :version "0.2.0"
    :name "easytime"
    :description "A less error-prone date&time manipulation library"
    :authors ["Sir Wabbit <wabbit@wabbit.one>"]
    :requires-python ">=3.10"
    :license null
    :dependencies [
        "pytz"
        "python-dateutil"
    ])

(python "python-fx"
    :version "0.2.0"
    :name "fx"
    :description "functional generator patterns"
    :authors ["Sir Wabbit <wabbit@wabbit.one>"]
    :requires-python ">=3.10"
    :license null)

(python "python-gigaword"
    :version "0.1.0"
    :name "gigaword"
    :description "gigaword parser"
    :authors ["Sir Wabbit <wabbit@wabbit.one>"]
    :requires-python ">=3.10"
    :license null)

(python "python-jeeves"
    :version "0.1.0"
    :name "jeeves"
    :requires-python ">=3.10"
    :license null
    :features [
        (python-deptry
            :package-map {
                "djangorestframework": "rest_framework"
                "imbalanced-learn": "imblearn"
                "scikit-learn": "sklearn"
            }
            :per-rule-ignores { "DEP002": ["hypothesis"] }
            :auto-package-map true)
        (python-importlinter
            :layers ["servant" "codi" "typed_json"])
    ]
    :source-sets [
        { "path": "codi" "kind": "main" }
        { "path": "servant" "kind": "main" }
        { "path": "typed_json" "kind": "main" }
        { "path": "tests" "kind": "test" }
        { "path": "codi/api/tests" "kind": "test" }
    ]
    :dependencies [
        "aiohttp"
        "defusedxml"
        "discord.py"
        "discord-ext-voice-recv"
        "Django"
        "djangorestframework"
        "emoji"
        "hypothesis"
        "imbalanced-learn"
        "Levenshtein"
        "numpy"
        "openai"
        "PyGithub"
        "PyNaCl>=1.6.2"
        "PyYAML"
        "python-dateutil"
        "python-dotenv"
        "pytz"
        "requests"
        "scikit-learn"
        "sentence-transformers"
        "timezonefinder"
        "tqdm"
        "youtube-transcript-api"
    ])

(python "python-lang-mu"
    :version "1.0.0"
    :name "python-lang-mu"
    :description "Mu Configuration Language"
    :authors ["Sir Wabbit <wabbit@wabbit.one>"]
    :requires-python ">=3.10"
    :license null
    :dev-dependencies ["pytest"])

(python "python-calibre-helper"
    :version "0.1.0"
    :name "python-calibre-helper"
    :requires-python ">=3.10"
    :license null
    :dependencies [
        "arxiv"
        "ocrmypdf"
        "openai"
        "PyMuPDF"
        "pypdf"
        "pytz"
        "requests"
    ])

(python "python-vintagestory"
    :version "0.1.0"
    :name "python-vintagestory"
    :requires-python ">=3.10"
    :license null
    :dependencies [
        "aiohttp"
        "beautifulsoup4"
        "termcolor"
    ])

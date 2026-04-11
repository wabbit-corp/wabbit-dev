Publishing a Python package to the Python Package Index (PyPI) involves careful preparation, packaging, and security steps. This guide (updated as of May 4, 2025) walks you through structuring your project, configuring packaging metadata, building distributions, and uploading securely to PyPI. We assume you have a unique package name (e.g. derived from your own domain) and an email address on that domain for your PyPI account.

Preparation
-----------

Before publishing, set up your project structure and development environment:

*   **Project Structure:** Organize your code into a Python package directory, typically using a “src layout” for clarity. For example:
    
    ```text
    your-package/
    ├── pyproject.toml          # Build configuration (or setup.py/setup.cfg)
    ├── README.md               # Project README for PyPI description
    ├── LICENSE                 # License file (e.g. MIT, Apache 2.0)
    ├── src/
    │   └── your_package/       # Package source code
    │       ├── __init__.py
    │       └── module.py
    └── tests/                  # (Optional) test suite
        └── test_module.py
    ```
    
    The package directory (`your_package/`) should have an `__init__.py` (even if empty) so Python recognizes it as a package[packaging.python.org](https://packaging.python.org/tutorials/packaging-projects/#:~:text=%E2%94%94%E2%94%80%E2%94%80%20example_package_YOUR_USERNAME_HERE%2F%20%E2%94%9C%E2%94%80%E2%94%80%20__init__,py). The `src/` layout is recommended to avoid import confusion during development[packaging.python.org](https://packaging.python.org/tutorials/packaging-projects/#:~:text=Create%20the%20following%20file%20structure,locally). Choose a **unique distribution name** for your project – it can contain letters, numbers, `_` or `-` and must not already exist on PyPI[packaging.python.org](https://packaging.python.org/tutorials/packaging-projects/#:~:text=Issues%20%3D%20).
    
*   **Required Files:** Include a **README** (often in Markdown or reStructuredText) describing your project, and a **LICENSE** file with your open-source license. PyPI will display the README as the long description on your package page, and including a license file is important for users and compliance[packaging.python.org](https://packaging.python.org/tutorials/packaging-projects/#:~:text=description%20%3D%20,files%20%3D%20%5B%22LICEN%5BCS%5DE)[packaging.python.org](https://packaging.python.org/tutorials/packaging-projects/#:~:text=https%3A%2F%2Fpypi). Common practice also includes files like `CHANGELOG.md` or `HISTORY.md` (to record changes), and possibly a `CONTRIBUTING.md` for open-source contributors, though these aren’t required by PyPI.
    
*   **Pure Python vs. Extensions:** If your project is pure Python, your source tree will just contain `.py` files. If you need to include compiled code (e.g. a C extension or Cython module), plan for additional files:
    
    *   **C/C++ extensions:** You might have a `src/your_package` directory with C/C++ source (`.c`/`.cpp`) and possibly a `setup.py` or build script to compile them.
        
    *   **Cython modules:** Include the `.pyx` Cython source and any generated C code or build instructions. You’ll use Cython during the build process to generate the extension module.
        
    
    The packaging process supports both pure-Python and binary extensions, but binary extensions require building wheels for each target platform. We’ll discuss how to include and distribute these in the “Build and Distribute” section.
    
*   **Virtual Environment for Development:** Use a virtual environment to isolate your project:
    
    *   Create a venv: for example, `python3 -m venv .venv` and activate it (this ensures dependencies you install for development don’t pollute your system Python).
        
    *   Inside the venv, install the tools you’ll need (like `build`, `twine`, and linters or test frameworks).
        
    *   Manage **dependencies**: distinguish between _project runtime dependencies_ and _development dependencies_. For runtime dependencies (needed by your package), you will declare them in your packaging config (so they get installed with your package). For dev/test dependencies (like pytest, black, etc.), use a separate `requirements-dev.txt` or specify them as extras (e.g. a `dev` extra) or use a tool like Poetry to manage them separately. This separation prevents installing unnecessary packages for end users.
        
*   **Domain Email:** Ensure you have a professional email (e.g. `you@yourdomain.com`) ready. You will use this email for your PyPI account and can also list it in package metadata as the author or maintainer email. Using your own domain email adds credibility and consistency to your package identity.
    

Packaging Approaches
--------------------

Python packaging has evolved to support multiple approaches. We’ll cover three common methods: the legacy `setup.py` (with or without `setup.cfg`), the modern `pyproject.toml` (PEP 517/518 with setuptools), and using **Poetry**. Each approach ultimately produces installable distributions, but they differ in configuration style and tooling.

### Legacy: `setup.py` (and `setup.cfg`)

Traditionally, Python packages used a **setup script**. A `setup.py` file at the project root executes setuptools’ `setup()` function to define package metadata and build instructions. For example:

```python
# setup.py (legacy approach)
import setuptools

setuptools.setup(
    name="your-package",
    version="0.1.0",
    description="A short description of your package",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    author="Your Name",
    author_email="you@yourdomain.com",
    url="https://yourproject.yourdomain.com",
    license="MIT",
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    packages=setuptools.find_packages(where="src"),
    package_dir={"": "src"},
    python_requires=">=3.8",
    install_requires=[
        "requests>=2.0,<3.0",   # example dependency
    ],
    extras_require={
        "dev": ["pytest>=6.0", "cython"]  # example extra group
    },
)
```

This script includes all metadata (name, version, author, description, etc.) and configuration for building the package. **However, `setup.py` is now considered legacy** for defining metadata. Modern tools favor static configuration in declarative files instead of executing code to get metadata. In fact, features like PEP 517 build isolation mean that `setup.py` isn’t invoked directly in many cases[packaging.python.org](https://packaging.python.org/tutorials/packaging-projects/#:~:text=The%20,own%20documentation%20for%20more%20details). Today, you typically still include a minimal `setup.py` only if needed for backward compatibility or for dynamic behaviors (like custom build steps). Many projects instead use a `setup.cfg` (a static setup configuration) or just `pyproject.toml`.

**Setup.cfg:** This is an INI-format configuration file that can be used alongside a minimal `setup.py`. For example, you could move most of the above settings into `setup.cfg`:

```ini
# setup.cfg (alternative to encoding metadata in code)
[metadata]
name = your-package
version = 0.1.0
description = A short description of your package
long_description = file: README.md
long_description_content_type = text/markdown
author = Your Name
author_email = you@yourdomain.com
url = https://yourproject.yourdomain.com
license = MIT
classifiers =
    Programming Language :: Python :: 3
    License :: OSI Approved :: MIT License
    Operating System :: OS Independent

[options]
packages = find:
package_dir =
    = src
python_requires = >=3.8
install_requires =
    requests>=2.0,<3.0

[options.extras_require]
dev = 
    pytest>=6.0
    cython
```

With this approach, `setup.py` can be as simple as:

```python
import setuptools
setuptools.setup()  # it will read setup.cfg
```

Setuptools will automatically read the configuration from `setup.cfg` when `setup()` is called. This **declarative config** is easier to maintain and avoids executing code for metadata.

**Note:** If you use `setup.py`/`setup.cfg`, you still need a minimal `pyproject.toml` to declare the build system (PEP 518). For example, include a `pyproject.toml` with:

```toml
[build-system]
requires = ["setuptools>=61.0", "wheel"]
build-backend = "setuptools.build_meta"
```

This tells tools like pip to use setuptools as the build backend[packaging.python.org](https://packaging.python.org/tutorials/packaging-projects/#:~:text=setuptools). (We cover `pyproject.toml` in detail next.) In summary, the legacy approach works, but modern standards favor the next method.

### Modern: `pyproject.toml` with Setuptools (PEP 517/621)

PEP 517 and PEP 518 introduced a standardized build interface using `pyproject.toml`. This file declares the **build system requirements** and can also include package metadata via PEP 621’s `[project]` table. Using `pyproject.toml` is now the recommended standard for packaging.

**Build system declaration:** In your `pyproject.toml`, specify the build backend and its requirement. For setuptools, for example:

```toml
[build-system]
requires = ["setuptools >= 77.0.0", "wheel"]  # use a recent setuptools and wheel
build-backend = "setuptools.build_meta"
```

This ensures tools will install setuptools and wheel in an isolated environment to build your package[packaging.python.org](https://packaging.python.org/tutorials/packaging-projects/#:~:text=%5Bbuild,backend%20%3D%20%22setuptools.build_meta)[packaging.python.org](https://packaging.python.org/tutorials/packaging-projects/#:~:text=The%20,introduced%20support%20for%20%20104). Now, instead of using `setup.cfg`, you can put package metadata in the `[project]` section of `pyproject.toml` (supported by setuptools versions ≥61 which implement PEP 621):

```toml
[project]
name = "your-package"
version = "0.1.0"
description = "A short description of your package"
readme = "README.md"
requires-python = ">=3.8"
license = "MIT"
authors = [
    { name="Your Name", email="you@yourdomain.com" }
]
classifiers = [
    "Programming Language :: Python :: 3",
    "Operating System :: OS Independent",
    "License :: OSI Approved :: MIT License"
]
dependencies = [
    "requests>=2.0,<3.0",
]
dynamic = []  # (if any fields are computed dynamically, list them here)
```

```toml
[project.optional-dependencies]
dev = [
    "pytest>=6.0",
    "cython",
]
```

```toml
[project.urls]
Homepage = "https://yourproject.yourdomain.com"
Source = "https://github.com/youruser/yourproject"
```

In this example, the `[project]` table defines the core metadata:

*   **name & version:** Distribution name on PyPI and release version. These are required. The name must be unique on PyPI[packaging.python.org](https://packaging.python.org/tutorials/packaging-projects/#:~:text=,as%20one%20which%20already%20exists), and the version should follow PEP 440 (e.g. semantic versioning).
    
*   **description & readme:** A short summary and the README file for long description. By pointing to `README.md`, PyPI will show its content on your project page[packaging.python.org](https://packaging.python.org/tutorials/packaging-projects/#:~:text=,toml%20guide).
    
*   **requires-python:** The Python versions your package supports (e.g. `>=3.8` means it requires Python 3.8 or newer)[packaging.python.org](https://packaging.python.org/tutorials/packaging-projects/#:~:text=%2A%20%60requires,has%20a%20matching%20Python%20version). Tools like pip use this to refuse installation on unsupported Python versions.
    
*   **license:** The license identifier (setuptools now supports SPDX license identifiers via PEP 639)[packaging.python.org](https://packaging.python.org/tutorials/packaging-projects/#:~:text=https%3A%2F%2Fpypi). Here we use `"MIT"` which is a known SPDX ID for the MIT License.
    
*   **authors/maintainers:** You can list authors and/or maintainers with name and email[packaging.python.org](https://packaging.python.org/tutorials/packaging-projects/#:~:text=,in%20the%20same%20format). This information is included in package metadata (and is public on PyPI). Using your domain email here is fine.
    
*   **classifiers:** Trove classifiers for metadata. At minimum, indicate your intended Python versions and OS compatibility[packaging.python.org](https://packaging.python.org/tutorials/packaging-projects/#:~:text=,org%2Fclassifiers), and the License classifier (e.g. “OSI Approved :: MIT License”). These classifiers make your project searchable on PyPI.
    
*   **dependencies:** This lists your runtime dependencies (what will be installed alongside your package). Each entry should ideally include a version range. (The example uses `requests>=2.0,<3.0` which means any 2.x version of requests is acceptable). Avoid pinning to exact versions unless absolutely necessary, to prevent conflicts[discuss.python.org](https://discuss.python.org/t/should-i-be-pinning-my-dependencies/13159#:~:text=jwodder%20%28John%20T,15%2C%202022%2C%2011%3A38pm%20%202).
    
*   **optional-dependencies:** These define extras. In the above, a “dev” extra includes `pytest` and `cython` which a developer or contributor can install with `pip install your-package[dev]`. You can define multiple extras groups (e.g. for docs, testing, etc.) similarly[packaging.python.org](https://packaging.python.org/tutorials/packaging-projects/#:~:text=,a%20file%20or%20Git%20tag).
    
*   **urls:** Additional links for the project (these will show up as buttons on PyPI, e.g. “Homepage”, “Source”, “Documentation”, etc.)[packaging.python.org](https://packaging.python.org/tutorials/packaging-projects/#:~:text=,source%2C%20documentation%2C%20issue%20trackers%2C%20etc). It’s good practice to at least provide a source code link and project homepage if available.
    

Setuptools will use this `[project]` metadata when building the package, so you don’t need a `setup.py` at all for a pure-python project. If you have special build steps (like compiling C code or generating files), you might still include a `setup.cfg` or `setup.py` to configure that, but for most packages this won’t be needed.

**Dynamic vs Static metadata:** The `dynamic = []` list in the example above is left empty, indicating all fields are statically defined. If, for instance, you wanted the version to be read from your module (to avoid duplication), you would list `"version"` as dynamic and provide it via code. However, static definitions are simpler and preferred for consistency.

### Using Poetry

Poetry is an all-in-one tool that manages dependencies and packaging. It uses `pyproject.toml` under the hood, but with its own `[tool.poetry]` configuration section for metadata and dependencies (instead of the `[project]` table). Poetry can simplify environment management and publishing, at the cost of adding an extra tool requirement for collaborators.

If you initialize a project with Poetry (`poetry new`), it will create a `pyproject.toml` like:

```toml
[tool.poetry]
name = "your-package"
version = "0.1.0"
description = "A short description of your package"
authors = ["Your Name <you@yourdomain.com>"]
readme = "README.md"
license = "MIT"
repository = "https://github.com/youruser/yourproject"
homepage = "https://yourproject.yourdomain.com"
keywords = ["example", "packaging"]

[tool.poetry.dependencies]
python = ">=3.8"
requests = "^2.0.0"

[tool.poetry.dev-dependencies]
pytest = "^6.0"

[build-system]
requires = ["poetry-core>=1.5.0"]
build-backend = "poetry.core.masonry.api"
```

Key points for Poetry:

*   The `[tool.poetry]` section fields largely mirror the standard metadata (name, version, description, authors, etc.). Poetry enforces PEP 440 versions and encourages semantic versioning.
    
*   Dependencies are split into `dependencies` (runtime) and `dev-dependencies` (for development only). Poetry uses caret (`^`) by default to specify version ranges (e.g. `^2.0.0` means `>=2.0.0, <3.0.0` in PEP 440 terms).
    
*   Poetry will manage a `poetry.lock` file with exact resolved versions for reproducible environments, but that lock file is not used by pip when someone installs your package from PyPI. (It’s mainly for development workflows or if you publish an application and want to lock dependencies.)
    
*   The `[build-system]` here indicates Poetry’s own build backend (`poetry-core`). When you run `poetry build`, it will create the same kind of sdist and wheel as other methods, ready for upload.
    

Using Poetry can simplify publishing: `poetry publish` can build and upload in one command. Poetry will ask for PyPI credentials or you can configure an API token (`poetry config pypi-token.pypi <token>`). Under the hood, it performs similarly to using `build` + `twine`. If you prefer a more hands-on approach or need fine control (especially with compiled extensions), the setuptools approach might be preferable.

**Comparison of approaches:** In summary:

*   _Setup.py (legacy):_ Imperative, flexible if you need custom code, but now mostly replaced by declarative configs. You should not use `setup.py upload` (deprecated in favor of Twine) and you’ll still need a `pyproject.toml` for PEP 517 builds.
    
*   _Setup.cfg + pyproject.toml:_ Declarative metadata via setup.cfg or `[project]` table, using setuptools build backend. This is a “modernized” approach fully supported by PyPA. It’s great for most packages, including those with simple extension builds.
    
*   _Poetry:_ High-level tool managing the entire lifecycle (dependency locking, build, publish). Good for application projects or maintainers who prefer its workflow. The package produced is standard, but contributors must install Poetry to work with the project configuration.
    

No matter which approach, the output (sdist and wheel distributions) is what ultimately gets uploaded to PyPI.

Metadata and Configuration Details
----------------------------------

Getting the package metadata right is crucial. We’ve touched on many fields; here we consolidate important configuration across different file formats:

**Core metadata fields (Name, Version, Description, Python Requires, etc.):** These are required or strongly recommended:

*   **Name**: Unique package name on PyPI (`name` in setup.py/setup.cfg or pyproject). Must not conflict with existing project names[packaging.python.org](https://packaging.python.org/tutorials/packaging-projects/#:~:text=,as%20one%20which%20already%20exists).
    
*   **Version**: Package version, following PEP 440 (e.g. `0.1.0`, `1.0.0b1` for beta, etc.). Use a consistent versioning strategy (semantic versioning is common). Some projects manage version automatically (e.g. reading from a single source in code). If so, mark it as dynamic in pyproject or use tools like `setuptools_scm`.
    
*   **Description**: A short one-line description. In `setup.py` this is `description="..."`. In pyproject `[project]` it’s `description` field. Keep it concise.
    
*   **Long Description**: The detailed description shown on PyPI. This often comes from your README. With setuptools, you either specify `long_description = open("README.md").read()` and `long_description_content_type = "text/markdown"` (if using setup.py) or use `readme = "README.md"` in pyproject which will include the file’s content[packaging.python.org](https://packaging.python.org/tutorials/packaging-projects/#:~:text=,toml%20guide). Make sure the content type is correct (Markdown vs RST) so PyPI renders it properly. You can test rendering by using `twine check` on your distribution files before uploading.
    
*   **Author/Maintainer**: Identify who wrote or maintains the package. Typically you use `author` and `author_email` (and/or `maintainer` variants) in setup.cfg or `authors = [{name, email}]` in pyproject[packaging.python.org](https://packaging.python.org/tutorials/packaging-projects/#:~:text=,in%20the%20same%20format). This is public metadata. If you’re a solo maintainer, you can just use Author. If the project is transferred, Maintainer fields can be used.
    
*   **License**: It’s important to declare a license. In older setup.py, one might put `license="MIT"` and include the full text in a LICENSE file. Trove classifiers also indicated the license. Now, with PEP 639, tools support an explicit license field with an SPDX ID[packaging.python.org](https://packaging.python.org/tutorials/packaging-projects/#:~:text=https%3A%2F%2Fpypi) and a way to include license files. For example, `license = "MIT"` and `license-files = ["LICENSE"]` in pyproject will include the LICENSE file in your sdist/wheel automatically[packaging.python.org](https://packaging.python.org/tutorials/packaging-projects/#:~:text=https%3A%2F%2Fpypi) (setuptools 60+ needed). Always include the actual license text file for clarity.
    
*   **Python Requires**: Use `python_requires=">=X.Y"` in setup.py/setup.cfg or `requires-python = ">=X.Y"` in pyproject[packaging.python.org](https://packaging.python.org/tutorials/packaging-projects/#:~:text=%2A%20%60requires,has%20a%20matching%20Python%20version) to prevent installation on unsupported Python versions. This helps communicate which Python versions you support and pip will refuse to install the package on older Python if not compatible.
    

**Optional/Additional metadata:**

*   **Classifiers**: We discussed these – provide as many applicable classifiers as make sense (intended audience, topic, programming language versions, etc.). Classifiers are specified as a list of strings in setup or pyproject[packaging.python.org](https://packaging.python.org/tutorials/packaging-projects/#:~:text=requires,files%20%3D%20%5B%22LICEN%5BCS%5DE). For the list of valid classifiers, see the \[PyPI classifiers page\]\[106\].
    
*   **Keywords**: A list of keywords (tags) can be provided (e.g. in `setup.cfg` or `pyproject.project.keywords`) to help discoverability.
    
*   **Project URLs**: We showed how to add multiple URLs (documentation, source, issue tracker, funding, etc.)[packaging.python.org](https://packaging.python.org/tutorials/packaging-projects/#:~:text=%5Bproject.urls%5D%20Homepage%20%3D%20,https%3A%2F%2Fgithub.com%2Fpypa%2Fsampleproject%2Fissues). These show up nicely on the PyPI project page as quick links.
    
*   **Entry Points**: If your package provides console scripts or plugins, you would configure **entry points** (in setup.cfg’s `[options.entry_points]` or pyproject under tool-specific settings). For example, a console script entry point allows installing a command-line tool via your package. This is more advanced, so refer to the Python Packaging User Guide for “Creating and packaging command-line tools” if needed.
    
*   **Package Data**: If your package includes non-Python files that it needs at runtime (templates, data files, etc.), you must include them. In setup.cfg, you might use `include_package_data=True` and a `MANIFEST.in` to include those files in the source distribution[packaging.python.org](https://packaging.python.org/guides/distributing-packages-using-setuptools/#:~:text=Packaging%20and%20distributing%20projects%20,included%20in%20a%20source%20distribution). In pyproject (setuptools), you can use `packages = "find:"` plus include directives or use `tool.setuptools.package-data` entries. Make sure to list anything needed (or use wildcard patterns).
    
*   **Versioning Strategy**: Decide how to update version numbers. Many projects use **SemVer** (MAJOR.MINOR.PATCH). As you publish updates:
    
    *   Bump the version number in your metadata.
        
    *   Tag the release in version control with the same version (e.g. `git tag v0.2.0`).
        
    *   You may use tools to automate version bumps and changelog (e.g. `bump2version` or towncrier).
        
    *   If you need to release pre-releases, use PEP 440 notation (e.g. `1.0.0a1` for alpha, `1.0.0rc1` for release candidate). Pip will treat those appropriately (and won’t install pre-releases unless explicitly allowed by the user’s version spec).
        
    *   Avoid reusing a version number once published — PyPI will not allow re-uploading files for an existing version (to ensure integrity)[packaging.python.org](https://packaging.python.org/tutorials/packaging-projects/#:~:text=You%20will%20be%20prompted%20for,so%20be%20sure%20to%20paste). If you find a critical bug, you must release a new version (or in extreme cases, yank the bad release, described later).
        

**Dependencies and extras:** How you declare dependencies differs slightly by tool, but the concept is the same. In `setup.py`, use `install_requires=[...]` and `extras_require={...}`. In `setup.cfg`, under `[options]` you list `install_requires` and under `[options.extras_require]` define extras. In `pyproject.toml [project]`, use `dependencies = [...]` and `[project.optional-dependencies]` for extras groups. In Poetry, use `[tool.poetry.dependencies]` and `[tool.poetry.extras]` (or dev-dependencies separately). Whichever method, follow these best practices:

*   **Don’t over-pin** your dependencies. For library packages, it’s recommended _not_ to pin exact versions, but rather specify a range that is known to work[discuss.python.org](https://discuss.python.org/t/should-i-be-pinning-my-dependencies/13159#:~:text=jwodder%20%28John%20T,15%2C%202022%2C%2011%3A38pm%20%202). Pinning (e.g. requiring `requests==2.25.1`) can cause conflicts if another package requires a different version. Instead, use inequalities: lower bound at the minimum you’ve tested, and upper bound if you know future major releases might be incompatible (e.g. `<3.0` if 3.x could break compatibility).
    
*   **Optional dependencies (extras):** Only list truly optional features under extras. Common extras are `dev`, `docs`, `test` or optional feature groups (for example, a package might have `excel = ["pandas"]` extra for Excel support, which normal users don’t need). Document these extras in your README so users know they exist.
    
*   **Environmental markers:** If a dependency is needed only on certain Python versions or platforms, use environment markers (setuptools supports this in install\_requires, or in pyproject you can include a PEP 508 marker). Example: `importlib-resources>=1.0; python_version < "3.9"` – this means on Python 3.8 and below, install importlib-resources, but not on 3.9+ where the functionality is built-in.
    

By carefully specifying metadata and dependencies, you make installation and usage smoother for users and avoid issues like missing information on PyPI or installation conflicts.

Build and Distribute
--------------------

Once your project is configured, the next step is to build distributable packages. PyPI accepts two main distribution formats:

*   **Source Distribution (sdist)** – a tarball (usually `.tar.gz`) of your raw source files.
    
*   **Built Distribution (wheel)** – a Python Wheel (`.whl`) file, which is a binary package format that can contain compiled extensions and is ready to install.
    

You should generally provide both. The source distribution is a fallback for scenarios where a wheel is not available for a platform; pip can compile it (if possible) when installing[packaging.python.org](https://packaging.python.org/tutorials/packaging-projects/#:~:text=The%20,one%20built%20distribution%20is%20needed).

### Building the package

Use standardized tools to build:

*   **`build` package (PEP 517)**: This is the recommended build frontend. Once your `pyproject.toml` is set up, simply run:
    
    ```bash
    python3 -m pip install --upgrade build  # ensure build tool is installed
    python3 -m build
    ```
    
    This will invoke the specified build backend (setuptools or poetry, etc.) and produce files in the `dist/` directory[packaging.python.org](https://packaging.python.org/tutorials/packaging-projects/#:~:text=This%20command%20should%20output%20a,directory). You should see output like:
    
    ```text
    dist/
    ├── your_package-0.1.0-py3-none-any.whl
    └── your_package-0.1.0.tar.gz
    ```
    
    Here, `py3-none-any.whl` indicates a pure-Python wheel (for any OS, Python 3 only) and the tar.gz is the source. If you have C extensions, the wheel name will include specifics (like cp39-cp39-win\_amd64.whl for a Windows Python 3.9 build, etc.).
    
*   **Setuptools directly**: Alternatively, if using the legacy approach, you can run `python setup.py sdist bdist_wheel` (ensure you have `wheel` installed). This achieves a similar result: a tar.gz in `dist/` and a `.whl` if the wheel build succeeded. However, using `build` is preferred as it performs builds in an isolated environment and aligns with modern PEP 517 workflows.
    
*   **Poetry**: If you are using Poetry, run `poetry build`. This will create the sdist and wheel under `dist/` as well. Poetry takes care of calling its build backend (poetry-core) to generate these.
    

After building, verify the contents of `dist/`. The **source distribution** should include your source files, README, license, and setup files (if any). The **wheel** should include your code ready to import, and any compiled binaries (for extension modules).

**Including compiled extensions:** If your package contains a C/C++ or Cython extension:

*   Ensure your build backend knows how to build it. With setuptools, you typically define extension modules via `setup.py` (using `setuptools.Extension` and perhaps `Cython.Build.cythonize`). When you run `bdist_wheel`, it compiles the extensions. In `pyproject.toml` context, you might need a small `setup.py` to call `cythonize` or specify a build hook in setup.cfg.
    
*   The wheel filenames will reflect the platform and Python ABI. For example: `your_package-0.1.0-cp310-cp310-win_amd64.whl` for a build targeting CPython 3.10 on Windows 64-bit. These are **binary wheels**.
    
*   You should build wheels for each major OS and Python version you intend to support[packaging.python.org](https://packaging.python.org/guides/packaging-binary-extensions/#:~:text=If%20you%20plan%20to%20distribute,CI%3B%20these%20include%20cibuildwheel%20and). A common practice is to use CI services to build Windows, macOS, and manylinux (for Linux) wheels. Tools like **cibuildwheel** can automate building a matrix of wheels on CI[packaging.python.org](https://packaging.python.org/guides/packaging-binary-extensions/#:~:text=If%20you%20plan%20to%20distribute,CI%3B%20these%20include%20cibuildwheel%20and).
    
*   Use the “Stable ABI” if possible for compiled extensions (i.e., build against Python’s limited ABI to get an `abi3` wheel tag). This can reduce the number of wheels you need to produce (one wheel can work across all Python 3.x versions in that case)[packaging.python.org](https://packaging.python.org/guides/packaging-binary-extensions/#:~:text=match%20at%20L414%20Using%20CPython%E2%80%99s,new%20minor%20version%20of%20Python).
    
*   Always provide an sdist in addition to wheels[packaging.python.org](https://packaging.python.org/tutorials/packaging-projects/#:~:text=The%20,one%20built%20distribution%20is%20needed). If a user’s platform or Python version isn’t covered by your uploaded wheels, pip will fall back to the sdist and attempt to build it locally. (For this to work, the user needs a compiler and the required development libraries – which is why providing pre-built wheels is user-friendly).
    

After building, you can check the distributions:

*   **Twine check**: run `twine check dist/*` to catch common issues like broken README formatting or missing metadata. This isn’t required but is a useful validation step.
    
*   You can even test installing the wheel locally in a clean venv: `pip install dist/your_package-0.1.0-py3-none-any.whl` to ensure it installs and the package can be imported.
    

### Distribution files recap

*   **.tar.gz (sdist)**: Contains your source files exactly as in your repository (including setup.cfg/pyproject, etc.). Users installing this will run the build process on their machine.
    
*   **.whl (wheel)**: A zip-format archive that contains the ready-to-install files. Installing a wheel just unpacks files; no compilation needed. Wheels can be pure Python (suffix `-py3-none-any.whl` means no specific ABI or OS requirements) or platform-specific (with tags for python version, ABI, platform).
    

By building both, you maximize compatibility. As the Python Packaging User Guide advises: always upload a source distribution, and additionally provide wheels for the platforms you support[packaging.python.org](https://packaging.python.org/tutorials/packaging-projects/#:~:text=The%20,one%20built%20distribution%20is%20needed).

PyPI Account Setup
------------------

To upload packages, you need an account on PyPI (the Python Package Index). Since 2024, PyPI has tightened security for maintainers, so setting up your account properly is important.

*   **Create a PyPI account:** Go to pypi.org and register. Use your custom domain email (e.g. `you@yourdomain.com`) as the email for the account – you’ll need to verify this email. PyPI will send a confirmation link; verify before proceeding to uploads[packaging.python.org](https://packaging.python.org/tutorials/packaging-projects/#:~:text=The%20first%20thing%20you%E2%80%99ll%20need,more%20details%2C%20see%20Using%20TestPyPI). (If you want to test on TestPyPI, that’s a separate site with separate accounts – we’ll cover that in the next section.)
    
*   **Enable Two-Factor Authentication (2FA):** **PyPI requires 2FA on all accounts as of January 1, 2024[blog.pypi.org](https://blog.pypi.org/posts/2023-12-13-2fa-enforcement/#:~:text=What%27s%20changing%3F).** After logging in, go to your Account Settings and **add 2FA**. You can use an authenticator app (TOTP) or a security key (WebAuthn) – PyPI supports both. It’s wise to set up at least two 2FA methods (e.g. two authenticators or an authenticator + a hardware key) so you have a backup. Also save your recovery codes offline. Once 2FA is enabled:
    
    *   You **must use an API token or trusted publisher to upload** packages (username/password no longer works for uploads)[blog.pypi.org](https://blog.pypi.org/posts/2023-12-13-2fa-enforcement/#:~:text=2FA,you%27ll%20need%20to%20enable%202FA)[blog.pypi.org](https://blog.pypi.org/posts/2023-12-13-2fa-enforcement/#:~:text=When%20uploading%20a%20file%2C%20you,link%20to%20API%20Tokens%20help). This means you won’t directly use your PyPI password for publishing.
        
*   **Create an API token:** PyPI allows you to create scoped API tokens for uploads instead of using your username/password. In your PyPI account settings, find the **API tokens** section. Create a token and give it a meaningful name (e.g. “your-package upload token”). You can scope it to a specific project or “Entire account”. If the project doesn’t exist yet, you might start with an entire account token and later scope it. PyPI will show you the token **once** – copy it and keep it safe (e.g. in a password manager)[packaging.python.org](https://packaging.python.org/tutorials/packaging-projects/#:~:text=To%20securely%20upload%20your%20project%2C,won%E2%80%99t%20see%20that%20token%20again). The token will start with `pypi-` followed by a long string; it essentially serves as your “password” for uploads[packaging.python.org](https://packaging.python.org/tutorials/packaging-projects/#:~:text=You%20will%20be%20prompted%20for,be%20sure%20to%20paste%20correctly).
    
*   **Using your domain email:** With your account set up, you can optionally add your domain as a verified domain on PyPI (PyPI has an option to verify domain ownership for organizations/projects). At minimum, using the domain email ensures that communications from PyPI (like password resets, security notifications) come to an email under your control. It also shows professionalism; when you upload a package, PyPI will display the maintainer username (not email) publicly, but having a custom domain email in your account can be reused in project metadata.
    
*   **Security considerations:** Make sure to enable _notification settings_ in PyPI (there are options to be emailed on new login or new project releases). Also, since you have 2FA, consider adding a **WebAuthn security device** (like YubiKey) as a second factor for stronger phishing protection.
    

At this point, you have a PyPI account with 2FA and an API token ready. Next, you’ll use these credentials to upload your package.

Uploading to PyPI
-----------------

Uploading involves packaging your distribution files to the index. It’s best practice to **test your upload on TestPyPI** (a staging environment) before uploading to the real PyPI.

### Using TestPyPI for a Dry Run

**TestPyPI** is a separate instance of PyPI for testing (at `test.pypi.org`). Packages uploaded there won’t be visible on the real PyPI and can be safely experimented with.

1.  **Register on TestPyPI:** Create an account on test.pypi.org (you can use the same username/email as on PyPI, but you must register separately). Verify your email on TestPyPI as well[packaging.python.org](https://packaging.python.org/tutorials/packaging-projects/#:~:text=The%20first%20thing%20you%E2%80%99ll%20need,more%20details%2C%20see%20Using%20TestPyPI).
    
2.  **Create a TestPyPI API token:** Just like before, go to your TestPyPI account settings and create an API token[packaging.python.org](https://packaging.python.org/tutorials/packaging-projects/#:~:text=To%20securely%20upload%20your%20project%2C,won%E2%80%99t%20see%20that%20token%20again). Copy it. (It will also start with `pypi-`, but is only valid for the test site).
    
3.  **Upload to TestPyPI using Twine:** Install Twine if you haven’t already (`pip install twine`). Twine is the recommended tool for uploading to PyPI securely (it uses HTTPS and supports tokens). Make sure your `dist/` folder has the files (e.g. `your_package-0.1.0.tar.gz` and `.whl`). Then run:
    
    ```bash
    twine upload --repository testpypi dist/*
    ```
    
    Twine will use the `testpypi` repository configuration by default. It will prompt for your username and password. For username, enter `__token__` (literally, that keyword) and for password, paste the TestPyPI token (including the `pypi-` prefix)[packaging.python.org](https://packaging.python.org/tutorials/packaging-projects/#:~:text=You%20will%20be%20prompted%20for,be%20sure%20to%20paste%20correctly). The input will be hidden (no characters as you paste) – just hit Enter after pasting. You should see an upload log for each file, ending with a success message and URL[packaging.python.org](https://packaging.python.org/tutorials/packaging-projects/#:~:text=Uploading%20distributions%20to%20https%3A%2F%2Ftest,kB%20%E2%80%A2%2000%3A00%20%E2%80%A2).
    
    _Alternatively:_ You can configure a `~/.pypirc` file to avoid entering credentials each time. For example, in `~/.pypirc`:
    
    ```ini
    [distutils]
    index-servers =
        pypi
        testpypi
    
    [pypi]
    username = __token__
    password = <production PyPI token>
    
    [testpypi]
    repository = https://test.pypi.org/legacy/
    username = __token__
    password = <your TestPyPI token>
    ```
    
    Ensure this file is chmod 600 (user-readable only) since it contains secrets[packaging.python.org](https://packaging.python.org/specifications/pypirc/#:~:text=Warning)[packaging.python.org](https://packaging.python.org/specifications/pypirc/#:~:text=Warning). With this, `twine upload -r testpypi dist/*` will use saved tokens.
    
4.  **Verify on TestPyPI:** Once uploaded, go to the TestPyPI URL for your project: `https://test.pypi.org/project/your-package/0.1.0/` (the exact path was shown in the Twine output). Check that the metadata (description, classifiers, etc.) looks correct. You can also test installation from TestPyPI:
    
    ```bash
    python -m venv test_env
    source test_env/bin/activate
    pip install --no-deps -U pip  # upgrade pip in the venv
    pip install --index-url https://test.pypi.org/simple/ --no-deps your-package
    ```
    
    We use `--no-deps` to avoid pulling dependencies from TestPyPI (since TestPyPI may not have them all)[packaging.python.org](https://packaging.python.org/tutorials/packaging-projects/#:~:text=Note). If your package has dependencies, you might need to either upload them to TestPyPI as well or install them manually from real PyPI before installing your package.
    
    After installing, open a Python shell in that venv and try `import your_package` and perhaps call a simple function to ensure it works[packaging.python.org](https://packaging.python.org/tutorials/packaging-projects/#:~:text=and%20import%20the%20package%3A)[packaging.python.org](https://packaging.python.org/tutorials/packaging-projects/#:~:text=,add_one%282%29%203). This step ensures the wheel is usable.
    
5.  If something is wrong (e.g., the description is not rendering, or a file is missing in the package), you can fix your setup and increment the version (e.g. to 0.1.1) and rebuild, then try again on TestPyPI. Remember, you cannot reuse the same version number once uploaded (even on TestPyPI, deleting releases is possible but not on real PyPI after a short window). So bump the version for any re-upload attempt.
    

### Uploading to the real PyPI

Once you’re satisfied with TestPyPI results:

1.  **Create the real release**: Update any last metadata (e.g., remove “Test release” notes if you added any), bump version if you did multiple test iterations (use the final new version for the real release), rebuild the distributions (`python -m build` or equivalent). Ensure you have the final dist files ready.
    
2.  **Upload with Twine to PyPI**: Use Twine with the real PyPI repository (which is default). For example:
    
    ```bash
    twine upload dist/*
    ```
    
    Since PyPI now mandates 2FA, Twine will **not** accept your username & password login. Instead, you again use an API token. If not configured in `~/.pypirc`, Twine will prompt for credentials. Enter `__token__` as username and the **production** PyPI token as password[packaging.python.org](https://packaging.python.org/specifications/pypirc/#:~:text=,PyPI%20token)[packaging.python.org](https://packaging.python.org/specifications/pypirc/#:~:text=username%20%3D%20__token__%20password%20%3D,PyPI%20token). The upload URL will be `https://upload.pypi.org/legacy/` by default and you should see similar output as before (but for the real site)[packaging.python.org](https://packaging.python.org/tutorials/packaging-projects/#:~:text=,org%2F%20by%20default).
    
    If you set up `~/.pypirc` with the token, just running `twine upload dist/*` will pick it up and not prompt, uploading directly to PyPI.
    
3.  **Common upload issues**:
    
    *   _“Repository not found” or authentication errors:_ Check that you used the correct repository URL or name in Twine command and that the token is correct. Ensure you included the `pypi-` prefix if copy-pasting. If 2FA wasn’t enabled, PyPI would reject password auth for uploads[blog.pypi.org](https://blog.pypi.org/posts/2023-12-13-2fa-enforcement/#:~:text=When%20uploading%20a%20file%2C%20you,link%20to%20API%20Tokens%20help), but since you enabled it, you should be using token.
        
    *   _HTTP 400 or “File already exists” errors:_ This means you are trying to upload a file name that PyPI already has for that project & version. It occurs if you accidentally repeated a version. Solution: bump the version, rebuild, and try again. PyPI does not allow replacing an existing file.
        
    *   _Metadata or validation errors:_ Twine will check your package metadata on upload. If your long description is badly formatted (for example, invalid RST syntax), PyPI may reject it. The error message will indicate the problem. Use `twine check` to diagnose in advance. Fix and rebuild if needed (e.g., add a `long_description_content_type` or correct your README syntax).
        
    *   _Missing files in sdist:_ If users report that something is missing when installing from sdist (like no license file, or missing package data), it means your MANIFEST.in or include patterns might be wrong. Update them and publish a new version.
        
    *   _Large files:_ PyPI has file size limits. If you have very large files, you might need to contact PyPI admins or use FileStorage. But most pure code packages are small. Data-heavy packages might consider alternatives.
        
4.  **Success confirmation:** After a successful upload, go to the PyPI URL for your project: `https://pypi.org/project/your-package/0.1.0/`. It may take a minute for everything to sync. You should see your release, the description, and all metadata on display. You can now try `pip install your-package` (this will get from real PyPI) in a fresh environment to double-check everything works as expected.
    

**Tip:** You can automate the version bump, build, and twine upload sequence with a Makefile or script to reduce manual steps and avoid mistakes, especially as your release process becomes routine.

Advanced Publishing Features
----------------------------

Now that you know the basics, here are some advanced features and best practices to consider for professional package maintenance.

### GPG Signing (Optional)

You might have seen that Twine has options to GPG-sign your packages (`--sign` flag). This attaches a PGP signature (`.asc` file) to your uploads for integrity verification. In practice, **PyPI has deprecated PGP signatures** – as of 2023, PyPI no longer displays or provides new signature files to users, effectively ignoring uploaded `.asc` files[blog.pypi.org](https://blog.pypi.org/posts/2023-05-23-removing-pgp/#:~:text=If%20you%20are%20someone%20who,False). This is because so few users were verifying them and many signatures were unverifiable[blog.pypi.org](https://blog.pypi.org/posts/2023-05-23-removing-pgp/#:~:text=that%20the%20current%20support%20for,signatures%20is%20not%20proving%20useful).

However, you can still sign distributions if you want an external verification path:

*   Generate a GPG key (if you don’t have one).
    
*   Use Twine with `twine upload -s dist/*` (and `--sign-with <keyid>` if you have multiple keys). Twine will invoke GPG to create signatures before upload[discuss.python.org](https://discuss.python.org/t/gpg-key-created-when-uploading-package-to-pypi/35527#:~:text=I%E2%80%99m%20interested%20to%20know%20what,more%20recently%20disallowed%20it%20entirely)[discuss.python.org](https://discuss.python.org/t/gpg-key-created-when-uploading-package-to-pypi/35527#:~:text=Removing%20PGP%20from%20PyPI%20,The%20Python%20Package%20Index).
    
*   Upload proceeds as normal, with `.asc` files accompanying your package files. PyPI will accept them (not reject), but users won’t see a “Verified” flag or automatically use them. Interested users would have to manually fetch the `.asc` from PyPI’s backend and verify with your public key.
    

Going forward, the Python packaging ecosystem is exploring **trusted supply chain** tools (like Sigstore and trusted publishing). Currently, PGP signing is optional and yields little benefit on PyPI itself. If you want to sign releases for the sake of GitHub releases or your own records, you can do so, but it’s not a common requirement for PyPI.

### Automating Releases with CI/CD

It’s a good practice to automate your publishing process to avoid manual errors and integrate it with your development workflow. Using **continuous integration (CI)** pipelines (like GitHub Actions, GitLab CI, Travis CI, etc.), you can trigger package builds and uploads whenever you create a new release tag.

**GitHub Actions example:** PyPA provides an official GitHub Action for publishing to PyPI. You can use **pypa/gh-action-pypi-publish** in your workflow. For instance, create `.github/workflows/publish.yml`:

```yaml
name: Publish to PyPI
on:
  push:
    tags: "v*.*.*"    # triggers on tagging a version like v1.2.3

jobs:
  build-and-publish:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.10'
      - name: Install build tools
        run: python -m pip install build twine
      - name: Build distributions
        run: python -m build
      - name: Publish to TestPyPI
        if: github.event_name == 'push' && contains(github.ref, '-beta')  # example condition
        uses: pypa/gh-action-pypi-publish@release/v1
        with:
          repository-url: https://test.pypi.org/legacy/
          password: ${{ secrets.TEST_PYPI_TOKEN }}
      - name: Publish to PyPI
        if: github.event_name == 'push' && startsWith(github.ref, 'refs/tags/v')
        uses: pypa/gh-action-pypi-publish@release/v1
        with:
          password: ${{ secrets.PYPI_TOKEN }}
```

In this example:

*   It triggers on pushed tags that look like version numbers.
    
*   It builds the package.
    
*   It uses the PyPI publish action to upload. The credentials are taken from repository secrets (you would add `PYPI_TOKEN` and optionally `TEST_PYPI_TOKEN` in your GitHub repo secrets). The action expects the token as `password` with username `__token__` by default.
    
*   We showed an optional step to upload to TestPyPI if the tag indicates a beta, and then to PyPI for a final release.
    

Instead of storing a long-lasting token, PyPI now also supports **Trusted Publishers** using OpenID Connect (OIDC). This means GitHub can authenticate to PyPI without you managing a token, via an authorized link between your PyPI project and GitHub Actions[packaging.python.org](https://packaging.python.org/guides/publishing-package-distribution-releases-using-github-actions-ci-cd-workflows/#:~:text=Configuring%20trusted%20publishing%C2%B6). To use this:

*   In PyPI, go to your project’s “Manage” > “Advanced” > “Trusted Publishers” and follow steps to add GitHub as a trusted publisher (you’ll specify your repository).
    
*   Update the GitHub Actions workflow to use `pypa/gh-action-pypi-publish@release/v1` without a password, but ensure it’s running in an environment PyPI trusts (the action’s docs detail this). Essentially, PyPI will issue a one-time token to the workflow, eliminating the need to store one yourself[packaging.python.org](https://packaging.python.org/guides/publishing-package-distribution-releases-using-github-actions-ci-cd-workflows/#:~:text=This%20guide%20relies%20on%20PyPI%E2%80%99s,to%20provide%20a%20username%2Fpassword%20combination).
    

Using CI/CD for publishing ensures each release is done the same way, with the correct files, and can be tied to other steps (like running tests, linting, etc., before publishing). It also enables multiple maintainers to release new versions without manually handling credentials each time.

### Tagging Releases and Release Management

Always tag your releases in version control (e.g., Git). For example, if releasing version 0.1.0, do:

```bash
git tag -a v0.1.0 -m "Release version 0.1.0"
git push origin v0.1.0
```

This not only marks the commit of that release but also can trigger CI workflows as shown. Tags (especially annotated tags) serve as a historical record. On GitHub, you might also create a GitHub Release which can auto-generate from the tag and include release notes or changelogs.

If you use GitHub Releases, you might attach the source distribution and wheel there as well (some users like downloading from GitHub). This is optional since they can always get it from PyPI.

Consider signing your tags with GPG as well (Git can show a “verified” badge on signed tags/commits). This doesn’t directly affect PyPI but contributes to the trust of your source code provenance.

When you plan significant changes, communicate them via versioning:

*   Bump the major version for breaking changes.
    
*   If deprecating features, perhaps issue warnings in code and mention in documentation for a couple of minor releases before removing them in a major bump.
    

### Supporting Multiple Python Versions

To reach more users, you often want to support a range of Python versions (commonly, the latest 3.x versions that are not end-of-life). Here’s how to manage this:

*   **Testing**: Use CI to run your test suite on multiple Python versions (3.8, 3.9, 3.10, 3.11, etc.). This gives you confidence your package works across them.
    
*   **Declare compatibility**: As mentioned, use `python_requires` to prevent installation on incompatible Pythons. And use Trove classifiers like “Programming Language :: Python :: 3.9” etc., for each version you support.
    
*   **Conditional dependencies or code**: If you need to support an older Python, you might include conditional dependencies (e.g., importlib-resources for older versions). You might also use `sys.version_info` checks in code for minor differences. Keep these minimal to avoid maintenance burden.
    
*   **Multiple wheels**: If you have binary extensions, you must produce wheels for each Python version (unless using the stable ABI). Manylinux wheels can often be built that work for all Python versions (embedding the ABI for each). As noted earlier, tools like `cibuildwheel` come in handy to build a matrix of (OS x Python) wheels in one go[packaging.python.org](https://packaging.python.org/guides/packaging-binary-extensions/#:~:text=If%20you%20plan%20to%20distribute,CI%3B%20these%20include%20cibuildwheel%20and).
    
*   **End-of-life Pythons**: When a Python version is end-of-life (no longer supported, e.g., 3.6 or 3.7 by 2025), you may wish to drop support. To do so in a new release, update `requires-python` to a higher minimum. It’s good to communicate this in your changelog (“Dropped support for Python 3.x”). You can also use environment markers to exclude installation on those versions.
    
*   **Future compatibility**: Test against Python beta releases if possible (e.g., if Python 3.12 is in beta, try to test your package on it). This way, your package will likely work day-one when new Python versions are released.
    

Post-Publish Considerations
---------------------------

Congratulations – your package is on PyPI! Now you should ensure everything is in order and plan for maintaining the project.

### Verify Installation from PyPI

Even if you tested with TestPyPI, do a final verification with the real deal:

*   In a fresh environment (or using Docker or a clean VM), run `pip install your-package`. This will fetch from PyPI. Make sure it installs without errors and the package import works. This catches any last-minute issues like missing files or packaging quirks.
    
*   If something critical is wrong (e.g. installation fails for all users), you have a few options: you can **yank** the release or push a quick fix update:
    
    *   **Yanking a release**: PyPI allows marking a release as yanked (via the PyPI UI or CLI tools). A yanked release is still available for those who explicitly request that version, but pip will skip it when installing without version specifiers. Yank only in serious cases (like a broken release or security issue) since it effectively hides that version from normal installs.
        
    *   Generally, for a minor issue, it’s often better to fix and release a new patch version.
        

### Project Documentation and Enhancements on PyPI

A PyPI project page can show more than just description text. Make your project page welcoming:

*   **Project description**: If you wrote your README in Markdown and specified `long_description_content_type`, check that it rendered correctly on PyPI (no broken links or images). If you see “Unable to render” errors, adjust the content (PyPI uses strict RST for `.rst` READMEs, but for Markdown it usually just works if the syntax is standard).
    
*   **Badges**: Many projects include badges in their README (e.g., build status, PyPI version, downloads, license). These badges will appear on PyPI too, since it renders your README. Feel free to add them for a professional touch:
    
    *   A badge for PyPI version (so your GitHub README always shows the latest version from PyPI).
        
    *   Build/test CI status badge.
        
    *   License badge, etc.  
        Just ensure the image links are stable (using services like shields.io). PyPI’s renderer will cache them.
        
*   **Changelog**: If you maintain a CHANGELOG.md, consider linking to it. For example, in the project URLs you could add `Changelog = https://github.com/youruser/yourproject/blob/main/CHANGELOG.md`. There’s no dedicated field for changelog, but interested users will find the link.
    
*   **Homepage/Docs**: If you have extensive documentation on a website or readthedocs, add that URL. A documentation link can be named "Documentation" under project URLs.
    
*   **Maintainers**: If your project is open to contributions, you might add a `CONTRIBUTING.md` link in the README, or include a note like “Issues and pull requests welcome on GitHub.”
    

On PyPI, you as a maintainer can also add collaborators to the project (via “Maintainership” settings). If you have a team, consider using the new **PyPI Organizations** feature (introduced in 2022) which allows grouping packages and managing teams, especially if publishing under a common namespace or domain name.

### Updates and Deprecation

Maintaining the package means releasing updates and managing older versions:

*   **Releasing updates**: Follow the same process for new versions. Keep incrementing version numbers. Try not to break backward compatibility in minor updates; if you need to, communicate clearly (in the changelog, project description, or documentation) that a breaking change happened.
    
*   **Deprecating features**: If you plan to remove a feature, you can:
    
    *   Deprecate it in code (emit a `DeprecationWarning`).
        
    *   Note in the documentation that it will be removed in a future version.
        
    *   Remove it in a major version bump.
        
*   **Yanking or removing releases**: As mentioned, PyPI allows yanking (which hides the release from default installs). Deletion of releases is generally discouraged and only allowed within a short time window after upload. After that, a release can’t be truly deleted (this is to preserve the ecosystem’s consistency). If a release is problematic, yank it and push a fix in a new version.
    
*   **Supporting older releases**: If you have a user base on older versions, you might occasionally patch an older branch. PyPI allows multiple versions to coexist. You could release a bugfix as 0.1.5 while the latest is 0.2.3, for example. This is more common in large projects. For a small project, it might be overkill – encourage users to upgrade to the latest version unless they have a constraint.
    
*   **Package deprecation/transfer**: If you decide to discontinue the project, you can mark it as such on PyPI by adding a Trove classifier “Development Status :: 7 - Inactive” or “Development Status :: 6 - Mature” depending on context. If someone else is to take over, you can transfer the ownership on PyPI to them (add as owner). PEP 541 governs name transfers if a project is abandoned – owning your domain and using domain-based names can help establish your claim if ever needed.
    

Security and Best Practices
---------------------------

Finally, consider the security of your package and users:

*   **Credential Security:** Never hardcode credentials or tokens in your repository. Use `.pypirc` or environment variables for Twine, as discussed, and restrict access. Since your PyPI token essentially grants publish rights, treat it like a password:
    
    *   If using CI, store the token as an encrypted secret, not in the code.
        
    *   If someone gains commit access to your repository and CI is auto-publishing (especially with a stored token), they could publish a malicious release. Mitigate this by protecting your CI secrets (use required code reviews, branch protection, or better yet, use Trusted Publishing which doesn’t expose a reusable token).
        
    *   Rotate tokens if you suspect compromise. You can create a new token on PyPI and delete the old one at any time.
        
    *   Use 2FA on your VCS account (GitHub, GitLab, etc.) as well, since that can indirectly affect your package trust.
        
*   **Dependency Security:** Be mindful of supply chain attacks:
    
    *   **Typosquatting**: Attackers upload a package with a name very similar to a popular one (e.g., `reqeusts`). If a user misspells when installing, they might install the wrong package[discuss.python.org](https://discuss.python.org/t/typosquatting-dependency-confusion-supply-chain-attack-call-it-as-you-wish/52615#:~:text=Python%20script%20of%20his%20own,debugging%20in%20less%20than%2015mn)[discuss.python.org](https://discuss.python.org/t/typosquatting-dependency-confusion-supply-chain-attack-call-it-as-you-wish/52615#:~:text=But%20then%20I%E2%80%99ve%20opened%20the,I%20was%20not%20convinced). As a publisher, you can’t prevent this entirely, but you can encourage users to install via your documented instructions (copy-paste the correct name). Owning a domain-based unique name helps (an attacker is less likely to spoof `yourcompany-lib` if it’s niche). PyPI monitors for malicious uploads, but it’s a constant battle.
        
    *   **Dependency confusion**: If your package is meant for internal use with a certain name, but you also publish something public with the same name, be careful. Attackers could guess internal names and upload to PyPI first. In your case, you are publishing open-source, but if you ever have internal packages, give them unique names or host them on a private index to avoid confusion[discuss.python.org](https://discuss.python.org/t/typosquatting-dependency-confusion-supply-chain-attack-call-it-as-you-wish/52615#:~:text=From%20the%20forum%20I%20could,consequences%20against%20typosquatting%20on%20pypi). Large companies often prefix internal packages or use private indexes.
        
    *   **Vulnerabilities in dependencies**: Keep an eye on security advisories. Use tools like `pip-audit` or `safety` to scan your project’s dependencies for known vulnerabilities. If a dependency has a severe issue, release a new version of your package pinning or updating to a safe version if necessary.
        
    *   **Minimum dependency versions**: Don’t set your minimum required version too low if that version has known bugs or security issues. It’s better to require a slightly newer bugfix release of a library if it resolves important issues.
        
*   **Package Name Ownership:** If your package name is similar to your domain or trademark, you have some protection via PEP 541 (against name squatting or misuse). Conversely, never choose a name that infringes on existing trademarks or packages. A unique name reduces the risk of conflict and confusion.
    
*   **Pinned vs Unpinned Dependencies:** As noted, libraries should not pin exact versions of dependencies[discuss.python.org](https://discuss.python.org/t/should-i-be-pinning-my-dependencies/13159#:~:text=jwodder%20%28John%20T,15%2C%202022%2C%2011%3A38pm%20%202). This can cause “dependency hell” for users. Instead, aim for broad compatibility. For applications (if you ever use this guide for an app that you deploy, not a library), pinning is acceptable and even recommended for repeatable deployments – but that’s usually handled via requirements files or lockfiles, not in the published metadata.
    
*   **Use of DNS (domain) in package:** Since you have a domain, you could use it for namespacing if you wish. For example, some packages incorporate the company domain in reverse (like Java style, `com.yourdomain.project`) as a unique identifier, but Python packaging doesn’t commonly do reverse-DNS package names. Instead, you might create a namespace package if you plan many packages (e.g., `yourdomain.core`, `yourdomain.utils` could be separate distributions forming a family). Namespace packages allow splitting a top-level package across distributions. This is an advanced technique (see “Packaging namespace packages” guide if needed).
    
*   **Malware scans:** PyPI runs some automated scans. If you ever get a warning or find that your release was pulled for security reasons, address it immediately. Common false positives could be if your package bundles binary blobs or does something odd in setup; try to avoid those.
    
*   **Project governance:** If your project grows popular, consider a CONTRIBUTING file and maybe a code of conduct. These aren’t directly about packaging, but good documentation and governance attract positive contributions and reduce the chance of needing to give publish rights to someone you don’t fully trust. Only add trusted collaborators as maintainers on PyPI.
    
*   **Continuous improvement:** Stay updated with Python Packaging developments. New PEPs and tools keep emerging (for instance, **Hatch** is an upcoming build backend mentioned in PyPA docs, and **PDM** for managing projects, etc.). The landscape in 2025 continues to evolve towards more secure and convenient workflows. The official Python Packaging User Guide is an excellent resource[packaging.python.org](https://packaging.python.org/guides/packaging-binary-extensions/#:~:text=,Tutorials), and the PyPI blog announces important changes (like 2FA requirement, deprecated features, etc.).
    

By following this guide, you’ve prepared, packaged, and published your Python project to PyPI with modern best practices. Your project is now installable via `pip install your-package`. Remember to maintain the project by keeping dependencies up to date, handling user feedback (issues), and publishing new releases as needed. Good luck with your open-source package! 🚀

**Sources:**

*   Python Packaging User Guide – _Tutorial: Packaging Python Projects_[packaging.python.org](https://packaging.python.org/tutorials/packaging-projects/#:~:text=%5Bproject%5D%20name%20%3D%20,python%20%3D%20%22%3E%3D3.9)[packaging.python.org](https://packaging.python.org/tutorials/packaging-projects/#:~:text=The%20,one%20built%20distribution%20is%20needed)
    
*   Python Packaging User Guide – _Core Metadata specifications_[packaging.python.org](https://packaging.python.org/tutorials/packaging-projects/#:~:text=,a%20file%20or%20Git%20tag)[packaging.python.org](https://packaging.python.org/tutorials/packaging-projects/#:~:text=%2A%20%60requires,has%20a%20matching%20Python%20version)
    
*   Python Packaging User Guide – _Using TestPyPI_[packaging.python.org](https://packaging.python.org/tutorials/packaging-projects/#:~:text=The%20first%20thing%20you%E2%80%99ll%20need,more%20details%2C%20see%20Using%20TestPyPI)[packaging.python.org](https://packaging.python.org/tutorials/packaging-projects/#:~:text=To%20securely%20upload%20your%20project%2C,won%E2%80%99t%20see%20that%20token%20again)
    
*   PyPI Administrators – “2FA requirement for PyPI” (Dec 2023)[blog.pypi.org](https://blog.pypi.org/posts/2023-12-13-2fa-enforcement/#:~:text=What%27s%20changing%3F)[blog.pypi.org](https://blog.pypi.org/posts/2023-12-13-2fa-enforcement/#:~:text=2FA,you%27ll%20need%20to%20enable%202FA)
    
*   Python Packaging – _The .pypirc file_ (config for Twine)[packaging.python.org](https://packaging.python.org/specifications/pypirc/#:~:text=,PyPI%20token)[packaging.python.org](https://packaging.python.org/specifications/pypirc/#:~:text=Warning)
    
*   Discussion on Python.org – _Pinning dependencies (John Wodder’s advice)_[discuss.python.org](https://discuss.python.org/t/should-i-be-pinning-my-dependencies/13159#:~:text=jwodder%20%28John%20T,15%2C%202022%2C%2011%3A38pm%20%202)
    
*   Python Packaging User Guide – _Packaging binary extensions_[packaging.python.org](https://packaging.python.org/guides/packaging-binary-extensions/#:~:text=If%20you%20plan%20to%20distribute,CI%3B%20these%20include%20cibuildwheel%20and)[packaging.python.org](https://packaging.python.org/guides/packaging-binary-extensions/#:~:text=match%20at%20L414%20Using%20CPython%E2%80%99s,new%20minor%20version%20of%20Python)
    
*   PyPI Security Blog – _Removing PGP from PyPI_ (May 2023)[blog.pypi.org](https://blog.pypi.org/posts/2023-05-23-removing-pgp/#:~:text=If%20you%20are%20someone%20who,False)[blog.pypi.org](https://blog.pypi.org/posts/2023-05-23-removing-pgp/#:~:text=that%20the%20current%20support%20for,signatures%20is%20not%20proving%20useful)
    
*   Python Packaging User Guide – _Publishing using GitHub Actions_[packaging.python.org](https://packaging.python.org/guides/publishing-package-distribution-releases-using-github-actions-ci-cd-workflows/#:~:text=This%20guide%20relies%20on%20PyPI%E2%80%99s,to%20provide%20a%20username%2Fpassword%20combination)
    
*   Python Packaging Discussion – _Typosquatting and dependency confusion_[discuss.python.org](https://discuss.python.org/t/typosquatting-dependency-confusion-supply-chain-attack-call-it-as-you-wish/52615#:~:text=Python%20script%20of%20his%20own,debugging%20in%20less%20than%2015mn)[discuss.python.org](https://discuss.python.org/t/typosquatting-dependency-confusion-supply-chain-attack-call-it-as-you-wish/52615#:~:text=From%20the%20forum%20I%20could,consequences%20against%20typosquatting%20on%20pypi)

## Prompt:
Complete Guide to Publishing Python Packages to PyPI in 2025

Publishing an Open-Source Python Package to PyPI (2025 Guide)
=============================================================

Publishing a Python package to the Python Package Index (PyPI) involves careful preparation, packaging, and security steps. This guide (updated as of May 4, 2025) walks you through structuring your project, configuring packaging metadata, building distributions, and uploading securely to PyPI. We assume you have a unique package name (e.g. derived from your own domain) and an email address on that domain for your PyPI account.

Preparation
-----------

Before publishing, set up your project structure and development environment:

*   **Project Structure:** Organize your code into a Python package directory, typically using a “src layout” for clarity. For example:
    
    ```text
    your-package/
    ├── pyproject.toml          # Build configuration (or setup.py/setup.cfg)
    ├── README.md               # Project README for PyPI description
    ├── LICENSE                 # License file (e.g. MIT, Apache 2.0)
    ├── src/
    │   └── your_package/       # Package source code
    │       ├── __init__.py
    │       └── module.py
    └── tests/                  # (Optional) test suite
        └── test_module.py
    ```
    
    The package directory (`your_package/`) should have an `__init__.py` (even if empty) so Python recognizes it as a package[packaging.python.org](https://packaging.python.org/tutorials/packaging-projects/#:~:text=%E2%94%94%E2%94%80%E2%94%80%20example_package_YOUR_USERNAME_HERE%2F%20%E2%94%9C%E2%94%80%E2%94%80%20__init__,py). The `src/` layout is recommended to avoid import confusion during development[packaging.python.org](https://packaging.python.org/tutorials/packaging-projects/#:~:text=Create%20the%20following%20file%20structure,locally). Choose a **unique distribution name** for your project – it can contain letters, numbers, `_` or `-` and must not already exist on PyPI[packaging.python.org](https://packaging.python.org/tutorials/packaging-projects/#:~:text=Issues%20%3D%20).
    
*   **Required Files:** Include a **README** (often in Markdown or reStructuredText) describing your project, and a **LICENSE** file with your open-source license. PyPI will display the README as the long description on your package page, and including a license file is important for users and compliance[packaging.python.org](https://packaging.python.org/tutorials/packaging-projects/#:~:text=description%20%3D%20,files%20%3D%20%5B%22LICEN%5BCS%5DE)[packaging.python.org](https://packaging.python.org/tutorials/packaging-projects/#:~:text=https%3A%2F%2Fpypi). Common practice also includes files like `CHANGELOG.md` or `HISTORY.md` (to record changes), and possibly a `CONTRIBUTING.md` for open-source contributors, though these aren’t required by PyPI.
    
*   **Pure Python vs. Extensions:** If your project is pure Python, your source tree will just contain `.py` files. If you need to include compiled code (e.g. a C extension or Cython module), plan for additional files:
    
    *   **C/C++ extensions:** You might have a `src/your_package` directory with C/C++ source (`.c`/`.cpp`) and possibly a `setup.py` or build script to compile them.
        
    *   **Cython modules:** Include the `.pyx` Cython source and any generated C code or build instructions. You’ll use Cython during the build process to generate the extension module.
        
    
    The packaging process supports both pure-Python and binary extensions, but binary extensions require building wheels for each target platform. We’ll discuss how to include and distribute these in the “Build and Distribute” section.
    
*   **Virtual Environment for Development:** Use a virtual environment to isolate your project:
    
    *   Create a venv: for example, `python3 -m venv .venv` and activate it (this ensures dependencies you install for development don’t pollute your system Python).
        
    *   Inside the venv, install the tools you’ll need (like `build`, `twine`, and linters or test frameworks).
        
    *   Manage **dependencies**: distinguish between _project runtime dependencies_ and _development dependencies_. For runtime dependencies (needed by your package), you will declare them in your packaging config (so they get installed with your package). For dev/test dependencies (like pytest, black, etc.), use a separate `requirements-dev.txt` or specify them as extras (e.g. a `dev` extra) or use a tool like Poetry to manage them separately. This separation prevents installing unnecessary packages for end users.
        
*   **Domain Email:** Ensure you have a professional email (e.g. `you@yourdomain.com`) ready. You will use this email for your PyPI account and can also list it in package metadata as the author or maintainer email. Using your own domain email adds credibility and consistency to your package identity.
    

Packaging Approaches
--------------------

Python packaging has evolved to support multiple approaches. We’ll cover three common methods: the legacy `setup.py` (with or without `setup.cfg`), the modern `pyproject.toml` (PEP 517/518 with setuptools), and using **Poetry**. Each approach ultimately produces installable distributions, but they differ in configuration style and tooling.

### Legacy: `setup.py` (and `setup.cfg`)

Traditionally, Python packages used a **setup script**. A `setup.py` file at the project root executes setuptools’ `setup()` function to define package metadata and build instructions. For example:

```python
# setup.py (legacy approach)
import setuptools

setuptools.setup(
    name="your-package",
    version="0.1.0",
    description="A short description of your package",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    author="Your Name",
    author_email="you@yourdomain.com",
    url="https://yourproject.yourdomain.com",
    license="MIT",
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    packages=setuptools.find_packages(where="src"),
    package_dir={"": "src"},
    python_requires=">=3.8",
    install_requires=[
        "requests>=2.0,<3.0",   # example dependency
    ],
    extras_require={
        "dev": ["pytest>=6.0", "cython"]  # example extra group
    },
)
```

This script includes all metadata (name, version, author, description, etc.) and configuration for building the package. **However, `setup.py` is now considered legacy** for defining metadata. Modern tools favor static configuration in declarative files instead of executing code to get metadata. In fact, features like PEP 517 build isolation mean that `setup.py` isn’t invoked directly in many cases[packaging.python.org](https://packaging.python.org/tutorials/packaging-projects/#:~:text=The%20,own%20documentation%20for%20more%20details). Today, you typically still include a minimal `setup.py` only if needed for backward compatibility or for dynamic behaviors (like custom build steps). Many projects instead use a `setup.cfg` (a static setup configuration) or just `pyproject.toml`.

**Setup.cfg:** This is an INI-format configuration file that can be used alongside a minimal `setup.py`. For example, you could move most of the above settings into `setup.cfg`:

```ini
# setup.cfg (alternative to encoding metadata in code)
[metadata]
name = your-package
version = 0.1.0
description = A short description of your package
long_description = file: README.md
long_description_content_type = text/markdown
author = Your Name
author_email = you@yourdomain.com
url = https://yourproject.yourdomain.com
license = MIT
classifiers =
    Programming Language :: Python :: 3
    License :: OSI Approved :: MIT License
    Operating System :: OS Independent

[options]
packages = find:
package_dir =
    = src
python_requires = >=3.8
install_requires =
    requests>=2.0,<3.0

[options.extras_require]
dev = 
    pytest>=6.0
    cython
```

With this approach, `setup.py` can be as simple as:

```python
import setuptools
setuptools.setup()  # it will read setup.cfg
```

Setuptools will automatically read the configuration from `setup.cfg` when `setup()` is called. This **declarative config** is easier to maintain and avoids executing code for metadata.

**Note:** If you use `setup.py`/`setup.cfg`, you still need a minimal `pyproject.toml` to declare the build system (PEP 518). For example, include a `pyproject.toml` with:

```toml
[build-system]
requires = ["setuptools>=61.0", "wheel"]
build-backend = "setuptools.build_meta"
```

This tells tools like pip to use setuptools as the build backend[packaging.python.org](https://packaging.python.org/tutorials/packaging-projects/#:~:text=setuptools). (We cover `pyproject.toml` in detail next.) In summary, the legacy approach works, but modern standards favor the next method.

### Modern: `pyproject.toml` with Setuptools (PEP 517/621)

PEP 517 and PEP 518 introduced a standardized build interface using `pyproject.toml`. This file declares the **build system requirements** and can also include package metadata via PEP 621’s `[project]` table. Using `pyproject.toml` is now the recommended standard for packaging.

**Build system declaration:** In your `pyproject.toml`, specify the build backend and its requirement. For setuptools, for example:

```toml
[build-system]
requires = ["setuptools >= 77.0.0", "wheel"]  # use a recent setuptools and wheel
build-backend = "setuptools.build_meta"
```

This ensures tools will install setuptools and wheel in an isolated environment to build your package[packaging.python.org](https://packaging.python.org/tutorials/packaging-projects/#:~:text=%5Bbuild,backend%20%3D%20%22setuptools.build_meta)[packaging.python.org](https://packaging.python.org/tutorials/packaging-projects/#:~:text=The%20,introduced%20support%20for%20%20104). Now, instead of using `setup.cfg`, you can put package metadata in the `[project]` section of `pyproject.toml` (supported by setuptools versions ≥61 which implement PEP 621):

```toml
[project]
name = "your-package"
version = "0.1.0"
description = "A short description of your package"
readme = "README.md"
requires-python = ">=3.8"
license = "MIT"
authors = [
    { name="Your Name", email="you@yourdomain.com" }
]
classifiers = [
    "Programming Language :: Python :: 3",
    "Operating System :: OS Independent",
    "License :: OSI Approved :: MIT License"
]
dependencies = [
    "requests>=2.0,<3.0",
]
dynamic = []  # (if any fields are computed dynamically, list them here)
```

```toml
[project.optional-dependencies]
dev = [
    "pytest>=6.0",
    "cython",
]
```

```toml
[project.urls]
Homepage = "https://yourproject.yourdomain.com"
Source = "https://github.com/youruser/yourproject"
```

In this example, the `[project]` table defines the core metadata:

*   **name & version:** Distribution name on PyPI and release version. These are required. The name must be unique on PyPI[packaging.python.org](https://packaging.python.org/tutorials/packaging-projects/#:~:text=,as%20one%20which%20already%20exists), and the version should follow PEP 440 (e.g. semantic versioning).
    
*   **description & readme:** A short summary and the README file for long description. By pointing to `README.md`, PyPI will show its content on your project page[packaging.python.org](https://packaging.python.org/tutorials/packaging-projects/#:~:text=,toml%20guide).
    
*   **requires-python:** The Python versions your package supports (e.g. `>=3.8` means it requires Python 3.8 or newer)[packaging.python.org](https://packaging.python.org/tutorials/packaging-projects/#:~:text=%2A%20%60requires,has%20a%20matching%20Python%20version). Tools like pip use this to refuse installation on unsupported Python versions.
    
*   **license:** The license identifier (setuptools now supports SPDX license identifiers via PEP 639)[packaging.python.org](https://packaging.python.org/tutorials/packaging-projects/#:~:text=https%3A%2F%2Fpypi). Here we use `"MIT"` which is a known SPDX ID for the MIT License.
    
*   **authors/maintainers:** You can list authors and/or maintainers with name and email[packaging.python.org](https://packaging.python.org/tutorials/packaging-projects/#:~:text=,in%20the%20same%20format). This information is included in package metadata (and is public on PyPI). Using your domain email here is fine.
    
*   **classifiers:** Trove classifiers for metadata. At minimum, indicate your intended Python versions and OS compatibility[packaging.python.org](https://packaging.python.org/tutorials/packaging-projects/#:~:text=,org%2Fclassifiers), and the License classifier (e.g. “OSI Approved :: MIT License”). These classifiers make your project searchable on PyPI.
    
*   **dependencies:** This lists your runtime dependencies (what will be installed alongside your package). Each entry should ideally include a version range. (The example uses `requests>=2.0,<3.0` which means any 2.x version of requests is acceptable). Avoid pinning to exact versions unless absolutely necessary, to prevent conflicts[discuss.python.org](https://discuss.python.org/t/should-i-be-pinning-my-dependencies/13159#:~:text=jwodder%20%28John%20T,15%2C%202022%2C%2011%3A38pm%20%202).
    
*   **optional-dependencies:** These define extras. In the above, a “dev” extra includes `pytest` and `cython` which a developer or contributor can install with `pip install your-package[dev]`. You can define multiple extras groups (e.g. for docs, testing, etc.) similarly[packaging.python.org](https://packaging.python.org/tutorials/packaging-projects/#:~:text=,a%20file%20or%20Git%20tag).
    
*   **urls:** Additional links for the project (these will show up as buttons on PyPI, e.g. “Homepage”, “Source”, “Documentation”, etc.)[packaging.python.org](https://packaging.python.org/tutorials/packaging-projects/#:~:text=,source%2C%20documentation%2C%20issue%20trackers%2C%20etc). It’s good practice to at least provide a source code link and project homepage if available.
    

Setuptools will use this `[project]` metadata when building the package, so you don’t need a `setup.py` at all for a pure-python project. If you have special build steps (like compiling C code or generating files), you might still include a `setup.cfg` or `setup.py` to configure that, but for most packages this won’t be needed.

**Dynamic vs Static metadata:** The `dynamic = []` list in the example above is left empty, indicating all fields are statically defined. If, for instance, you wanted the version to be read from your module (to avoid duplication), you would list `"version"` as dynamic and provide it via code. However, static definitions are simpler and preferred for consistency.

### Using Poetry

Poetry is an all-in-one tool that manages dependencies and packaging. It uses `pyproject.toml` under the hood, but with its own `[tool.poetry]` configuration section for metadata and dependencies (instead of the `[project]` table). Poetry can simplify environment management and publishing, at the cost of adding an extra tool requirement for collaborators.

If you initialize a project with Poetry (`poetry new`), it will create a `pyproject.toml` like:

```toml
[tool.poetry]
name = "your-package"
version = "0.1.0"
description = "A short description of your package"
authors = ["Your Name <you@yourdomain.com>"]
readme = "README.md"
license = "MIT"
repository = "https://github.com/youruser/yourproject"
homepage = "https://yourproject.yourdomain.com"
keywords = ["example", "packaging"]

[tool.poetry.dependencies]
python = ">=3.8"
requests = "^2.0.0"

[tool.poetry.dev-dependencies]
pytest = "^6.0"

[build-system]
requires = ["poetry-core>=1.5.0"]
build-backend = "poetry.core.masonry.api"
```

Key points for Poetry:

*   The `[tool.poetry]` section fields largely mirror the standard metadata (name, version, description, authors, etc.). Poetry enforces PEP 440 versions and encourages semantic versioning.
    
*   Dependencies are split into `dependencies` (runtime) and `dev-dependencies` (for development only). Poetry uses caret (`^`) by default to specify version ranges (e.g. `^2.0.0` means `>=2.0.0, <3.0.0` in PEP 440 terms).
    
*   Poetry will manage a `poetry.lock` file with exact resolved versions for reproducible environments, but that lock file is not used by pip when someone installs your package from PyPI. (It’s mainly for development workflows or if you publish an application and want to lock dependencies.)
    
*   The `[build-system]` here indicates Poetry’s own build backend (`poetry-core`). When you run `poetry build`, it will create the same kind of sdist and wheel as other methods, ready for upload.
    

Using Poetry can simplify publishing: `poetry publish` can build and upload in one command. Poetry will ask for PyPI credentials or you can configure an API token (`poetry config pypi-token.pypi <token>`). Under the hood, it performs similarly to using `build` + `twine`. If you prefer a more hands-on approach or need fine control (especially with compiled extensions), the setuptools approach might be preferable.

**Comparison of approaches:** In summary:

*   _Setup.py (legacy):_ Imperative, flexible if you need custom code, but now mostly replaced by declarative configs. You should not use `setup.py upload` (deprecated in favor of Twine) and you’ll still need a `pyproject.toml` for PEP 517 builds.
    
*   _Setup.cfg + pyproject.toml:_ Declarative metadata via setup.cfg or `[project]` table, using setuptools build backend. This is a “modernized” approach fully supported by PyPA. It’s great for most packages, including those with simple extension builds.
    
*   _Poetry:_ High-level tool managing the entire lifecycle (dependency locking, build, publish). Good for application projects or maintainers who prefer its workflow. The package produced is standard, but contributors must install Poetry to work with the project configuration.
    

No matter which approach, the output (sdist and wheel distributions) is what ultimately gets uploaded to PyPI.

Metadata and Configuration Details
----------------------------------

Getting the package metadata right is crucial. We’ve touched on many fields; here we consolidate important configuration across different file formats:

**Core metadata fields (Name, Version, Description, Python Requires, etc.):** These are required or strongly recommended:

*   **Name**: Unique package name on PyPI (`name` in setup.py/setup.cfg or pyproject). Must not conflict with existing project names[packaging.python.org](https://packaging.python.org/tutorials/packaging-projects/#:~:text=,as%20one%20which%20already%20exists).
    
*   **Version**: Package version, following PEP 440 (e.g. `0.1.0`, `1.0.0b1` for beta, etc.). Use a consistent versioning strategy (semantic versioning is common). Some projects manage version automatically (e.g. reading from a single source in code). If so, mark it as dynamic in pyproject or use tools like `setuptools_scm`.
    
*   **Description**: A short one-line description. In `setup.py` this is `description="..."`. In pyproject `[project]` it’s `description` field. Keep it concise.
    
*   **Long Description**: The detailed description shown on PyPI. This often comes from your README. With setuptools, you either specify `long_description = open("README.md").read()` and `long_description_content_type = "text/markdown"` (if using setup.py) or use `readme = "README.md"` in pyproject which will include the file’s content[packaging.python.org](https://packaging.python.org/tutorials/packaging-projects/#:~:text=,toml%20guide). Make sure the content type is correct (Markdown vs RST) so PyPI renders it properly. You can test rendering by using `twine check` on your distribution files before uploading.
    
*   **Author/Maintainer**: Identify who wrote or maintains the package. Typically you use `author` and `author_email` (and/or `maintainer` variants) in setup.cfg or `authors = [{name, email}]` in pyproject[packaging.python.org](https://packaging.python.org/tutorials/packaging-projects/#:~:text=,in%20the%20same%20format). This is public metadata. If you’re a solo maintainer, you can just use Author. If the project is transferred, Maintainer fields can be used.
    
*   **License**: It’s important to declare a license. In older setup.py, one might put `license="MIT"` and include the full text in a LICENSE file. Trove classifiers also indicated the license. Now, with PEP 639, tools support an explicit license field with an SPDX ID[packaging.python.org](https://packaging.python.org/tutorials/packaging-projects/#:~:text=https%3A%2F%2Fpypi) and a way to include license files. For example, `license = "MIT"` and `license-files = ["LICENSE"]` in pyproject will include the LICENSE file in your sdist/wheel automatically[packaging.python.org](https://packaging.python.org/tutorials/packaging-projects/#:~:text=https%3A%2F%2Fpypi) (setuptools 60+ needed). Always include the actual license text file for clarity.
    
*   **Python Requires**: Use `python_requires=">=X.Y"` in setup.py/setup.cfg or `requires-python = ">=X.Y"` in pyproject[packaging.python.org](https://packaging.python.org/tutorials/packaging-projects/#:~:text=%2A%20%60requires,has%20a%20matching%20Python%20version) to prevent installation on unsupported Python versions. This helps communicate which Python versions you support and pip will refuse to install the package on older Python if not compatible.
    

**Optional/Additional metadata:**

*   **Classifiers**: We discussed these – provide as many applicable classifiers as make sense (intended audience, topic, programming language versions, etc.). Classifiers are specified as a list of strings in setup or pyproject[packaging.python.org](https://packaging.python.org/tutorials/packaging-projects/#:~:text=requires,files%20%3D%20%5B%22LICEN%5BCS%5DE). For the list of valid classifiers, see the \[PyPI classifiers page\]\[106\].
    
*   **Keywords**: A list of keywords (tags) can be provided (e.g. in `setup.cfg` or `pyproject.project.keywords`) to help discoverability.
    
*   **Project URLs**: We showed how to add multiple URLs (documentation, source, issue tracker, funding, etc.)[packaging.python.org](https://packaging.python.org/tutorials/packaging-projects/#:~:text=%5Bproject.urls%5D%20Homepage%20%3D%20,https%3A%2F%2Fgithub.com%2Fpypa%2Fsampleproject%2Fissues). These show up nicely on the PyPI project page as quick links.
    
*   **Entry Points**: If your package provides console scripts or plugins, you would configure **entry points** (in setup.cfg’s `[options.entry_points]` or pyproject under tool-specific settings). For example, a console script entry point allows installing a command-line tool via your package. This is more advanced, so refer to the Python Packaging User Guide for “Creating and packaging command-line tools” if needed.
    
*   **Package Data**: If your package includes non-Python files that it needs at runtime (templates, data files, etc.), you must include them. In setup.cfg, you might use `include_package_data=True` and a `MANIFEST.in` to include those files in the source distribution[packaging.python.org](https://packaging.python.org/guides/distributing-packages-using-setuptools/#:~:text=Packaging%20and%20distributing%20projects%20,included%20in%20a%20source%20distribution). In pyproject (setuptools), you can use `packages = "find:"` plus include directives or use `tool.setuptools.package-data` entries. Make sure to list anything needed (or use wildcard patterns).
    
*   **Versioning Strategy**: Decide how to update version numbers. Many projects use **SemVer** (MAJOR.MINOR.PATCH). As you publish updates:
    
    *   Bump the version number in your metadata.
        
    *   Tag the release in version control with the same version (e.g. `git tag v0.2.0`).
        
    *   You may use tools to automate version bumps and changelog (e.g. `bump2version` or towncrier).
        
    *   If you need to release pre-releases, use PEP 440 notation (e.g. `1.0.0a1` for alpha, `1.0.0rc1` for release candidate). Pip will treat those appropriately (and won’t install pre-releases unless explicitly allowed by the user’s version spec).
        
    *   Avoid reusing a version number once published — PyPI will not allow re-uploading files for an existing version (to ensure integrity)[packaging.python.org](https://packaging.python.org/tutorials/packaging-projects/#:~:text=You%20will%20be%20prompted%20for,so%20be%20sure%20to%20paste). If you find a critical bug, you must release a new version (or in extreme cases, yank the bad release, described later).
        

**Dependencies and extras:** How you declare dependencies differs slightly by tool, but the concept is the same. In `setup.py`, use `install_requires=[...]` and `extras_require={...}`. In `setup.cfg`, under `[options]` you list `install_requires` and under `[options.extras_require]` define extras. In `pyproject.toml [project]`, use `dependencies = [...]` and `[project.optional-dependencies]` for extras groups. In Poetry, use `[tool.poetry.dependencies]` and `[tool.poetry.extras]` (or dev-dependencies separately). Whichever method, follow these best practices:

*   **Don’t over-pin** your dependencies. For library packages, it’s recommended _not_ to pin exact versions, but rather specify a range that is known to work[discuss.python.org](https://discuss.python.org/t/should-i-be-pinning-my-dependencies/13159#:~:text=jwodder%20%28John%20T,15%2C%202022%2C%2011%3A38pm%20%202). Pinning (e.g. requiring `requests==2.25.1`) can cause conflicts if another package requires a different version. Instead, use inequalities: lower bound at the minimum you’ve tested, and upper bound if you know future major releases might be incompatible (e.g. `<3.0` if 3.x could break compatibility).
    
*   **Optional dependencies (extras):** Only list truly optional features under extras. Common extras are `dev`, `docs`, `test` or optional feature groups (for example, a package might have `excel = ["pandas"]` extra for Excel support, which normal users don’t need). Document these extras in your README so users know they exist.
    
*   **Environmental markers:** If a dependency is needed only on certain Python versions or platforms, use environment markers (setuptools supports this in install\_requires, or in pyproject you can include a PEP 508 marker). Example: `importlib-resources>=1.0; python_version < "3.9"` – this means on Python 3.8 and below, install importlib-resources, but not on 3.9+ where the functionality is built-in.
    

By carefully specifying metadata and dependencies, you make installation and usage smoother for users and avoid issues like missing information on PyPI or installation conflicts.

Build and Distribute
--------------------

Once your project is configured, the next step is to build distributable packages. PyPI accepts two main distribution formats:

*   **Source Distribution (sdist)** – a tarball (usually `.tar.gz`) of your raw source files.
    
*   **Built Distribution (wheel)** – a Python Wheel (`.whl`) file, which is a binary package format that can contain compiled extensions and is ready to install.
    

You should generally provide both. The source distribution is a fallback for scenarios where a wheel is not available for a platform; pip can compile it (if possible) when installing[packaging.python.org](https://packaging.python.org/tutorials/packaging-projects/#:~:text=The%20,one%20built%20distribution%20is%20needed).

### Building the package

Use standardized tools to build:

*   **`build` package (PEP 517)**: This is the recommended build frontend. Once your `pyproject.toml` is set up, simply run:
    
    ```bash
    python3 -m pip install --upgrade build  # ensure build tool is installed
    python3 -m build
    ```
    
    This will invoke the specified build backend (setuptools or poetry, etc.) and produce files in the `dist/` directory[packaging.python.org](https://packaging.python.org/tutorials/packaging-projects/#:~:text=This%20command%20should%20output%20a,directory). You should see output like:
    
    ```text
    dist/
    ├── your_package-0.1.0-py3-none-any.whl
    └── your_package-0.1.0.tar.gz
    ```
    
    Here, `py3-none-any.whl` indicates a pure-Python wheel (for any OS, Python 3 only) and the tar.gz is the source. If you have C extensions, the wheel name will include specifics (like cp39-cp39-win\_amd64.whl for a Windows Python 3.9 build, etc.).
    
*   **Setuptools directly**: Alternatively, if using the legacy approach, you can run `python setup.py sdist bdist_wheel` (ensure you have `wheel` installed). This achieves a similar result: a tar.gz in `dist/` and a `.whl` if the wheel build succeeded. However, using `build` is preferred as it performs builds in an isolated environment and aligns with modern PEP 517 workflows.
    
*   **Poetry**: If you are using Poetry, run `poetry build`. This will create the sdist and wheel under `dist/` as well. Poetry takes care of calling its build backend (poetry-core) to generate these.
    

After building, verify the contents of `dist/`. The **source distribution** should include your source files, README, license, and setup files (if any). The **wheel** should include your code ready to import, and any compiled binaries (for extension modules).

**Including compiled extensions:** If your package contains a C/C++ or Cython extension:

*   Ensure your build backend knows how to build it. With setuptools, you typically define extension modules via `setup.py` (using `setuptools.Extension` and perhaps `Cython.Build.cythonize`). When you run `bdist_wheel`, it compiles the extensions. In `pyproject.toml` context, you might need a small `setup.py` to call `cythonize` or specify a build hook in setup.cfg.
    
*   The wheel filenames will reflect the platform and Python ABI. For example: `your_package-0.1.0-cp310-cp310-win_amd64.whl` for a build targeting CPython 3.10 on Windows 64-bit. These are **binary wheels**.
    
*   You should build wheels for each major OS and Python version you intend to support[packaging.python.org](https://packaging.python.org/guides/packaging-binary-extensions/#:~:text=If%20you%20plan%20to%20distribute,CI%3B%20these%20include%20cibuildwheel%20and). A common practice is to use CI services to build Windows, macOS, and manylinux (for Linux) wheels. Tools like **cibuildwheel** can automate building a matrix of wheels on CI[packaging.python.org](https://packaging.python.org/guides/packaging-binary-extensions/#:~:text=If%20you%20plan%20to%20distribute,CI%3B%20these%20include%20cibuildwheel%20and).
    
*   Use the “Stable ABI” if possible for compiled extensions (i.e., build against Python’s limited ABI to get an `abi3` wheel tag). This can reduce the number of wheels you need to produce (one wheel can work across all Python 3.x versions in that case)[packaging.python.org](https://packaging.python.org/guides/packaging-binary-extensions/#:~:text=match%20at%20L414%20Using%20CPython%E2%80%99s,new%20minor%20version%20of%20Python).
    
*   Always provide an sdist in addition to wheels[packaging.python.org](https://packaging.python.org/tutorials/packaging-projects/#:~:text=The%20,one%20built%20distribution%20is%20needed). If a user’s platform or Python version isn’t covered by your uploaded wheels, pip will fall back to the sdist and attempt to build it locally. (For this to work, the user needs a compiler and the required development libraries – which is why providing pre-built wheels is user-friendly).
    

After building, you can check the distributions:

*   **Twine check**: run `twine check dist/*` to catch common issues like broken README formatting or missing metadata. This isn’t required but is a useful validation step.
    
*   You can even test installing the wheel locally in a clean venv: `pip install dist/your_package-0.1.0-py3-none-any.whl` to ensure it installs and the package can be imported.
    

### Distribution files recap

*   **.tar.gz (sdist)**: Contains your source files exactly as in your repository (including setup.cfg/pyproject, etc.). Users installing this will run the build process on their machine.
    
*   **.whl (wheel)**: A zip-format archive that contains the ready-to-install files. Installing a wheel just unpacks files; no compilation needed. Wheels can be pure Python (suffix `-py3-none-any.whl` means no specific ABI or OS requirements) or platform-specific (with tags for python version, ABI, platform).
    

By building both, you maximize compatibility. As the Python Packaging User Guide advises: always upload a source distribution, and additionally provide wheels for the platforms you support[packaging.python.org](https://packaging.python.org/tutorials/packaging-projects/#:~:text=The%20,one%20built%20distribution%20is%20needed).

PyPI Account Setup
------------------

To upload packages, you need an account on PyPI (the Python Package Index). Since 2024, PyPI has tightened security for maintainers, so setting up your account properly is important.

*   **Create a PyPI account:** Go to pypi.org and register. Use your custom domain email (e.g. `you@yourdomain.com`) as the email for the account – you’ll need to verify this email. PyPI will send a confirmation link; verify before proceeding to uploads[packaging.python.org](https://packaging.python.org/tutorials/packaging-projects/#:~:text=The%20first%20thing%20you%E2%80%99ll%20need,more%20details%2C%20see%20Using%20TestPyPI). (If you want to test on TestPyPI, that’s a separate site with separate accounts – we’ll cover that in the next section.)
    
*   **Enable Two-Factor Authentication (2FA):** **PyPI requires 2FA on all accounts as of January 1, 2024[blog.pypi.org](https://blog.pypi.org/posts/2023-12-13-2fa-enforcement/#:~:text=What%27s%20changing%3F).** After logging in, go to your Account Settings and **add 2FA**. You can use an authenticator app (TOTP) or a security key (WebAuthn) – PyPI supports both. It’s wise to set up at least two 2FA methods (e.g. two authenticators or an authenticator + a hardware key) so you have a backup. Also save your recovery codes offline. Once 2FA is enabled:
    
    *   You **must use an API token or trusted publisher to upload** packages (username/password no longer works for uploads)[blog.pypi.org](https://blog.pypi.org/posts/2023-12-13-2fa-enforcement/#:~:text=2FA,you%27ll%20need%20to%20enable%202FA)[blog.pypi.org](https://blog.pypi.org/posts/2023-12-13-2fa-enforcement/#:~:text=When%20uploading%20a%20file%2C%20you,link%20to%20API%20Tokens%20help). This means you won’t directly use your PyPI password for publishing.
        
*   **Create an API token:** PyPI allows you to create scoped API tokens for uploads instead of using your username/password. In your PyPI account settings, find the **API tokens** section. Create a token and give it a meaningful name (e.g. “your-package upload token”). You can scope it to a specific project or “Entire account”. If the project doesn’t exist yet, you might start with an entire account token and later scope it. PyPI will show you the token **once** – copy it and keep it safe (e.g. in a password manager)[packaging.python.org](https://packaging.python.org/tutorials/packaging-projects/#:~:text=To%20securely%20upload%20your%20project%2C,won%E2%80%99t%20see%20that%20token%20again). The token will start with `pypi-` followed by a long string; it essentially serves as your “password” for uploads[packaging.python.org](https://packaging.python.org/tutorials/packaging-projects/#:~:text=You%20will%20be%20prompted%20for,be%20sure%20to%20paste%20correctly).
    
*   **Using your domain email:** With your account set up, you can optionally add your domain as a verified domain on PyPI (PyPI has an option to verify domain ownership for organizations/projects). At minimum, using the domain email ensures that communications from PyPI (like password resets, security notifications) come to an email under your control. It also shows professionalism; when you upload a package, PyPI will display the maintainer username (not email) publicly, but having a custom domain email in your account can be reused in project metadata.
    
*   **Security considerations:** Make sure to enable _notification settings_ in PyPI (there are options to be emailed on new login or new project releases). Also, since you have 2FA, consider adding a **WebAuthn security device** (like YubiKey) as a second factor for stronger phishing protection.
    

At this point, you have a PyPI account with 2FA and an API token ready. Next, you’ll use these credentials to upload your package.

Uploading to PyPI
-----------------

Uploading involves packaging your distribution files to the index. It’s best practice to **test your upload on TestPyPI** (a staging environment) before uploading to the real PyPI.

### Using TestPyPI for a Dry Run

**TestPyPI** is a separate instance of PyPI for testing (at `test.pypi.org`). Packages uploaded there won’t be visible on the real PyPI and can be safely experimented with.

1.  **Register on TestPyPI:** Create an account on test.pypi.org (you can use the same username/email as on PyPI, but you must register separately). Verify your email on TestPyPI as well[packaging.python.org](https://packaging.python.org/tutorials/packaging-projects/#:~:text=The%20first%20thing%20you%E2%80%99ll%20need,more%20details%2C%20see%20Using%20TestPyPI).
    
2.  **Create a TestPyPI API token:** Just like before, go to your TestPyPI account settings and create an API token[packaging.python.org](https://packaging.python.org/tutorials/packaging-projects/#:~:text=To%20securely%20upload%20your%20project%2C,won%E2%80%99t%20see%20that%20token%20again). Copy it. (It will also start with `pypi-`, but is only valid for the test site).
    
3.  **Upload to TestPyPI using Twine:** Install Twine if you haven’t already (`pip install twine`). Twine is the recommended tool for uploading to PyPI securely (it uses HTTPS and supports tokens). Make sure your `dist/` folder has the files (e.g. `your_package-0.1.0.tar.gz` and `.whl`). Then run:
    
    ```bash
    twine upload --repository testpypi dist/*
    ```
    
    Twine will use the `testpypi` repository configuration by default. It will prompt for your username and password. For username, enter `__token__` (literally, that keyword) and for password, paste the TestPyPI token (including the `pypi-` prefix)[packaging.python.org](https://packaging.python.org/tutorials/packaging-projects/#:~:text=You%20will%20be%20prompted%20for,be%20sure%20to%20paste%20correctly). The input will be hidden (no characters as you paste) – just hit Enter after pasting. You should see an upload log for each file, ending with a success message and URL[packaging.python.org](https://packaging.python.org/tutorials/packaging-projects/#:~:text=Uploading%20distributions%20to%20https%3A%2F%2Ftest,kB%20%E2%80%A2%2000%3A00%20%E2%80%A2).
    
    _Alternatively:_ You can configure a `~/.pypirc` file to avoid entering credentials each time. For example, in `~/.pypirc`:
    
    ```ini
    [distutils]
    index-servers =
        pypi
        testpypi
    
    [pypi]
    username = __token__
    password = <production PyPI token>
    
    [testpypi]
    repository = https://test.pypi.org/legacy/
    username = __token__
    password = <your TestPyPI token>
    ```
    
    Ensure this file is chmod 600 (user-readable only) since it contains secrets[packaging.python.org](https://packaging.python.org/specifications/pypirc/#:~:text=Warning)[packaging.python.org](https://packaging.python.org/specifications/pypirc/#:~:text=Warning). With this, `twine upload -r testpypi dist/*` will use saved tokens.
    
4.  **Verify on TestPyPI:** Once uploaded, go to the TestPyPI URL for your project: `https://test.pypi.org/project/your-package/0.1.0/` (the exact path was shown in the Twine output). Check that the metadata (description, classifiers, etc.) looks correct. You can also test installation from TestPyPI:
    
    ```bash
    python -m venv test_env
    source test_env/bin/activate
    pip install --no-deps -U pip  # upgrade pip in the venv
    pip install --index-url https://test.pypi.org/simple/ --no-deps your-package
    ```
    
    We use `--no-deps` to avoid pulling dependencies from TestPyPI (since TestPyPI may not have them all)[packaging.python.org](https://packaging.python.org/tutorials/packaging-projects/#:~:text=Note). If your package has dependencies, you might need to either upload them to TestPyPI as well or install them manually from real PyPI before installing your package.
    
    After installing, open a Python shell in that venv and try `import your_package` and perhaps call a simple function to ensure it works[packaging.python.org](https://packaging.python.org/tutorials/packaging-projects/#:~:text=and%20import%20the%20package%3A)[packaging.python.org](https://packaging.python.org/tutorials/packaging-projects/#:~:text=,add_one%282%29%203). This step ensures the wheel is usable.
    
5.  If something is wrong (e.g., the description is not rendering, or a file is missing in the package), you can fix your setup and increment the version (e.g. to 0.1.1) and rebuild, then try again on TestPyPI. Remember, you cannot reuse the same version number once uploaded (even on TestPyPI, deleting releases is possible but not on real PyPI after a short window). So bump the version for any re-upload attempt.
    

### Uploading to the real PyPI

Once you’re satisfied with TestPyPI results:

1.  **Create the real release**: Update any last metadata (e.g., remove “Test release” notes if you added any), bump version if you did multiple test iterations (use the final new version for the real release), rebuild the distributions (`python -m build` or equivalent). Ensure you have the final dist files ready.
    
2.  **Upload with Twine to PyPI**: Use Twine with the real PyPI repository (which is default). For example:
    
    ```bash
    twine upload dist/*
    ```
    
    Since PyPI now mandates 2FA, Twine will **not** accept your username & password login. Instead, you again use an API token. If not configured in `~/.pypirc`, Twine will prompt for credentials. Enter `__token__` as username and the **production** PyPI token as password[packaging.python.org](https://packaging.python.org/specifications/pypirc/#:~:text=,PyPI%20token)[packaging.python.org](https://packaging.python.org/specifications/pypirc/#:~:text=username%20%3D%20__token__%20password%20%3D,PyPI%20token). The upload URL will be `https://upload.pypi.org/legacy/` by default and you should see similar output as before (but for the real site)[packaging.python.org](https://packaging.python.org/tutorials/packaging-projects/#:~:text=,org%2F%20by%20default).
    
    If you set up `~/.pypirc` with the token, just running `twine upload dist/*` will pick it up and not prompt, uploading directly to PyPI.
    
3.  **Common upload issues**:
    
    *   _“Repository not found” or authentication errors:_ Check that you used the correct repository URL or name in Twine command and that the token is correct. Ensure you included the `pypi-` prefix if copy-pasting. If 2FA wasn’t enabled, PyPI would reject password auth for uploads[blog.pypi.org](https://blog.pypi.org/posts/2023-12-13-2fa-enforcement/#:~:text=When%20uploading%20a%20file%2C%20you,link%20to%20API%20Tokens%20help), but since you enabled it, you should be using token.
        
    *   _HTTP 400 or “File already exists” errors:_ This means you are trying to upload a file name that PyPI already has for that project & version. It occurs if you accidentally repeated a version. Solution: bump the version, rebuild, and try again. PyPI does not allow replacing an existing file.
        
    *   _Metadata or validation errors:_ Twine will check your package metadata on upload. If your long description is badly formatted (for example, invalid RST syntax), PyPI may reject it. The error message will indicate the problem. Use `twine check` to diagnose in advance. Fix and rebuild if needed (e.g., add a `long_description_content_type` or correct your README syntax).
        
    *   _Missing files in sdist:_ If users report that something is missing when installing from sdist (like no license file, or missing package data), it means your MANIFEST.in or include patterns might be wrong. Update them and publish a new version.
        
    *   _Large files:_ PyPI has file size limits. If you have very large files, you might need to contact PyPI admins or use FileStorage. But most pure code packages are small. Data-heavy packages might consider alternatives.
        
4.  **Success confirmation:** After a successful upload, go to the PyPI URL for your project: `https://pypi.org/project/your-package/0.1.0/`. It may take a minute for everything to sync. You should see your release, the description, and all metadata on display. You can now try `pip install your-package` (this will get from real PyPI) in a fresh environment to double-check everything works as expected.
    

**Tip:** You can automate the version bump, build, and twine upload sequence with a Makefile or script to reduce manual steps and avoid mistakes, especially as your release process becomes routine.

Advanced Publishing Features
----------------------------

Now that you know the basics, here are some advanced features and best practices to consider for professional package maintenance.

### GPG Signing (Optional)

You might have seen that Twine has options to GPG-sign your packages (`--sign` flag). This attaches a PGP signature (`.asc` file) to your uploads for integrity verification. In practice, **PyPI has deprecated PGP signatures** – as of 2023, PyPI no longer displays or provides new signature files to users, effectively ignoring uploaded `.asc` files[blog.pypi.org](https://blog.pypi.org/posts/2023-05-23-removing-pgp/#:~:text=If%20you%20are%20someone%20who,False). This is because so few users were verifying them and many signatures were unverifiable[blog.pypi.org](https://blog.pypi.org/posts/2023-05-23-removing-pgp/#:~:text=that%20the%20current%20support%20for,signatures%20is%20not%20proving%20useful).

However, you can still sign distributions if you want an external verification path:

*   Generate a GPG key (if you don’t have one).
    
*   Use Twine with `twine upload -s dist/*` (and `--sign-with <keyid>` if you have multiple keys). Twine will invoke GPG to create signatures before upload[discuss.python.org](https://discuss.python.org/t/gpg-key-created-when-uploading-package-to-pypi/35527#:~:text=I%E2%80%99m%20interested%20to%20know%20what,more%20recently%20disallowed%20it%20entirely)[discuss.python.org](https://discuss.python.org/t/gpg-key-created-when-uploading-package-to-pypi/35527#:~:text=Removing%20PGP%20from%20PyPI%20,The%20Python%20Package%20Index).
    
*   Upload proceeds as normal, with `.asc` files accompanying your package files. PyPI will accept them (not reject), but users won’t see a “Verified” flag or automatically use them. Interested users would have to manually fetch the `.asc` from PyPI’s backend and verify with your public key.
    

Going forward, the Python packaging ecosystem is exploring **trusted supply chain** tools (like Sigstore and trusted publishing). Currently, PGP signing is optional and yields little benefit on PyPI itself. If you want to sign releases for the sake of GitHub releases or your own records, you can do so, but it’s not a common requirement for PyPI.

### Automating Releases with CI/CD

It’s a good practice to automate your publishing process to avoid manual errors and integrate it with your development workflow. Using **continuous integration (CI)** pipelines (like GitHub Actions, GitLab CI, Travis CI, etc.), you can trigger package builds and uploads whenever you create a new release tag.

**GitHub Actions example:** PyPA provides an official GitHub Action for publishing to PyPI. You can use **pypa/gh-action-pypi-publish** in your workflow. For instance, create `.github/workflows/publish.yml`:

```yaml
name: Publish to PyPI
on:
  push:
    tags: "v*.*.*"    # triggers on tagging a version like v1.2.3

jobs:
  build-and-publish:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.10'
      - name: Install build tools
        run: python -m pip install build twine
      - name: Build distributions
        run: python -m build
      - name: Publish to TestPyPI
        if: github.event_name == 'push' && contains(github.ref, '-beta')  # example condition
        uses: pypa/gh-action-pypi-publish@release/v1
        with:
          repository-url: https://test.pypi.org/legacy/
          password: ${{ secrets.TEST_PYPI_TOKEN }}
      - name: Publish to PyPI
        if: github.event_name == 'push' && startsWith(github.ref, 'refs/tags/v')
        uses: pypa/gh-action-pypi-publish@release/v1
        with:
          password: ${{ secrets.PYPI_TOKEN }}
```

In this example:

*   It triggers on pushed tags that look like version numbers.
    
*   It builds the package.
    
*   It uses the PyPI publish action to upload. The credentials are taken from repository secrets (you would add `PYPI_TOKEN` and optionally `TEST_PYPI_TOKEN` in your GitHub repo secrets). The action expects the token as `password` with username `__token__` by default.
    
*   We showed an optional step to upload to TestPyPI if the tag indicates a beta, and then to PyPI for a final release.
    

Instead of storing a long-lasting token, PyPI now also supports **Trusted Publishers** using OpenID Connect (OIDC). This means GitHub can authenticate to PyPI without you managing a token, via an authorized link between your PyPI project and GitHub Actions[packaging.python.org](https://packaging.python.org/guides/publishing-package-distribution-releases-using-github-actions-ci-cd-workflows/#:~:text=Configuring%20trusted%20publishing%C2%B6). To use this:

*   In PyPI, go to your project’s “Manage” > “Advanced” > “Trusted Publishers” and follow steps to add GitHub as a trusted publisher (you’ll specify your repository).
    
*   Update the GitHub Actions workflow to use `pypa/gh-action-pypi-publish@release/v1` without a password, but ensure it’s running in an environment PyPI trusts (the action’s docs detail this). Essentially, PyPI will issue a one-time token to the workflow, eliminating the need to store one yourself[packaging.python.org](https://packaging.python.org/guides/publishing-package-distribution-releases-using-github-actions-ci-cd-workflows/#:~:text=This%20guide%20relies%20on%20PyPI%E2%80%99s,to%20provide%20a%20username%2Fpassword%20combination).
    

Using CI/CD for publishing ensures each release is done the same way, with the correct files, and can be tied to other steps (like running tests, linting, etc., before publishing). It also enables multiple maintainers to release new versions without manually handling credentials each time.

### Tagging Releases and Release Management

Always tag your releases in version control (e.g., Git). For example, if releasing version 0.1.0, do:

```bash
git tag -a v0.1.0 -m "Release version 0.1.0"
git push origin v0.1.0
```

This not only marks the commit of that release but also can trigger CI workflows as shown. Tags (especially annotated tags) serve as a historical record. On GitHub, you might also create a GitHub Release which can auto-generate from the tag and include release notes or changelogs.

If you use GitHub Releases, you might attach the source distribution and wheel there as well (some users like downloading from GitHub). This is optional since they can always get it from PyPI.

Consider signing your tags with GPG as well (Git can show a “verified” badge on signed tags/commits). This doesn’t directly affect PyPI but contributes to the trust of your source code provenance.

When you plan significant changes, communicate them via versioning:

*   Bump the major version for breaking changes.
    
*   If deprecating features, perhaps issue warnings in code and mention in documentation for a couple of minor releases before removing them in a major bump.
    

### Supporting Multiple Python Versions

To reach more users, you often want to support a range of Python versions (commonly, the latest 3.x versions that are not end-of-life). Here’s how to manage this:

*   **Testing**: Use CI to run your test suite on multiple Python versions (3.8, 3.9, 3.10, 3.11, etc.). This gives you confidence your package works across them.
    
*   **Declare compatibility**: As mentioned, use `python_requires` to prevent installation on incompatible Pythons. And use Trove classifiers like “Programming Language :: Python :: 3.9” etc., for each version you support.
    
*   **Conditional dependencies or code**: If you need to support an older Python, you might include conditional dependencies (e.g., importlib-resources for older versions). You might also use `sys.version_info` checks in code for minor differences. Keep these minimal to avoid maintenance burden.
    
*   **Multiple wheels**: If you have binary extensions, you must produce wheels for each Python version (unless using the stable ABI). Manylinux wheels can often be built that work for all Python versions (embedding the ABI for each). As noted earlier, tools like `cibuildwheel` come in handy to build a matrix of (OS x Python) wheels in one go[packaging.python.org](https://packaging.python.org/guides/packaging-binary-extensions/#:~:text=If%20you%20plan%20to%20distribute,CI%3B%20these%20include%20cibuildwheel%20and).
    
*   **End-of-life Pythons**: When a Python version is end-of-life (no longer supported, e.g., 3.6 or 3.7 by 2025), you may wish to drop support. To do so in a new release, update `requires-python` to a higher minimum. It’s good to communicate this in your changelog (“Dropped support for Python 3.x”). You can also use environment markers to exclude installation on those versions.
    
*   **Future compatibility**: Test against Python beta releases if possible (e.g., if Python 3.12 is in beta, try to test your package on it). This way, your package will likely work day-one when new Python versions are released.
    

Post-Publish Considerations
---------------------------

Congratulations – your package is on PyPI! Now you should ensure everything is in order and plan for maintaining the project.

### Verify Installation from PyPI

Even if you tested with TestPyPI, do a final verification with the real deal:

*   In a fresh environment (or using Docker or a clean VM), run `pip install your-package`. This will fetch from PyPI. Make sure it installs without errors and the package import works. This catches any last-minute issues like missing files or packaging quirks.
    
*   If something critical is wrong (e.g. installation fails for all users), you have a few options: you can **yank** the release or push a quick fix update:
    
    *   **Yanking a release**: PyPI allows marking a release as yanked (via the PyPI UI or CLI tools). A yanked release is still available for those who explicitly request that version, but pip will skip it when installing without version specifiers. Yank only in serious cases (like a broken release or security issue) since it effectively hides that version from normal installs.
        
    *   Generally, for a minor issue, it’s often better to fix and release a new patch version.
        

### Project Documentation and Enhancements on PyPI

A PyPI project page can show more than just description text. Make your project page welcoming:

*   **Project description**: If you wrote your README in Markdown and specified `long_description_content_type`, check that it rendered correctly on PyPI (no broken links or images). If you see “Unable to render” errors, adjust the content (PyPI uses strict RST for `.rst` READMEs, but for Markdown it usually just works if the syntax is standard).
    
*   **Badges**: Many projects include badges in their README (e.g., build status, PyPI version, downloads, license). These badges will appear on PyPI too, since it renders your README. Feel free to add them for a professional touch:
    
    *   A badge for PyPI version (so your GitHub README always shows the latest version from PyPI).
        
    *   Build/test CI status badge.
        
    *   License badge, etc.  
        Just ensure the image links are stable (using services like shields.io). PyPI’s renderer will cache them.
        
*   **Changelog**: If you maintain a CHANGELOG.md, consider linking to it. For example, in the project URLs you could add `Changelog = https://github.com/youruser/yourproject/blob/main/CHANGELOG.md`. There’s no dedicated field for changelog, but interested users will find the link.
    
*   **Homepage/Docs**: If you have extensive documentation on a website or readthedocs, add that URL. A documentation link can be named "Documentation" under project URLs.
    
*   **Maintainers**: If your project is open to contributions, you might add a `CONTRIBUTING.md` link in the README, or include a note like “Issues and pull requests welcome on GitHub.”
    

On PyPI, you as a maintainer can also add collaborators to the project (via “Maintainership” settings). If you have a team, consider using the new **PyPI Organizations** feature (introduced in 2022) which allows grouping packages and managing teams, especially if publishing under a common namespace or domain name.

### Updates and Deprecation

Maintaining the package means releasing updates and managing older versions:

*   **Releasing updates**: Follow the same process for new versions. Keep incrementing version numbers. Try not to break backward compatibility in minor updates; if you need to, communicate clearly (in the changelog, project description, or documentation) that a breaking change happened.
    
*   **Deprecating features**: If you plan to remove a feature, you can:
    
    *   Deprecate it in code (emit a `DeprecationWarning`).
        
    *   Note in the documentation that it will be removed in a future version.
        
    *   Remove it in a major version bump.
        
*   **Yanking or removing releases**: As mentioned, PyPI allows yanking (which hides the release from default installs). Deletion of releases is generally discouraged and only allowed within a short time window after upload. After that, a release can’t be truly deleted (this is to preserve the ecosystem’s consistency). If a release is problematic, yank it and push a fix in a new version.
    
*   **Supporting older releases**: If you have a user base on older versions, you might occasionally patch an older branch. PyPI allows multiple versions to coexist. You could release a bugfix as 0.1.5 while the latest is 0.2.3, for example. This is more common in large projects. For a small project, it might be overkill – encourage users to upgrade to the latest version unless they have a constraint.
    
*   **Package deprecation/transfer**: If you decide to discontinue the project, you can mark it as such on PyPI by adding a Trove classifier “Development Status :: 7 - Inactive” or “Development Status :: 6 - Mature” depending on context. If someone else is to take over, you can transfer the ownership on PyPI to them (add as owner). PEP 541 governs name transfers if a project is abandoned – owning your domain and using domain-based names can help establish your claim if ever needed.
    

Security and Best Practices
---------------------------

Finally, consider the security of your package and users:

*   **Credential Security:** Never hardcode credentials or tokens in your repository. Use `.pypirc` or environment variables for Twine, as discussed, and restrict access. Since your PyPI token essentially grants publish rights, treat it like a password:
    
    *   If using CI, store the token as an encrypted secret, not in the code.
        
    *   If someone gains commit access to your repository and CI is auto-publishing (especially with a stored token), they could publish a malicious release. Mitigate this by protecting your CI secrets (use required code reviews, branch protection, or better yet, use Trusted Publishing which doesn’t expose a reusable token).
        
    *   Rotate tokens if you suspect compromise. You can create a new token on PyPI and delete the old one at any time.
        
    *   Use 2FA on your VCS account (GitHub, GitLab, etc.) as well, since that can indirectly affect your package trust.
        
*   **Dependency Security:** Be mindful of supply chain attacks:
    
    *   **Typosquatting**: Attackers upload a package with a name very similar to a popular one (e.g., `reqeusts`). If a user misspells when installing, they might install the wrong package[discuss.python.org](https://discuss.python.org/t/typosquatting-dependency-confusion-supply-chain-attack-call-it-as-you-wish/52615#:~:text=Python%20script%20of%20his%20own,debugging%20in%20less%20than%2015mn)[discuss.python.org](https://discuss.python.org/t/typosquatting-dependency-confusion-supply-chain-attack-call-it-as-you-wish/52615#:~:text=But%20then%20I%E2%80%99ve%20opened%20the,I%20was%20not%20convinced). As a publisher, you can’t prevent this entirely, but you can encourage users to install via your documented instructions (copy-paste the correct name). Owning a domain-based unique name helps (an attacker is less likely to spoof `yourcompany-lib` if it’s niche). PyPI monitors for malicious uploads, but it’s a constant battle.
        
    *   **Dependency confusion**: If your package is meant for internal use with a certain name, but you also publish something public with the same name, be careful. Attackers could guess internal names and upload to PyPI first. In your case, you are publishing open-source, but if you ever have internal packages, give them unique names or host them on a private index to avoid confusion[discuss.python.org](https://discuss.python.org/t/typosquatting-dependency-confusion-supply-chain-attack-call-it-as-you-wish/52615#:~:text=From%20the%20forum%20I%20could,consequences%20against%20typosquatting%20on%20pypi). Large companies often prefix internal packages or use private indexes.
        
    *   **Vulnerabilities in dependencies**: Keep an eye on security advisories. Use tools like `pip-audit` or `safety` to scan your project’s dependencies for known vulnerabilities. If a dependency has a severe issue, release a new version of your package pinning or updating to a safe version if necessary.
        
    *   **Minimum dependency versions**: Don’t set your minimum required version too low if that version has known bugs or security issues. It’s better to require a slightly newer bugfix release of a library if it resolves important issues.
        
*   **Package Name Ownership:** If your package name is similar to your domain or trademark, you have some protection via PEP 541 (against name squatting or misuse). Conversely, never choose a name that infringes on existing trademarks or packages. A unique name reduces the risk of conflict and confusion.
    
*   **Pinned vs Unpinned Dependencies:** As noted, libraries should not pin exact versions of dependencies[discuss.python.org](https://discuss.python.org/t/should-i-be-pinning-my-dependencies/13159#:~:text=jwodder%20%28John%20T,15%2C%202022%2C%2011%3A38pm%20%202). This can cause “dependency hell” for users. Instead, aim for broad compatibility. For applications (if you ever use this guide for an app that you deploy, not a library), pinning is acceptable and even recommended for repeatable deployments – but that’s usually handled via requirements files or lockfiles, not in the published metadata.
    
*   **Use of DNS (domain) in package:** Since you have a domain, you could use it for namespacing if you wish. For example, some packages incorporate the company domain in reverse (like Java style, `com.yourdomain.project`) as a unique identifier, but Python packaging doesn’t commonly do reverse-DNS package names. Instead, you might create a namespace package if you plan many packages (e.g., `yourdomain.core`, `yourdomain.utils` could be separate distributions forming a family). Namespace packages allow splitting a top-level package across distributions. This is an advanced technique (see “Packaging namespace packages” guide if needed).
    
*   **Malware scans:** PyPI runs some automated scans. If you ever get a warning or find that your release was pulled for security reasons, address it immediately. Common false positives could be if your package bundles binary blobs or does something odd in setup; try to avoid those.
    
*   **Project governance:** If your project grows popular, consider a CONTRIBUTING file and maybe a code of conduct. These aren’t directly about packaging, but good documentation and governance attract positive contributions and reduce the chance of needing to give publish rights to someone you don’t fully trust. Only add trusted collaborators as maintainers on PyPI.
    
*   **Continuous improvement:** Stay updated with Python Packaging developments. New PEPs and tools keep emerging (for instance, **Hatch** is an upcoming build backend mentioned in PyPA docs, and **PDM** for managing projects, etc.). The landscape in 2025 continues to evolve towards more secure and convenient workflows. The official Python Packaging User Guide is an excellent resource[packaging.python.org](https://packaging.python.org/guides/packaging-binary-extensions/#:~:text=,Tutorials), and the PyPI blog announces important changes (like 2FA requirement, deprecated features, etc.).
    

By following this guide, you’ve prepared, packaged, and published your Python project to PyPI with modern best practices. Your project is now installable via `pip install your-package`. Remember to maintain the project by keeping dependencies up to date, handling user feedback (issues), and publishing new releases as needed. Good luck with your open-source package! 🚀

**Sources:**

*   Python Packaging User Guide – _Tutorial: Packaging Python Projects_[packaging.python.org](https://packaging.python.org/tutorials/packaging-projects/#:~:text=%5Bproject%5D%20name%20%3D%20,python%20%3D%20%22%3E%3D3.9)[packaging.python.org](https://packaging.python.org/tutorials/packaging-projects/#:~:text=The%20,one%20built%20distribution%20is%20needed)
    
*   Python Packaging User Guide – _Core Metadata specifications_[packaging.python.org](https://packaging.python.org/tutorials/packaging-projects/#:~:text=,a%20file%20or%20Git%20tag)[packaging.python.org](https://packaging.python.org/tutorials/packaging-projects/#:~:text=%2A%20%60requires,has%20a%20matching%20Python%20version)
    
*   Python Packaging User Guide – _Using TestPyPI_[packaging.python.org](https://packaging.python.org/tutorials/packaging-projects/#:~:text=The%20first%20thing%20you%E2%80%99ll%20need,more%20details%2C%20see%20Using%20TestPyPI)[packaging.python.org](https://packaging.python.org/tutorials/packaging-projects/#:~:text=To%20securely%20upload%20your%20project%2C,won%E2%80%99t%20see%20that%20token%20again)
    
*   PyPI Administrators – “2FA requirement for PyPI” (Dec 2023)[blog.pypi.org](https://blog.pypi.org/posts/2023-12-13-2fa-enforcement/#:~:text=What%27s%20changing%3F)[blog.pypi.org](https://blog.pypi.org/posts/2023-12-13-2fa-enforcement/#:~:text=2FA,you%27ll%20need%20to%20enable%202FA)
    
*   Python Packaging – _The .pypirc file_ (config for Twine)[packaging.python.org](https://packaging.python.org/specifications/pypirc/#:~:text=,PyPI%20token)[packaging.python.org](https://packaging.python.org/specifications/pypirc/#:~:text=Warning)
    
*   Discussion on Python.org – _Pinning dependencies (John Wodder’s advice)_[discuss.python.org](https://discuss.python.org/t/should-i-be-pinning-my-dependencies/13159#:~:text=jwodder%20%28John%20T,15%2C%202022%2C%2011%3A38pm%20%202)
    
*   Python Packaging User Guide – _Packaging binary extensions_[packaging.python.org](https://packaging.python.org/guides/packaging-binary-extensions/#:~:text=If%20you%20plan%20to%20distribute,CI%3B%20these%20include%20cibuildwheel%20and)[packaging.python.org](https://packaging.python.org/guides/packaging-binary-extensions/#:~:text=match%20at%20L414%20Using%20CPython%E2%80%99s,new%20minor%20version%20of%20Python)
    
*   PyPI Security Blog – _Removing PGP from PyPI_ (May 2023)[blog.pypi.org](https://blog.pypi.org/posts/2023-05-23-removing-pgp/#:~:text=If%20you%20are%20someone%20who,False)[blog.pypi.org](https://blog.pypi.org/posts/2023-05-23-removing-pgp/#:~:text=that%20the%20current%20support%20for,signatures%20is%20not%20proving%20useful)
    
*   Python Packaging User Guide – _Publishing using GitHub Actions_[packaging.python.org](https://packaging.python.org/guides/publishing-package-distribution-releases-using-github-actions-ci-cd-workflows/#:~:text=This%20guide%20relies%20on%20PyPI%E2%80%99s,to%20provide%20a%20username%2Fpassword%20combination)
    
*   Python Packaging Discussion – _Typosquatting and dependency confusion_[discuss.python.org](https://discuss.python.org/t/typosquatting-dependency-confusion-supply-chain-attack-call-it-as-you-wish/52615#:~:text=Python%20script%20of%20his%20own,debugging%20in%20less%20than%2015mn)[discuss.python.org](https://discuss.python.org/t/typosquatting-dependency-confusion-supply-chain-attack-call-it-as-you-wish/52615#:~:text=From%20the%20forum%20I%20could,consequences%20against%20typosquatting%20on%20pypi)
## Prompt:
what's the full syntax for requirements.txt in Python

## Response:
Thought for a couple of seconds

Below is a comprehensive summary of the syntax and features you can use in a `requirements.txt` file for Python (as supported by pip). Most of these rules come from [PEP 508](https://peps.python.org/pep-0508/) and pip’s own documentation. The goal is to show how packages can be specified with version constraints, environment markers, extras, URLs, local directories, VCS links, and so forth.

* * *

Basic Package Names
-------------------

```
SomePackage
AnotherLibrary
```

*   You can list package names on each line.
    
*   By default, pip installs the latest published version if no version specifier is given.
    

* * *

Version Specifiers
------------------

```
package==1.2.3       # Exactly version 1.2.3
package>=1.2,<2.0    # Version 1.2 or higher, but below 2.0
package~=1.4.5       # Compatible release: >=1.4.5 and <1.5
package!=1.3.4       # Exclude a specific version
```

*   Common comparison operators:
    
    *   `==`
        
    *   `>=`
        
    *   `>`
        
    *   `<=`
        
    *   `<`
        
    *   `!=`
        
    *   `~=`
        
    *   `===` (for exact string match, rarely used)
        

* * *

Environment Markers
-------------------

You can include environment markers to specify conditions (e.g., Python version, OS, etc.) under which a package should be installed:

```
package; python_version < '3.8'
package==1.2.3; sys_platform == 'win32'
package>=2.0; python_version >= '3.7'
```

*   These markers follow [PEP 508](https://peps.python.org/pep-0508/).
    
*   Common environment marker variables:
    
    *   `sys_platform` (e.g. `'win32'`, `'linux'`, `'darwin'`)
        
    *   `platform_machine`
        
    *   `platform_python_implementation`
        
    *   `python_version`
        
    *   `python_full_version`
        
    *   `os_name`
        
    *   `extra` (used especially with extras in a `setup.py` or `pyproject.toml`)
        

* * *

Extras
------

If a distribution provides “extra” optional dependencies, you can specify them using square brackets:

```
SomePackage[PDF]            # Install SomePackage plus the "PDF" extra
SomePackage[PDF,tests]>=1.0 # Multiple extras and version constraints
```

* * *

Comments
--------

Lines starting with `#` are ignored, as are trailing comments:

```
# This is a comment line
SomePackage  # trailing comment
```

* * *

Constraints Files
-----------------

You can reference another file that provides constraints:

```
-c constraints.txt
```

In `constraints.txt` you might have pinned versions, e.g.:

```
SomePackage==1.3.4
AnotherPackage==2.0.1
```

*   This forces the specified versions in `constraints.txt` to be used, without having to pin them directly in the main requirements file.
    

* * *

Editable Installs (Local Projects)
----------------------------------

You can install a local project in “editable” mode using the `-e` (or `--editable`) flag:

```
-e /path/to/local/project
-e git+https://github.com/SomeUser/SomeProject.git#egg=SomeProject
```

Editable mode means pip will install the project in such a way that changes to the local source code (or the Git clone) will reflect in your environment without reinstallation.

* * *

Direct URLs (PEP 508 URL Dependencies)
--------------------------------------

You can directly reference a package by URL (e.g., a wheel, a tarball, or a zip file):

```
https://example.com/packages/SomePackage-1.2.3-py3-none-any.whl
https://example.com/packages/SomePackage-1.2.3.tar.gz
```

Or, using the `@` syntax from [PEP 508](https://peps.python.org/pep-0508/#url-dependencies):

```
SomePackage @ https://example.com/packages/SomePackage-1.2.3-py3-none-any.whl
```

This installs the package under the name `SomePackage` but fetches it from the provided URL.

* * *

VCS (Version Control System) URLs
---------------------------------

You can specify dependencies that come straight from a Git, Mercurial, or Subversion repository:

*   **Git**:
    
    ```
    git+https://github.com/SomeUser/SomeRepo.git#egg=PackageName
    git+ssh://git@github.com:SomeUser/SomeRepo.git#egg=PackageName
    ```
    
*   **Git with a commit/branch/tag**:
    
    ```
    git+https://github.com/SomeUser/SomeRepo.git@<commit_hash>#egg=PackageName
    git+https://github.com/SomeUser/SomeRepo.git@<branch_or_tag>#egg=PackageName
    ```
    
*   **Editable Git**:
    
    ```
    -e git+https://github.com/SomeUser/SomeRepo.git@main#egg=PackageName
    ```
    
*   **Mercurial**:
    
    ```
    hg+https://hg.example.com/SomeRepo#egg=PackageName
    ```
    
*   **Subversion**:
    
    ```
    svn+svn://svn.example.com/SomeRepo/trunk#egg=PackageName
    ```
    

When using VCS links, you must provide `#egg=PackageName` at the end to tell pip the distribution/package name it should track.

* * *

Local Paths (Non-Editable)
--------------------------

If you have a locally packaged distribution (e.g. a `.whl` or `.tar.gz`) in a directory, you can reference it directly:

```
/path/to/package/dist/SomePackage-1.2.3-py3-none-any.whl
```

or a directory that contains a `setup.py` or `pyproject.toml` (non-editable mode):

```
/path/to/unpacked/dist
```

* * *

Including Other Requirements Files
----------------------------------

You can include another requirements file within the current one using `-r` (or `--requirement`):

```
-r common-requirements.txt
```

This can be helpful if you have multiple layers of dependencies or want to logically group them.

* * *

Handling Options in `requirements.txt`
--------------------------------------

All pip install command-line options can appear in a requirements file:

```
--index-url https://my.custom.index/simple
--extra-index-url https://another.index/simple
--find-links /local/wheels
--no-binary :all:
```

*   These lines must appear before or in between package lines.
    
*   Useful if you want to specify a custom package index or set certain pip behaviors.
    

* * *

Complete Example
----------------

Here’s a sample `requirements.txt` illustrating many of these features:

```text
# Use a custom PyPI index
--index-url https://mycustompypi.example.com/simple
--extra-index-url https://pypi.org/simple
--no-binary :all:

# Include a shared constraints file
-c constraints.txt

# Basic requirement
requests>=2.25.0

# This package only for Python 3.8+ on Linux
numpy==1.21.0; python_version >= "3.8" and sys_platform == "linux"

# Optional extras
matplotlib[tk]>=3.0

# VCS direct install
git+https://github.com/psf/requests.git@v2.26.0#egg=requests

# Editable local source
-e /path/to/my_local_package

# Another requirements file
-r dev-requirements.txt
```

* * *

Further Reference
-----------------

*   [pip User Guide: Requirements Files](https://pip.pypa.io/en/stable/cli/pip_install/#requirements-file-format)
    
*   [PEP 508 – Dependency specification for Python Software Packages](https://peps.python.org/pep-0508/)
    

Those documents go into even more detail and describe advanced usage, constraints, environment markers, and more.
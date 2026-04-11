High-quality documentation is essential for C++ projects, but creating aesthetically pleasing and accessible docs can be challenging. Two popular tools for C++ documentation are **Doxygen** and **Sphinx** (with the **Breathe** and **Exhale** extensions). This guide evaluates Doxygen vs Sphinx in terms of output quality, customization, and C++ support, and then recommends a solution. We provide a step-by-step setup for the chosen tool, including automation with Python scripts and continuous deployment to GitHub Pages. Instructions are included for integration with common build systems (Premake, CMake, and Make).

Comparing Doxygen and Sphinx for C++ Documentation
--------------------------------------------------

**Doxygen:** Doxygen is a long-standing standard for generating C++ API docs from annotated source code[danielsieger.com](https://danielsieger.com/blog/2021/07/07/awesome-doxygen-style.html#:~:text=Doxygen%20is%20the%20de,references). It automatically extracts documentation from comments and provides built-in cross-references for classes, functions, etc. However, Doxygen’s default HTML output is _dated_ in style and can appear cluttered[danielsieger.com](https://danielsieger.com/blog/2021/07/07/awesome-doxygen-style.html#:~:text=Unfortunately%2C%20the%20default%20Doxygen%20HTML,Here%E2%80%99s%20an%20example). By default, pages have a 1990s-like layout with frames or bulky navigation and a lot of boilerplate. Customizing the look is possible (e.g. via HTML/CSS templates), but not straightforward out of the box. Advanced Doxygen features include diagram generation (via Graphviz) and support for Markdown in comments, but complex template-heavy C++ code can sometimes be challenging for it to document clearly[devblogs.microsoft.com](https://devblogs.microsoft.com/cppblog/clear-functional-c-documentation-with-sphinx-breathe-doxygen-cmake/#:~:text=Doxygen%20has%20been%20around%20for,and%20semantic%20markup%20for%20simplicity). On the plus side, Doxygen natively **parses C++ code** and fully understands C++ constructs, so support for C++17/20 features is strong.

**Sphinx (with Breathe & Exhale):** Sphinx is a Python-based documentation generator originally for Python projects, using **reStructuredText** (or Markdown with extensions) to write documentation. On its own, Sphinx does not parse C++ code, but the **Breathe** extension bridges this gap by feeding Sphinx the XML output from Doxygen[waterprogramming.wordpress.com](https://waterprogramming.wordpress.com/2025/01/22/launching-the-waterpaths-documentation-on-github-pages/#:~:text=Breathe%20is%20the%20Sphinx%20plugin,readable%20manner%20and%20generating%20more). In this combo, Doxygen still does the heavy lifting of C++ code parsing, while Sphinx handles the presentation. Sphinx’s output is highly themable and modern-looking by default – it supports many themes and a mobile-friendly, search-enabled interface. In fact, Sphinx docs tend to look more minimal and polished compared to default Doxygen output[devblogs.microsoft.com](https://devblogs.microsoft.com/cppblog/clear-functional-c-documentation-with-sphinx-breathe-doxygen-cmake/#:~:text=The%20docs%20generated%20by%20Sphinx,the%20layout%20of%20the%20pages)[waterprogramming.wordpress.com](https://waterprogramming.wordpress.com/2025/01/22/launching-the-waterpaths-documentation-on-github-pages/#:~:text=you%20may%20have%20noted%2C%20the,used%20to%20document%20Python%20code). Sphinx also excels at writing rich narrative documentation (user guides, tutorials) in addition to API refs, thanks to its flexible markup and extensions. The **Exhale** extension builds on Breathe to automatically generate Sphinx pages for each C++ class, file, etc., mirroring Doxygen’s structured hierarchy[exhale.readthedocs.io](https://exhale.readthedocs.io/#:~:text=Automatic%20C%2B%2B%20library%20API%20documentation,available%20in%20Sphinx%20documented%20projects). This avoids having to manually write Sphinx `.rst` files for each API element. The downside is added complexity: you must configure and run both Doxygen and Sphinx, and the initial setup of Breathe/Exhale requires some effort.

### Output Quality and Aesthetics

![https://devblogs.microsoft.com/cppblog/clear-functional-c-documentation-with-sphinx-breathe-doxygen-cmake/](blob:https://chatgpt.com/7dab6ca4-594d-4288-8e7d-43e1fc940146)

_Figure: Doxygen’s default HTML output for a C++ struct, which includes a lot of boilerplate and unused space[devblogs.microsoft.com](https://devblogs.microsoft.com/cppblog/clear-functional-c-documentation-with-sphinx-breathe-doxygen-cmake/#:~:text=the%20amount%20of%20information%20which,the%20layout%20of%20the%20pages)._ Doxygen’s generated pages tend to be visually noisy and somewhat old-fashioned in style[devblogs.microsoft.com](https://devblogs.microsoft.com/cppblog/clear-functional-c-documentation-with-sphinx-breathe-doxygen-cmake/#:~:text=Doxygen%20has%20been%20around%20for,and%20semantic%20markup%20for%20simplicity). The default templates result in a lot of empty space and a dense layout that can be hard to navigate. Improving the look requires manual tweaking of CSS or using a custom theme. For example, the community-maintained **Doxygen Awesome** theme provides a modern CSS/JS overhaul of Doxygen’s HTML (with better typography, mobile support, and dark mode)[danielsieger.com](https://danielsieger.com/blog/2021/07/07/awesome-doxygen-style.html#:~:text=I%20recently%20came%20across%20a,css%20project%20developed%20by%20%40jothepro)[danielsieger.com](https://danielsieger.com/blog/2021/07/07/awesome-doxygen-style.html#:~:text=If%20you%20are%20looking%20for,option). While such themes significantly improve Doxygen’s appearance (making it cleaner and more modern), this is an extra customization step.

![https://devblogs.microsoft.com/cppblog/clear-functional-c-documentation-with-sphinx-breathe-doxygen-cmake/](blob:https://chatgpt.com/86811cc0-dd7d-46e8-ab44-2619f12f2e0e)

_Figure: The same struct’s documentation generated with Sphinx (using a modern theme). The output is much more compact and attractive[devblogs.microsoft.com](https://devblogs.microsoft.com/cppblog/clear-functional-c-documentation-with-sphinx-breathe-doxygen-cmake/#:~:text=the%20amount%20of%20information%20which,the%20layout%20of%20the%20pages)._ Sphinx, in contrast, can produce attractive documentation with minimal effort by choosing a pre-built theme. For instance, the popular **Read the Docs** theme (`sphinx_rtd_theme`) or **Sphinx Book Theme** can give a clean, responsive design instantly. Sphinx pages are generally more aesthetically pleasing out-of-the-box, with a modern web design and JavaScript-based full-text search. It’s also easy to switch or customize themes in Sphinx[devblogs.microsoft.com](https://devblogs.microsoft.com/cppblog/clear-functional-c-documentation-with-sphinx-breathe-doxygen-cmake/#:~:text=The%20docs%20generated%20by%20Sphinx,the%20layout%20of%20the%20pages) – simply adjust a setting in the config file to completely change the look. This flexibility makes Sphinx a winner in terms of documentation **look and feel**.

### Customization and Flexibility

**Doxygen:** Customization in Doxygen is done through the `Doxyfile` configuration. You can control which content to generate (HTML, LaTeX, man pages, etc.), what to include, and some style options (like enabling a project logo, toggling the navigation tree, etc.). However, fine-grained styling (fonts, colors, layout) requires providing custom CSS/HTML via settings like `HTML_HEADER`, `HTML_FOOTER`, and `HTML_EXTRA_STYLESHEET`[danielsieger.com](https://danielsieger.com/blog/2021/07/07/awesome-doxygen-style.html#:~:text=If%20you%20are%20looking%20for,option). Using `HTML_EXTRA_STYLESHEET` to include a custom CSS (such as _doxygen-awesome.css_) is an effective way to modernize the look[danielsieger.com](https://danielsieger.com/blog/2021/07/07/awesome-doxygen-style.html#:~:text=If%20you%20are%20looking%20for,option). Beyond styling, Doxygen supports some extension via custom commands/aliases in comments, but it’s largely a fixed system geared towards API reference generation. It’s excellent for reference docs, but integrating extensive tutorials or multi-page guides into Doxygen’s output can be cumbersome (Doxygen does allow Markdown pages for additional documentation, but the styling and linking of those pages are still under the Doxygen framework).

**Sphinx:** Sphinx is extremely flexible. The entire documentation structure (sections, subpages, etc.) is in your control via `.rst` (reStructuredText) or Markdown files. You can intermix narrative documentation with auto-generated API docs. Sphinx **extensions** provide a wide array of extra functionality (embedding diagrams, LaTeX math, indexing, etc.). For C++ specifically, Breathe provides directives to insert Doxygen-documented items into Sphinx pages[devblogs.microsoft.com](https://devblogs.microsoft.com/cppblog/clear-functional-c-documentation-with-sphinx-breathe-doxygen-cmake/#:~:text=We%E2%80%99ll%20need%20to%20put%20placeholders,by%20Breathe%2C%20such%20as%20doxygenstruct)[devblogs.microsoft.com](https://devblogs.microsoft.com/cppblog/clear-functional-c-documentation-with-sphinx-breathe-doxygen-cmake/#:~:text=Docs%20%3D%3D%3D%3D). Exhale goes further by automatically creating a set of reStructuredText files that reconstruct Doxygen’s **class and file hierarchies** inside Sphinx[exhale.readthedocs.io](https://exhale.readthedocs.io/#:~:text=Automatic%20C%2B%2B%20library%20API%20documentation,available%20in%20Sphinx%20documented%20projects)[exhale.readthedocs.io](https://exhale.readthedocs.io/#:~:text=You%20would%20use%20Exhale%20if,on%20the%20fly%20every%20time). The result is the best of both worlds: you get the structured API reference of Doxygen _and_ the theming and content flexibility of Sphinx. With Sphinx, it’s also easier to control the **amount of information** shown for each item and to write additional explanatory text or examples. For example, you might have a high-level tutorial in one Sphinx page and then link to the detailed C++ API section generated by Breathe/Exhale. This separation of concerns (narrative vs API) is harder to achieve in pure Doxygen. In summary, Sphinx offers far greater customization: you can choose among many themes, add custom CSS/JS easily, and leverage a rich ecosystem of plugins – making it ideal for creating a beautiful documentation site.

### C++ Support and Completeness

Out of the box, Doxygen has the clear advantage in C++ support – it is built to parse C/C++ (and other languages) and extract documentation. It handles complex C++ features (templates, overloads, etc.) and links symbols appropriately in the generated docs. Sphinx on its own doesn’t know how to parse C++ code, but with **Breathe**, it can utilize Doxygen’s XML output. Breathe essentially acts as a middleman: _“Breathe reads the XML files generated by Doxygen and translates them into a format that Sphinx can render into RST…maintaining the ease of use of Sphinx for writing narrative docs and using user-friendly themes.”_[waterprogramming.wordpress.com](https://waterprogramming.wordpress.com/2025/01/22/launching-the-waterpaths-documentation-on-github-pages/#:~:text=Breathe%20is%20the%20Sphinx%20plugin,readable%20manner%20and%20generating%20more) In practice, this means you run Doxygen first (to generate XML), then Sphinx+Breathe will produce the documentation pages. The combination is quite robust – virtually anything that Doxygen captures about your C++ code can be presented through Sphinx. There are a few edge cases where Breathe might not expose every Doxygen feature, but for most projects this is not a problem[exhale.readthedocs.io](https://exhale.readthedocs.io/#:~:text=Why%20not%20use%20it%3F). Exhale further ensures no piece of the C++ API is missed by automating the creation of Sphinx content for every class, namespace, etc., thereby keeping the docs in sync with the code[exhale.readthedocs.io](https://exhale.readthedocs.io/#:~:text=You%20would%20use%20Exhale%20if,on%20the%20fly%20every%20time). In short, using Doxygen+Sphinx together gives full C++ coverage.

One thing to note is that Doxygen and Breathe both need to be configured consistently. For example, if you enable certain Doxygen options (like HAVE\_DOT for class diagrams), you should ensure the output (graphs, etc.) can be handled or linked in Sphinx. Generally, Breathe supports most Doxygen XML output, and you can always fall back to directly linking the Doxygen-generated HTML for very specialized pages if needed. But for the scope of typical API documentation, Sphinx with Breathe is effectively as capable as Doxygen alone in terms of C++ knowledge.

### Summary of Pros and Cons

*   **Doxygen Pros:** Purpose-built for C++, single-step tool (generate docs directly), no need for additional formatting language, supports various output formats (not just HTML), widely used.
    
*   **Doxygen Cons:** Default HTML is visually outdated[devblogs.microsoft.com](https://devblogs.microsoft.com/cppblog/clear-functional-c-documentation-with-sphinx-breathe-doxygen-cmake/#:~:text=Doxygen%20has%20been%20around%20for,and%20semantic%20markup%20for%20simplicity)[waterprogramming.wordpress.com](https://waterprogramming.wordpress.com/2025/01/22/launching-the-waterpaths-documentation-on-github-pages/#:~:text=statements,see%20some%20examples%20here), theming requires extra work or third-party CSS, less flexible for adding rich narrative content, search UI and mobile view are not as good without customizations.
    
*   **Sphinx Pros:** Highly themable (many beautiful themes available)[devblogs.microsoft.com](https://devblogs.microsoft.com/cppblog/clear-functional-c-documentation-with-sphinx-breathe-doxygen-cmake/#:~:text=The%20docs%20generated%20by%20Sphinx,the%20layout%20of%20the%20pages)[waterprogramming.wordpress.com](https://waterprogramming.wordpress.com/2025/01/22/launching-the-waterpaths-documentation-on-github-pages/#:~:text=you%20may%20have%20noted%2C%20the,used%20to%20document%20Python%20code), supports rich content (tutorials, notes, etc.) in reStructuredText/Markdown, can integrate multiple languages’ docs (via extensions), outputs a modern website feel with built-in search. Great customization via extensions (e.g. syntax highlighting, math, diagrams, etc.).
    
*   **Sphinx Cons:** Requires using reStructuredText/Markdown for writing docs (learning curve if not familiar), and for C++ it **must** be coupled with Doxygen (cannot extract C++ docs by itself). Initial setup of Sphinx+Breathe/Exhale is more involved than running Doxygen alone. Build time might be a bit longer since two tools are run in sequence.
    

**Recommendation:** Given the priority on documentation aesthetics and a high-quality look, **Sphinx with Breathe/Exhale is the recommended approach**. This combination yields a modern, beautiful documentation site and retains excellent C++ support[devblogs.microsoft.com](https://devblogs.microsoft.com/cppblog/clear-functional-c-documentation-with-sphinx-breathe-doxygen-cmake/#:~:text=The%20docs%20generated%20by%20Sphinx,the%20layout%20of%20the%20pages)[waterprogramming.wordpress.com](https://waterprogramming.wordpress.com/2025/01/22/launching-the-waterpaths-documentation-on-github-pages/#:~:text=Breathe%20is%20the%20Sphinx%20plugin,readable%20manner%20and%20generating%20more). The extra setup effort is justified by the end result – a documentation that is easier to navigate and more appealing to users. Doxygen is still an important part of the toolchain (for extracting the docs), but we will use it behind the scenes and let Sphinx handle the presentation. (If one prefers not to use Sphinx, an alternative is to use Doxygen with a custom theme like _doxygen-awesome-css_ to improve its appearance[danielsieger.com](https://danielsieger.com/blog/2021/07/07/awesome-doxygen-style.html#:~:text=If%20you%20are%20looking%20for,option), but you would miss out on Sphinx’s flexibility in writing additional docs.) The rest of this guide will focus on setting up Sphinx+Breathe+Exhale for a C++ project, and automating the generation and deployment of the docs.

Setting Up Sphinx Documentation for a C++ Project
-------------------------------------------------

Follow these steps to set up documentation generation using **Doxygen + Sphinx** (with Breathe and Exhale) for your C++ project. We will assume your project source code is in a directory like `src/` or `include/`, and we’ll create a `docs/` directory for documentation configuration and output.

**1\. Install Dependencies:** Ensure that Doxygen and Python (for Sphinx) are installed on your system. Install **Doxygen** from the official site[devblogs.microsoft.com](https://devblogs.microsoft.com/cppblog/clear-functional-c-documentation-with-sphinx-breathe-doxygen-cmake/#:~:text=this%20needs%20to%20be%20supplied,source%20which%20you%20can%20build) or via your package manager (e.g., `sudo apt install doxygen`). Then install the Sphinx toolchain via pip:

```bash
pip install sphinx breathe exhale sphinx_rtd_theme
```

This will install **Sphinx**, the **Breathe** bridge, **Exhale**, and the Read the Docs theme (you can choose a different theme later). Verify the installations: running `doxygen --version` and `sphinx-build --version` should show that the commands are available.

**2\. Initialize Sphinx in your project:** Sphinx can create a sample project for you. Navigate to your project’s `docs/` folder (create one if not exists) and run the quickstart:

```bash
cd docs
sphinx-quickstart  # or `sphinx-quickstart.exe` on Windows
```

The quickstart will ask some questions. You can accept defaults, but be sure to enter your project name and author when prompted. You may also choose separate source/build directories if you prefer (for clarity, e.g. `docs/source` and `docs/build`). For this guide, assume Sphinx source files (like `conf.py` and `.rst` files) live in `docs/` (or `docs/source/` if separated), and HTML output will be generated to `docs/_build/html` (default) or `docs/build/html`. After running the quickstart, a `conf.py` (configuration) file and an `index.rst` should be created, among others. At this point, you can test Sphinx alone by running `make html` (which calls `sphinx-build`) – it will produce a basic site with a welcome page. We will now customize the configuration to integrate Doxygen.

**3\. Set up a Doxygen configuration:** If you don’t already have a `Doxyfile` for your project, generate one by running `doxygen -g` (this creates a default `Doxyfile` in the current directory). Move this file into the `docs/` directory for convenience. Open the `Doxyfile` in a text editor and **configure at least the following settings**:

*   **PROJECT\_NAME:** Set this to your project’s name (appears in generated docs).
    
*   **OUTPUT\_DIRECTORY:** Set to `docs/doxygen` (for example) so that Doxygen’s output files go to the docs folder. Keeping outputs in `docs/` makes it easier to manage and deploy.
    
*   **GENERATE\_HTML:** Set to `NO` if you only want to use Sphinx for HTML. (We don’t need Doxygen’s HTML when using Sphinx, but we do need Doxygen’s XML.)
    
*   **GENERATE\_XML:** Set this to `YES`[devblogs.microsoft.com](https://devblogs.microsoft.com/cppblog/clear-functional-c-documentation-with-sphinx-breathe-doxygen-cmake/#:~:text=Breathe%20uses%20Doxygen%E2%80%99s%20XML%20output%2C,need%20to%20turn%20it%20on) – this is crucial, as Breathe will read the XML output. Specify **XML\_OUTPUT** (optional) to a convenient subfolder name like `xml` (default is `xml`).
    
*   **INPUT:** Set this to the paths of your source code. For example, `INPUT = ../src ../include`. You can list multiple directories/files that contain documentation comments.
    
*   **FILE\_PATTERNS:** Ensure it includes your file extensions (e.g., `.h, .hpp, .cpp` etc.) so Doxygen knows to scan those files.
    
*   **EXTRACT\_PRIVATE:** (Optional) set to YES if you want to include private class members in the docs.
    
*   **USE\_MDFILE\_AS\_MAINPAGE:** (Optional) if you have a Markdown file (like a README) to serve as the main page.
    
*   **STRIP\_FROM\_PATH:** (Optional) to trim common path prefixes from file names in output.
    

Here’s an excerpt of important Doxyfile settings to change:

```ini
PROJECT_NAME           = MyProject
OUTPUT_DIRECTORY       = docs/doxygen
GENERATE_HTML          = NO       # We'll use Sphinx for HTML
GENERATE_XML           = YES
XML_OUTPUT             = xml      # XML files will be in docs/doxygen/xml/
INPUT                  = ../src ../include
FILE_PATTERNS          = *.cpp *.h *.hpp
EXTRACT_PRIVATE        = NO       # Yes to include private members
```

After editing, run `doxygen docs/Doxyfile` to test it. It should scan your code and produce XML files in `docs/doxygen/xml/` (and possibly other outputs like LaTeX if not disabled). We’ll integrate this with Sphinx next.

**4\. Configure Sphinx to use Breathe and Exhale:** Open the Sphinx `conf.py` in the `docs/` directory. We need to enable the Breathe and Exhale extensions and point them to Doxygen’s output. Make the following changes in `conf.py`:

*   **Extensions:** Add `'breathe'` and `'exhale'` to the `extensions` list. (Also add any theme extensions if needed, e.g. `'sphinx_rtd_theme'` for Read the Docs theme.)
    
*   **Breathe Configuration:** Define a dictionary mapping project names to the path of Doxygen’s XML output. For example: `breathe_projects = {"MyProject": "./doxygen/xml"}` assuming `conf.py` is in `docs/` and XML is in `docs/doxygen/xml`. Also set `breathe_default_project = "MyProject"`.
    
*   **Exhale Configuration:** Define `exhale_args` to tell Exhale where to generate API pages and how to structure them. At minimum, set:
    
    *   `containmentFolder` – a subfolder (relative to Sphinx source) where Exhale will write the API reST files (e.g. `"./api"` to create a docs/api/ folder).
        
    *   `rootFileName` – the name of the root API page file (e.g. `"library_root.rst"`).
        
    *   `rootFileTitle` – the title for the root API page (e.g. `"API Reference"` or your project name + "API").
        
    *   `doxygenStripFromPath` – a path prefix to strip from file paths (to make file names shorter in docs, e.g. `"../.."` to remove the leading path above your src directory).
        
    *   Optionally, `createTreeView` set to `True` if you want a collapsible tree menu for the API (requires a theme that supports it, like certain Bootstrap-based themes).
        
*   **Primary Domain:** Set `primary_domain = 'cpp'` so that Sphinx treats C++ as the main language for roles and directives. Also set `highlight_language = 'cpp'` for code highlighting in C++.
    
*   **HTML Theme:** Set your desired HTML theme, e.g. `html_theme = "sphinx_rtd_theme"` for Read the Docs theme (make sure you pip installed it). You can also configure theme options or custom static files if needed.
    

Putting it together, your `conf.py` might include lines like this (simplified example):

```python
# -- Extensions for Sphinx -------------------------------------------------
extensions = [
    'breathe',
    'exhale',
    'sphinx_rtd_theme'   # using Read the Docs theme as an example
]

# -- Breathe Configuration -------------------------------------------------
breathe_projects = {
    "MyProject": "./doxygen/xml"
}
breathe_default_project = "MyProject"

# -- Exhale Configuration --------------------------------------------------
exhale_args = {
    "containmentFolder": "./api",
    "rootFileName": "library_root.rst",
    "rootFileTitle": "API Reference",
    "doxygenStripFromPath": "../..",  # adjust path as needed
    "createTreeView": True
}
primary_domain = 'cpp'
highlight_language = 'cpp'

# -- Options for HTML output -------------------------------------------------
html_theme = "sphinx_rtd_theme"
```

After saving `conf.py`, Sphinx is now configured to use Breathe and Exhale. The `exhale_args` above will cause Exhale to generate an `api/` folder in the build process containing reStructuredText files for each class, namespace, etc., with a root file `library_root.rst` that serves as an index of the API.

**5\. Connect the documentation pages:** We need to include the generated API documentation in our Sphinx TOC so it appears in the site. Open `index.rst` (the main documentation page) and add a reference to Exhale’s root document. For example, at the bottom of `index.rst`, include:

```restructuredtext
.. toctree::
   :maxdepth: 2
   :caption: Contents:

   api/library_root
```

This will insert the API reference (all the content under `api/` generated by Exhale) into the Sphinx site’s table of contents. The `library_root` page (with title "API Reference") will contain an organized list of all classes, files, namespaces, etc., thanks to Exhale. You can adjust `:maxdepth:` or the caption as needed. If you have other documentation pages (e.g. a general introduction or user guides), list them in the toctree as well above or below the API reference.

_Without Exhale:_ If you choose not to use Exhale, you would instead manually use Breathe directives in your `.rst` files to include API information (for example, using `.. doxygenclass:: MyClass` or Breathe’s `.. doxygenindex::` to pull in entire index). Breathe also provides a `breathe-apidoc` tool similar to Sphinx’s `apidoc` to generate stub `.rst` files from Doxygen XML[exhale.readthedocs.io](https://exhale.readthedocs.io/#:~:text=It%20may%20be%20more%20involved,to%20get%20your%20documentation%20displayed). However, Exhale largely automates this, so we recommend it for convenience.

**6\. Build the documentation:** Now that everything is configured, you can generate the docs. It will be a two-step process (Doxygen then Sphinx):

*   First run Doxygen to produce/update the XML:
    
    ```bash
    doxygen docs/Doxyfile
    ```
    
    Ensure this runs without errors. It should output files into `docs/doxygen/xml/`.
    
*   Then run Sphinx to build the HTML:
    
    ```bash
    sphinx-build -b html docs/ docs/_build/html
    ```
    
    (Adjust paths if you have separate source directory, e.g. `sphinx-build -b html docs/source docs/build/html`.) You can also use the makefile Sphinx provided: `make html` from the `docs/` directory (on Windows use `make.bat html`). Sphinx will read your reST files, use Breathe to pull in Doxygen XML data, and Exhale will generate the API pages on the fly. If everything is set up correctly, you should see it writing out pages for your classes, etc., during the build.
    

When done, open the resulting `index.html` (in `docs/_build/html/` or `docs/build/html/`) in a browser. You should see a nicely formatted site with your project’s documentation. The index page should list the “API Reference” (or whatever you titled it) and other sections. Navigate through and verify that classes, functions, and other API elements are documented. Congratulations – you have a beautiful documentation site locally!

Automating Documentation Generation and Deployment
--------------------------------------------------

Manually running Doxygen and Sphinx and then publishing the files can become tedious. We want to **fully automate** this process both for local convenience and as part of Continuous Integration (CI) so that any new code changes can trigger a documentation update on GitHub Pages. We will set up a Python script to generate and deploy the docs, and also integrate it with GitHub Actions for CI/CD. The end goal: whenever you push to the main branch (or whenever you desire, e.g. on a version tag), the docs will rebuild and publish to GitHub Pages automatically.

### Python Script for Local Automation

You can create a Python script (e.g. `deploy_docs.py`) at the root of your repository to streamline the doc generation. This script will run Doxygen and Sphinx, then push the results to the `gh-pages` branch of your repo (which is used by GitHub Pages). Using a script means you or the CI can use the same code path to deploy. Below is an example of what such a script might look like:

```python
import os
import subprocess
import sys

# Paths and configurations
DOXYFILE_PATH = os.path.join("docs", "Doxyfile")
SPHINX_SRC = os.path.join("docs")          # Sphinx source (conf.py location)
SPHINX_HTML = os.path.join("docs", "_build", "html")  # HTML output folder

# 1. Run Doxygen to generate XML
ret = subprocess.run(["doxygen", DOXYFILE_PATH], check=False)
if ret.returncode != 0:
    sys.exit(f"Doxygen failed with code {ret.returncode}")

# 2. Run Sphinx to generate HTML
ret = subprocess.run(["sphinx-build", "-b", "html", SPHINX_SRC, SPHINX_HTML], check=False)
if ret.returncode != 0:
    sys.exit(f"Sphinx build failed with code {ret.returncode}")

# 3. Deploy to GitHub Pages:
# Initialize gh-pages branch in docs/_build/html and push (using ghp-import for simplicity)
try:
    import ghp_import
except ImportError:
    # Install ghp-import if not available
    subprocess.run([sys.executable, "-m", "pip", "install", "ghp-import"], check=True)
import ghp_import
ghp_import.ghp_import(SPHINX_HTML, push=True, cname=None)
```

This script uses the `ghp-import` utility to push the HTML in `docs/_build/html` to the `gh-pages` branch. The `ghp_import.ghp_import(..., push=True)` call will create/overwrite the gh-pages branch (in the local git repo) and push to origin. You may need to configure `ghp-import` with your repo URL or ensure you have the proper permissions (in CI, the GitHub token can be used, as shown later). Alternatively, you could replace this step with manual Git commands (initializing a repo in the HTML folder, committing, and pushing to `gh-pages`). The idea is that running `deploy_docs.py` will end up publishing the latest docs to GitHub Pages.

**Usage:** Run `python deploy_docs.py` whenever you want to update the docs. For local use, you should have push access to the repository (and ideally do this on a clean working tree). In CI, we’ll run the same script (with the CI-provided token) to update pages automatically.

### Continuous Deployment with GitHub Actions

To set up continuous deployment of docs on GitHub Pages, we use **GitHub Actions**. We’ll create a workflow YAML file that triggers on each push (or on certain branches) to build the docs and deploy. Ensure that GitHub Pages is enabled for your repository (in the repo Settings -> Pages, set it to use the `gh-pages` branch or `docs/` folder on main as appropriate). For this guide, we’ll use the `gh-pages` branch approach, which is common for CI deployments.

Create a file `.github/workflows/docs.yml` in your repository with the following content (comments added for explanation):

```yaml
name: Build and Deploy Docs
on:
  push:
    branches: [ main ]    # Run on each push to main (adjust branch as needed)

jobs:
  docs:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
        with:
          persist-credentials: false   # we'll use a token for pushing

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.9'

      - name: Install dependencies
        run: |
          sudo apt-get update && sudo apt-get install -y doxygen graphviz
          pip install sphinx breathe exhale sphinx_rtd_theme ghp-import

      - name: Build documentation
        run: |
          doxygen docs/Doxyfile
          sphinx-build -b html docs docs/_build/html

      - name: Deploy to GitHub Pages
        run: |
          ghp-import -n -p docs/_build/html
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

Let’s break down what this does:

*   It triggers on pushes to the `main` branch.
    
*   It checks out the code (without using the default credentials, because we’ll use the token explicitly for deployment).
    
*   It sets up Python 3.9 (you can use any version >=3.6).
    
*   **Install dependencies:** We install Doxygen (and `graphviz` in case you use Doxygen for diagrams) via apt, and the Python packages via pip (including ghp-import for deployment). This ensures the runner has everything needed.
    
*   **Build documentation:** This runs the same commands we tested locally – generating Doxygen XML and then Sphinx HTML. If the `Doxyfile` or Sphinx config is misconfigured, this step may fail, which will stop the workflow (you’d see the error in the Actions logs). Make sure the paths are correct (in this example, we assume `docs/` contains both `Doxyfile` and Sphinx’s `conf.py`). Adjust if your structure is different (e.g., `doxygen docs/Doxyfile` and `sphinx-build -b html docs/source docs/build/html` if using separate source directory).
    
*   **Deploy to GitHub Pages:** This uses `ghp-import` to push the HTML. The flags used: `-n` to **disable Jekyll** on GitHub Pages (adding a `.nojekyll` file, since Sphinx site doesn’t need Jekyll), and `-p` to push to origin. We rely on the `${{ secrets.GITHUB_TOKEN }}` which is GitHub’s automatic token for the action – `ghp-import` will pick it up to authenticate (the `env` line passes it). Alternatively, you could use the official `peaceiris/actions-gh-pages@v3` action for deployment, but `ghp-import` is straightforward for this purpose.
    

After adding this workflow, commit and push it. On the next push to main (including this one), the GitHub Actions runner will execute these steps. If successful, it will push a commit to the `gh-pages` branch of your repo containing the built documentation. The first time, you might need to go to your repository’s Settings -> Pages and ensure it’s set to deploy from the `gh-pages` branch (GitHub might do this automatically when it sees a gh-pages branch). You only need to configure that once.

**Tip:** You might want to restrict the workflow to run only when documentation changes, or maybe only on release tags. You can adjust the trigger (`on:`) to suit your workflow (for example, trigger on pushes to a `docs` folder, or on publishing a new release). The above is a simple setup that ensures docs are updated on every commit to main.

From now on, your documentation process is automated. Developers can still run `make html` (or the Python script) locally to preview changes, and the CI will deploy the official docs. This ensures your GitHub Pages site is always up-to-date with the latest documentation of your C++ project.

Integrating Documentation with Build Systems
--------------------------------------------

Depending on your development workflow, you might want to tie documentation generation into your build system so that, for example, `make docs` or a similar command produces the docs, or to have CMake generate docs as a target. Below are brief suggestions for Premake, CMake, and Make integration. These are optional – with the above automation, you might just let CI handle docs – but they can be useful for developers.

### Premake Integration (Premake5)

Premake (a Lua-based build configuration tool) doesn’t have built-in Doxygen support, but you can extend it. One approach is to define a **custom action** in the `premake5.lua` script. Premake’s `newaction` API allows adding new command-line actions[premake.github.io](https://premake.github.io/docs/Command-Line-Arguments/#:~:text=Command%20Line%20Arguments%20,the%20newaction%20and%20newoption%20functions). For example, you can add a “docs” action:

```lua
-- premake5.lua
newaction {
   trigger     = "docs",
   description = "Generate documentation using Doxygen and Sphinx",
   execute     = function()
      os.execute("doxygen docs/Doxyfile")
      os.execute("sphinx-build -b html docs docs/_build/html")
      print("Documentation generated in docs/_build/html")
   end
}
```

With this in your premake script, a developer can run `premake5 docs` to generate the documentation (assuming premake is installed and your premake script is in the project root). This will simply call the commands we discussed. You can refine the paths as needed or even call the Python automation script from Premake (using `os.execute("python deploy_docs.py")`). This approach keeps documentation generation as part of your project’s developer tools. It won’t automatically deploy to GitHub Pages – it’s mainly for local use (deployment is handled by CI as above).

### CMake Integration

CMake is quite friendly to Doxygen integration and can also call Sphinx. A common strategy is to create a custom CMake target for docs. You can use the built-in `FindDoxygen` module to locate Doxygen and even use the macro `doxygen_add_docs()` (available in recent CMake versions) to simplify some steps[aliceo2group.github.io](https://aliceo2group.github.io/advanced/doxygen.html#:~:text=Doxygen%20,doxygen_add_docs%20function%20to%20generate)[cmake.org](https://cmake.org/cmake/help/latest/module/FindDoxygen.html#:~:text=,DOXYGEN_GENERATE_HTML%20NO). For full control, you can do something like this in your top-level `CMakeLists.txt` (or a `docs/CMakeLists.txt`):

```cmake
find_package(Doxygen REQUIRED)
# Optionally, configure the Doxyfile by substituting variables:
#set(DOXYGEN_INPUT_DIR "${CMAKE_SOURCE_DIR}/src")
#configure_file(${CMAKE_SOURCE_DIR}/docs/Doxyfile.in ${CMAKE_BINARY_DIR}/Doxyfile @ONLY)

find_package(Sphinx REQUIRED)  # if you wrote a FindSphinx.cmake as in the blog example

# Doxygen generation step
add_custom_command(OUTPUT ${CMAKE_CURRENT_BINARY_DIR}/doxygen/xml/index.xml
    COMMAND ${DOXYGEN_EXECUTABLE} docs/Doxyfile
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
    DEPENDS ${CMAKE_SOURCE_DIR}/docs/Doxyfile ${MY_PROJECT_HEADERS}
    COMMENT "Generating Doxygen XML"
)
add_custom_target(doxygen-docs ALL DEPENDS ${CMAKE_CURRENT_BINARY_DIR}/doxygen/xml/index.xml)

# Sphinx generation step (depends on Doxygen)
add_custom_command(OUTPUT ${CMAKE_CURRENT_BINARY_DIR}/sphinx/index.html
    COMMAND sphinx-build -b html docs docs/_build/html
            -Dbreathe_projects.MyProject=${CMAKE_CURRENT_BINARY_DIR}/doxygen/xml
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
    DEPENDS doxygen-docs ${CMAKE_SOURCE_DIR}/docs/conf.py ${CMAKE_SOURCE_DIR}/docs/index.rst
    COMMENT "Generating HTML documentation with Sphinx"
)
add_custom_target(sphinx-docs ALL DEPENDS ${CMAKE_CURRENT_BINARY_DIR}/sphinx/index.html)
```

In this snippet, we define a target `doxygen-docs` that runs Doxygen (producing XML), and a target `sphinx-docs` that runs Sphinx, depending on the Doxygen output. The `-D breathe_projects.MyProject=...` part passes the Doxygen XML path to Sphinx on the command line[devblogs.microsoft.com](https://devblogs.microsoft.com/cppblog/clear-functional-c-documentation-with-sphinx-breathe-doxygen-cmake/#:~:text=add_custom_target%28Sphinx%20ALL%20COMMAND%20%24%7BSPHINX_EXECUTABLE%7D%20,Generating%20documentation%20with%20Sphinx)[devblogs.microsoft.com](https://devblogs.microsoft.com/cppblog/clear-functional-c-documentation-with-sphinx-breathe-doxygen-cmake/#:~:text=,Generating%20documentation%20with%20Sphinx) (this assumes your Sphinx `conf.py` uses that variable; alternatively you could hardcode the path in conf.py or set an env var). We also list dependencies so that CMake knows when to rerun these (here `${MY_PROJECT_HEADERS}` would be a list of header files we gather to trigger Doxygen rebuild if any change). The result is that running `make sphinx-docs` (or just building `ALL` if marked as ALL) will produce the docs. This approach is detailed in a Microsoft C++ team blog[devblogs.microsoft.com](https://devblogs.microsoft.com/cppblog/clear-functional-c-documentation-with-sphinx-breathe-doxygen-cmake/#:~:text=,VERBATIM)[devblogs.microsoft.com](https://devblogs.microsoft.com/cppblog/clear-functional-c-documentation-with-sphinx-breathe-doxygen-cmake/#:~:text=%23%20,to%20find%20the%20Doxygen%20output) – they show how to configure the dependencies to avoid unnecessary rebuilds. You can refine it as needed, for example only build docs on demand (omit `ALL` from the custom targets) so it doesn’t run every build.

If you prefer using `doxygen_add_docs()` (which encapsulates some of this), you could call:

```cmake
doxygen_add_docs(doxygen-docs ${PROJECT_SOURCE_DIR}/include COMMENT "Generate Doxygen docs")
```

This will auto-generate a target that runs Doxygen for the given path(s) with some default settings (you still need a Doxyfile present, and you might need to set some CMake variables to control Doxyfile options via `DOXYGEN_*` variables[cmake.org](https://cmake.org/cmake/help/latest/module/FindDoxygen.html#:~:text=variables%20before%20calling%20,full%20list%20of%20supported%20configuration)[cmake.org](https://cmake.org/cmake/help/latest/module/FindDoxygen.html#:~:text=relevant%20variables%20before%20calling%20,For%20example)). You’d then add a separate custom target for Sphinx as above.

### Make (GNU Make) Integration

If you are using a raw Makefile (for a simpler C++ project without CMake/Premake), you can add a documentation rule. For example:

```make
docs:
	@echo "Generating Doxygen docs..."
	doxygen docs/Doxyfile
	@echo "Generating Sphinx docs..."
	sphinx-build -b html docs docs/_build/html
	@echo "Documentation generated at docs/_build/html"
```

This assumes the `docs/` directory has your Doxyfile and Sphinx conf.py. Now a `make docs` will produce the HTML docs. You might also include a `publish` step depending on your needs (though it’s often safer to let CI handle publishing to avoid accidentally overwriting gh-pages from a developer machine).

### Summary of Build Integration

Integrating documentation generation with the build can be convenient for developers to preview docs. Premake allows adding a custom action as shown. CMake can use custom targets or its Doxygen module to tie into the build graph (the example above ensures Sphinx runs after Doxygen, and only when needed)[devblogs.microsoft.com](https://devblogs.microsoft.com/cppblog/clear-functional-c-documentation-with-sphinx-breathe-doxygen-cmake/#:~:text=,VERBATIM)[devblogs.microsoft.com](https://devblogs.microsoft.com/cppblog/clear-functional-c-documentation-with-sphinx-breathe-doxygen-cmake/#:~:text=%23%20,to%20find%20the%20Doxygen%20output). Makefiles can call the tools directly. In all cases, ensure the tools (Doxygen, Sphinx, etc.) are installed in the environment where the build runs. For CI, you might still rely on the separate GitHub Actions workflow as described, but it’s not uncommon to hook a `docs` target in CMake that developers can run, and perhaps have the CI job simply call that target.

Conclusion
----------

By leveraging **Doxygen** for C++ code parsing and **Sphinx** (with **Breathe** and **Exhale**) for presentation, you can create a documentation website for your C++ project that is both comprehensive and visually appealing. We evaluated the two approaches: while Doxygen alone can generate API docs, the Sphinx route offers superior aesthetics and customization[devblogs.microsoft.com](https://devblogs.microsoft.com/cppblog/clear-functional-c-documentation-with-sphinx-breathe-doxygen-cmake/#:~:text=The%20docs%20generated%20by%20Sphinx,the%20layout%20of%20the%20pages)[waterprogramming.wordpress.com](https://waterprogramming.wordpress.com/2025/01/22/launching-the-waterpaths-documentation-on-github-pages/#:~:text=your%20documentation%20%28i,see%20some%20examples%20here). The step-by-step setup above helps you configure the toolchain. With the provided Python script and GitHub Actions workflow, documentation generation and deployment to **GitHub Pages** becomes fully automated. This means your docs will stay up-to-date with minimal effort, and developers/contributors can focus on writing good comments and docs content rather than fiddling with publishing.

By integrating with build systems (Premake/CMake/Make), you further streamline the process of generating docs during development or release cycles. The result is a professional documentation site for your C++ project that can greatly enhance its usability and appeal to users. Now you can enjoy a continuous documentation workflow – write code and comments, push to GitHub, and let the automation produce beautiful docs for you and your users to explore. Happy documenting!

**Sources:** The approach and configurations are informed by official tool documentation and community best practices. Key references include the Microsoft C++ Team Blog on Sphinx+Breathe+Doxygen[devblogs.microsoft.com](https://devblogs.microsoft.com/cppblog/clear-functional-c-documentation-with-sphinx-breathe-doxygen-cmake/#:~:text=Doxygen%20has%20been%20around%20for,and%20semantic%20markup%20for%20simplicity)[devblogs.microsoft.com](https://devblogs.microsoft.com/cppblog/clear-functional-c-documentation-with-sphinx-breathe-doxygen-cmake/#:~:text=The%20docs%20generated%20by%20Sphinx,the%20layout%20of%20the%20pages), the WaterPaths documentation guide[waterprogramming.wordpress.com](https://waterprogramming.wordpress.com/2025/01/22/launching-the-waterpaths-documentation-on-github-pages/#:~:text=statements,see%20some%20examples%20here)[waterprogramming.wordpress.com](https://waterprogramming.wordpress.com/2025/01/22/launching-the-waterpaths-documentation-on-github-pages/#:~:text=you%20may%20have%20noted%2C%20the,used%20to%20document%20Python%20code), and the Exhale documentation[exhale.readthedocs.io](https://exhale.readthedocs.io/#:~:text=Automatic%20C%2B%2B%20library%20API%20documentation,available%20in%20Sphinx%20documented%20projects)[exhale.readthedocs.io](https://exhale.readthedocs.io/#:~:text=You%20would%20use%20Exhale%20if,on%20the%20fly%20every%20time). These resources delve deeper into why Sphinx offers a modern documentation style and how Breathe/Exhale tie into Doxygen for C++ projects. Additional references are provided inline for specific points.

## Prompt:
Automated Beautiful Documentation for C++ with GitHub Pages

Generating Beautiful C++ Documentation (Doxygen vs Sphinx) with GitHub Pages Automation
=======================================================================================

Introduction
------------

High-quality documentation is essential for C++ projects, but creating aesthetically pleasing and accessible docs can be challenging. Two popular tools for C++ documentation are **Doxygen** and **Sphinx** (with the **Breathe** and **Exhale** extensions). This guide evaluates Doxygen vs Sphinx in terms of output quality, customization, and C++ support, and then recommends a solution. We provide a step-by-step setup for the chosen tool, including automation with Python scripts and continuous deployment to GitHub Pages. Instructions are included for integration with common build systems (Premake, CMake, and Make).

Comparing Doxygen and Sphinx for C++ Documentation
--------------------------------------------------

**Doxygen:** Doxygen is a long-standing standard for generating C++ API docs from annotated source code[danielsieger.com](https://danielsieger.com/blog/2021/07/07/awesome-doxygen-style.html#:~:text=Doxygen%20is%20the%20de,references). It automatically extracts documentation from comments and provides built-in cross-references for classes, functions, etc. However, Doxygen’s default HTML output is _dated_ in style and can appear cluttered[danielsieger.com](https://danielsieger.com/blog/2021/07/07/awesome-doxygen-style.html#:~:text=Unfortunately%2C%20the%20default%20Doxygen%20HTML,Here%E2%80%99s%20an%20example). By default, pages have a 1990s-like layout with frames or bulky navigation and a lot of boilerplate. Customizing the look is possible (e.g. via HTML/CSS templates), but not straightforward out of the box. Advanced Doxygen features include diagram generation (via Graphviz) and support for Markdown in comments, but complex template-heavy C++ code can sometimes be challenging for it to document clearly[devblogs.microsoft.com](https://devblogs.microsoft.com/cppblog/clear-functional-c-documentation-with-sphinx-breathe-doxygen-cmake/#:~:text=Doxygen%20has%20been%20around%20for,and%20semantic%20markup%20for%20simplicity). On the plus side, Doxygen natively **parses C++ code** and fully understands C++ constructs, so support for C++17/20 features is strong.

**Sphinx (with Breathe & Exhale):** Sphinx is a Python-based documentation generator originally for Python projects, using **reStructuredText** (or Markdown with extensions) to write documentation. On its own, Sphinx does not parse C++ code, but the **Breathe** extension bridges this gap by feeding Sphinx the XML output from Doxygen[waterprogramming.wordpress.com](https://waterprogramming.wordpress.com/2025/01/22/launching-the-waterpaths-documentation-on-github-pages/#:~:text=Breathe%20is%20the%20Sphinx%20plugin,readable%20manner%20and%20generating%20more). In this combo, Doxygen still does the heavy lifting of C++ code parsing, while Sphinx handles the presentation. Sphinx’s output is highly themable and modern-looking by default – it supports many themes and a mobile-friendly, search-enabled interface. In fact, Sphinx docs tend to look more minimal and polished compared to default Doxygen output[devblogs.microsoft.com](https://devblogs.microsoft.com/cppblog/clear-functional-c-documentation-with-sphinx-breathe-doxygen-cmake/#:~:text=The%20docs%20generated%20by%20Sphinx,the%20layout%20of%20the%20pages)[waterprogramming.wordpress.com](https://waterprogramming.wordpress.com/2025/01/22/launching-the-waterpaths-documentation-on-github-pages/#:~:text=you%20may%20have%20noted%2C%20the,used%20to%20document%20Python%20code). Sphinx also excels at writing rich narrative documentation (user guides, tutorials) in addition to API refs, thanks to its flexible markup and extensions. The **Exhale** extension builds on Breathe to automatically generate Sphinx pages for each C++ class, file, etc., mirroring Doxygen’s structured hierarchy[exhale.readthedocs.io](https://exhale.readthedocs.io/#:~:text=Automatic%20C%2B%2B%20library%20API%20documentation,available%20in%20Sphinx%20documented%20projects). This avoids having to manually write Sphinx `.rst` files for each API element. The downside is added complexity: you must configure and run both Doxygen and Sphinx, and the initial setup of Breathe/Exhale requires some effort.

### Output Quality and Aesthetics

![https://devblogs.microsoft.com/cppblog/clear-functional-c-documentation-with-sphinx-breathe-doxygen-cmake/](blob:https://chatgpt.com/7dab6ca4-594d-4288-8e7d-43e1fc940146)

_Figure: Doxygen’s default HTML output for a C++ struct, which includes a lot of boilerplate and unused space[devblogs.microsoft.com](https://devblogs.microsoft.com/cppblog/clear-functional-c-documentation-with-sphinx-breathe-doxygen-cmake/#:~:text=the%20amount%20of%20information%20which,the%20layout%20of%20the%20pages)._ Doxygen’s generated pages tend to be visually noisy and somewhat old-fashioned in style[devblogs.microsoft.com](https://devblogs.microsoft.com/cppblog/clear-functional-c-documentation-with-sphinx-breathe-doxygen-cmake/#:~:text=Doxygen%20has%20been%20around%20for,and%20semantic%20markup%20for%20simplicity). The default templates result in a lot of empty space and a dense layout that can be hard to navigate. Improving the look requires manual tweaking of CSS or using a custom theme. For example, the community-maintained **Doxygen Awesome** theme provides a modern CSS/JS overhaul of Doxygen’s HTML (with better typography, mobile support, and dark mode)[danielsieger.com](https://danielsieger.com/blog/2021/07/07/awesome-doxygen-style.html#:~:text=I%20recently%20came%20across%20a,css%20project%20developed%20by%20%40jothepro)[danielsieger.com](https://danielsieger.com/blog/2021/07/07/awesome-doxygen-style.html#:~:text=If%20you%20are%20looking%20for,option). While such themes significantly improve Doxygen’s appearance (making it cleaner and more modern), this is an extra customization step.

![https://devblogs.microsoft.com/cppblog/clear-functional-c-documentation-with-sphinx-breathe-doxygen-cmake/](blob:https://chatgpt.com/86811cc0-dd7d-46e8-ab44-2619f12f2e0e)

_Figure: The same struct’s documentation generated with Sphinx (using a modern theme). The output is much more compact and attractive[devblogs.microsoft.com](https://devblogs.microsoft.com/cppblog/clear-functional-c-documentation-with-sphinx-breathe-doxygen-cmake/#:~:text=the%20amount%20of%20information%20which,the%20layout%20of%20the%20pages)._ Sphinx, in contrast, can produce attractive documentation with minimal effort by choosing a pre-built theme. For instance, the popular **Read the Docs** theme (`sphinx_rtd_theme`) or **Sphinx Book Theme** can give a clean, responsive design instantly. Sphinx pages are generally more aesthetically pleasing out-of-the-box, with a modern web design and JavaScript-based full-text search. It’s also easy to switch or customize themes in Sphinx[devblogs.microsoft.com](https://devblogs.microsoft.com/cppblog/clear-functional-c-documentation-with-sphinx-breathe-doxygen-cmake/#:~:text=The%20docs%20generated%20by%20Sphinx,the%20layout%20of%20the%20pages) – simply adjust a setting in the config file to completely change the look. This flexibility makes Sphinx a winner in terms of documentation **look and feel**.

### Customization and Flexibility

**Doxygen:** Customization in Doxygen is done through the `Doxyfile` configuration. You can control which content to generate (HTML, LaTeX, man pages, etc.), what to include, and some style options (like enabling a project logo, toggling the navigation tree, etc.). However, fine-grained styling (fonts, colors, layout) requires providing custom CSS/HTML via settings like `HTML_HEADER`, `HTML_FOOTER`, and `HTML_EXTRA_STYLESHEET`[danielsieger.com](https://danielsieger.com/blog/2021/07/07/awesome-doxygen-style.html#:~:text=If%20you%20are%20looking%20for,option). Using `HTML_EXTRA_STYLESHEET` to include a custom CSS (such as _doxygen-awesome.css_) is an effective way to modernize the look[danielsieger.com](https://danielsieger.com/blog/2021/07/07/awesome-doxygen-style.html#:~:text=If%20you%20are%20looking%20for,option). Beyond styling, Doxygen supports some extension via custom commands/aliases in comments, but it’s largely a fixed system geared towards API reference generation. It’s excellent for reference docs, but integrating extensive tutorials or multi-page guides into Doxygen’s output can be cumbersome (Doxygen does allow Markdown pages for additional documentation, but the styling and linking of those pages are still under the Doxygen framework).

**Sphinx:** Sphinx is extremely flexible. The entire documentation structure (sections, subpages, etc.) is in your control via `.rst` (reStructuredText) or Markdown files. You can intermix narrative documentation with auto-generated API docs. Sphinx **extensions** provide a wide array of extra functionality (embedding diagrams, LaTeX math, indexing, etc.). For C++ specifically, Breathe provides directives to insert Doxygen-documented items into Sphinx pages[devblogs.microsoft.com](https://devblogs.microsoft.com/cppblog/clear-functional-c-documentation-with-sphinx-breathe-doxygen-cmake/#:~:text=We%E2%80%99ll%20need%20to%20put%20placeholders,by%20Breathe%2C%20such%20as%20doxygenstruct)[devblogs.microsoft.com](https://devblogs.microsoft.com/cppblog/clear-functional-c-documentation-with-sphinx-breathe-doxygen-cmake/#:~:text=Docs%20%3D%3D%3D%3D). Exhale goes further by automatically creating a set of reStructuredText files that reconstruct Doxygen’s **class and file hierarchies** inside Sphinx[exhale.readthedocs.io](https://exhale.readthedocs.io/#:~:text=Automatic%20C%2B%2B%20library%20API%20documentation,available%20in%20Sphinx%20documented%20projects)[exhale.readthedocs.io](https://exhale.readthedocs.io/#:~:text=You%20would%20use%20Exhale%20if,on%20the%20fly%20every%20time). The result is the best of both worlds: you get the structured API reference of Doxygen _and_ the theming and content flexibility of Sphinx. With Sphinx, it’s also easier to control the **amount of information** shown for each item and to write additional explanatory text or examples. For example, you might have a high-level tutorial in one Sphinx page and then link to the detailed C++ API section generated by Breathe/Exhale. This separation of concerns (narrative vs API) is harder to achieve in pure Doxygen. In summary, Sphinx offers far greater customization: you can choose among many themes, add custom CSS/JS easily, and leverage a rich ecosystem of plugins – making it ideal for creating a beautiful documentation site.

### C++ Support and Completeness

Out of the box, Doxygen has the clear advantage in C++ support – it is built to parse C/C++ (and other languages) and extract documentation. It handles complex C++ features (templates, overloads, etc.) and links symbols appropriately in the generated docs. Sphinx on its own doesn’t know how to parse C++ code, but with **Breathe**, it can utilize Doxygen’s XML output. Breathe essentially acts as a middleman: _“Breathe reads the XML files generated by Doxygen and translates them into a format that Sphinx can render into RST…maintaining the ease of use of Sphinx for writing narrative docs and using user-friendly themes.”_[waterprogramming.wordpress.com](https://waterprogramming.wordpress.com/2025/01/22/launching-the-waterpaths-documentation-on-github-pages/#:~:text=Breathe%20is%20the%20Sphinx%20plugin,readable%20manner%20and%20generating%20more) In practice, this means you run Doxygen first (to generate XML), then Sphinx+Breathe will produce the documentation pages. The combination is quite robust – virtually anything that Doxygen captures about your C++ code can be presented through Sphinx. There are a few edge cases where Breathe might not expose every Doxygen feature, but for most projects this is not a problem[exhale.readthedocs.io](https://exhale.readthedocs.io/#:~:text=Why%20not%20use%20it%3F). Exhale further ensures no piece of the C++ API is missed by automating the creation of Sphinx content for every class, namespace, etc., thereby keeping the docs in sync with the code[exhale.readthedocs.io](https://exhale.readthedocs.io/#:~:text=You%20would%20use%20Exhale%20if,on%20the%20fly%20every%20time). In short, using Doxygen+Sphinx together gives full C++ coverage.

One thing to note is that Doxygen and Breathe both need to be configured consistently. For example, if you enable certain Doxygen options (like HAVE\_DOT for class diagrams), you should ensure the output (graphs, etc.) can be handled or linked in Sphinx. Generally, Breathe supports most Doxygen XML output, and you can always fall back to directly linking the Doxygen-generated HTML for very specialized pages if needed. But for the scope of typical API documentation, Sphinx with Breathe is effectively as capable as Doxygen alone in terms of C++ knowledge.

### Summary of Pros and Cons

*   **Doxygen Pros:** Purpose-built for C++, single-step tool (generate docs directly), no need for additional formatting language, supports various output formats (not just HTML), widely used.
    
*   **Doxygen Cons:** Default HTML is visually outdated[devblogs.microsoft.com](https://devblogs.microsoft.com/cppblog/clear-functional-c-documentation-with-sphinx-breathe-doxygen-cmake/#:~:text=Doxygen%20has%20been%20around%20for,and%20semantic%20markup%20for%20simplicity)[waterprogramming.wordpress.com](https://waterprogramming.wordpress.com/2025/01/22/launching-the-waterpaths-documentation-on-github-pages/#:~:text=statements,see%20some%20examples%20here), theming requires extra work or third-party CSS, less flexible for adding rich narrative content, search UI and mobile view are not as good without customizations.
    
*   **Sphinx Pros:** Highly themable (many beautiful themes available)[devblogs.microsoft.com](https://devblogs.microsoft.com/cppblog/clear-functional-c-documentation-with-sphinx-breathe-doxygen-cmake/#:~:text=The%20docs%20generated%20by%20Sphinx,the%20layout%20of%20the%20pages)[waterprogramming.wordpress.com](https://waterprogramming.wordpress.com/2025/01/22/launching-the-waterpaths-documentation-on-github-pages/#:~:text=you%20may%20have%20noted%2C%20the,used%20to%20document%20Python%20code), supports rich content (tutorials, notes, etc.) in reStructuredText/Markdown, can integrate multiple languages’ docs (via extensions), outputs a modern website feel with built-in search. Great customization via extensions (e.g. syntax highlighting, math, diagrams, etc.).
    
*   **Sphinx Cons:** Requires using reStructuredText/Markdown for writing docs (learning curve if not familiar), and for C++ it **must** be coupled with Doxygen (cannot extract C++ docs by itself). Initial setup of Sphinx+Breathe/Exhale is more involved than running Doxygen alone. Build time might be a bit longer since two tools are run in sequence.
    

**Recommendation:** Given the priority on documentation aesthetics and a high-quality look, **Sphinx with Breathe/Exhale is the recommended approach**. This combination yields a modern, beautiful documentation site and retains excellent C++ support[devblogs.microsoft.com](https://devblogs.microsoft.com/cppblog/clear-functional-c-documentation-with-sphinx-breathe-doxygen-cmake/#:~:text=The%20docs%20generated%20by%20Sphinx,the%20layout%20of%20the%20pages)[waterprogramming.wordpress.com](https://waterprogramming.wordpress.com/2025/01/22/launching-the-waterpaths-documentation-on-github-pages/#:~:text=Breathe%20is%20the%20Sphinx%20plugin,readable%20manner%20and%20generating%20more). The extra setup effort is justified by the end result – a documentation that is easier to navigate and more appealing to users. Doxygen is still an important part of the toolchain (for extracting the docs), but we will use it behind the scenes and let Sphinx handle the presentation. (If one prefers not to use Sphinx, an alternative is to use Doxygen with a custom theme like _doxygen-awesome-css_ to improve its appearance[danielsieger.com](https://danielsieger.com/blog/2021/07/07/awesome-doxygen-style.html#:~:text=If%20you%20are%20looking%20for,option), but you would miss out on Sphinx’s flexibility in writing additional docs.) The rest of this guide will focus on setting up Sphinx+Breathe+Exhale for a C++ project, and automating the generation and deployment of the docs.

Setting Up Sphinx Documentation for a C++ Project
-------------------------------------------------

Follow these steps to set up documentation generation using **Doxygen + Sphinx** (with Breathe and Exhale) for your C++ project. We will assume your project source code is in a directory like `src/` or `include/`, and we’ll create a `docs/` directory for documentation configuration and output.

**1\. Install Dependencies:** Ensure that Doxygen and Python (for Sphinx) are installed on your system. Install **Doxygen** from the official site[devblogs.microsoft.com](https://devblogs.microsoft.com/cppblog/clear-functional-c-documentation-with-sphinx-breathe-doxygen-cmake/#:~:text=this%20needs%20to%20be%20supplied,source%20which%20you%20can%20build) or via your package manager (e.g., `sudo apt install doxygen`). Then install the Sphinx toolchain via pip:

```bash
pip install sphinx breathe exhale sphinx_rtd_theme
```

This will install **Sphinx**, the **Breathe** bridge, **Exhale**, and the Read the Docs theme (you can choose a different theme later). Verify the installations: running `doxygen --version` and `sphinx-build --version` should show that the commands are available.

**2\. Initialize Sphinx in your project:** Sphinx can create a sample project for you. Navigate to your project’s `docs/` folder (create one if not exists) and run the quickstart:

```bash
cd docs
sphinx-quickstart  # or `sphinx-quickstart.exe` on Windows
```

The quickstart will ask some questions. You can accept defaults, but be sure to enter your project name and author when prompted. You may also choose separate source/build directories if you prefer (for clarity, e.g. `docs/source` and `docs/build`). For this guide, assume Sphinx source files (like `conf.py` and `.rst` files) live in `docs/` (or `docs/source/` if separated), and HTML output will be generated to `docs/_build/html` (default) or `docs/build/html`. After running the quickstart, a `conf.py` (configuration) file and an `index.rst` should be created, among others. At this point, you can test Sphinx alone by running `make html` (which calls `sphinx-build`) – it will produce a basic site with a welcome page. We will now customize the configuration to integrate Doxygen.

**3\. Set up a Doxygen configuration:** If you don’t already have a `Doxyfile` for your project, generate one by running `doxygen -g` (this creates a default `Doxyfile` in the current directory). Move this file into the `docs/` directory for convenience. Open the `Doxyfile` in a text editor and **configure at least the following settings**:

*   **PROJECT\_NAME:** Set this to your project’s name (appears in generated docs).
    
*   **OUTPUT\_DIRECTORY:** Set to `docs/doxygen` (for example) so that Doxygen’s output files go to the docs folder. Keeping outputs in `docs/` makes it easier to manage and deploy.
    
*   **GENERATE\_HTML:** Set to `NO` if you only want to use Sphinx for HTML. (We don’t need Doxygen’s HTML when using Sphinx, but we do need Doxygen’s XML.)
    
*   **GENERATE\_XML:** Set this to `YES`[devblogs.microsoft.com](https://devblogs.microsoft.com/cppblog/clear-functional-c-documentation-with-sphinx-breathe-doxygen-cmake/#:~:text=Breathe%20uses%20Doxygen%E2%80%99s%20XML%20output%2C,need%20to%20turn%20it%20on) – this is crucial, as Breathe will read the XML output. Specify **XML\_OUTPUT** (optional) to a convenient subfolder name like `xml` (default is `xml`).
    
*   **INPUT:** Set this to the paths of your source code. For example, `INPUT = ../src ../include`. You can list multiple directories/files that contain documentation comments.
    
*   **FILE\_PATTERNS:** Ensure it includes your file extensions (e.g., `.h, .hpp, .cpp` etc.) so Doxygen knows to scan those files.
    
*   **EXTRACT\_PRIVATE:** (Optional) set to YES if you want to include private class members in the docs.
    
*   **USE\_MDFILE\_AS\_MAINPAGE:** (Optional) if you have a Markdown file (like a README) to serve as the main page.
    
*   **STRIP\_FROM\_PATH:** (Optional) to trim common path prefixes from file names in output.
    

Here’s an excerpt of important Doxyfile settings to change:

```ini
PROJECT_NAME           = MyProject
OUTPUT_DIRECTORY       = docs/doxygen
GENERATE_HTML          = NO       # We'll use Sphinx for HTML
GENERATE_XML           = YES
XML_OUTPUT             = xml      # XML files will be in docs/doxygen/xml/
INPUT                  = ../src ../include
FILE_PATTERNS          = *.cpp *.h *.hpp
EXTRACT_PRIVATE        = NO       # Yes to include private members
```

After editing, run `doxygen docs/Doxyfile` to test it. It should scan your code and produce XML files in `docs/doxygen/xml/` (and possibly other outputs like LaTeX if not disabled). We’ll integrate this with Sphinx next.

**4\. Configure Sphinx to use Breathe and Exhale:** Open the Sphinx `conf.py` in the `docs/` directory. We need to enable the Breathe and Exhale extensions and point them to Doxygen’s output. Make the following changes in `conf.py`:

*   **Extensions:** Add `'breathe'` and `'exhale'` to the `extensions` list. (Also add any theme extensions if needed, e.g. `'sphinx_rtd_theme'` for Read the Docs theme.)
    
*   **Breathe Configuration:** Define a dictionary mapping project names to the path of Doxygen’s XML output. For example: `breathe_projects = {"MyProject": "./doxygen/xml"}` assuming `conf.py` is in `docs/` and XML is in `docs/doxygen/xml`. Also set `breathe_default_project = "MyProject"`.
    
*   **Exhale Configuration:** Define `exhale_args` to tell Exhale where to generate API pages and how to structure them. At minimum, set:
    
    *   `containmentFolder` – a subfolder (relative to Sphinx source) where Exhale will write the API reST files (e.g. `"./api"` to create a docs/api/ folder).
        
    *   `rootFileName` – the name of the root API page file (e.g. `"library_root.rst"`).
        
    *   `rootFileTitle` – the title for the root API page (e.g. `"API Reference"` or your project name + "API").
        
    *   `doxygenStripFromPath` – a path prefix to strip from file paths (to make file names shorter in docs, e.g. `"../.."` to remove the leading path above your src directory).
        
    *   Optionally, `createTreeView` set to `True` if you want a collapsible tree menu for the API (requires a theme that supports it, like certain Bootstrap-based themes).
        
*   **Primary Domain:** Set `primary_domain = 'cpp'` so that Sphinx treats C++ as the main language for roles and directives. Also set `highlight_language = 'cpp'` for code highlighting in C++.
    
*   **HTML Theme:** Set your desired HTML theme, e.g. `html_theme = "sphinx_rtd_theme"` for Read the Docs theme (make sure you pip installed it). You can also configure theme options or custom static files if needed.
    

Putting it together, your `conf.py` might include lines like this (simplified example):

```python
# -- Extensions for Sphinx -------------------------------------------------
extensions = [
    'breathe',
    'exhale',
    'sphinx_rtd_theme'   # using Read the Docs theme as an example
]

# -- Breathe Configuration -------------------------------------------------
breathe_projects = {
    "MyProject": "./doxygen/xml"
}
breathe_default_project = "MyProject"

# -- Exhale Configuration --------------------------------------------------
exhale_args = {
    "containmentFolder": "./api",
    "rootFileName": "library_root.rst",
    "rootFileTitle": "API Reference",
    "doxygenStripFromPath": "../..",  # adjust path as needed
    "createTreeView": True
}
primary_domain = 'cpp'
highlight_language = 'cpp'

# -- Options for HTML output -------------------------------------------------
html_theme = "sphinx_rtd_theme"
```

After saving `conf.py`, Sphinx is now configured to use Breathe and Exhale. The `exhale_args` above will cause Exhale to generate an `api/` folder in the build process containing reStructuredText files for each class, namespace, etc., with a root file `library_root.rst` that serves as an index of the API.

**5\. Connect the documentation pages:** We need to include the generated API documentation in our Sphinx TOC so it appears in the site. Open `index.rst` (the main documentation page) and add a reference to Exhale’s root document. For example, at the bottom of `index.rst`, include:

```restructuredtext
.. toctree::
   :maxdepth: 2
   :caption: Contents:

   api/library_root
```

This will insert the API reference (all the content under `api/` generated by Exhale) into the Sphinx site’s table of contents. The `library_root` page (with title "API Reference") will contain an organized list of all classes, files, namespaces, etc., thanks to Exhale. You can adjust `:maxdepth:` or the caption as needed. If you have other documentation pages (e.g. a general introduction or user guides), list them in the toctree as well above or below the API reference.

_Without Exhale:_ If you choose not to use Exhale, you would instead manually use Breathe directives in your `.rst` files to include API information (for example, using `.. doxygenclass:: MyClass` or Breathe’s `.. doxygenindex::` to pull in entire index). Breathe also provides a `breathe-apidoc` tool similar to Sphinx’s `apidoc` to generate stub `.rst` files from Doxygen XML[exhale.readthedocs.io](https://exhale.readthedocs.io/#:~:text=It%20may%20be%20more%20involved,to%20get%20your%20documentation%20displayed). However, Exhale largely automates this, so we recommend it for convenience.

**6\. Build the documentation:** Now that everything is configured, you can generate the docs. It will be a two-step process (Doxygen then Sphinx):

*   First run Doxygen to produce/update the XML:
    
    ```bash
    doxygen docs/Doxyfile
    ```
    
    Ensure this runs without errors. It should output files into `docs/doxygen/xml/`.
    
*   Then run Sphinx to build the HTML:
    
    ```bash
    sphinx-build -b html docs/ docs/_build/html
    ```
    
    (Adjust paths if you have separate source directory, e.g. `sphinx-build -b html docs/source docs/build/html`.) You can also use the makefile Sphinx provided: `make html` from the `docs/` directory (on Windows use `make.bat html`). Sphinx will read your reST files, use Breathe to pull in Doxygen XML data, and Exhale will generate the API pages on the fly. If everything is set up correctly, you should see it writing out pages for your classes, etc., during the build.
    

When done, open the resulting `index.html` (in `docs/_build/html/` or `docs/build/html/`) in a browser. You should see a nicely formatted site with your project’s documentation. The index page should list the “API Reference” (or whatever you titled it) and other sections. Navigate through and verify that classes, functions, and other API elements are documented. Congratulations – you have a beautiful documentation site locally!

Automating Documentation Generation and Deployment
--------------------------------------------------

Manually running Doxygen and Sphinx and then publishing the files can become tedious. We want to **fully automate** this process both for local convenience and as part of Continuous Integration (CI) so that any new code changes can trigger a documentation update on GitHub Pages. We will set up a Python script to generate and deploy the docs, and also integrate it with GitHub Actions for CI/CD. The end goal: whenever you push to the main branch (or whenever you desire, e.g. on a version tag), the docs will rebuild and publish to GitHub Pages automatically.

### Python Script for Local Automation

You can create a Python script (e.g. `deploy_docs.py`) at the root of your repository to streamline the doc generation. This script will run Doxygen and Sphinx, then push the results to the `gh-pages` branch of your repo (which is used by GitHub Pages). Using a script means you or the CI can use the same code path to deploy. Below is an example of what such a script might look like:

```python
import os
import subprocess
import sys

# Paths and configurations
DOXYFILE_PATH = os.path.join("docs", "Doxyfile")
SPHINX_SRC = os.path.join("docs")          # Sphinx source (conf.py location)
SPHINX_HTML = os.path.join("docs", "_build", "html")  # HTML output folder

# 1. Run Doxygen to generate XML
ret = subprocess.run(["doxygen", DOXYFILE_PATH], check=False)
if ret.returncode != 0:
    sys.exit(f"Doxygen failed with code {ret.returncode}")

# 2. Run Sphinx to generate HTML
ret = subprocess.run(["sphinx-build", "-b", "html", SPHINX_SRC, SPHINX_HTML], check=False)
if ret.returncode != 0:
    sys.exit(f"Sphinx build failed with code {ret.returncode}")

# 3. Deploy to GitHub Pages:
# Initialize gh-pages branch in docs/_build/html and push (using ghp-import for simplicity)
try:
    import ghp_import
except ImportError:
    # Install ghp-import if not available
    subprocess.run([sys.executable, "-m", "pip", "install", "ghp-import"], check=True)
import ghp_import
ghp_import.ghp_import(SPHINX_HTML, push=True, cname=None)
```

This script uses the `ghp-import` utility to push the HTML in `docs/_build/html` to the `gh-pages` branch. The `ghp_import.ghp_import(..., push=True)` call will create/overwrite the gh-pages branch (in the local git repo) and push to origin. You may need to configure `ghp-import` with your repo URL or ensure you have the proper permissions (in CI, the GitHub token can be used, as shown later). Alternatively, you could replace this step with manual Git commands (initializing a repo in the HTML folder, committing, and pushing to `gh-pages`). The idea is that running `deploy_docs.py` will end up publishing the latest docs to GitHub Pages.

**Usage:** Run `python deploy_docs.py` whenever you want to update the docs. For local use, you should have push access to the repository (and ideally do this on a clean working tree). In CI, we’ll run the same script (with the CI-provided token) to update pages automatically.

### Continuous Deployment with GitHub Actions

To set up continuous deployment of docs on GitHub Pages, we use **GitHub Actions**. We’ll create a workflow YAML file that triggers on each push (or on certain branches) to build the docs and deploy. Ensure that GitHub Pages is enabled for your repository (in the repo Settings -> Pages, set it to use the `gh-pages` branch or `docs/` folder on main as appropriate). For this guide, we’ll use the `gh-pages` branch approach, which is common for CI deployments.

Create a file `.github/workflows/docs.yml` in your repository with the following content (comments added for explanation):

```yaml
name: Build and Deploy Docs
on:
  push:
    branches: [ main ]    # Run on each push to main (adjust branch as needed)

jobs:
  docs:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
        with:
          persist-credentials: false   # we'll use a token for pushing

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.9'

      - name: Install dependencies
        run: |
          sudo apt-get update && sudo apt-get install -y doxygen graphviz
          pip install sphinx breathe exhale sphinx_rtd_theme ghp-import

      - name: Build documentation
        run: |
          doxygen docs/Doxyfile
          sphinx-build -b html docs docs/_build/html

      - name: Deploy to GitHub Pages
        run: |
          ghp-import -n -p docs/_build/html
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

Let’s break down what this does:

*   It triggers on pushes to the `main` branch.
    
*   It checks out the code (without using the default credentials, because we’ll use the token explicitly for deployment).
    
*   It sets up Python 3.9 (you can use any version >=3.6).
    
*   **Install dependencies:** We install Doxygen (and `graphviz` in case you use Doxygen for diagrams) via apt, and the Python packages via pip (including ghp-import for deployment). This ensures the runner has everything needed.
    
*   **Build documentation:** This runs the same commands we tested locally – generating Doxygen XML and then Sphinx HTML. If the `Doxyfile` or Sphinx config is misconfigured, this step may fail, which will stop the workflow (you’d see the error in the Actions logs). Make sure the paths are correct (in this example, we assume `docs/` contains both `Doxyfile` and Sphinx’s `conf.py`). Adjust if your structure is different (e.g., `doxygen docs/Doxyfile` and `sphinx-build -b html docs/source docs/build/html` if using separate source directory).
    
*   **Deploy to GitHub Pages:** This uses `ghp-import` to push the HTML. The flags used: `-n` to **disable Jekyll** on GitHub Pages (adding a `.nojekyll` file, since Sphinx site doesn’t need Jekyll), and `-p` to push to origin. We rely on the `${{ secrets.GITHUB_TOKEN }}` which is GitHub’s automatic token for the action – `ghp-import` will pick it up to authenticate (the `env` line passes it). Alternatively, you could use the official `peaceiris/actions-gh-pages@v3` action for deployment, but `ghp-import` is straightforward for this purpose.
    

After adding this workflow, commit and push it. On the next push to main (including this one), the GitHub Actions runner will execute these steps. If successful, it will push a commit to the `gh-pages` branch of your repo containing the built documentation. The first time, you might need to go to your repository’s Settings -> Pages and ensure it’s set to deploy from the `gh-pages` branch (GitHub might do this automatically when it sees a gh-pages branch). You only need to configure that once.

**Tip:** You might want to restrict the workflow to run only when documentation changes, or maybe only on release tags. You can adjust the trigger (`on:`) to suit your workflow (for example, trigger on pushes to a `docs` folder, or on publishing a new release). The above is a simple setup that ensures docs are updated on every commit to main.

From now on, your documentation process is automated. Developers can still run `make html` (or the Python script) locally to preview changes, and the CI will deploy the official docs. This ensures your GitHub Pages site is always up-to-date with the latest documentation of your C++ project.

Integrating Documentation with Build Systems
--------------------------------------------

Depending on your development workflow, you might want to tie documentation generation into your build system so that, for example, `make docs` or a similar command produces the docs, or to have CMake generate docs as a target. Below are brief suggestions for Premake, CMake, and Make integration. These are optional – with the above automation, you might just let CI handle docs – but they can be useful for developers.

### Premake Integration (Premake5)

Premake (a Lua-based build configuration tool) doesn’t have built-in Doxygen support, but you can extend it. One approach is to define a **custom action** in the `premake5.lua` script. Premake’s `newaction` API allows adding new command-line actions[premake.github.io](https://premake.github.io/docs/Command-Line-Arguments/#:~:text=Command%20Line%20Arguments%20,the%20newaction%20and%20newoption%20functions). For example, you can add a “docs” action:

```lua
-- premake5.lua
newaction {
   trigger     = "docs",
   description = "Generate documentation using Doxygen and Sphinx",
   execute     = function()
      os.execute("doxygen docs/Doxyfile")
      os.execute("sphinx-build -b html docs docs/_build/html")
      print("Documentation generated in docs/_build/html")
   end
}
```

With this in your premake script, a developer can run `premake5 docs` to generate the documentation (assuming premake is installed and your premake script is in the project root). This will simply call the commands we discussed. You can refine the paths as needed or even call the Python automation script from Premake (using `os.execute("python deploy_docs.py")`). This approach keeps documentation generation as part of your project’s developer tools. It won’t automatically deploy to GitHub Pages – it’s mainly for local use (deployment is handled by CI as above).

### CMake Integration

CMake is quite friendly to Doxygen integration and can also call Sphinx. A common strategy is to create a custom CMake target for docs. You can use the built-in `FindDoxygen` module to locate Doxygen and even use the macro `doxygen_add_docs()` (available in recent CMake versions) to simplify some steps[aliceo2group.github.io](https://aliceo2group.github.io/advanced/doxygen.html#:~:text=Doxygen%20,doxygen_add_docs%20function%20to%20generate)[cmake.org](https://cmake.org/cmake/help/latest/module/FindDoxygen.html#:~:text=,DOXYGEN_GENERATE_HTML%20NO). For full control, you can do something like this in your top-level `CMakeLists.txt` (or a `docs/CMakeLists.txt`):

```cmake
find_package(Doxygen REQUIRED)
# Optionally, configure the Doxyfile by substituting variables:
#set(DOXYGEN_INPUT_DIR "${CMAKE_SOURCE_DIR}/src")
#configure_file(${CMAKE_SOURCE_DIR}/docs/Doxyfile.in ${CMAKE_BINARY_DIR}/Doxyfile @ONLY)

find_package(Sphinx REQUIRED)  # if you wrote a FindSphinx.cmake as in the blog example

# Doxygen generation step
add_custom_command(OUTPUT ${CMAKE_CURRENT_BINARY_DIR}/doxygen/xml/index.xml
    COMMAND ${DOXYGEN_EXECUTABLE} docs/Doxyfile
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
    DEPENDS ${CMAKE_SOURCE_DIR}/docs/Doxyfile ${MY_PROJECT_HEADERS}
    COMMENT "Generating Doxygen XML"
)
add_custom_target(doxygen-docs ALL DEPENDS ${CMAKE_CURRENT_BINARY_DIR}/doxygen/xml/index.xml)

# Sphinx generation step (depends on Doxygen)
add_custom_command(OUTPUT ${CMAKE_CURRENT_BINARY_DIR}/sphinx/index.html
    COMMAND sphinx-build -b html docs docs/_build/html
            -Dbreathe_projects.MyProject=${CMAKE_CURRENT_BINARY_DIR}/doxygen/xml
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
    DEPENDS doxygen-docs ${CMAKE_SOURCE_DIR}/docs/conf.py ${CMAKE_SOURCE_DIR}/docs/index.rst
    COMMENT "Generating HTML documentation with Sphinx"
)
add_custom_target(sphinx-docs ALL DEPENDS ${CMAKE_CURRENT_BINARY_DIR}/sphinx/index.html)
```

In this snippet, we define a target `doxygen-docs` that runs Doxygen (producing XML), and a target `sphinx-docs` that runs Sphinx, depending on the Doxygen output. The `-D breathe_projects.MyProject=...` part passes the Doxygen XML path to Sphinx on the command line[devblogs.microsoft.com](https://devblogs.microsoft.com/cppblog/clear-functional-c-documentation-with-sphinx-breathe-doxygen-cmake/#:~:text=add_custom_target%28Sphinx%20ALL%20COMMAND%20%24%7BSPHINX_EXECUTABLE%7D%20,Generating%20documentation%20with%20Sphinx)[devblogs.microsoft.com](https://devblogs.microsoft.com/cppblog/clear-functional-c-documentation-with-sphinx-breathe-doxygen-cmake/#:~:text=,Generating%20documentation%20with%20Sphinx) (this assumes your Sphinx `conf.py` uses that variable; alternatively you could hardcode the path in conf.py or set an env var). We also list dependencies so that CMake knows when to rerun these (here `${MY_PROJECT_HEADERS}` would be a list of header files we gather to trigger Doxygen rebuild if any change). The result is that running `make sphinx-docs` (or just building `ALL` if marked as ALL) will produce the docs. This approach is detailed in a Microsoft C++ team blog[devblogs.microsoft.com](https://devblogs.microsoft.com/cppblog/clear-functional-c-documentation-with-sphinx-breathe-doxygen-cmake/#:~:text=,VERBATIM)[devblogs.microsoft.com](https://devblogs.microsoft.com/cppblog/clear-functional-c-documentation-with-sphinx-breathe-doxygen-cmake/#:~:text=%23%20,to%20find%20the%20Doxygen%20output) – they show how to configure the dependencies to avoid unnecessary rebuilds. You can refine it as needed, for example only build docs on demand (omit `ALL` from the custom targets) so it doesn’t run every build.

If you prefer using `doxygen_add_docs()` (which encapsulates some of this), you could call:

```cmake
doxygen_add_docs(doxygen-docs ${PROJECT_SOURCE_DIR}/include COMMENT "Generate Doxygen docs")
```

This will auto-generate a target that runs Doxygen for the given path(s) with some default settings (you still need a Doxyfile present, and you might need to set some CMake variables to control Doxyfile options via `DOXYGEN_*` variables[cmake.org](https://cmake.org/cmake/help/latest/module/FindDoxygen.html#:~:text=variables%20before%20calling%20,full%20list%20of%20supported%20configuration)[cmake.org](https://cmake.org/cmake/help/latest/module/FindDoxygen.html#:~:text=relevant%20variables%20before%20calling%20,For%20example)). You’d then add a separate custom target for Sphinx as above.

### Make (GNU Make) Integration

If you are using a raw Makefile (for a simpler C++ project without CMake/Premake), you can add a documentation rule. For example:

```make
docs:
	@echo "Generating Doxygen docs..."
	doxygen docs/Doxyfile
	@echo "Generating Sphinx docs..."
	sphinx-build -b html docs docs/_build/html
	@echo "Documentation generated at docs/_build/html"
```

This assumes the `docs/` directory has your Doxyfile and Sphinx conf.py. Now a `make docs` will produce the HTML docs. You might also include a `publish` step depending on your needs (though it’s often safer to let CI handle publishing to avoid accidentally overwriting gh-pages from a developer machine).

### Summary of Build Integration

Integrating documentation generation with the build can be convenient for developers to preview docs. Premake allows adding a custom action as shown. CMake can use custom targets or its Doxygen module to tie into the build graph (the example above ensures Sphinx runs after Doxygen, and only when needed)[devblogs.microsoft.com](https://devblogs.microsoft.com/cppblog/clear-functional-c-documentation-with-sphinx-breathe-doxygen-cmake/#:~:text=,VERBATIM)[devblogs.microsoft.com](https://devblogs.microsoft.com/cppblog/clear-functional-c-documentation-with-sphinx-breathe-doxygen-cmake/#:~:text=%23%20,to%20find%20the%20Doxygen%20output). Makefiles can call the tools directly. In all cases, ensure the tools (Doxygen, Sphinx, etc.) are installed in the environment where the build runs. For CI, you might still rely on the separate GitHub Actions workflow as described, but it’s not uncommon to hook a `docs` target in CMake that developers can run, and perhaps have the CI job simply call that target.

Conclusion
----------

By leveraging **Doxygen** for C++ code parsing and **Sphinx** (with **Breathe** and **Exhale**) for presentation, you can create a documentation website for your C++ project that is both comprehensive and visually appealing. We evaluated the two approaches: while Doxygen alone can generate API docs, the Sphinx route offers superior aesthetics and customization[devblogs.microsoft.com](https://devblogs.microsoft.com/cppblog/clear-functional-c-documentation-with-sphinx-breathe-doxygen-cmake/#:~:text=The%20docs%20generated%20by%20Sphinx,the%20layout%20of%20the%20pages)[waterprogramming.wordpress.com](https://waterprogramming.wordpress.com/2025/01/22/launching-the-waterpaths-documentation-on-github-pages/#:~:text=your%20documentation%20%28i,see%20some%20examples%20here). The step-by-step setup above helps you configure the toolchain. With the provided Python script and GitHub Actions workflow, documentation generation and deployment to **GitHub Pages** becomes fully automated. This means your docs will stay up-to-date with minimal effort, and developers/contributors can focus on writing good comments and docs content rather than fiddling with publishing.

By integrating with build systems (Premake/CMake/Make), you further streamline the process of generating docs during development or release cycles. The result is a professional documentation site for your C++ project that can greatly enhance its usability and appeal to users. Now you can enjoy a continuous documentation workflow – write code and comments, push to GitHub, and let the automation produce beautiful docs for you and your users to explore. Happy documenting!

**Sources:** The approach and configurations are informed by official tool documentation and community best practices. Key references include the Microsoft C++ Team Blog on Sphinx+Breathe+Doxygen[devblogs.microsoft.com](https://devblogs.microsoft.com/cppblog/clear-functional-c-documentation-with-sphinx-breathe-doxygen-cmake/#:~:text=Doxygen%20has%20been%20around%20for,and%20semantic%20markup%20for%20simplicity)[devblogs.microsoft.com](https://devblogs.microsoft.com/cppblog/clear-functional-c-documentation-with-sphinx-breathe-doxygen-cmake/#:~:text=The%20docs%20generated%20by%20Sphinx,the%20layout%20of%20the%20pages), the WaterPaths documentation guide[waterprogramming.wordpress.com](https://waterprogramming.wordpress.com/2025/01/22/launching-the-waterpaths-documentation-on-github-pages/#:~:text=statements,see%20some%20examples%20here)[waterprogramming.wordpress.com](https://waterprogramming.wordpress.com/2025/01/22/launching-the-waterpaths-documentation-on-github-pages/#:~:text=you%20may%20have%20noted%2C%20the,used%20to%20document%20Python%20code), and the Exhale documentation[exhale.readthedocs.io](https://exhale.readthedocs.io/#:~:text=Automatic%20C%2B%2B%20library%20API%20documentation,available%20in%20Sphinx%20documented%20projects)[exhale.readthedocs.io](https://exhale.readthedocs.io/#:~:text=You%20would%20use%20Exhale%20if,on%20the%20fly%20every%20time). These resources delve deeper into why Sphinx offers a modern documentation style and how Breathe/Exhale tie into Doxygen for C++ projects. Additional references are provided inline for specific points.
High-quality documentation is crucial for any Python project. The good news is there are mature tools to generate documentation automatically from your code and docstrings. The most widely adopted solutions are **Sphinx**, **MkDocs**, and **pdoc**. Each of these supports standard docstring formats (Google style, NumPy style, Markdown, etc.) and can produce a professional static website for your docs. Below is a brief overview of these tools:

*   **Sphinx** – A powerful documentation generator that uses _reStructuredText_ by default, but with the **Napoleon** extension it can parse Google-style and NumPy-style docstrings[sphinx-doc.org](https://www.sphinx-doc.org/en/master/usage/extensions/napoleon.html#:~:text=True%20to%20parse%20Google%20style,support%20for%20Google%20style%20docstrings)[sphinx-doc.org](https://www.sphinx-doc.org/en/master/usage/extensions/napoleon.html#:~:text=True%20to%20parse%20NumPy%20style,support%20for%20NumPy%20style%20docstrings). Sphinx is widely used (e.g. on Read the Docs) and supports many extensions, theming options, and PDF/EPUB output.
    
*   **MkDocs** – A static site generator geared towards project documentation. It uses Markdown for content and has a popular **Material for MkDocs** theme. With the **mkdocstrings** plugin, MkDocs can automatically document code and supports Google/NumPy docstrings[mkdocstrings.github.io](https://mkdocstrings.github.io/python/usage/configuration/docstrings/#:~:text=%2A%20Type%20str%20%20%60). It produces a sleek web docs site with search functionality.
    
*   **pdoc** – A lightweight documentation generator that directly reads your Python docstrings and outputs HTML or Markdown. It natively supports Google and NumPy docstring formats (converting them to Markdown)[pdoc.dev](https://pdoc.dev/docs/pdoc.html#:~:text=While%20pdoc%20prefers%20docstrings%20that,of%20these%20styles%2C%20you%20can)[pdoc.dev](https://pdoc.dev/docs/pdoc.html#:~:text=,then%20Numpydoc%20syntax%2C%20then%20Markdown). pdoc is easy to set up for simple API reference docs.
    

All of these can be integrated into an automated pipeline. The typical workflow is: write clear docstrings in a standard style, use one of the tools to generate HTML documentation from those docstrings (and any additional docs you write), then automatically publish the site to **GitHub Pages** via **GitHub Actions**. In the sections below, we’ll set up a documentation pipeline step-by-step using Sphinx and MkDocs (as primary examples), and mention how to adapt for pdoc. We’ll also cover optional features like versioning, theming, and localization.

Setting Up Documentation with **Sphinx**
----------------------------------------

Sphinx is a robust choice for generating documentation from Python source code. Follow these steps to configure Sphinx for your project:

### 1\. Install Sphinx and Extensions

Begin by installing Sphinx and some useful extensions in your Python environment (you can use pip):

```bash
pip install sphinx sphinx-rtd-theme sphinx-ext-napoleon sphinx-autodoc-typehints
```

*   **sphinx-rtd-theme**: Common theme (Read the Docs style) for a clean look.
    
*   **sphinx-ext-napoleon**: The Napoleon extension to parse Google/NumPy style docstrings[sphinx-doc.org](https://www.sphinx-doc.org/en/master/usage/extensions/napoleon.html#:~:text=True%20to%20parse%20Google%20style,support%20for%20Google%20style%20docstrings).
    
*   **sphinx-autodoc-typehints**: Optional, to automatically include type hints in the docs.
    

_(Alternatively, you can install Sphinx via Poetry or conda depending on your setup.)_

### 2\. Run Sphinx Quickstart

Sphinx provides a quick-start utility to initialize a docs folder. From your project root, run:

```bash
sphinx-quickstart docs
```

This will interactively ask some questions. You can accept defaults, but make sure to choose **yes** for “autodoc” support if prompted (this adds the `sphinx.ext.autodoc` extension for pulling in docstrings). The quickstart will create a `docs/` directory with a basic configuration:

*   `docs/conf.py`: Configuration file for Sphinx.
    
*   `docs/index.rst`: The root document.
    
*   Makefile and/or batch file for building (optional, depending on options).
    

### 3\. Configure `conf.py` for Docstrings and Themes

Open `docs/conf.py` in a text editor. We need to enable the extensions and configure Sphinx to understand our docstring style:

*   Enable the **autodoc** and **napoleon** extensions by adding them to the `extensions` list:
    
    ```python
    extensions = [
        "sphinx.ext.autodoc",
        "sphinx.ext.napoleon",
        "sphinx.ext.viewcode",     # shows source code in docs
        "sphinx.ext.githubpages"   # adds .nojekyll for GitHub Pages
    ]
    ```
    
    _Napoleon_ allows Sphinx to parse Google and NumPy style docstrings and convert them to the proper format internally[sphinx-doc.org](https://www.sphinx-doc.org/en/master/usage/extensions/napoleon.html#:~:text=True%20to%20parse%20Google%20style,support%20for%20Google%20style%20docstrings). By default, Napoleon is enabled with both `napoleon_google_docstring = True` and `napoleon_numpy_docstring = True`[sphinx-doc.org](https://www.sphinx-doc.org/en/master/usage/extensions/napoleon.html#:~:text=True%20to%20parse%20Google%20style,support%20for%20Google%20style%20docstrings)[sphinx-doc.org](https://www.sphinx-doc.org/en/master/usage/extensions/napoleon.html#:~:text=True%20to%20parse%20NumPy%20style,support%20for%20NumPy%20style%20docstrings), so it will handle either style automatically.
    
*   Set the project information at the top (project name, author, version).
    
*   Choose a HTML theme. For example, to use the ReadTheDocs theme:
    
    ```python
    html_theme = "sphinx_rtd_theme"
    ```
    
    Make sure you installed `sphinx-rtd-theme` as shown earlier. Sphinx has many themes; you can also try `"furo"` or the default `"alabaster"`.
    
*   (Optional) If using type hints in your code and sphinx-autodoc-typehints, add:
    
    ```python
    extensions.append("sphinx_autodoc_typehints")
    ```
    
    This will integrate Python type hints into the parameter documentation.
    
*   Ensure `templates_path` and `exclude_patterns` are set appropriately (defaults are usually fine). The `master_doc` (or `root_doc` in newer Sphinx) should point to `index` by default.
    

After configuring, save `conf.py`. Sphinx is now set to extract documentation from your code’s docstrings.

### 4\. Write Docstrings in a Supported Style

With Napoleon enabled, you can write docstrings in **Google style** or **NumPy style** (or even in reStructuredText). For example, a Google-style docstring:

```python
def add(x, y):
    """Add two numbers.

    Args:
        x (int): The first number.
        y (int): The second number.

    Returns:
        int: The sum of x and y.
    """
    return x + y
```

Napoleon will parse sections like **Args**, **Returns**, etc., and format them properly in the output[sphinx-doc.org](https://www.sphinx-doc.org/en/master/usage/extensions/napoleon.html#:~:text=Google%20style%20docstrings%20and%20converts,your%20actual%20source%20code%20files). If you prefer NumPy style:

```python
def add(x, y):
    """Add two numbers.

    Parameters
    ----------
    x : int
        The first number.
    y : int
        The second number.

    Returns
    -------
    int
        The sum of x and y.
    """
    return x + y
```

This will also be understood by Napoleon and converted appropriately.

### 5\. Generate API Documentation Pages

Sphinx can automatically create RST files listing your modules and classes using the **apidoc** tool. Run the following command (adjusting package path and output directory):

```bash
sphinx-apidoc -o docs/source/ your_project_package/
```

*   `your_project_package/` is the path to your Python package or module.
    
*   `-o docs/source/` tells Sphinx to place the generated `.rst` files in `docs/source` (you might need to create `docs/source` or adjust if your structure differs).
    

The `sphinx-apidoc` tool will create `.rst` files for each module, with `.. automodule::` and `.. autofunction::` directives to pull in docstrings via autodoc[sphinx-doc.org](https://www.sphinx-doc.org/en/master/man/sphinx-apidoc.html#:~:text=Description%C2%B6). It also creates a `modules.rst` (table of contents of modules). Include these generated files in your main `index.rst` or another toctree so Sphinx knows to build them. For example, in `index.rst` you might add:

```rst
.. toctree::
   :maxdepth: 2
   :caption: API Reference

   modules
```

_(Alternatively,_ instead of using sphinx-apidoc, you can manually create `.rst` files and use directives like `.. automodule:: module.name` with `:members:` to document all functions/classes in that module. Another advanced option is **sphinx-autoapi** which parses code without importing it, but sphinx-apidoc + autodoc is simpler for most cases.)\*

### 6\. Build the Documentation Locally

Now build the HTML documentation to verify everything works:

*   If you have a Makefile, simply run: `make html` (from the `docs/` directory).
    
*   Without Makefile, use:
    
    ```bash
    sphinx-build -b html docs docs/_build/html
    ```
    

This tells Sphinx to take the content in `docs/` (it looks for `conf.py` and `index.rst` there) and generate a static HTML site in `docs/_build/html`. After a successful build, open `docs/_build/html/index.html` in a browser to see your documentation. It should have the API reference pulled from your code’s docstrings, formatted nicely.

**Troubleshooting:** If Sphinx can’t import your project modules (for autodoc), you may need to adjust the `sys.path` in `conf.py` to include your project path. For example, add:

```python
import os
import sys
sys.path.insert(0, os.path.abspath(".."))
```

if your project is one level up from `docs/`.

Setting Up Documentation with **MkDocs**
----------------------------------------

MkDocs offers a modern approach using Markdown for documentation pages. We will use the **mkdocstrings** plugin to integrate API docs from docstrings. Here’s how to set up a MkDocs documentation pipeline:

### 1\. Install MkDocs and Plugins

Install MkDocs and the necessary plugins with pip:

```bash
pip install mkdocs mkdocs-material mkdocstrings[python]
```

*   **mkdocs-material**: Provides the popular Material theme (you can choose others, but Material is feature-rich and widely used).
    
*   **mkdocstrings\[python\]**: The mkdocstrings plugin with Python handler (the `[python]` extra installs the Python-specific parser, which uses the _Griffe_ library under the hood to parse code and docstrings).
    

### 2\. Create a MkDocs Configuration

In your project root, create a file named `mkdocs.yml`. This is the config for MkDocs. A basic configuration would look like:

```yaml
site_name: MyProject Documentation
site_url: "https://yourusername.github.io/yourproject/"  # optional, for sitemap
theme:
  name: material
plugins:
  - search
  - mkdocstrings:
      default_handler: python
      handlers:
        python:
          options:
            docstring_style: google
```

Key points in this config:

*   `site_name` is the title of your documentation site.
    
*   We selected the **Material** theme for a polished look (comes with built-in search and many features).
    
*   Enabled the **search** plugin (usually on by default with Material).
    
*   Added **mkdocstrings** plugin. We specify the default handler as Python and pass an option to indicate the docstring style. Here we chose `"google"` style, which means mkdocstrings/Griffe will expect Google-style formatting for sections[mkdocstrings.github.io](https://mkdocstrings.github.io/python/usage/configuration/docstrings/#:~:text=%2A%20%60,all%2C%20parse%20as%20regular%20text). If you use NumPy style, set `docstring_style: numpy`. (Mkdocstrings also supports `"sphinx"` style or can autodetect in some cases.)
    

MkDocs will by default serve content from a `docs/` folder (different from Sphinx’s usage of a docs folder). If your documentation pages will reside in a different directory, you can specify `docs_dir` in the config. By default, `docs_dir: docs`.

### 3\. Write Documentation Pages (Markdown)

Create the folder `docs/` in your project root (if not already) and add Markdown files for your documentation content. For example, you might have:

*   `docs/index.md` – the homepage (introduction) of your docs.
    
*   `docs/usage.md` – guide on how to use the project.
    
*   `docs/api.md` – a page to serve as the API reference.
    

In the Markdown files, you can write normal prose and also include **autodoc** references using mkdocstrings. For instance, in `docs/api.md`, you could document your package’s modules like:

```markdown
# API Reference

## Module: your_project_package

::: your_project_package
```

The `::: your_project_package` syntax is provided by mkdocstrings. It will automatically insert documentation for that module (all classes, functions, etc. in it), formatted according to the docstrings. You can also target specific classes or functions:

```markdown
::: your_project_package.mymodule.MyClass
```

This would document only `MyClass` in that module, including its methods and docstring, etc. You can control the depth and which members to show with options (see mkdocstrings docs), but by default it shows public members.

**Docstring formats:** Because we set `docstring_style: google` in the config, mkdocstrings will parse Google-style sections (Args, Returns, etc.) properly[mkdocstrings.github.io](https://mkdocstrings.github.io/python/usage/configuration/docstrings/#:~:text=%2A%20%60,all%2C%20parse%20as%20regular%20text). If your project uses NumPy style, use that setting. Mkdocstrings uses the same conventions as Sphinx’s Napoleon for these styles, so the Google/NumPy examples shown earlier will render correctly in MkDocs as well.

Organize your `docs/` folder with any structure you like. You will list these pages in the nav in `mkdocs.yml` next.

### 4\. Configure the Documentation Structure (nav)

Edit `mkdocs.yml` to add a navigation structure for your pages. For example:

```yaml
nav:
- Home: index.md
- Usage Guide: usage.md
- API Reference: api.md
```

This ensures the pages appear in the top menu (or sidebar, depending on theme). The names (“Home”, “Usage Guide”, etc.) will appear as section titles.

You can have nested nav items (for example, multiple API pages or sections) by indenting as a list under a section.

### 5\. Preview and Build the MkDocs Site

During writing, you can preview the site with MkDocs’ built-in server:

```bash
mkdocs serve
```

This will run a local web server (usually at http://127.0.0.1:8000) and auto-reload when you edit files – very handy for iterative writing.

Once you’re satisfied, build the static site:

```bash
mkdocs build
```

This generates a `site/` directory containing HTML, CSS, JS, etc. for the entire documentation site. Verify that `site/index.html` loads correctly in a browser. The API reference page(s) should have content pulled from your docstrings. Mkdocstrings/Griffe will have parsed your Python package without needing to import it (it reads the source), so this method is resilient even if importing the package is tricky.

_Note:_ If mkdocstrings fails to find your modules, ensure your package is installed (e.g., in a virtualenv) or specify the path in `mkdocs.yml` plugin config (`watch` or `paths` options). Usually, if your code is in the repo, Griffe can find it if you give the module path in the `:::` tag.

Using **pdoc** as an Alternative (Optional)
-------------------------------------------

If your needs are mostly an API reference and you want minimal configuration, **pdoc** is a great option. With pdoc, you don’t write a separate docs site structure – it directly generates documentation from the code.

**Setup and usage:**

1.  Install pdoc: `pip install pdoc`
    
2.  Run it for your project, specifying output directory (and docformat if needed):
    
    ```bash
    pdoc --docformat google --output-dir docs_html your_project_package
    ```
    
    The `--docformat google` flag tells pdoc your docstrings follow Google style (use `numpy` for NumPy style)[pdoc.dev](https://pdoc.dev/docs/pdoc.html#:~:text=While%20pdoc%20prefers%20docstrings%20that,of%20these%20styles%2C%20you%20can). You can also set `__docformat__ = "google"` in your package’s `__init__.py` as an alternative trigger.
    
3.  This will generate HTML files in `docs_html/` (you can name it as you like). You can then publish these on GitHub Pages (for example, by copying to the `gh-pages` branch or the `docs/` folder in main, as discussed below).
    

pdoc by default produces a clean single-page-per-module documentation with navigation. It understands Google/NumPy sections and converts them to Markdown internally[pdoc.dev](https://pdoc.dev/docs/pdoc.html#:~:text=,then%20Numpydoc%20syntax%2C%20then%20Markdown). Customization is more limited compared to Sphinx/MkDocs, but it is the simplest to automate (just one command).

Publishing Documentation to **GitHub Pages**
--------------------------------------------

After generating your docs, you’ll want to host them. GitHub Pages is a free hosting service for static content, perfect for docs. There are two main approaches:

*   **Deploy from the `docs/` folder on the default branch** – If you put the built HTML in a `/docs` directory in your repository, you can tell GitHub to publish that. This is simple but requires committing build artifacts to your main branch (not always ideal).
    
*   **Use a `gh-pages` branch for the built site** – Keep documentation source in main, and have the CI publish the generated site to a separate branch. This keeps generated files out of your code history. GitHub Pages can then serve from the `gh-pages` branch.
    

Using a CI/CD pipeline (GitHub Actions) is the recommended, fully automated route. Below, we’ll outline an approach using GitHub Actions to build and deploy the docs on each push to main.

### 1\. Enable GitHub Pages in Repo Settings

Go to your repository’s **Settings > Pages**, and set it to deploy from the **gh-pages** branch (you can keep the folder as root of gh-pages). If you haven’t created a gh-pages branch yet, the Action we set up will do it for you on first deploy. Alternatively, you can choose the `docs/` folder on `main` as the source for Pages[docs.github.com](https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site#:~:text=branch,to%20your%20GitHub%20Pages%20site)[docs.github.com](https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site#:~:text=Publishing%20from%20a%20branch), but we’ll proceed with the branch method.

Ensure the repository is public (or if private, you have GitHub Pro for private Pages). Also, note that by default GitHub Pages ignores files with a leading underscore (Jekyll behavior). Sphinx already addresses this by generating a `.nojekyll` file if you include `sphinx.ext.githubpages` in conf.py. MkDocs and pdoc outputs typically include a `.nojekyll` as well (MkDocs does via ghp-import). This file tells GitHub Pages to serve files as-is.

### 2\. GitHub Actions Workflow for Docs

Create a workflow file (YAML) in `.github/workflows/`, for example `docs.yml`. Below is an example that covers both Sphinx and MkDocs scenarios (you would pick one, depending on your tool):

**Example: Sphinx Documentation Deployment** – This workflow installs dependencies, builds Sphinx docs, and deploys to gh-pages.

```yaml
name: Docs Deployment

on:
  push:
    branches: [ main ]

jobs:
  build-and-deploy:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout source
        uses: actions/checkout@v3

      - name: Setup Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.10'

      - name: Install Sphinx
        run: |
          pip install sphinx sphinx-rtd-theme sphinx-ext-napoleon sphinx-autodoc-typehints
          pip install -e .   # install your project if needed (for autodoc)
      - name: Build Docs
        run: sphinx-build -b html docs docs/_build/html

      - name: Deploy to GitHub Pages
        uses: peaceiris/actions-gh-pages@v3
        with:
          github_token: ${{ secrets.GITHUB_TOKEN }}
          publish_dir: docs/_build/html
```

In this workflow:

*   We use **peaceiris/actions-gh-pages**@v3, a popular Action that handles pushing content to the gh-pages branch[stackoverflow.com](https://stackoverflow.com/questions/73532719/using-github-actions-to-deploy-sphinx-documentation#:~:text=path%3A%20docs%2Fbuild%2Fhtml%2F). The `publish_dir` is set to the folder containing the built HTML.
    
*   We also install our project (`pip install -e .`) so that Sphinx can import it for autodoc. Adjust the Python version as needed.
    

**Example: MkDocs Documentation Deployment** – If using MkDocs, the workflow is similar but with different build steps:

```yaml
name: Docs Deployment

on:
  push:
    branches: [ main ]

jobs:
  build-and-deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - uses: actions/setup-python@v4
        with:
          python-version: '3.10'

      - name: Install MkDocs
        run: |
          pip install mkdocs mkdocs-material mkdocstrings[python]
          pip install -e .
      - name: Build Docs
        run: mkdocs build

      - name: Deploy to GitHub Pages
        uses: peaceiris/actions-gh-pages@v3
        with:
          github_token: ${{ secrets.GITHUB_TOKEN }}
          publish_dir: site
```

Here we install MkDocs and related plugins, build the site (output goes to `site/` directory by default[mkdocs.org](https://www.mkdocs.org/user-guide/deploying-your-docs/#:~:text=mkdocs%20gh)), then deploy that. The peaceiris action will push the `site/` contents to the gh-pages branch.

**How it works:** On each push to main, the Action will run, building the latest docs and updating GitHub Pages. Typically, within a minute or two of the push, the live documentation site (your GitHub Pages URL) will reflect the new docs. There’s no need for manual intervention.

**Note:** If you prefer not to use the third-party action, you could run `mkdocs gh-deploy` with a token, or use `ghp-import` manually in a run step. But the above action simplifies it. MkDocs’ own documentation notes that `mkdocs gh-deploy` uses `ghp-import` to push to gh-pages branch[mkdocs.org](https://www.mkdocs.org/user-guide/deploying-your-docs/#:~:text=mkdocs%20gh).

### 3\. (Alternative) Publishing from `/docs` folder on main

As mentioned, you could also commit the built HTML to a `docs/` folder on your main branch and configure Pages to serve from there[docs.github.com](https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site#:~:text=branch,to%20your%20GitHub%20Pages%20site). In that case, your Action would build the docs and then commit the HTML files into `docs/` on the main branch. However, this approach clutters your repository with built files. The separate branch method is cleaner and is the one we detailed.

### 4\. Verify on GitHub Pages

Once the Action has run, go to your repository’s **Settings > Pages** to find the URL of your site (it will be something like `https://<username>.github.io/<repo>/`). Open that in a browser to see your live docs. Because we included `sphinx.ext.githubpages` (for Sphinx) or MkDocs added a `.nojekyll`, it should load correctly without Jekyll interference. You can now direct users to this site for documentation.

Optional Enhancements: Versioning, Theming, and Localization
------------------------------------------------------------

With the core pipeline in place, you may consider some advanced features for your documentation:

### Versioning Documentation

If you release versions of your package and want to keep documentation for each version available, you can implement versioned docs:

*   **Sphinx**: One approach is to maintain separate builds for each version and deploy them to different subfolders on GitHub Pages (e.g. `v1.x/`, `v2.x/`). You can script this or use tools. Another approach is to use **Read the Docs** which has built-in versioning if you host there. There is also a Sphinx extension `sphinx-multiversion` that can build multiple versions simultaneously, but it may require CI setup to iterate over tags.
    
*   **MkDocs**: The **mike** tool is specifically made for versioned MkDocs on GitHub Pages. It lets you deploy multiple versions to gh-pages and even generates a version selector banner. _Quote:_ “mike is a Python utility to easily deploy multiple versions of your MkDocs-powered docs to a Git branch, suitable for deploying to Github via gh-pages”[pypi.org](https://pypi.org/project/mike/0.3.4/#:~:text=mike%20is%20a%20Python%20utility,pages). Essentially, you would build docs for each release (maybe triggered on tagging a release) and use `mike deploy X.Y` to add that version’s docs to gh-pages without clobbering older versions. The Material theme documentation provides guidance on integrating mike with a version selector dropdown.
    

Whichever method, the idea is to have URLs like `/1.0/`, `/2.0/` for different versions, and possibly one for “latest” that points to the main branch docs.

### Theming and Styling

Out-of-the-box themes are usually sufficient, but you can customize the look:

*   **Sphinx**: Many themes are available. The **sphinx\_rtd\_theme** (Read the Docs theme) is a common default.[stackoverflow.com](https://stackoverflow.com/questions/73532719/using-github-actions-to-deploy-sphinx-documentation#:~:text=The%20content%20of%20my%20,file) In `conf.py` you can set `html_theme` and also provide custom CSS/JS by placing files in `_static` and adding paths in `html_css_files`. For a modern look, check out **Furo** or **Sphinx Book Theme**.
    
*   **MkDocs**: The **Material for MkDocs** theme is highly customizable via the config (colors, fonts, logos, etc.). You can set `theme:` options in `mkdocs.yml` (see Material’s documentation). There are also other MkDocs themes on PyPI you can use. Since Material is so prevalent, it’s a safe choice for mainstream use.
    
*   **pdoc**: It has a relatively minimal theme but you can override its templates or CSS if needed[pdoc.dev](https://pdoc.dev/docs/pdoc.html#:~:text=As%20a%20last%20resort%2C%20you,template%2Fmodule.html.jinja2)[pdoc.dev](https://pdoc.dev/docs/pdoc.html#:~:text=%28sub%29module%20names%20that%20match,foo.bar). Most often, if you need heavy customization, switching to Sphinx or MkDocs might be easier.
    

### Multi-Language Support (Localization)

If you need to provide documentation in multiple languages:

*   **Sphinx** has built-in i18n support. You can extract translatable text from your RST files using `sphinx-intl` or via `make gettext`, produce `.pot/.po` files for translators, then build the docs for each language by setting `language` in `conf.py` or via command-line. The output can be organized into subdirectories (e.g., `en/`, `fr/` for English and French).
    
*   **MkDocs** does not natively support multiple languages in one build, but it can be achieved by running separate builds for each language. The Material theme documentation suggests creating one docs folder per language (e.g., `docs/en/`, `docs/fr/`) and then using a plugin like mkdocs-static-i18n[pypi.org](https://pypi.org/project/mkdocs-static-i18n/#:~:text=MkDocs%20static%20i18n%20plugin%20,to%20your%20existing%20documentation) to combine them. Essentially, you maintain translations of each page in parallel folders. The theme can provide a language switcher. This requires a bit more setup, but several projects have done it.
    
*   If maintaining translations is too complex, an alternative is to use a service or just maintain a single language. Many open-source projects use English as the primary docs language for simplicity.
    

* * *

By leveraging these tools and approaches, you can have a **fully automated documentation pipeline** for your Python project. Write clear docstrings in a standard format, generate reference and guide pages with Sphinx or MkDocs, and let GitHub Actions publish it to GitHub Pages on every update. This ensures your documentation is always up-to-date with your code – increasing user trust and understanding of your project.

**Sources:**

*   Sphinx Napoleon (Google/NumPy docstring support)[sphinx-doc.org](https://www.sphinx-doc.org/en/master/usage/extensions/napoleon.html#:~:text=True%20to%20parse%20Google%20style,support%20for%20Google%20style%20docstrings)[sphinx-doc.org](https://www.sphinx-doc.org/en/master/usage/extensions/napoleon.html#:~:text=True%20to%20parse%20NumPy%20style,support%20for%20NumPy%20style%20docstrings)
    
*   MkDocstrings docstring style support[mkdocstrings.github.io](https://mkdocstrings.github.io/python/usage/configuration/docstrings/#:~:text=%2A%20Type%20str%20%20%60)
    
*   pdoc docstring format support[pdoc.dev](https://pdoc.dev/docs/pdoc.html#:~:text=While%20pdoc%20prefers%20docstrings%20that,of%20these%20styles%2C%20you%20can)[pdoc.dev](https://pdoc.dev/docs/pdoc.html#:~:text=,then%20Numpydoc%20syntax%2C%20then%20Markdown)
    
*   MkDocs deployment to GitHub Pages[mkdocs.org](https://www.mkdocs.org/user-guide/deploying-your-docs/#:~:text=mkdocs%20gh)
    
*   GitHub Actions deploying to Pages (example)[stackoverflow.com](https://stackoverflow.com/questions/73532719/using-github-actions-to-deploy-sphinx-documentation#:~:text=path%3A%20docs%2Fbuild%2Fhtml%2F)
    
*   Mike tool for MkDocs versioning[pypi.org](https://pypi.org/project/mike/0.3.4/#:~:text=mike%20is%20a%20Python%20utility,pages)

## Prompt:
Automated Python Documentation Pipeline with GitHub Pages

Automated Documentation Pipeline for Python Projects
====================================================

Overview and Tools
------------------

High-quality documentation is crucial for any Python project. The good news is there are mature tools to generate documentation automatically from your code and docstrings. The most widely adopted solutions are **Sphinx**, **MkDocs**, and **pdoc**. Each of these supports standard docstring formats (Google style, NumPy style, Markdown, etc.) and can produce a professional static website for your docs. Below is a brief overview of these tools:

*   **Sphinx** – A powerful documentation generator that uses _reStructuredText_ by default, but with the **Napoleon** extension it can parse Google-style and NumPy-style docstrings[sphinx-doc.org](https://www.sphinx-doc.org/en/master/usage/extensions/napoleon.html#:~:text=True%20to%20parse%20Google%20style,support%20for%20Google%20style%20docstrings)[sphinx-doc.org](https://www.sphinx-doc.org/en/master/usage/extensions/napoleon.html#:~:text=True%20to%20parse%20NumPy%20style,support%20for%20NumPy%20style%20docstrings). Sphinx is widely used (e.g. on Read the Docs) and supports many extensions, theming options, and PDF/EPUB output.
    
*   **MkDocs** – A static site generator geared towards project documentation. It uses Markdown for content and has a popular **Material for MkDocs** theme. With the **mkdocstrings** plugin, MkDocs can automatically document code and supports Google/NumPy docstrings[mkdocstrings.github.io](https://mkdocstrings.github.io/python/usage/configuration/docstrings/#:~:text=%2A%20Type%20str%20%20%60). It produces a sleek web docs site with search functionality.
    
*   **pdoc** – A lightweight documentation generator that directly reads your Python docstrings and outputs HTML or Markdown. It natively supports Google and NumPy docstring formats (converting them to Markdown)[pdoc.dev](https://pdoc.dev/docs/pdoc.html#:~:text=While%20pdoc%20prefers%20docstrings%20that,of%20these%20styles%2C%20you%20can)[pdoc.dev](https://pdoc.dev/docs/pdoc.html#:~:text=,then%20Numpydoc%20syntax%2C%20then%20Markdown). pdoc is easy to set up for simple API reference docs.
    

All of these can be integrated into an automated pipeline. The typical workflow is: write clear docstrings in a standard style, use one of the tools to generate HTML documentation from those docstrings (and any additional docs you write), then automatically publish the site to **GitHub Pages** via **GitHub Actions**. In the sections below, we’ll set up a documentation pipeline step-by-step using Sphinx and MkDocs (as primary examples), and mention how to adapt for pdoc. We’ll also cover optional features like versioning, theming, and localization.

Setting Up Documentation with **Sphinx**
----------------------------------------

Sphinx is a robust choice for generating documentation from Python source code. Follow these steps to configure Sphinx for your project:

### 1\. Install Sphinx and Extensions

Begin by installing Sphinx and some useful extensions in your Python environment (you can use pip):

```bash
pip install sphinx sphinx-rtd-theme sphinx-ext-napoleon sphinx-autodoc-typehints
```

*   **sphinx-rtd-theme**: Common theme (Read the Docs style) for a clean look.
    
*   **sphinx-ext-napoleon**: The Napoleon extension to parse Google/NumPy style docstrings[sphinx-doc.org](https://www.sphinx-doc.org/en/master/usage/extensions/napoleon.html#:~:text=True%20to%20parse%20Google%20style,support%20for%20Google%20style%20docstrings).
    
*   **sphinx-autodoc-typehints**: Optional, to automatically include type hints in the docs.
    

_(Alternatively, you can install Sphinx via Poetry or conda depending on your setup.)_

### 2\. Run Sphinx Quickstart

Sphinx provides a quick-start utility to initialize a docs folder. From your project root, run:

```bash
sphinx-quickstart docs
```

This will interactively ask some questions. You can accept defaults, but make sure to choose **yes** for “autodoc” support if prompted (this adds the `sphinx.ext.autodoc` extension for pulling in docstrings). The quickstart will create a `docs/` directory with a basic configuration:

*   `docs/conf.py`: Configuration file for Sphinx.
    
*   `docs/index.rst`: The root document.
    
*   Makefile and/or batch file for building (optional, depending on options).
    

### 3\. Configure `conf.py` for Docstrings and Themes

Open `docs/conf.py` in a text editor. We need to enable the extensions and configure Sphinx to understand our docstring style:

*   Enable the **autodoc** and **napoleon** extensions by adding them to the `extensions` list:
    
    ```python
    extensions = [
        "sphinx.ext.autodoc",
        "sphinx.ext.napoleon",
        "sphinx.ext.viewcode",     # shows source code in docs
        "sphinx.ext.githubpages"   # adds .nojekyll for GitHub Pages
    ]
    ```
    
    _Napoleon_ allows Sphinx to parse Google and NumPy style docstrings and convert them to the proper format internally[sphinx-doc.org](https://www.sphinx-doc.org/en/master/usage/extensions/napoleon.html#:~:text=True%20to%20parse%20Google%20style,support%20for%20Google%20style%20docstrings). By default, Napoleon is enabled with both `napoleon_google_docstring = True` and `napoleon_numpy_docstring = True`[sphinx-doc.org](https://www.sphinx-doc.org/en/master/usage/extensions/napoleon.html#:~:text=True%20to%20parse%20Google%20style,support%20for%20Google%20style%20docstrings)[sphinx-doc.org](https://www.sphinx-doc.org/en/master/usage/extensions/napoleon.html#:~:text=True%20to%20parse%20NumPy%20style,support%20for%20NumPy%20style%20docstrings), so it will handle either style automatically.
    
*   Set the project information at the top (project name, author, version).
    
*   Choose a HTML theme. For example, to use the ReadTheDocs theme:
    
    ```python
    html_theme = "sphinx_rtd_theme"
    ```
    
    Make sure you installed `sphinx-rtd-theme` as shown earlier. Sphinx has many themes; you can also try `"furo"` or the default `"alabaster"`.
    
*   (Optional) If using type hints in your code and sphinx-autodoc-typehints, add:
    
    ```python
    extensions.append("sphinx_autodoc_typehints")
    ```
    
    This will integrate Python type hints into the parameter documentation.
    
*   Ensure `templates_path` and `exclude_patterns` are set appropriately (defaults are usually fine). The `master_doc` (or `root_doc` in newer Sphinx) should point to `index` by default.
    

After configuring, save `conf.py`. Sphinx is now set to extract documentation from your code’s docstrings.

### 4\. Write Docstrings in a Supported Style

With Napoleon enabled, you can write docstrings in **Google style** or **NumPy style** (or even in reStructuredText). For example, a Google-style docstring:

```python
def add(x, y):
    """Add two numbers.

    Args:
        x (int): The first number.
        y (int): The second number.

    Returns:
        int: The sum of x and y.
    """
    return x + y
```

Napoleon will parse sections like **Args**, **Returns**, etc., and format them properly in the output[sphinx-doc.org](https://www.sphinx-doc.org/en/master/usage/extensions/napoleon.html#:~:text=Google%20style%20docstrings%20and%20converts,your%20actual%20source%20code%20files). If you prefer NumPy style:

```python
def add(x, y):
    """Add two numbers.

    Parameters
    ----------
    x : int
        The first number.
    y : int
        The second number.

    Returns
    -------
    int
        The sum of x and y.
    """
    return x + y
```

This will also be understood by Napoleon and converted appropriately.

### 5\. Generate API Documentation Pages

Sphinx can automatically create RST files listing your modules and classes using the **apidoc** tool. Run the following command (adjusting package path and output directory):

```bash
sphinx-apidoc -o docs/source/ your_project_package/
```

*   `your_project_package/` is the path to your Python package or module.
    
*   `-o docs/source/` tells Sphinx to place the generated `.rst` files in `docs/source` (you might need to create `docs/source` or adjust if your structure differs).
    

The `sphinx-apidoc` tool will create `.rst` files for each module, with `.. automodule::` and `.. autofunction::` directives to pull in docstrings via autodoc[sphinx-doc.org](https://www.sphinx-doc.org/en/master/man/sphinx-apidoc.html#:~:text=Description%C2%B6). It also creates a `modules.rst` (table of contents of modules). Include these generated files in your main `index.rst` or another toctree so Sphinx knows to build them. For example, in `index.rst` you might add:

```rst
.. toctree::
   :maxdepth: 2
   :caption: API Reference

   modules
```

_(Alternatively,_ instead of using sphinx-apidoc, you can manually create `.rst` files and use directives like `.. automodule:: module.name` with `:members:` to document all functions/classes in that module. Another advanced option is **sphinx-autoapi** which parses code without importing it, but sphinx-apidoc + autodoc is simpler for most cases.)\*

### 6\. Build the Documentation Locally

Now build the HTML documentation to verify everything works:

*   If you have a Makefile, simply run: `make html` (from the `docs/` directory).
    
*   Without Makefile, use:
    
    ```bash
    sphinx-build -b html docs docs/_build/html
    ```
    

This tells Sphinx to take the content in `docs/` (it looks for `conf.py` and `index.rst` there) and generate a static HTML site in `docs/_build/html`. After a successful build, open `docs/_build/html/index.html` in a browser to see your documentation. It should have the API reference pulled from your code’s docstrings, formatted nicely.

**Troubleshooting:** If Sphinx can’t import your project modules (for autodoc), you may need to adjust the `sys.path` in `conf.py` to include your project path. For example, add:

```python
import os
import sys
sys.path.insert(0, os.path.abspath(".."))
```

if your project is one level up from `docs/`.

Setting Up Documentation with **MkDocs**
----------------------------------------

MkDocs offers a modern approach using Markdown for documentation pages. We will use the **mkdocstrings** plugin to integrate API docs from docstrings. Here’s how to set up a MkDocs documentation pipeline:

### 1\. Install MkDocs and Plugins

Install MkDocs and the necessary plugins with pip:

```bash
pip install mkdocs mkdocs-material mkdocstrings[python]
```

*   **mkdocs-material**: Provides the popular Material theme (you can choose others, but Material is feature-rich and widely used).
    
*   **mkdocstrings\[python\]**: The mkdocstrings plugin with Python handler (the `[python]` extra installs the Python-specific parser, which uses the _Griffe_ library under the hood to parse code and docstrings).
    

### 2\. Create a MkDocs Configuration

In your project root, create a file named `mkdocs.yml`. This is the config for MkDocs. A basic configuration would look like:

```yaml
site_name: MyProject Documentation
site_url: "https://yourusername.github.io/yourproject/"  # optional, for sitemap
theme:
  name: material
plugins:
  - search
  - mkdocstrings:
      default_handler: python
      handlers:
        python:
          options:
            docstring_style: google
```

Key points in this config:

*   `site_name` is the title of your documentation site.
    
*   We selected the **Material** theme for a polished look (comes with built-in search and many features).
    
*   Enabled the **search** plugin (usually on by default with Material).
    
*   Added **mkdocstrings** plugin. We specify the default handler as Python and pass an option to indicate the docstring style. Here we chose `"google"` style, which means mkdocstrings/Griffe will expect Google-style formatting for sections[mkdocstrings.github.io](https://mkdocstrings.github.io/python/usage/configuration/docstrings/#:~:text=%2A%20%60,all%2C%20parse%20as%20regular%20text). If you use NumPy style, set `docstring_style: numpy`. (Mkdocstrings also supports `"sphinx"` style or can autodetect in some cases.)
    

MkDocs will by default serve content from a `docs/` folder (different from Sphinx’s usage of a docs folder). If your documentation pages will reside in a different directory, you can specify `docs_dir` in the config. By default, `docs_dir: docs`.

### 3\. Write Documentation Pages (Markdown)

Create the folder `docs/` in your project root (if not already) and add Markdown files for your documentation content. For example, you might have:

*   `docs/index.md` – the homepage (introduction) of your docs.
    
*   `docs/usage.md` – guide on how to use the project.
    
*   `docs/api.md` – a page to serve as the API reference.
    

In the Markdown files, you can write normal prose and also include **autodoc** references using mkdocstrings. For instance, in `docs/api.md`, you could document your package’s modules like:

```markdown
# API Reference

## Module: your_project_package

::: your_project_package
```

The `::: your_project_package` syntax is provided by mkdocstrings. It will automatically insert documentation for that module (all classes, functions, etc. in it), formatted according to the docstrings. You can also target specific classes or functions:

```markdown
::: your_project_package.mymodule.MyClass
```

This would document only `MyClass` in that module, including its methods and docstring, etc. You can control the depth and which members to show with options (see mkdocstrings docs), but by default it shows public members.

**Docstring formats:** Because we set `docstring_style: google` in the config, mkdocstrings will parse Google-style sections (Args, Returns, etc.) properly[mkdocstrings.github.io](https://mkdocstrings.github.io/python/usage/configuration/docstrings/#:~:text=%2A%20%60,all%2C%20parse%20as%20regular%20text). If your project uses NumPy style, use that setting. Mkdocstrings uses the same conventions as Sphinx’s Napoleon for these styles, so the Google/NumPy examples shown earlier will render correctly in MkDocs as well.

Organize your `docs/` folder with any structure you like. You will list these pages in the nav in `mkdocs.yml` next.

### 4\. Configure the Documentation Structure (nav)

Edit `mkdocs.yml` to add a navigation structure for your pages. For example:

```yaml
nav:
- Home: index.md
- Usage Guide: usage.md
- API Reference: api.md
```

This ensures the pages appear in the top menu (or sidebar, depending on theme). The names (“Home”, “Usage Guide”, etc.) will appear as section titles.

You can have nested nav items (for example, multiple API pages or sections) by indenting as a list under a section.

### 5\. Preview and Build the MkDocs Site

During writing, you can preview the site with MkDocs’ built-in server:

```bash
mkdocs serve
```

This will run a local web server (usually at http://127.0.0.1:8000) and auto-reload when you edit files – very handy for iterative writing.

Once you’re satisfied, build the static site:

```bash
mkdocs build
```

This generates a `site/` directory containing HTML, CSS, JS, etc. for the entire documentation site. Verify that `site/index.html` loads correctly in a browser. The API reference page(s) should have content pulled from your docstrings. Mkdocstrings/Griffe will have parsed your Python package without needing to import it (it reads the source), so this method is resilient even if importing the package is tricky.

_Note:_ If mkdocstrings fails to find your modules, ensure your package is installed (e.g., in a virtualenv) or specify the path in `mkdocs.yml` plugin config (`watch` or `paths` options). Usually, if your code is in the repo, Griffe can find it if you give the module path in the `:::` tag.

Using **pdoc** as an Alternative (Optional)
-------------------------------------------

If your needs are mostly an API reference and you want minimal configuration, **pdoc** is a great option. With pdoc, you don’t write a separate docs site structure – it directly generates documentation from the code.

**Setup and usage:**

1.  Install pdoc: `pip install pdoc`
    
2.  Run it for your project, specifying output directory (and docformat if needed):
    
    ```bash
    pdoc --docformat google --output-dir docs_html your_project_package
    ```
    
    The `--docformat google` flag tells pdoc your docstrings follow Google style (use `numpy` for NumPy style)[pdoc.dev](https://pdoc.dev/docs/pdoc.html#:~:text=While%20pdoc%20prefers%20docstrings%20that,of%20these%20styles%2C%20you%20can). You can also set `__docformat__ = "google"` in your package’s `__init__.py` as an alternative trigger.
    
3.  This will generate HTML files in `docs_html/` (you can name it as you like). You can then publish these on GitHub Pages (for example, by copying to the `gh-pages` branch or the `docs/` folder in main, as discussed below).
    

pdoc by default produces a clean single-page-per-module documentation with navigation. It understands Google/NumPy sections and converts them to Markdown internally[pdoc.dev](https://pdoc.dev/docs/pdoc.html#:~:text=,then%20Numpydoc%20syntax%2C%20then%20Markdown). Customization is more limited compared to Sphinx/MkDocs, but it is the simplest to automate (just one command).

Publishing Documentation to **GitHub Pages**
--------------------------------------------

After generating your docs, you’ll want to host them. GitHub Pages is a free hosting service for static content, perfect for docs. There are two main approaches:

*   **Deploy from the `docs/` folder on the default branch** – If you put the built HTML in a `/docs` directory in your repository, you can tell GitHub to publish that. This is simple but requires committing build artifacts to your main branch (not always ideal).
    
*   **Use a `gh-pages` branch for the built site** – Keep documentation source in main, and have the CI publish the generated site to a separate branch. This keeps generated files out of your code history. GitHub Pages can then serve from the `gh-pages` branch.
    

Using a CI/CD pipeline (GitHub Actions) is the recommended, fully automated route. Below, we’ll outline an approach using GitHub Actions to build and deploy the docs on each push to main.

### 1\. Enable GitHub Pages in Repo Settings

Go to your repository’s **Settings > Pages**, and set it to deploy from the **gh-pages** branch (you can keep the folder as root of gh-pages). If you haven’t created a gh-pages branch yet, the Action we set up will do it for you on first deploy. Alternatively, you can choose the `docs/` folder on `main` as the source for Pages[docs.github.com](https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site#:~:text=branch,to%20your%20GitHub%20Pages%20site)[docs.github.com](https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site#:~:text=Publishing%20from%20a%20branch), but we’ll proceed with the branch method.

Ensure the repository is public (or if private, you have GitHub Pro for private Pages). Also, note that by default GitHub Pages ignores files with a leading underscore (Jekyll behavior). Sphinx already addresses this by generating a `.nojekyll` file if you include `sphinx.ext.githubpages` in conf.py. MkDocs and pdoc outputs typically include a `.nojekyll` as well (MkDocs does via ghp-import). This file tells GitHub Pages to serve files as-is.

### 2\. GitHub Actions Workflow for Docs

Create a workflow file (YAML) in `.github/workflows/`, for example `docs.yml`. Below is an example that covers both Sphinx and MkDocs scenarios (you would pick one, depending on your tool):

**Example: Sphinx Documentation Deployment** – This workflow installs dependencies, builds Sphinx docs, and deploys to gh-pages.

```yaml
name: Docs Deployment

on:
  push:
    branches: [ main ]

jobs:
  build-and-deploy:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout source
        uses: actions/checkout@v3

      - name: Setup Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.10'

      - name: Install Sphinx
        run: |
          pip install sphinx sphinx-rtd-theme sphinx-ext-napoleon sphinx-autodoc-typehints
          pip install -e .   # install your project if needed (for autodoc)
      - name: Build Docs
        run: sphinx-build -b html docs docs/_build/html

      - name: Deploy to GitHub Pages
        uses: peaceiris/actions-gh-pages@v3
        with:
          github_token: ${{ secrets.GITHUB_TOKEN }}
          publish_dir: docs/_build/html
```

In this workflow:

*   We use **peaceiris/actions-gh-pages**@v3, a popular Action that handles pushing content to the gh-pages branch[stackoverflow.com](https://stackoverflow.com/questions/73532719/using-github-actions-to-deploy-sphinx-documentation#:~:text=path%3A%20docs%2Fbuild%2Fhtml%2F). The `publish_dir` is set to the folder containing the built HTML.
    
*   We also install our project (`pip install -e .`) so that Sphinx can import it for autodoc. Adjust the Python version as needed.
    

**Example: MkDocs Documentation Deployment** – If using MkDocs, the workflow is similar but with different build steps:

```yaml
name: Docs Deployment

on:
  push:
    branches: [ main ]

jobs:
  build-and-deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - uses: actions/setup-python@v4
        with:
          python-version: '3.10'

      - name: Install MkDocs
        run: |
          pip install mkdocs mkdocs-material mkdocstrings[python]
          pip install -e .
      - name: Build Docs
        run: mkdocs build

      - name: Deploy to GitHub Pages
        uses: peaceiris/actions-gh-pages@v3
        with:
          github_token: ${{ secrets.GITHUB_TOKEN }}
          publish_dir: site
```

Here we install MkDocs and related plugins, build the site (output goes to `site/` directory by default[mkdocs.org](https://www.mkdocs.org/user-guide/deploying-your-docs/#:~:text=mkdocs%20gh)), then deploy that. The peaceiris action will push the `site/` contents to the gh-pages branch.

**How it works:** On each push to main, the Action will run, building the latest docs and updating GitHub Pages. Typically, within a minute or two of the push, the live documentation site (your GitHub Pages URL) will reflect the new docs. There’s no need for manual intervention.

**Note:** If you prefer not to use the third-party action, you could run `mkdocs gh-deploy` with a token, or use `ghp-import` manually in a run step. But the above action simplifies it. MkDocs’ own documentation notes that `mkdocs gh-deploy` uses `ghp-import` to push to gh-pages branch[mkdocs.org](https://www.mkdocs.org/user-guide/deploying-your-docs/#:~:text=mkdocs%20gh).

### 3\. (Alternative) Publishing from `/docs` folder on main

As mentioned, you could also commit the built HTML to a `docs/` folder on your main branch and configure Pages to serve from there[docs.github.com](https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site#:~:text=branch,to%20your%20GitHub%20Pages%20site). In that case, your Action would build the docs and then commit the HTML files into `docs/` on the main branch. However, this approach clutters your repository with built files. The separate branch method is cleaner and is the one we detailed.

### 4\. Verify on GitHub Pages

Once the Action has run, go to your repository’s **Settings > Pages** to find the URL of your site (it will be something like `https://<username>.github.io/<repo>/`). Open that in a browser to see your live docs. Because we included `sphinx.ext.githubpages` (for Sphinx) or MkDocs added a `.nojekyll`, it should load correctly without Jekyll interference. You can now direct users to this site for documentation.

Optional Enhancements: Versioning, Theming, and Localization
------------------------------------------------------------

With the core pipeline in place, you may consider some advanced features for your documentation:

### Versioning Documentation

If you release versions of your package and want to keep documentation for each version available, you can implement versioned docs:

*   **Sphinx**: One approach is to maintain separate builds for each version and deploy them to different subfolders on GitHub Pages (e.g. `v1.x/`, `v2.x/`). You can script this or use tools. Another approach is to use **Read the Docs** which has built-in versioning if you host there. There is also a Sphinx extension `sphinx-multiversion` that can build multiple versions simultaneously, but it may require CI setup to iterate over tags.
    
*   **MkDocs**: The **mike** tool is specifically made for versioned MkDocs on GitHub Pages. It lets you deploy multiple versions to gh-pages and even generates a version selector banner. _Quote:_ “mike is a Python utility to easily deploy multiple versions of your MkDocs-powered docs to a Git branch, suitable for deploying to Github via gh-pages”[pypi.org](https://pypi.org/project/mike/0.3.4/#:~:text=mike%20is%20a%20Python%20utility,pages). Essentially, you would build docs for each release (maybe triggered on tagging a release) and use `mike deploy X.Y` to add that version’s docs to gh-pages without clobbering older versions. The Material theme documentation provides guidance on integrating mike with a version selector dropdown.
    

Whichever method, the idea is to have URLs like `/1.0/`, `/2.0/` for different versions, and possibly one for “latest” that points to the main branch docs.

### Theming and Styling

Out-of-the-box themes are usually sufficient, but you can customize the look:

*   **Sphinx**: Many themes are available. The **sphinx\_rtd\_theme** (Read the Docs theme) is a common default.[stackoverflow.com](https://stackoverflow.com/questions/73532719/using-github-actions-to-deploy-sphinx-documentation#:~:text=The%20content%20of%20my%20,file) In `conf.py` you can set `html_theme` and also provide custom CSS/JS by placing files in `_static` and adding paths in `html_css_files`. For a modern look, check out **Furo** or **Sphinx Book Theme**.
    
*   **MkDocs**: The **Material for MkDocs** theme is highly customizable via the config (colors, fonts, logos, etc.). You can set `theme:` options in `mkdocs.yml` (see Material’s documentation). There are also other MkDocs themes on PyPI you can use. Since Material is so prevalent, it’s a safe choice for mainstream use.
    
*   **pdoc**: It has a relatively minimal theme but you can override its templates or CSS if needed[pdoc.dev](https://pdoc.dev/docs/pdoc.html#:~:text=As%20a%20last%20resort%2C%20you,template%2Fmodule.html.jinja2)[pdoc.dev](https://pdoc.dev/docs/pdoc.html#:~:text=%28sub%29module%20names%20that%20match,foo.bar). Most often, if you need heavy customization, switching to Sphinx or MkDocs might be easier.
    

### Multi-Language Support (Localization)

If you need to provide documentation in multiple languages:

*   **Sphinx** has built-in i18n support. You can extract translatable text from your RST files using `sphinx-intl` or via `make gettext`, produce `.pot/.po` files for translators, then build the docs for each language by setting `language` in `conf.py` or via command-line. The output can be organized into subdirectories (e.g., `en/`, `fr/` for English and French).
    
*   **MkDocs** does not natively support multiple languages in one build, but it can be achieved by running separate builds for each language. The Material theme documentation suggests creating one docs folder per language (e.g., `docs/en/`, `docs/fr/`) and then using a plugin like mkdocs-static-i18n[pypi.org](https://pypi.org/project/mkdocs-static-i18n/#:~:text=MkDocs%20static%20i18n%20plugin%20,to%20your%20existing%20documentation) to combine them. Essentially, you maintain translations of each page in parallel folders. The theme can provide a language switcher. This requires a bit more setup, but several projects have done it.
    
*   If maintaining translations is too complex, an alternative is to use a service or just maintain a single language. Many open-source projects use English as the primary docs language for simplicity.
    

* * *

By leveraging these tools and approaches, you can have a **fully automated documentation pipeline** for your Python project. Write clear docstrings in a standard format, generate reference and guide pages with Sphinx or MkDocs, and let GitHub Actions publish it to GitHub Pages on every update. This ensures your documentation is always up-to-date with your code – increasing user trust and understanding of your project.

**Sources:**

*   Sphinx Napoleon (Google/NumPy docstring support)[sphinx-doc.org](https://www.sphinx-doc.org/en/master/usage/extensions/napoleon.html#:~:text=True%20to%20parse%20Google%20style,support%20for%20Google%20style%20docstrings)[sphinx-doc.org](https://www.sphinx-doc.org/en/master/usage/extensions/napoleon.html#:~:text=True%20to%20parse%20NumPy%20style,support%20for%20NumPy%20style%20docstrings)
    
*   MkDocstrings docstring style support[mkdocstrings.github.io](https://mkdocstrings.github.io/python/usage/configuration/docstrings/#:~:text=%2A%20Type%20str%20%20%60)
    
*   pdoc docstring format support[pdoc.dev](https://pdoc.dev/docs/pdoc.html#:~:text=While%20pdoc%20prefers%20docstrings%20that,of%20these%20styles%2C%20you%20can)[pdoc.dev](https://pdoc.dev/docs/pdoc.html#:~:text=,then%20Numpydoc%20syntax%2C%20then%20Markdown)
    
*   MkDocs deployment to GitHub Pages[mkdocs.org](https://www.mkdocs.org/user-guide/deploying-your-docs/#:~:text=mkdocs%20gh)
    
*   GitHub Actions deploying to Pages (example)[stackoverflow.com](https://stackoverflow.com/questions/73532719/using-github-actions-to-deploy-sphinx-documentation#:~:text=path%3A%20docs%2Fbuild%2Fhtml%2F)
    
*   Mike tool for MkDocs versioning[pypi.org](https://pypi.org/project/mike/0.3.4/#:~:text=mike%20is%20a%20Python%20utility,pages)
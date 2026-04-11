Publishing API documentation for a PureScript project can be fully automated. We will use **Spago**, the community-recommended build tool for PureScript, to generate documentation, then convert it into a polished static site. Spago leverages the PureScript compiler to produce documentation (similar to Pursuit) for your code[npmjs.com](https://www.npmjs.com/package/spago#:~:text=To%20build%20documentation%20for%20your,command). To enhance the visual appeal, we can feed the docs into a static site generator like **MkDocs** (with a modern theme such as _Material for MkDocs_). Finally, we’ll set up a Python script and a GitHub Actions workflow to automatically generate and deploy the documentation to the `gh-pages` branch on every release or push. This ensures your documentation is always up-to-date and beautifully presented.

Setting Up Documentation Generation with Spago
----------------------------------------------

The first step is to install PureScript and Spago, and then use Spago to generate your project’s documentation.

**Prerequisites:** Make sure you have Node.js installed. Then install the PureScript compiler and Spago via npm (the PureScript website recommends this method[purescript.org](https://www.purescript.org/#:~:text=The%20recommended%20build%20tool%20for,npm)):

```bash
npm install -g purescript spago   # Installs PureScript compiler (`purs`) and Spago
```

This gives you the `purs` compiler and the `spago` CLI tool on your PATH.

**1\. Generate documentation using Spago:**  
Spago can produce documentation for your project **and its dependencies**. By default, it emits a static HTML documentation site (analogous to a local Pursuit index). Simply run:

```bash
spago docs
```

This will compile your project (if not already built) and extract documentation from your source code. The output will be placed in a `generated-docs` directory. In particular, an `index.html` is generated as the entry point[npmjs.com](https://www.npmjs.com/package/spago#:~:text=To%20build%20documentation%20for%20your,command). You can open this file to browse the docs locally. The Spago-generated site includes all modules in your project _and_ any dependencies, complete with function/type documentation. It even provides a search interface out-of-the-box, thanks to the integrated **Docs Search** app[github.com](https://github.com/purescript/purescript-docs-search#:~:text=Installing).

> **Note:** Ensure your PureScript source files have proper documentation comments (e.g. preceding functions with `-- |` or `/** ... */` style comments). Spago/Pursuit will include those descriptions in the generated docs. Modules and declarations without comments will still appear but with minimal info.

**2\. Optional – Generate Markdown instead of HTML:**  
If you prefer to post-process or restyle the docs, Spago can output Markdown format. Spago supports multiple output formats – HTML by default, but also markdown, ctags, etc[github.com](https://github.com/purescript/spago#:~:text=You%20can%20customize%20the%20output,for%20use%20in%20your%20editor). For example:

```bash
spago docs --format markdown
```

This will produce a series of Markdown files (instead of HTML) under `generated-docs` (likely in a subfolder like `generated-docs/markdown/`). Each PureScript module’s documentation will be in a corresponding `.md` file. You might use this if you plan to feed the content into another tool or static site generator.

**3\. (Optional) Limit documentation to your project’s modules:**  
By default, `spago docs` includes documentation for all dependencies. This can make the site large or overwhelm readers with library internals. Currently, Spago does not have a built-in flag to document only specific modules (as of Spago 0.21). A common practice is to include everything (so that links to external types/functions work) but focus your navigation on your own modules. We will handle this when configuring the static site generator by customizing the navigation tree.

Converting Docs into a Beautiful Static Site
--------------------------------------------

While the HTML from `spago docs` is immediately usable (and includes a search UI similar to Pursuit), you may want a more customized or modern-looking site. Tools like **MkDocs** can turn Markdown docs into an attractive website with themes and navigation structure. MkDocs is popular for documentation sites – it takes Markdown files and produces a sleek static site **with minimal configuration**[blimped.nl](https://www.blimped.nl/creating-a-beautiful-documentation-site-with-mkdocs/#:~:text=So%20let%E2%80%99s%20get%20to%20it,and%20running%20in%20no%20time). We’ll use **MkDocs with the Material theme**, which is widely regarded as a beautiful theme in many communities.

**1\. Install MkDocs and Material theme:** MkDocs is a Python tool. Install it via pip (the Material theme package includes MkDocs as a dependency):

```bash
pip install mkdocs-material
```

This will install the `mkdocs` command. Verify by running `mkdocs --version`. (Alternatively, you can install `mkdocs` and a different theme or even use another static site generator – the concept remains similar.)

**2\. Prepare the documentation source:** We’ll use the Markdown output from Spago as the source for MkDocs. After running `spago docs --format markdown`, take the generated Markdown files and place them into MkDocs’s documentation directory. By default, MkDocs looks for a folder named `docs/` in your project for content. You can simply rename or copy `generated-docs/markdown` to `docs`. For example:

```bash
mv generated-docs/markdown docs
```

Ensure there's an `index.md` – MkDocs will use it as the homepage. If Spago did not create a top-level index in Markdown, you may create an `index.md` manually (perhaps with an introduction or linking to module pages). You could also generate HTML with Spago and write a custom `index.md` that links to your main module docs.

**3\. Configure MkDocs:** Create an `mkdocs.yml` configuration file at the project root. At minimum, specify the site name and theme. For example:

```yaml
site_name: My PureScript Project Docs  
theme:  
  name: material  
nav:  
- Home: index.md  
- Modules:
  - Module.One: Module.One.md
  - Module.Two: Module.Two.md
```

This YAML sets the site title and uses the Material theme. The `nav` section defines the left-hand navigation menu. Here we manually listed two modules; in a real project you’d list all your module docs (or nest them under categories). You can organize modules hierarchically if you have many (e.g., group by top-level namespace). If you omit `nav`, MkDocs will auto-list pages, but ordering may not be ideal. Refer to the MkDocs Configuration guide for details on organizing nav and other options.

**4\. Build and serve to preview:** Run MkDocs locally to ensure everything looks good:

```bash
mkdocs serve
```

This starts a dev server (usually at http://127.0.0.1:8000) where you can browse the docs live. Check that syntax highlighting, tables, and links between modules work. You might need to adjust relative links if any are broken. When satisfied, build the static site:

```bash
mkdocs build
```

This generates a `_site` (or `site/`) directory containing the final HTML, CSS, JS, etc.

The result should be a professional-looking documentation website. MkDocs (especially with Material) provides a clean layout, responsive design, search, and useful features like an automatically generated table of contents for each page. It’s an excellent way to present PureScript docs with modern aesthetics. _If you prefer not to use MkDocs_, an alternative is to simply deploy the `generated-docs/html` output from Spago directly – it will have a more minimal style (akin to Pursuit) but is ready to go without additional tooling[discourse.purescript.org](https://discourse.purescript.org/t/versioning-pursuit/3216#:~:text=I%20think%20we%E2%80%99re%20most%20of,care%20of%20generating%20the%20docs).

Automation with a Python Script
-------------------------------

To streamline the process of generating and publishing the docs, we can write a Python script that performs all the steps with one command. This script will: run Spago to generate docs, prepare the files for MkDocs, build the MkDocs site, and push the result to the `gh-pages` branch.

**Required Python libraries:** We can call out to system commands using Python’s subprocess, so we don’t need special libraries except ensuring the tools (`spago`, `mkdocs`) are installed. Optionally, the script could use the `ghp_import` Python library to push to GitHub Pages, but using MkDocs’ built-in deploy command is simpler.

Below is an example **`publish_docs.py`** script:

```python
import os, subprocess, shutil, sys

# 1. Generate docs with Spago (Markdown format)
print("Generating PureScript docs with Spago...")
result = subprocess.run(["spago", "docs", "--format", "markdown"], check=True)
print("Spago docs generation completed.")

# 2. Prepare MkDocs source directory
docs_src = "generated-docs/markdown"
mkdocs_docs_dir = "docs"
if os.path.isdir(mkdocs_docs_dir):
    shutil.rmtree(mkdocs_docs_dir)            # remove old docs folder if exists
shutil.copytree(docs_src, mkdocs_docs_dir)    # copy generated markdown to 'docs/'

# 3. (Optional) Add a custom index page if none exists
index_path = os.path.join(mkdocs_docs_dir, "index.md")
if not os.path.isfile(index_path):
    with open(index_path, "w") as f:
        f.write(f"# {os.path.basename(os.getcwd())} Documentation\n\n")
        f.write("Welcome to the API documentation for this PureScript project.\n")
        f.write("Use the navigation to browse modules.\n")

# 4. Build the static site with MkDocs
print("Building static site with MkDocs...")
subprocess.run(["mkdocs", "build"], check=True)
print("MkDocs site generated in './site' directory.")

# 5. Deploy to gh-pages branch using MkDocs
print("Deploying to GitHub Pages (gh-pages branch)...")
subprocess.run(["mkdocs", "gh-deploy", "--force"], check=True)
print("Deployment complete! Documentation is published to GitHub Pages.")
```

A few notes on this script:

*   It assumes you have already configured an `mkdocs.yml` in the current directory (the script does not create one). Make sure `mkdocs.yml` is present before running.
    
*   Step 5 uses `mkdocs gh-deploy` command. This command will internally commit the contents of the `site/` folder to the `gh-pages` branch and push to the repository’s GitHub Pages remote[mkdocs.org](https://www.mkdocs.org/user-guide/deploying-your-docs/#:~:text=mkdocs%20gh). The `--force` flag overwrites the remote content (useful if you want to replace the entire branch each time). MkDocs uses an underlying tool called **ghp-import** to handle this commit/push transparently[mkdocs.org](https://www.mkdocs.org/user-guide/deploying-your-docs/#:~:text=mkdocs%20gh).
    
*   For `mkdocs gh-deploy` to succeed, you need to have push access to the repo. If running locally, ensure your Git remote is set (the command will push to origin by default) and that you have credentials (e.g., an SSH key or a saved GitHub token). If something goes wrong, you can manually push the `gh-pages` branch.
    

**Usage:** Run the script from the root of your project (where `spago.dhall` and `mkdocs.yml` reside):

```bash
python publish_docs.py
```

It will print progress messages. After it completes, the documentation should be live on your GitHub Pages site (usually at `https://<username>.github.io/<repo>/`).

> **Tip:** You might want to automate when this script runs. For example, you could integrate it with your release process (run it whenever you bump the version), or just run it manually after significant updates to documentation comments. The next section shows how to let GitHub Actions run this automatically on every push or release tag.

CI/CD: GitHub Actions Workflow for Docs
---------------------------------------

We can achieve hands-free documentation deployment by using GitHub Actions. The idea is to have an Action workflow that triggers on each push to the main branch (or on new tags), generates the docs, and pushes to the `gh-pages` branch. This ensures GitHub Pages always serves the latest docs without any manual steps.

Below is a sample **`docs.yml`** workflow configuration for GitHub Actions:

```yaml
name: Documentation CI

on:
  push:
    branches: [ main, master ]   # run on pushes to main (adjust branch name as needed)
    
permissions:
  contents: write   # allow actions to push to repo

jobs:
  docs:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Node (for PureScript)
        uses: actions/setup-node@v3
        with:
          node-version: '18'   # Node 18.x, for example

      - name: Set up Python (for MkDocs)
        uses: actions/setup-python@v5
        with:
          python-version: '3.x'

      - name: Install PureScript and Spago
        run: npm install -g purescript spago  # installs purs compiler and spago

      - name: Install MkDocs and Material theme
        run: pip install mkdocs-material

      - name: Build and Deploy Docs to GitHub Pages
        run: |
          spago docs --format markdown
          mv generated-docs/markdown docs
          mkdocs gh-deploy --force
```

Let’s break down what this workflow does:

*   **Checkout code:** We use the official checkout action to fetch the repository code. This gives us the PureScript source and any existing docs config.
    
*   **Set up Node and Python:** We ensure the runner has Node.js (for Spago) and Python (for MkDocs). The `actions/setup-node` and `actions/setup-python` actions handle this. In the example, we specify Node 18 and the latest Python 3.x.
    
*   **Install dependencies:** We install PureScript and Spago globally via npm (this provides the `spago` command)[purescript.org](https://www.purescript.org/#:~:text=The%20recommended%20build%20tool%20for,npm). Then we install MkDocs and the Material theme via pip. (This single pip install is convenient[squidfunk.github.io](https://squidfunk.github.io/mkdocs-material/publishing-your-site/#:~:text=restore,force), but you could also use `pip install mkdocs mkdocs-material` if you want to pin specific versions.)
    
*   **Generate and deploy docs:** In one step, we run the same commands as our local pipeline:
    
    *   `spago docs --format markdown` – generates Markdown docs[github.com](https://github.com/purescript/spago#:~:text=You%20can%20customize%20the%20output,for%20use%20in%20your%20editor).
        
    *   Move/rename the markdown output to `docs` (so MkDocs will pick it up). We assume here that `mkdocs.yml` is already in the repo (perhaps checked in with a basic config as described earlier).
        
    *   `mkdocs gh-deploy --force` – builds and pushes the docs to the `gh-pages` branch. This command automatically uses the repository’s default GitHub token (provided by Actions) to authenticate the push. We set `permissions: contents: write` at the top of the workflow so that this token can push to the repo[squidfunk.github.io](https://squidfunk.github.io/mkdocs-material/publishing-your-site/#:~:text=permissions%3A%20contents%3A%20write%20jobs%3A%20deploy%3A,Configure%20Git%20Credentials%20run%3A). MkDocs will commit as a bot user (we configured a default identity in the Material theme guide[squidfunk.github.io](https://squidfunk.github.io/mkdocs-material/publishing-your-site/#:~:text=,python%40v5), but this step is optional).
        

After this workflow runs, you will have a `gh-pages` branch updated with the latest docs. GitHub Pages should serve the site shortly after.

**Important:** The first time, you may need to enable GitHub Pages in your repository settings. Go to **Settings → Pages**, and select **Source**: “Deploy from a branch”, then choose the `gh-pages` branch (root folder). Once set, GitHub Pages will serve any content from that branch. For a project site, the URL will be `https://<username>.github.io/<repo>/`. If you already had GitHub Pages on, ensure it’s pointed to `gh-pages`. (When using MkDocs’ deploy, it defaults to branch name `gh-pages` for Project Pages[mkdocs.org](https://www.mkdocs.org/user-guide/deploying-your-docs/#:~:text=Project%20Pages%EF%83%81).)

**Triggering on releases:** The above CI triggers on every push to main. You might instead want to trigger only on version tags (for example, to publish docs for released versions). In that case, modify the `on:` to:

```yaml
on:
  push:
    tags: ["v*.*.*"]
```

and perhaps include the version in the site (e.g., in `site_name` or publish to versioned directories – beyond our scope here).

Conclusion and References
-------------------------

By using Spago for documentation generation and MkDocs for site generation, we get the best of both worlds: **accurate API docs** extracted from code using the standard PureScript toolchain, and a **beautiful static website** that’s easy to navigate. The entire pipeline can be run locally with a single script or automated with CI so that every update gets published. The PureScript community’s standard tool (Spago) ensures the docs are consistent with Pursuit’s format[npmjs.com](https://www.npmjs.com/package/spago#:~:text=To%20build%20documentation%20for%20your,command), and MkDocs’s modern themes ensure a clean, responsive presentation[blimped.nl](https://www.blimped.nl/creating-a-beautiful-documentation-site-with-mkdocs/#:~:text=So%20let%E2%80%99s%20get%20to%20it,and%20running%20in%20no%20time).

With this setup in place, you can focus on writing good documentation in your code; the machinery will handle publishing it to your GitHub Pages site whenever you make changes. Your users or team will always have access to the latest documentation in a user-friendly format.

**References & Links:**

*   PureScript official website – how to install the compiler and Spago[purescript.org](https://www.purescript.org/#:~:text=The%20recommended%20build%20tool%20for,npm)
    
*   Spago documentation on generating docs[npmjs.com](https://www.npmjs.com/package/spago#:~:text=To%20build%20documentation%20for%20your,command)[github.com](https://github.com/purescript/spago#:~:text=You%20can%20customize%20the%20output,for%20use%20in%20your%20editor)
    
*   PureScript Discourse discussion (Starsuit) – mentions using `spago docs` and hosting on GitHub Pages[discourse.purescript.org](https://discourse.purescript.org/t/versioning-pursuit/3216#:~:text=,folder%20on%20GitHub%20pages)[discourse.purescript.org](https://discourse.purescript.org/t/versioning-pursuit/3216#:~:text=I%20think%20we%E2%80%99re%20most%20of,care%20of%20generating%20the%20docs)
    
*   MkDocs official site – introduction and deployment guide[blimped.nl](https://www.blimped.nl/creating-a-beautiful-documentation-site-with-mkdocs/#:~:text=So%20let%E2%80%99s%20get%20to%20it,and%20running%20in%20no%20time)[mkdocs.org](https://www.mkdocs.org/user-guide/deploying-your-docs/#:~:text=mkdocs%20gh)
    
*   MkDocs Material theme documentation – example GitHub Actions workflow[squidfunk.github.io](https://squidfunk.github.io/mkdocs-material/publishing-your-site/#:~:text=,python%40v5%20with)[squidfunk.github.io](https://squidfunk.github.io/mkdocs-material/publishing-your-site/#:~:text=restore,force)

## Prompt:
Automated Documentation Pipeline for PureScript via GitHub Pages

Automating PureScript Documentation Publishing via GitHub Pages
===============================================================

Introduction
------------

Publishing API documentation for a PureScript project can be fully automated. We will use **Spago**, the community-recommended build tool for PureScript, to generate documentation, then convert it into a polished static site. Spago leverages the PureScript compiler to produce documentation (similar to Pursuit) for your code[npmjs.com](https://www.npmjs.com/package/spago#:~:text=To%20build%20documentation%20for%20your,command). To enhance the visual appeal, we can feed the docs into a static site generator like **MkDocs** (with a modern theme such as _Material for MkDocs_). Finally, we’ll set up a Python script and a GitHub Actions workflow to automatically generate and deploy the documentation to the `gh-pages` branch on every release or push. This ensures your documentation is always up-to-date and beautifully presented.

Setting Up Documentation Generation with Spago
----------------------------------------------

The first step is to install PureScript and Spago, and then use Spago to generate your project’s documentation.

**Prerequisites:** Make sure you have Node.js installed. Then install the PureScript compiler and Spago via npm (the PureScript website recommends this method[purescript.org](https://www.purescript.org/#:~:text=The%20recommended%20build%20tool%20for,npm)):

```bash
npm install -g purescript spago   # Installs PureScript compiler (`purs`) and Spago
```

This gives you the `purs` compiler and the `spago` CLI tool on your PATH.

**1\. Generate documentation using Spago:**  
Spago can produce documentation for your project **and its dependencies**. By default, it emits a static HTML documentation site (analogous to a local Pursuit index). Simply run:

```bash
spago docs
```

This will compile your project (if not already built) and extract documentation from your source code. The output will be placed in a `generated-docs` directory. In particular, an `index.html` is generated as the entry point[npmjs.com](https://www.npmjs.com/package/spago#:~:text=To%20build%20documentation%20for%20your,command). You can open this file to browse the docs locally. The Spago-generated site includes all modules in your project _and_ any dependencies, complete with function/type documentation. It even provides a search interface out-of-the-box, thanks to the integrated **Docs Search** app[github.com](https://github.com/purescript/purescript-docs-search#:~:text=Installing).

> **Note:** Ensure your PureScript source files have proper documentation comments (e.g. preceding functions with `-- |` or `/** ... */` style comments). Spago/Pursuit will include those descriptions in the generated docs. Modules and declarations without comments will still appear but with minimal info.

**2\. Optional – Generate Markdown instead of HTML:**  
If you prefer to post-process or restyle the docs, Spago can output Markdown format. Spago supports multiple output formats – HTML by default, but also markdown, ctags, etc[github.com](https://github.com/purescript/spago#:~:text=You%20can%20customize%20the%20output,for%20use%20in%20your%20editor). For example:

```bash
spago docs --format markdown
```

This will produce a series of Markdown files (instead of HTML) under `generated-docs` (likely in a subfolder like `generated-docs/markdown/`). Each PureScript module’s documentation will be in a corresponding `.md` file. You might use this if you plan to feed the content into another tool or static site generator.

**3\. (Optional) Limit documentation to your project’s modules:**  
By default, `spago docs` includes documentation for all dependencies. This can make the site large or overwhelm readers with library internals. Currently, Spago does not have a built-in flag to document only specific modules (as of Spago 0.21). A common practice is to include everything (so that links to external types/functions work) but focus your navigation on your own modules. We will handle this when configuring the static site generator by customizing the navigation tree.

Converting Docs into a Beautiful Static Site
--------------------------------------------

While the HTML from `spago docs` is immediately usable (and includes a search UI similar to Pursuit), you may want a more customized or modern-looking site. Tools like **MkDocs** can turn Markdown docs into an attractive website with themes and navigation structure. MkDocs is popular for documentation sites – it takes Markdown files and produces a sleek static site **with minimal configuration**[blimped.nl](https://www.blimped.nl/creating-a-beautiful-documentation-site-with-mkdocs/#:~:text=So%20let%E2%80%99s%20get%20to%20it,and%20running%20in%20no%20time). We’ll use **MkDocs with the Material theme**, which is widely regarded as a beautiful theme in many communities.

**1\. Install MkDocs and Material theme:** MkDocs is a Python tool. Install it via pip (the Material theme package includes MkDocs as a dependency):

```bash
pip install mkdocs-material
```

This will install the `mkdocs` command. Verify by running `mkdocs --version`. (Alternatively, you can install `mkdocs` and a different theme or even use another static site generator – the concept remains similar.)

**2\. Prepare the documentation source:** We’ll use the Markdown output from Spago as the source for MkDocs. After running `spago docs --format markdown`, take the generated Markdown files and place them into MkDocs’s documentation directory. By default, MkDocs looks for a folder named `docs/` in your project for content. You can simply rename or copy `generated-docs/markdown` to `docs`. For example:

```bash
mv generated-docs/markdown docs
```

Ensure there's an `index.md` – MkDocs will use it as the homepage. If Spago did not create a top-level index in Markdown, you may create an `index.md` manually (perhaps with an introduction or linking to module pages). You could also generate HTML with Spago and write a custom `index.md` that links to your main module docs.

**3\. Configure MkDocs:** Create an `mkdocs.yml` configuration file at the project root. At minimum, specify the site name and theme. For example:

```yaml
site_name: My PureScript Project Docs  
theme:  
  name: material  
nav:  
- Home: index.md  
- Modules:
  - Module.One: Module.One.md
  - Module.Two: Module.Two.md
```

This YAML sets the site title and uses the Material theme. The `nav` section defines the left-hand navigation menu. Here we manually listed two modules; in a real project you’d list all your module docs (or nest them under categories). You can organize modules hierarchically if you have many (e.g., group by top-level namespace). If you omit `nav`, MkDocs will auto-list pages, but ordering may not be ideal. Refer to the MkDocs Configuration guide for details on organizing nav and other options.

**4\. Build and serve to preview:** Run MkDocs locally to ensure everything looks good:

```bash
mkdocs serve
```

This starts a dev server (usually at http://127.0.0.1:8000) where you can browse the docs live. Check that syntax highlighting, tables, and links between modules work. You might need to adjust relative links if any are broken. When satisfied, build the static site:

```bash
mkdocs build
```

This generates a `_site` (or `site/`) directory containing the final HTML, CSS, JS, etc.

The result should be a professional-looking documentation website. MkDocs (especially with Material) provides a clean layout, responsive design, search, and useful features like an automatically generated table of contents for each page. It’s an excellent way to present PureScript docs with modern aesthetics. _If you prefer not to use MkDocs_, an alternative is to simply deploy the `generated-docs/html` output from Spago directly – it will have a more minimal style (akin to Pursuit) but is ready to go without additional tooling[discourse.purescript.org](https://discourse.purescript.org/t/versioning-pursuit/3216#:~:text=I%20think%20we%E2%80%99re%20most%20of,care%20of%20generating%20the%20docs).

Automation with a Python Script
-------------------------------

To streamline the process of generating and publishing the docs, we can write a Python script that performs all the steps with one command. This script will: run Spago to generate docs, prepare the files for MkDocs, build the MkDocs site, and push the result to the `gh-pages` branch.

**Required Python libraries:** We can call out to system commands using Python’s subprocess, so we don’t need special libraries except ensuring the tools (`spago`, `mkdocs`) are installed. Optionally, the script could use the `ghp_import` Python library to push to GitHub Pages, but using MkDocs’ built-in deploy command is simpler.

Below is an example **`publish_docs.py`** script:

```python
import os, subprocess, shutil, sys

# 1. Generate docs with Spago (Markdown format)
print("Generating PureScript docs with Spago...")
result = subprocess.run(["spago", "docs", "--format", "markdown"], check=True)
print("Spago docs generation completed.")

# 2. Prepare MkDocs source directory
docs_src = "generated-docs/markdown"
mkdocs_docs_dir = "docs"
if os.path.isdir(mkdocs_docs_dir):
    shutil.rmtree(mkdocs_docs_dir)            # remove old docs folder if exists
shutil.copytree(docs_src, mkdocs_docs_dir)    # copy generated markdown to 'docs/'

# 3. (Optional) Add a custom index page if none exists
index_path = os.path.join(mkdocs_docs_dir, "index.md")
if not os.path.isfile(index_path):
    with open(index_path, "w") as f:
        f.write(f"# {os.path.basename(os.getcwd())} Documentation\n\n")
        f.write("Welcome to the API documentation for this PureScript project.\n")
        f.write("Use the navigation to browse modules.\n")

# 4. Build the static site with MkDocs
print("Building static site with MkDocs...")
subprocess.run(["mkdocs", "build"], check=True)
print("MkDocs site generated in './site' directory.")

# 5. Deploy to gh-pages branch using MkDocs
print("Deploying to GitHub Pages (gh-pages branch)...")
subprocess.run(["mkdocs", "gh-deploy", "--force"], check=True)
print("Deployment complete! Documentation is published to GitHub Pages.")
```

A few notes on this script:

*   It assumes you have already configured an `mkdocs.yml` in the current directory (the script does not create one). Make sure `mkdocs.yml` is present before running.
    
*   Step 5 uses `mkdocs gh-deploy` command. This command will internally commit the contents of the `site/` folder to the `gh-pages` branch and push to the repository’s GitHub Pages remote[mkdocs.org](https://www.mkdocs.org/user-guide/deploying-your-docs/#:~:text=mkdocs%20gh). The `--force` flag overwrites the remote content (useful if you want to replace the entire branch each time). MkDocs uses an underlying tool called **ghp-import** to handle this commit/push transparently[mkdocs.org](https://www.mkdocs.org/user-guide/deploying-your-docs/#:~:text=mkdocs%20gh).
    
*   For `mkdocs gh-deploy` to succeed, you need to have push access to the repo. If running locally, ensure your Git remote is set (the command will push to origin by default) and that you have credentials (e.g., an SSH key or a saved GitHub token). If something goes wrong, you can manually push the `gh-pages` branch.
    

**Usage:** Run the script from the root of your project (where `spago.dhall` and `mkdocs.yml` reside):

```bash
python publish_docs.py
```

It will print progress messages. After it completes, the documentation should be live on your GitHub Pages site (usually at `https://<username>.github.io/<repo>/`).

> **Tip:** You might want to automate when this script runs. For example, you could integrate it with your release process (run it whenever you bump the version), or just run it manually after significant updates to documentation comments. The next section shows how to let GitHub Actions run this automatically on every push or release tag.

CI/CD: GitHub Actions Workflow for Docs
---------------------------------------

We can achieve hands-free documentation deployment by using GitHub Actions. The idea is to have an Action workflow that triggers on each push to the main branch (or on new tags), generates the docs, and pushes to the `gh-pages` branch. This ensures GitHub Pages always serves the latest docs without any manual steps.

Below is a sample **`docs.yml`** workflow configuration for GitHub Actions:

```yaml
name: Documentation CI

on:
  push:
    branches: [ main, master ]   # run on pushes to main (adjust branch name as needed)
    
permissions:
  contents: write   # allow actions to push to repo

jobs:
  docs:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Node (for PureScript)
        uses: actions/setup-node@v3
        with:
          node-version: '18'   # Node 18.x, for example

      - name: Set up Python (for MkDocs)
        uses: actions/setup-python@v5
        with:
          python-version: '3.x'

      - name: Install PureScript and Spago
        run: npm install -g purescript spago  # installs purs compiler and spago

      - name: Install MkDocs and Material theme
        run: pip install mkdocs-material

      - name: Build and Deploy Docs to GitHub Pages
        run: |
          spago docs --format markdown
          mv generated-docs/markdown docs
          mkdocs gh-deploy --force
```

Let’s break down what this workflow does:

*   **Checkout code:** We use the official checkout action to fetch the repository code. This gives us the PureScript source and any existing docs config.
    
*   **Set up Node and Python:** We ensure the runner has Node.js (for Spago) and Python (for MkDocs). The `actions/setup-node` and `actions/setup-python` actions handle this. In the example, we specify Node 18 and the latest Python 3.x.
    
*   **Install dependencies:** We install PureScript and Spago globally via npm (this provides the `spago` command)[purescript.org](https://www.purescript.org/#:~:text=The%20recommended%20build%20tool%20for,npm). Then we install MkDocs and the Material theme via pip. (This single pip install is convenient[squidfunk.github.io](https://squidfunk.github.io/mkdocs-material/publishing-your-site/#:~:text=restore,force), but you could also use `pip install mkdocs mkdocs-material` if you want to pin specific versions.)
    
*   **Generate and deploy docs:** In one step, we run the same commands as our local pipeline:
    
    *   `spago docs --format markdown` – generates Markdown docs[github.com](https://github.com/purescript/spago#:~:text=You%20can%20customize%20the%20output,for%20use%20in%20your%20editor).
        
    *   Move/rename the markdown output to `docs` (so MkDocs will pick it up). We assume here that `mkdocs.yml` is already in the repo (perhaps checked in with a basic config as described earlier).
        
    *   `mkdocs gh-deploy --force` – builds and pushes the docs to the `gh-pages` branch. This command automatically uses the repository’s default GitHub token (provided by Actions) to authenticate the push. We set `permissions: contents: write` at the top of the workflow so that this token can push to the repo[squidfunk.github.io](https://squidfunk.github.io/mkdocs-material/publishing-your-site/#:~:text=permissions%3A%20contents%3A%20write%20jobs%3A%20deploy%3A,Configure%20Git%20Credentials%20run%3A). MkDocs will commit as a bot user (we configured a default identity in the Material theme guide[squidfunk.github.io](https://squidfunk.github.io/mkdocs-material/publishing-your-site/#:~:text=,python%40v5), but this step is optional).
        

After this workflow runs, you will have a `gh-pages` branch updated with the latest docs. GitHub Pages should serve the site shortly after.

**Important:** The first time, you may need to enable GitHub Pages in your repository settings. Go to **Settings → Pages**, and select **Source**: “Deploy from a branch”, then choose the `gh-pages` branch (root folder). Once set, GitHub Pages will serve any content from that branch. For a project site, the URL will be `https://<username>.github.io/<repo>/`. If you already had GitHub Pages on, ensure it’s pointed to `gh-pages`. (When using MkDocs’ deploy, it defaults to branch name `gh-pages` for Project Pages[mkdocs.org](https://www.mkdocs.org/user-guide/deploying-your-docs/#:~:text=Project%20Pages%EF%83%81).)

**Triggering on releases:** The above CI triggers on every push to main. You might instead want to trigger only on version tags (for example, to publish docs for released versions). In that case, modify the `on:` to:

```yaml
on:
  push:
    tags: ["v*.*.*"]
```

and perhaps include the version in the site (e.g., in `site_name` or publish to versioned directories – beyond our scope here).

Conclusion and References
-------------------------

By using Spago for documentation generation and MkDocs for site generation, we get the best of both worlds: **accurate API docs** extracted from code using the standard PureScript toolchain, and a **beautiful static website** that’s easy to navigate. The entire pipeline can be run locally with a single script or automated with CI so that every update gets published. The PureScript community’s standard tool (Spago) ensures the docs are consistent with Pursuit’s format[npmjs.com](https://www.npmjs.com/package/spago#:~:text=To%20build%20documentation%20for%20your,command), and MkDocs’s modern themes ensure a clean, responsive presentation[blimped.nl](https://www.blimped.nl/creating-a-beautiful-documentation-site-with-mkdocs/#:~:text=So%20let%E2%80%99s%20get%20to%20it,and%20running%20in%20no%20time).

With this setup in place, you can focus on writing good documentation in your code; the machinery will handle publishing it to your GitHub Pages site whenever you make changes. Your users or team will always have access to the latest documentation in a user-friendly format.

**References & Links:**

*   PureScript official website – how to install the compiler and Spago[purescript.org](https://www.purescript.org/#:~:text=The%20recommended%20build%20tool%20for,npm)
    
*   Spago documentation on generating docs[npmjs.com](https://www.npmjs.com/package/spago#:~:text=To%20build%20documentation%20for%20your,command)[github.com](https://github.com/purescript/spago#:~:text=You%20can%20customize%20the%20output,for%20use%20in%20your%20editor)
    
*   PureScript Discourse discussion (Starsuit) – mentions using `spago docs` and hosting on GitHub Pages[discourse.purescript.org](https://discourse.purescript.org/t/versioning-pursuit/3216#:~:text=,folder%20on%20GitHub%20pages)[discourse.purescript.org](https://discourse.purescript.org/t/versioning-pursuit/3216#:~:text=I%20think%20we%E2%80%99re%20most%20of,care%20of%20generating%20the%20docs)
    
*   MkDocs official site – introduction and deployment guide[blimped.nl](https://www.blimped.nl/creating-a-beautiful-documentation-site-with-mkdocs/#:~:text=So%20let%E2%80%99s%20get%20to%20it,and%20running%20in%20no%20time)[mkdocs.org](https://www.mkdocs.org/user-guide/deploying-your-docs/#:~:text=mkdocs%20gh)
    
*   MkDocs Material theme documentation – example GitHub Actions workflow[squidfunk.github.io](https://squidfunk.github.io/mkdocs-material/publishing-your-site/#:~:text=,python%40v5%20with)[squidfunk.github.io](https://squidfunk.github.io/mkdocs-material/publishing-your-site/#:~:text=restore,force)
This guide explains how to automate the generation and publication of **Scala API documentation** using **Scaladoc** for Gradle-built projects. We will set up a pipeline that produces polished, user-friendly docs for both **versioned releases** and the **latest** (development) code, and deploys them to **GitHub Pages**. The solution will cover both manual execution (via a Python script) and Continuous Integration (CI) with GitHub Actions. Key objectives include:

*   **Using Scaladoc with Gradle:** Configure Gradle to generate Scaladoc HTML documentation from Scala source code (instead of sbt or Maven).
    
*   **Polishing the Docs:** Apply theming and customization (project name, version, logos, etc.) to make the documentation look professional and easy to navigate.
    
*   **Versioned Documentation Structure:** Organize the published docs by version (e.g. one folder per release) and maintain a **`latest`** docs for the current build.
    
*   **Automated Deployment:** Provide steps (and scripts) to automatically build the docs, push them to the **`gh-pages`** branch, and optionally integrate this into a GitHub Actions workflow (triggered on new commits or tags).
    
*   **Best Practices:** Ensure older docs remain available (don’t overwrite previous versions), and optionally enable a version selector in the doc site for easy navigation between versions.
    

By the end, you should have a clear blueprint for generating Scaladoc and publishing it to GitHub Pages with minimal manual effort.

Generating Scaladoc with Gradle
-------------------------------

First, ensure your Gradle build is configured for Scala. Apply the Scala plugin in your `build.gradle` (or Gradle Kotlin DSL) to add Scala compilation and Scaladoc support:

```groovy
plugins {
    id 'scala'  // applies the Scala plugin
}
// ... (your Scala library dependency, etc.)
```

The Scala plugin automatically provides a task called **`scaladoc`** which generates API docs for your Scala sources[docs.gradle.org](https://docs.gradle.org/current/userguide/scala_plugin.html#:~:text=). After compiling your project, you can run this task to produce the documentation:

```bash
./gradlew scaladoc
```

By default, Gradle will output the Scaladoc HTML files to the directory **`build/docs/scaladoc`**[github.com](https://github.com/decisionbrain/cplex-scala#:~:text=To%20generate%20the%20scala%20docs%2C,do). Open the generated `index.html` in that folder to verify the documentation. The docs will include all public Scala classes, traits, objects, and methods in your project’s **`src/main/scala`** (and any Scala sources in other source sets).

**Multi-module projects:** If your project has multiple submodules, each would generate its own Scaladoc by default. You may choose to aggregate them (e.g., by configuring a root project task that depends on subprojects’ `scaladoc` tasks and copies outputs together). However, for simplicity, this guide assumes a single-module project. (Aggregation can be done by customizing the ScalaDoc task to include sources from subprojects if needed.)

Customizing and Theming Scaladoc Output
---------------------------------------

The out-of-the-box Scaladoc is functional, but we can improve its appearance and usefulness with a few options:

*   **Project Title and Version:** You can set a custom title or project name in the documentation, and display the project’s version. ScalaDoc (Scala 2) supports `-doc-title` and `-doc-version` options. In Scala 3, these correspond to `-project` and `-project-version`. For example, setting `-project MyLibrary -project-version 1.2.3` will show _“MyLibrary 1.2.3”_ in the doc header[docs.scala-lang.org](https://docs.scala-lang.org/scala3/guides/scaladoc/settings.html#:~:text=%23%23%20). You can configure Gradle to pass these options. In a Gradle build script, you might do:
    
    ```groovy
    tasks.withType(ScalaDoc) {
        // For Scala 2.x:
        scalaDocOptions.setDocTitle("${project.name} API")
        scalaDocOptions.setWindowTitle("${project.name} ${project.version} API")
        scalaDocOptions.setFooter("© 2025 My Company")
        scalaDocOptions.setAdditionalParameters(["-doc-version", "${project.version}"])
        // For Scala 3, use -project and -project-version via additionalParameters if needed.
    }
    ```
    
    This will label your docs with the project name and version and add a custom footer. (Gradle’s `ScalaDocOptions` allows setting title, footer, etc., but some settings may internally pass to the Scaladoc tool[stackoverflow.com](https://stackoverflow.com/questions/39088691/setting-scaladoc-header-footer-in-gradle#:~:text=project).)
    
*   **Logo and Styling:** Scaladoc (especially Scala 3’s version) lets you include a project logo in the navigation header. Use the `-doc-logo` option (Scala 2) or `-project-logo` (Scala 3) to specify an image. For Scala 3, if you provide `mylogo.png`, you can also provide an optional `mylogo_dark.png` for dark mode[docs.scala-lang.org](https://docs.scala-lang.org/scala3/guides/scaladoc/settings.html#:~:text=%23%23%20). Place these image files where Scaladoc can find them (e.g., in the current directory or a known path) and add the option in Gradle:
    
    ```groovy
    tasks.withType(ScalaDoc) {
        scalaDocOptions.setAdditionalParameters([...,
            "-doc-version", "${project.version}",
            "-doc-logo", "path/to/mylogo.png"
        ])
    }
    ```
    
    This will embed your logo at the top of each page. Ensure the path is correct (you may copy the logo into the `build/docs/scaladoc/images/` folder after generation if needed, as Scaladoc might expect it in the output’s `images/` directory).
    
*   **Dark Theme and Appearance:** Scala 3’s new Scaladoc has a modern UI with dark mode support automatically. By providing a `_dark` variant of your logo as mentioned, you ensure it looks good on both light and dark themes[docs.scala-lang.org](https://docs.scala-lang.org/scala3/guides/scaladoc/settings.html#:~:text=The%20logo%20of%20your%20project,logo). The default color scheme of Scala 3’s docs has been debated, but it’s generally much nicer than Scala 2’s older frame-based docs. If using Scala 2 and you find the style dated, consider migrating to Scala 3’s doc tool or using custom CSS (though the latter is non-trivial without forking the doc template). For Scala 2, you can at least customize the header/footer text as shown, to replace the default “Generated by Scaladoc” footer with your own.
    
*   **Social and Source Links:** Scaladoc can integrate handy links. For instance, you can add links to your project’s GitHub, Twitter, etc., via the `-social-links` option (Scala 3 only). For example:
    
    ```scala
    -social-links:github::https://github.com/YourUser/YourRepo
    ```
    
    would add a GitHub icon in the docs that links to your repo[docs.scala-lang.org](https://docs.scala-lang.org/scala3/guides/scaladoc/settings.html#:~:text=%23%23%20). You can list multiple links (comma-separated) for different services (supported icons include GitHub, Gitter, Twitter, Discord, or even custom icons).
    
    Another very useful feature is linking from the API docs to your source code on GitHub. ScalaDoc 3 supports `-source-links` to map source files to a GitHub repository URL pattern[docs.scala-lang.org](https://docs.scala-lang.org/scala3/guides/scaladoc/settings.html#:~:text=%23%23%20). By configuring this with your repo info and the appropriate branch/tag, the generated docs will show “Source” links for classes, letting users jump to the code on GitHub. For example:
    
    ```scala
    -source-links:github://YourUser/YourRepo/main#src/main/scala
    ```
    
    would construct GitHub URLs for each source file (you might include `-revision ${SHA}` or tag to lock to the correct version).
    
*   **Grouping and Index:** If you have many APIs, you can group related ones using Scaladoc’s @group annotations and enable grouping with `-groups`. This will categorize functions or types in the output (Scala 2 needed `-groups`; Scala 3 might do this by default for certain annotations). Additionally, ScalaDoc (Scala 3) will by default generate an **index** and a search feature, making it easier to find classes by name.
    
*   **Inheritance Diagrams:** For Scala 2.x projects, Scaladoc can generate UML-style inheritance diagrams for classes and traits if Graphviz is available. Enabling the `-diagrams` option will create SVG diagrams illustrating class hierarchies[stackoverflow.com](https://stackoverflow.com/questions/20009030/where-is-the-man-page-for-scaladoc#:~:text=,Eg%3A%20%2Fusr%2Fbin%2Fdot). This can make the documentation more insightful visually. To use this, ensure the Graphviz `dot` tool is installed and on the PATH, and Gradle can be configured to add `-diagrams` to `scalaDocOptions.additionalParameters`. _Note:_ This is a Scala 2 feature; Scala 3’s doc tool currently does not generate these diagrams.
    
*   **Static Pages and Site Material:** One powerful new feature of Scala 3’s Scaladoc is the ability to include **static documentation pages** (similar to Jekyll or Docusaurus sites) along with the API docs[docs.scala-lang.org](https://docs.scala-lang.org/scala3/guides/scaladoc/static-site.html#:~:text=Scaladoc%20can%20generate%20static%20sites%2C,between%20static%20documentation%20and%20API)[docs.scala-lang.org](https://docs.scala-lang.org/scala3/guides/scaladoc/#:~:text=Scaladoc%20,well%20as%20jekyll%20or%20docusaurus). By default, if you put markdown files in a `docs/` directory, Scaladoc will incorporate them into the generated site (you may need to specify `-siteroot ./docs` if different)[docs.scala-lang.org](https://docs.scala-lang.org/scala3/guides/scaladoc/settings.html#:~:text=%23%23%20). This means you can have a user guide, examples, or other markdown pages in addition to the API reference, all in one site. For example, a `docs/Overview.md` can become a welcome page on your docs site. Leveraging this feature can greatly improve user-friendliness by providing context and tutorials alongside raw API docs.
    

In summary, take advantage of Scaladoc options to make your documentation stand out. At minimum, set the project name and version, and consider adding a project logo and useful links (source repository, etc.) to give users of your library a richer experience[docs.scala-lang.org](https://docs.scala-lang.org/scala3/guides/scaladoc/settings.html#:~:text=%23%23%20). Once you’ve configured these in Gradle, you’re ready to generate attractive docs.

Organizing Versioned Documentation on GitHub Pages
--------------------------------------------------

With Scaladoc generation in place, the next step is to publish the HTML files to GitHub Pages. We want to host multiple versions of the docs so users can browse older versions if needed, as well as a “latest” version (for the current development state or snapshot).

**GitHub Pages via `gh-pages` branch:** A common approach (which we’ll use) is to keep a separate branch `gh-pages` in your repository that contains the built documentation. GitHub will serve this content at `https://<username>.github.io/<repo>/`. We won’t use Jekyll or generators on GitHub’s side; we’ll simply push the static HTML that Scaladoc produces.

**Directory structure:** On the `gh-pages` branch, organize the docs by version. For example:

```text
gh-pages branch:
├── index.html  (optional landing page or redirect)
├── latest/     (latest docs for main branch)
├── 1.0.0/      (docs for version 1.0.0)
├── 1.1.0/      (docs for version 1.1.0)
└── versions.json  (optional version info file for the version menu)
```

Each version’s folder (e.g. **`1.0.0/`**) contains the `index.html` and resources exactly as generated by Scaladoc for that release. The **`latest/`** folder will contain the docs for the current state of the default branch (or you could use it for the latest _released_ version, but typically “latest” implies the cutting-edge documentation).

**Landing page:** You can have an `index.html` at the root of gh-pages to welcome users or automatically redirect them to the latest docs. For instance, your `index.html` could contain a meta-refresh or JavaScript to redirect to `latest/index.html`, or just a simple page with links to each version’s documentation. This is optional but improves usability (someone visiting the base URL will see something helpful).

**Preserving older versions:** It is important **not to delete** previously published docs when adding a new version. Each time you release a new version and push its docs, ensure you don't wipe out the existing folders. The process should be cumulative: add new version directory (and update “latest”), while keeping the others intact. This way, URLs for older docs (like `/1.0.0/index.html`) remain valid. We will implement our deployment scripts/steps to only add or update specific directories. (For example, if using a tool, use include/exclude filters to preserve certain folders[github.com](https://github.com/ajoberstar/gradle-git-publish#:~:text=%2F%2F%20what%20to%20keep%20in,exclude%20%271.0.0%2Ftemp.txt%27)).

**Version dropdown (optional):** As a bonus, Scala 3 Scaladoc can display a version selector in the top menu if you provide a JSON mapping of version names to URLs. This is done via the `-versions-dictionary-url` option[docs.scala-lang.org](https://docs.scala-lang.org/scala3/guides/scaladoc/settings.html#:~:text=%23%23%20). You host a JSON file (say, `versions.json` in the gh-pages branch) that looks like:

```json
{
  "versions": {
    "1.0.0": "https://your-user.github.io/your-repo/1.0.0/index.html",
    "1.1.0": "https://your-user.github.io/your-repo/1.1.0/index.html",
    "Latest": "https://your-user.github.io/your-repo/latest/index.html"
  }
}
```

Then, when generating Scaladoc for a given version, pass `-versions-dictionary-url https://your-user.github.io/your-repo/versions.json`. The resulting HTML pages will include a “versions” dropdown that lets readers switch between 1.0.0, 1.1.0, Latest, etc., and navigate to those URLs[docs.scala-lang.org](https://docs.scala-lang.org/scala3/guides/scaladoc/settings.html#:~:text=%7B%20,). Maintaining this JSON is simple: whenever you add a new version, update the file with that version and URL. (You can automate updating this file in the deployment script.)

Now that the structure and approach are defined, let's see how to actually copy and publish the files.

Manual Publishing with a Python Script
--------------------------------------

We can create a Python script to automate the documentation publishing steps. This script will:

1.  **Run the Gradle Scaladoc task** to generate the docs.
    
2.  **Check out (or clone) the `gh-pages` branch** of the repository.
    
3.  **Copy the newly generated docs** into the appropriate directory in the `gh-pages` working copy (e.g., into `latest/` and/or a versioned folder).
    
4.  **Commit and push** the changes to the `gh-pages` branch (publishing the docs).
    

Using Python allows us to execute this process on any machine (locally or in CI) in a controlled way. We will rely on Git being available for pushing to GitHub. You can use a library like **GitPython** for finer control, but using `subprocess` to call Git is straightforward and avoids extra dependencies.

Below is a sample **`publish_docs.py`** script outline:

```python
import subprocess, os, shutil

# Configuration – adjust these for your repository
repo_url = "git@github.com:YourUser/YourRepo.git"  # SSH URL (or use https:// with token)
branch = "gh-pages"
build_dir = "build/docs/scaladoc"  # Scaladoc output directory

# Optionally accept a version argument (e.g., via env var or CLI arg)
version = os.getenv('DOC_VERSION')  # e.g., "1.2.0" for releases; None for latest

# 1. Build the documentation using Gradle
subprocess.run(["./gradlew", "scaladoc"], check=True)

# 2. Clone the gh-pages branch to a temporary directory
gh_pages_dir = ".gh-pages-temp"
if os.path.exists(gh_pages_dir):
    shutil.rmtree(gh_pages_dir)
subprocess.run(["git", "clone", "-b", branch, "--single-branch", repo_url, gh_pages_dir], check=True)

# 3. Copy the new docs into the gh-pages working tree
target_folder = version if version else "latest"
dest_path = os.path.join(gh_pages_dir, target_folder)
# Remove old files in target_folder to avoid stale files
shutil.rmtree(dest_path, ignore_errors=True)
shutil.copytree(build_dir, dest_path)

# (Optional) Update 'latest' as an alias for this version
if version:
    latest_path = os.path.join(gh_pages_dir, "latest")
    shutil.rmtree(latest_path, ignore_errors=True)
    shutil.copytree(build_dir, latest_path)

# (Optional) Update versions.json for version dropdown
versions_file = os.path.join(gh_pages_dir, "versions.json")
if os.path.exists(versions_file) and version:
    import json
    with open(versions_file, 'r') as vf:
        data = json.load(vf)
    label = version  # e.g. "1.2.0"
    url = f"https://your-user.github.io/your-repo/{version}/index.html"
    data["versions"][label] = url
    # Also update "Latest" to point to this version if desired:
    data["versions"]["Latest"] = f"https://your-user.github.io/your-repo/latest/index.html"
    with open(versions_file, 'w') as vf:
        json.dump(data, vf, indent=2)

# 4. Commit and push the changes to gh-pages
subprocess.run(["git", "add", "."], cwd=gh_pages_dir, check=True)
msg = f"Publish docs for {version}" if version else "Update latest docs"
subprocess.run(["git", "commit", "-m", msg], cwd=gh_pages_dir, check=True)
subprocess.run(["git", "push"], cwd=gh_pages_dir, check=True)
```

**How to use this script:** Ensure you have push access to the repo (for example, set up SSH auth or have a personal access token if using HTTPS). Then run `python publish_docs.py`. If you set an environment variable `DOC_VERSION` to a version number, the script will treat it as a release and publish to that version folder (and also update “latest” to that version). If no version is provided, it will publish only to `latest/`.

For a real implementation, you might want to add error handling, argument parsing (e.g., use `argparse` to take a `--version` flag), and logging for clarity. You should also configure Git identity if not already (the script assumes your global Git config has user name/email or you could set env like `GIT_AUTHOR_NAME` for CI commits).

**Security:** If running in CI, you wouldn’t use `git@github.com` (SSH) unless you set up keys; instead, you might use an HTTPS URL with a token: e.g., `https://x-access-token:${GITHUB_TOKEN}@github.com/YourUser/YourRepo.git`. In GitHub Actions, `${{ secrets.GITHUB_TOKEN }}` can be used for authentication. Our next section covers the CI setup.

CI/CD Integration with GitHub Actions
-------------------------------------

To fully automate the docs publishing, we can use GitHub Actions to trigger the process on certain events, such as pushes to the main branch and new version tags. GitHub Actions can run the Gradle build, then either use our Python script or directly use an action to deploy to Pages.

Using the script in CI is as simple as adding a step to run `publish_docs.py` (with the proper environment). Alternatively, there are community Actions specifically for deploying to GitHub Pages which can simplify things. One popular choice is **JamesIves/github-pages-deploy-action**, which handles the git work for you[stackoverflow.com](https://stackoverflow.com/questions/62913488/how-can-i-publish-the-docs-to-github-pages-after-generating-it-via-dokka-kotlin#:~:text=,pages%20FOLDER%3A%20build%2Fdocs).

Below is an example workflow that builds and publishes docs on two events:

*   **Push to main**: updates the **latest** docs.
    
*   **Push of a git tag** (e.g., a version tag like v1.2.0): publishes docs under that version directory (and updates latest accordingly).
    

```yaml
name: PublishDocs
on:
  push:
    branches: [ main ]
    tags: [ 'v*' ]   # triggers on tag pushes like v1.2.0, v2.0, etc.

jobs:
  docs:
    runs-on: ubuntu-latest
    permissions:
      contents: write   # allow pushing to gh-pages
    steps:
      - uses: actions/checkout@v3
        with:
          persist-credentials: false   # we'll use a token explicitly
          fetch-depth: 0   # fetch all history to get tags if needed

      - name: Set up JDK
        uses: actions/setup-java@v3
        with:
          distribution: 'Temurin'  # AdoptOpenJDK (Eclipse Temurin)
          java-version: '17'       # or 11, depending on your project

      - name: Build Scaladoc
        run: ./gradlew scaladoc

      - name: Publish docs (latest)
        if: ${{ github.ref == 'refs/heads/main' }}
        uses: JamesIves/github-pages-deploy-action@v4
        with:
          branch: gh-pages
          folder: build/docs/scaladoc
          target-folder: latest
          clean: true           # remove outdated files in 'latest/'
          token: ${{ secrets.GITHUB_TOKEN }}

      - name: Publish docs (versioned)
        if: ${{ startsWith(github.ref, 'refs/tags/') }}
        uses: JamesIves/github-pages-deploy-action@v4
        with:
          branch: gh-pages
          folder: build/docs/scaladoc
          target-folder: ${{ github.ref_name }}   # e.g. 'v1.2.0'
          clean: false          # don't wipe entire branch, just add/update this folder
          token: ${{ secrets.GITHUB_TOKEN }}
```

Let’s break down what this workflow does:

*   It triggers on pushes to `main` and on pushes of tags matching `v*`. (You could also trigger on the creation of a GitHub Release if you prefer, but using tags is straightforward).
    
*   It checks out the code. We disable `persist-credentials` so that the checkout action doesn’t retain the repo’s token (since we will use the deploy action’s token to push). We also fetch full history (`fetch-depth: 0`) in case we need tag info (not strictly required for this deploy, but good practice when using tags).
    
*   It sets up Java (Gradle needs a JDK). Ensure the Java version here matches what your project needs (Scala 2.13/3 requires JDK 8+; using 11 or 17 is fine).
    
*   It runs `./gradlew scaladoc` to generate the docs.
    
*   Then we have two deploy steps:
    
    *   **Latest**: runs only on the main branch push. It uses the GitHub Pages Deploy Action. We specify the `folder` as the output directory (`build/docs/scaladoc`) and `target-folder: latest`. This tells the action to take everything in `build/docs/scaladoc` and push it to the `gh-pages` branch under a folder named “latest”. We set `clean: true` here to ensure that the `latest/` folder on the branch is fully synced with this new content (any old files in `latest/` that aren’t in the new build will be removed) – this is fine because `latest` is supposed to track the current content exactly. The action uses the provided `GITHUB_TOKEN` (which is an automatically provided token with permissions to the repo) to authenticate the push. (No need to create a personal token for this, unless you prefer; the built-in token works for pushing to `gh-pages` on the same repo, given `contents: write` permission was set).
        
    *   **Versioned**: runs only on tag pushes. This one deploys to a folder named after the tag. GitHub Actions exposes the tag name in `github.ref_name` (for a tag ref `refs/tags/v1.2.0`, `ref_name` is `v1.2.0`). We use that as the folder. We set `clean: false` to avoid wiping other content on the branch. This means it will add/update the files in the `v1.2.0/` directory and leave everything else untouched – which is what we want for preserving older docs. We could additionally use `clean-exclude` if needed to be extra safe in preserving, but with `target-folder` and `clean:false`, it should only affect that subdirectory. After this step, the new version’s docs are published. We did not explicitly update “latest” here; if you want the tag deployment to also update the `latest` docs (assuming “latest” should always mirror the newest release), you could add another step in the tag workflow to copy the same files to `latest/`. In our example, if main is always ahead with potentially unreleased changes, you might keep latest tied to main, not to the last tag – this choice is up to your project’s versioning strategy.
        

This workflow approach uses the community action for convenience. It encapsulates the git clone/add/commit/push steps, so you don't need to maintain that logic. On each run, the action will output logs of its operation (cloning gh-pages, committing new files, etc.).

**Enabling GitHub Pages:** Remember to enable GitHub Pages in your repository settings to serve from the `gh-pages` branch. Go to **Settings > Pages**, and set the source to “Deploy from a branch”, then select `gh-pages` and root (or `gh-pages` and `/docs` if you put site in a docs folder on that branch; in our case it’s root). Once enabled, your pages will be live at the URL given. The workflow above even notes that you might need to run it once to create the `gh-pages` branch if it doesn’t exist[stackoverflow.com](https://stackoverflow.com/questions/62913488/how-can-i-publish-the-docs-to-github-pages-after-generating-it-via-dokka-kotlin#:~:text=BRANCH%3A%20gh), and then configure the Pages settings.

**Using the Python script in CI:** Alternatively, you could replace the deploy action steps with a call to the Python script we wrote. For example, install Python and any requirements in the workflow, then run `python publish_docs.py`. You’d need to supply credentials (perhaps by setting `GITHUB_TOKEN` or using a PAT) for the script’s git push. The deploy action simplifies this by using the provided token. Both approaches are valid; using the script might give you more control (e.g., updating the versions JSON, which the simple action approach above doesn’t do automatically). You could incorporate the JSON update logic into the workflow as well – for instance, after publishing, do a separate commit to add/update `versions.json`. Depending on your needs, choose the method you’re most comfortable with. The **official tools** (like the deploy Action or the Gradle plugin mentioned below) are robust and maintained, which reduces the chance of script errors.

Best Practices and Alternatives
-------------------------------

*   **Keep “latest” up to date**: If your project’s default branch (e.g. main) is where development happens, it’s useful to auto-publish those docs to “latest” on every push. That way, contributors or users can see documentation for the unreleased state. If you want “latest” instead to point to the most recent _release_, you can adjust your strategy: for example, only update “latest” when a tag is released (or have a “snapshot” vs “stable” distinction).
    
*   **Maintain older versions**: We addressed this, but always double-check that your automation script/action does not delete the existing version directories on gh-pages. When using the GitHub Pages Deploy Action, using `target-folder` for a subdirectory and `clean: false` is one way to ensure only that subfolder is touched. If writing your own script, be careful to not call `git push --force` on the entire branch in a way that resets history (prefer a regular commit that only adds the new files).
    
*   **Gradle plugin approach**: Instead of a custom Python script or GitHub Action, you can also consider the Gradle plugin **gradle-git-publish** (by ajoberstar). This plugin can automate publishing to a git branch as part of your Gradle build. For example, you can configure it to publish the contents of `build/docs/scaladoc` to `gh-pages`, and specify patterns to preserve certain files/folders[github.com](https://github.com/ajoberstar/gradle-git-publish#:~:text=%2F%2F%20what%20to%20keep%20in,exclude%20%271.0.0%2Ftemp.txt%27) (to avoid deleting older docs). Then you could run `./gradlew gitPublishPush` to push docs. This is a more “all-Gradle” solution. However, using it still requires providing credentials (which you’d do via environment variables for GH token or using your SSH agent), and in CI you’d hook it up similarly. Both approaches are valid; using the standalone script or action might be easier to understand and maintain for many.
    
*   **Testing the setup**: It’s a good idea to test the publishing process on a dummy repository or a personal fork first, especially the GitHub Actions workflow, to ensure everything works as expected (and the docs look correct on GitHub Pages). Once confirmed, you can integrate it into your main repo.
    
*   **Using custom domains or project pages**: If your GitHub Pages is using a custom domain or is the user/org page, the principle is the same — just be sure the links and JSON version URLs reflect the correct domain.
    

With this setup, every time you merge to main or push a new version tag, your Scaladoc will be generated and published automatically. The documentation site will be nicely themed (with your project’s branding) and users will be able to browse the API for the latest code as well as switch between versions. This provides a professional touch to your Scala project and reduces the manual work in keeping docs up-to-date. Enjoy your fully automated Scaladoc pipeline! 🚀

**Sources:**

*   Gradle Scala Plugin documentation – confirms the `scaladoc` task for generating Scala API docs[docs.gradle.org](https://docs.gradle.org/current/userguide/scala_plugin.html#:~:text=) and default output location[github.com](https://github.com/decisionbrain/cplex-scala#:~:text=To%20generate%20the%20scala%20docs%2C,do).
    
*   Scala 3 Scaladoc options – for theming (project logo, version, footer, etc.)[docs.scala-lang.org](https://docs.scala-lang.org/scala3/guides/scaladoc/settings.html#:~:text=%23%23%20) and version menu support[docs.scala-lang.org](https://docs.scala-lang.org/scala3/guides/scaladoc/settings.html#:~:text=%23%23%20)[docs.scala-lang.org](https://docs.scala-lang.org/scala3/guides/scaladoc/settings.html#:~:text=%7B%20,).
    
*   Example GitHub Actions usage of GitHub Pages Deploy Action[stackoverflow.com](https://stackoverflow.com/questions/62913488/how-can-i-publish-the-docs-to-github-pages-after-generating-it-via-dokka-kotlin#:~:text=,pages%20FOLDER%3A%20build%2Fdocs) and guidelines for tokens[stackoverflow.com](https://stackoverflow.com/questions/62913488/how-can-i-publish-the-docs-to-github-pages-after-generating-it-via-dokka-kotlin#:~:text=You%27ll%20need%20to%20adapt%20the,where%20the%20docs%20are%20generated).
    
*   Gradle Git Publish plugin example – shows preserving an older docs folder during publish[github.com](https://github.com/ajoberstar/gradle-git-publish#:~:text=%2F%2F%20what%20to%20keep%20in,exclude%20%271.0.0%2Ftemp.txt%27).

## Prompt:
Automated Scaladoc Publishing with Gradle and Python to GitHub Pages

Publishing Scala Scaladoc Documentation with Gradle and GitHub Pages
====================================================================

Overview and Goals
------------------

This guide explains how to automate the generation and publication of **Scala API documentation** using **Scaladoc** for Gradle-built projects. We will set up a pipeline that produces polished, user-friendly docs for both **versioned releases** and the **latest** (development) code, and deploys them to **GitHub Pages**. The solution will cover both manual execution (via a Python script) and Continuous Integration (CI) with GitHub Actions. Key objectives include:

*   **Using Scaladoc with Gradle:** Configure Gradle to generate Scaladoc HTML documentation from Scala source code (instead of sbt or Maven).
    
*   **Polishing the Docs:** Apply theming and customization (project name, version, logos, etc.) to make the documentation look professional and easy to navigate.
    
*   **Versioned Documentation Structure:** Organize the published docs by version (e.g. one folder per release) and maintain a **`latest`** docs for the current build.
    
*   **Automated Deployment:** Provide steps (and scripts) to automatically build the docs, push them to the **`gh-pages`** branch, and optionally integrate this into a GitHub Actions workflow (triggered on new commits or tags).
    
*   **Best Practices:** Ensure older docs remain available (don’t overwrite previous versions), and optionally enable a version selector in the doc site for easy navigation between versions.
    

By the end, you should have a clear blueprint for generating Scaladoc and publishing it to GitHub Pages with minimal manual effort.

Generating Scaladoc with Gradle
-------------------------------

First, ensure your Gradle build is configured for Scala. Apply the Scala plugin in your `build.gradle` (or Gradle Kotlin DSL) to add Scala compilation and Scaladoc support:

```groovy
plugins {
    id 'scala'  // applies the Scala plugin
}
// ... (your Scala library dependency, etc.)
```

The Scala plugin automatically provides a task called **`scaladoc`** which generates API docs for your Scala sources[docs.gradle.org](https://docs.gradle.org/current/userguide/scala_plugin.html#:~:text=). After compiling your project, you can run this task to produce the documentation:

```bash
./gradlew scaladoc
```

By default, Gradle will output the Scaladoc HTML files to the directory **`build/docs/scaladoc`**[github.com](https://github.com/decisionbrain/cplex-scala#:~:text=To%20generate%20the%20scala%20docs%2C,do). Open the generated `index.html` in that folder to verify the documentation. The docs will include all public Scala classes, traits, objects, and methods in your project’s **`src/main/scala`** (and any Scala sources in other source sets).

**Multi-module projects:** If your project has multiple submodules, each would generate its own Scaladoc by default. You may choose to aggregate them (e.g., by configuring a root project task that depends on subprojects’ `scaladoc` tasks and copies outputs together). However, for simplicity, this guide assumes a single-module project. (Aggregation can be done by customizing the ScalaDoc task to include sources from subprojects if needed.)

Customizing and Theming Scaladoc Output
---------------------------------------

The out-of-the-box Scaladoc is functional, but we can improve its appearance and usefulness with a few options:

*   **Project Title and Version:** You can set a custom title or project name in the documentation, and display the project’s version. ScalaDoc (Scala 2) supports `-doc-title` and `-doc-version` options. In Scala 3, these correspond to `-project` and `-project-version`. For example, setting `-project MyLibrary -project-version 1.2.3` will show _“MyLibrary 1.2.3”_ in the doc header[docs.scala-lang.org](https://docs.scala-lang.org/scala3/guides/scaladoc/settings.html#:~:text=%23%23%20). You can configure Gradle to pass these options. In a Gradle build script, you might do:
    
    ```groovy
    tasks.withType(ScalaDoc) {
        // For Scala 2.x:
        scalaDocOptions.setDocTitle("${project.name} API")
        scalaDocOptions.setWindowTitle("${project.name} ${project.version} API")
        scalaDocOptions.setFooter("© 2025 My Company")
        scalaDocOptions.setAdditionalParameters(["-doc-version", "${project.version}"])
        // For Scala 3, use -project and -project-version via additionalParameters if needed.
    }
    ```
    
    This will label your docs with the project name and version and add a custom footer. (Gradle’s `ScalaDocOptions` allows setting title, footer, etc., but some settings may internally pass to the Scaladoc tool[stackoverflow.com](https://stackoverflow.com/questions/39088691/setting-scaladoc-header-footer-in-gradle#:~:text=project).)
    
*   **Logo and Styling:** Scaladoc (especially Scala 3’s version) lets you include a project logo in the navigation header. Use the `-doc-logo` option (Scala 2) or `-project-logo` (Scala 3) to specify an image. For Scala 3, if you provide `mylogo.png`, you can also provide an optional `mylogo_dark.png` for dark mode[docs.scala-lang.org](https://docs.scala-lang.org/scala3/guides/scaladoc/settings.html#:~:text=%23%23%20). Place these image files where Scaladoc can find them (e.g., in the current directory or a known path) and add the option in Gradle:
    
    ```groovy
    tasks.withType(ScalaDoc) {
        scalaDocOptions.setAdditionalParameters([...,
            "-doc-version", "${project.version}",
            "-doc-logo", "path/to/mylogo.png"
        ])
    }
    ```
    
    This will embed your logo at the top of each page. Ensure the path is correct (you may copy the logo into the `build/docs/scaladoc/images/` folder after generation if needed, as Scaladoc might expect it in the output’s `images/` directory).
    
*   **Dark Theme and Appearance:** Scala 3’s new Scaladoc has a modern UI with dark mode support automatically. By providing a `_dark` variant of your logo as mentioned, you ensure it looks good on both light and dark themes[docs.scala-lang.org](https://docs.scala-lang.org/scala3/guides/scaladoc/settings.html#:~:text=The%20logo%20of%20your%20project,logo). The default color scheme of Scala 3’s docs has been debated, but it’s generally much nicer than Scala 2’s older frame-based docs. If using Scala 2 and you find the style dated, consider migrating to Scala 3’s doc tool or using custom CSS (though the latter is non-trivial without forking the doc template). For Scala 2, you can at least customize the header/footer text as shown, to replace the default “Generated by Scaladoc” footer with your own.
    
*   **Social and Source Links:** Scaladoc can integrate handy links. For instance, you can add links to your project’s GitHub, Twitter, etc., via the `-social-links` option (Scala 3 only). For example:
    
    ```scala
    -social-links:github::https://github.com/YourUser/YourRepo
    ```
    
    would add a GitHub icon in the docs that links to your repo[docs.scala-lang.org](https://docs.scala-lang.org/scala3/guides/scaladoc/settings.html#:~:text=%23%23%20). You can list multiple links (comma-separated) for different services (supported icons include GitHub, Gitter, Twitter, Discord, or even custom icons).
    
    Another very useful feature is linking from the API docs to your source code on GitHub. ScalaDoc 3 supports `-source-links` to map source files to a GitHub repository URL pattern[docs.scala-lang.org](https://docs.scala-lang.org/scala3/guides/scaladoc/settings.html#:~:text=%23%23%20). By configuring this with your repo info and the appropriate branch/tag, the generated docs will show “Source” links for classes, letting users jump to the code on GitHub. For example:
    
    ```scala
    -source-links:github://YourUser/YourRepo/main#src/main/scala
    ```
    
    would construct GitHub URLs for each source file (you might include `-revision ${SHA}` or tag to lock to the correct version).
    
*   **Grouping and Index:** If you have many APIs, you can group related ones using Scaladoc’s @group annotations and enable grouping with `-groups`. This will categorize functions or types in the output (Scala 2 needed `-groups`; Scala 3 might do this by default for certain annotations). Additionally, ScalaDoc (Scala 3) will by default generate an **index** and a search feature, making it easier to find classes by name.
    
*   **Inheritance Diagrams:** For Scala 2.x projects, Scaladoc can generate UML-style inheritance diagrams for classes and traits if Graphviz is available. Enabling the `-diagrams` option will create SVG diagrams illustrating class hierarchies[stackoverflow.com](https://stackoverflow.com/questions/20009030/where-is-the-man-page-for-scaladoc#:~:text=,Eg%3A%20%2Fusr%2Fbin%2Fdot). This can make the documentation more insightful visually. To use this, ensure the Graphviz `dot` tool is installed and on the PATH, and Gradle can be configured to add `-diagrams` to `scalaDocOptions.additionalParameters`. _Note:_ This is a Scala 2 feature; Scala 3’s doc tool currently does not generate these diagrams.
    
*   **Static Pages and Site Material:** One powerful new feature of Scala 3’s Scaladoc is the ability to include **static documentation pages** (similar to Jekyll or Docusaurus sites) along with the API docs[docs.scala-lang.org](https://docs.scala-lang.org/scala3/guides/scaladoc/static-site.html#:~:text=Scaladoc%20can%20generate%20static%20sites%2C,between%20static%20documentation%20and%20API)[docs.scala-lang.org](https://docs.scala-lang.org/scala3/guides/scaladoc/#:~:text=Scaladoc%20,well%20as%20jekyll%20or%20docusaurus). By default, if you put markdown files in a `docs/` directory, Scaladoc will incorporate them into the generated site (you may need to specify `-siteroot ./docs` if different)[docs.scala-lang.org](https://docs.scala-lang.org/scala3/guides/scaladoc/settings.html#:~:text=%23%23%20). This means you can have a user guide, examples, or other markdown pages in addition to the API reference, all in one site. For example, a `docs/Overview.md` can become a welcome page on your docs site. Leveraging this feature can greatly improve user-friendliness by providing context and tutorials alongside raw API docs.
    

In summary, take advantage of Scaladoc options to make your documentation stand out. At minimum, set the project name and version, and consider adding a project logo and useful links (source repository, etc.) to give users of your library a richer experience[docs.scala-lang.org](https://docs.scala-lang.org/scala3/guides/scaladoc/settings.html#:~:text=%23%23%20). Once you’ve configured these in Gradle, you’re ready to generate attractive docs.

Organizing Versioned Documentation on GitHub Pages
--------------------------------------------------

With Scaladoc generation in place, the next step is to publish the HTML files to GitHub Pages. We want to host multiple versions of the docs so users can browse older versions if needed, as well as a “latest” version (for the current development state or snapshot).

**GitHub Pages via `gh-pages` branch:** A common approach (which we’ll use) is to keep a separate branch `gh-pages` in your repository that contains the built documentation. GitHub will serve this content at `https://<username>.github.io/<repo>/`. We won’t use Jekyll or generators on GitHub’s side; we’ll simply push the static HTML that Scaladoc produces.

**Directory structure:** On the `gh-pages` branch, organize the docs by version. For example:

```text
gh-pages branch:
├── index.html  (optional landing page or redirect)
├── latest/     (latest docs for main branch)
├── 1.0.0/      (docs for version 1.0.0)
├── 1.1.0/      (docs for version 1.1.0)
└── versions.json  (optional version info file for the version menu)
```

Each version’s folder (e.g. **`1.0.0/`**) contains the `index.html` and resources exactly as generated by Scaladoc for that release. The **`latest/`** folder will contain the docs for the current state of the default branch (or you could use it for the latest _released_ version, but typically “latest” implies the cutting-edge documentation).

**Landing page:** You can have an `index.html` at the root of gh-pages to welcome users or automatically redirect them to the latest docs. For instance, your `index.html` could contain a meta-refresh or JavaScript to redirect to `latest/index.html`, or just a simple page with links to each version’s documentation. This is optional but improves usability (someone visiting the base URL will see something helpful).

**Preserving older versions:** It is important **not to delete** previously published docs when adding a new version. Each time you release a new version and push its docs, ensure you don't wipe out the existing folders. The process should be cumulative: add new version directory (and update “latest”), while keeping the others intact. This way, URLs for older docs (like `/1.0.0/index.html`) remain valid. We will implement our deployment scripts/steps to only add or update specific directories. (For example, if using a tool, use include/exclude filters to preserve certain folders[github.com](https://github.com/ajoberstar/gradle-git-publish#:~:text=%2F%2F%20what%20to%20keep%20in,exclude%20%271.0.0%2Ftemp.txt%27)).

**Version dropdown (optional):** As a bonus, Scala 3 Scaladoc can display a version selector in the top menu if you provide a JSON mapping of version names to URLs. This is done via the `-versions-dictionary-url` option[docs.scala-lang.org](https://docs.scala-lang.org/scala3/guides/scaladoc/settings.html#:~:text=%23%23%20). You host a JSON file (say, `versions.json` in the gh-pages branch) that looks like:

```json
{
  "versions": {
    "1.0.0": "https://your-user.github.io/your-repo/1.0.0/index.html",
    "1.1.0": "https://your-user.github.io/your-repo/1.1.0/index.html",
    "Latest": "https://your-user.github.io/your-repo/latest/index.html"
  }
}
```

Then, when generating Scaladoc for a given version, pass `-versions-dictionary-url https://your-user.github.io/your-repo/versions.json`. The resulting HTML pages will include a “versions” dropdown that lets readers switch between 1.0.0, 1.1.0, Latest, etc., and navigate to those URLs[docs.scala-lang.org](https://docs.scala-lang.org/scala3/guides/scaladoc/settings.html#:~:text=%7B%20,). Maintaining this JSON is simple: whenever you add a new version, update the file with that version and URL. (You can automate updating this file in the deployment script.)

Now that the structure and approach are defined, let's see how to actually copy and publish the files.

Manual Publishing with a Python Script
--------------------------------------

We can create a Python script to automate the documentation publishing steps. This script will:

1.  **Run the Gradle Scaladoc task** to generate the docs.
    
2.  **Check out (or clone) the `gh-pages` branch** of the repository.
    
3.  **Copy the newly generated docs** into the appropriate directory in the `gh-pages` working copy (e.g., into `latest/` and/or a versioned folder).
    
4.  **Commit and push** the changes to the `gh-pages` branch (publishing the docs).
    

Using Python allows us to execute this process on any machine (locally or in CI) in a controlled way. We will rely on Git being available for pushing to GitHub. You can use a library like **GitPython** for finer control, but using `subprocess` to call Git is straightforward and avoids extra dependencies.

Below is a sample **`publish_docs.py`** script outline:

```python
import subprocess, os, shutil

# Configuration – adjust these for your repository
repo_url = "git@github.com:YourUser/YourRepo.git"  # SSH URL (or use https:// with token)
branch = "gh-pages"
build_dir = "build/docs/scaladoc"  # Scaladoc output directory

# Optionally accept a version argument (e.g., via env var or CLI arg)
version = os.getenv('DOC_VERSION')  # e.g., "1.2.0" for releases; None for latest

# 1. Build the documentation using Gradle
subprocess.run(["./gradlew", "scaladoc"], check=True)

# 2. Clone the gh-pages branch to a temporary directory
gh_pages_dir = ".gh-pages-temp"
if os.path.exists(gh_pages_dir):
    shutil.rmtree(gh_pages_dir)
subprocess.run(["git", "clone", "-b", branch, "--single-branch", repo_url, gh_pages_dir], check=True)

# 3. Copy the new docs into the gh-pages working tree
target_folder = version if version else "latest"
dest_path = os.path.join(gh_pages_dir, target_folder)
# Remove old files in target_folder to avoid stale files
shutil.rmtree(dest_path, ignore_errors=True)
shutil.copytree(build_dir, dest_path)

# (Optional) Update 'latest' as an alias for this version
if version:
    latest_path = os.path.join(gh_pages_dir, "latest")
    shutil.rmtree(latest_path, ignore_errors=True)
    shutil.copytree(build_dir, latest_path)

# (Optional) Update versions.json for version dropdown
versions_file = os.path.join(gh_pages_dir, "versions.json")
if os.path.exists(versions_file) and version:
    import json
    with open(versions_file, 'r') as vf:
        data = json.load(vf)
    label = version  # e.g. "1.2.0"
    url = f"https://your-user.github.io/your-repo/{version}/index.html"
    data["versions"][label] = url
    # Also update "Latest" to point to this version if desired:
    data["versions"]["Latest"] = f"https://your-user.github.io/your-repo/latest/index.html"
    with open(versions_file, 'w') as vf:
        json.dump(data, vf, indent=2)

# 4. Commit and push the changes to gh-pages
subprocess.run(["git", "add", "."], cwd=gh_pages_dir, check=True)
msg = f"Publish docs for {version}" if version else "Update latest docs"
subprocess.run(["git", "commit", "-m", msg], cwd=gh_pages_dir, check=True)
subprocess.run(["git", "push"], cwd=gh_pages_dir, check=True)
```

**How to use this script:** Ensure you have push access to the repo (for example, set up SSH auth or have a personal access token if using HTTPS). Then run `python publish_docs.py`. If you set an environment variable `DOC_VERSION` to a version number, the script will treat it as a release and publish to that version folder (and also update “latest” to that version). If no version is provided, it will publish only to `latest/`.

For a real implementation, you might want to add error handling, argument parsing (e.g., use `argparse` to take a `--version` flag), and logging for clarity. You should also configure Git identity if not already (the script assumes your global Git config has user name/email or you could set env like `GIT_AUTHOR_NAME` for CI commits).

**Security:** If running in CI, you wouldn’t use `git@github.com` (SSH) unless you set up keys; instead, you might use an HTTPS URL with a token: e.g., `https://x-access-token:${GITHUB_TOKEN}@github.com/YourUser/YourRepo.git`. In GitHub Actions, `${{ secrets.GITHUB_TOKEN }}` can be used for authentication. Our next section covers the CI setup.

CI/CD Integration with GitHub Actions
-------------------------------------

To fully automate the docs publishing, we can use GitHub Actions to trigger the process on certain events, such as pushes to the main branch and new version tags. GitHub Actions can run the Gradle build, then either use our Python script or directly use an action to deploy to Pages.

Using the script in CI is as simple as adding a step to run `publish_docs.py` (with the proper environment). Alternatively, there are community Actions specifically for deploying to GitHub Pages which can simplify things. One popular choice is **JamesIves/github-pages-deploy-action**, which handles the git work for you[stackoverflow.com](https://stackoverflow.com/questions/62913488/how-can-i-publish-the-docs-to-github-pages-after-generating-it-via-dokka-kotlin#:~:text=,pages%20FOLDER%3A%20build%2Fdocs).

Below is an example workflow that builds and publishes docs on two events:

*   **Push to main**: updates the **latest** docs.
    
*   **Push of a git tag** (e.g., a version tag like v1.2.0): publishes docs under that version directory (and updates latest accordingly).
    

```yaml
name: PublishDocs
on:
  push:
    branches: [ main ]
    tags: [ 'v*' ]   # triggers on tag pushes like v1.2.0, v2.0, etc.

jobs:
  docs:
    runs-on: ubuntu-latest
    permissions:
      contents: write   # allow pushing to gh-pages
    steps:
      - uses: actions/checkout@v3
        with:
          persist-credentials: false   # we'll use a token explicitly
          fetch-depth: 0   # fetch all history to get tags if needed

      - name: Set up JDK
        uses: actions/setup-java@v3
        with:
          distribution: 'Temurin'  # AdoptOpenJDK (Eclipse Temurin)
          java-version: '17'       # or 11, depending on your project

      - name: Build Scaladoc
        run: ./gradlew scaladoc

      - name: Publish docs (latest)
        if: ${{ github.ref == 'refs/heads/main' }}
        uses: JamesIves/github-pages-deploy-action@v4
        with:
          branch: gh-pages
          folder: build/docs/scaladoc
          target-folder: latest
          clean: true           # remove outdated files in 'latest/'
          token: ${{ secrets.GITHUB_TOKEN }}

      - name: Publish docs (versioned)
        if: ${{ startsWith(github.ref, 'refs/tags/') }}
        uses: JamesIves/github-pages-deploy-action@v4
        with:
          branch: gh-pages
          folder: build/docs/scaladoc
          target-folder: ${{ github.ref_name }}   # e.g. 'v1.2.0'
          clean: false          # don't wipe entire branch, just add/update this folder
          token: ${{ secrets.GITHUB_TOKEN }}
```

Let’s break down what this workflow does:

*   It triggers on pushes to `main` and on pushes of tags matching `v*`. (You could also trigger on the creation of a GitHub Release if you prefer, but using tags is straightforward).
    
*   It checks out the code. We disable `persist-credentials` so that the checkout action doesn’t retain the repo’s token (since we will use the deploy action’s token to push). We also fetch full history (`fetch-depth: 0`) in case we need tag info (not strictly required for this deploy, but good practice when using tags).
    
*   It sets up Java (Gradle needs a JDK). Ensure the Java version here matches what your project needs (Scala 2.13/3 requires JDK 8+; using 11 or 17 is fine).
    
*   It runs `./gradlew scaladoc` to generate the docs.
    
*   Then we have two deploy steps:
    
    *   **Latest**: runs only on the main branch push. It uses the GitHub Pages Deploy Action. We specify the `folder` as the output directory (`build/docs/scaladoc`) and `target-folder: latest`. This tells the action to take everything in `build/docs/scaladoc` and push it to the `gh-pages` branch under a folder named “latest”. We set `clean: true` here to ensure that the `latest/` folder on the branch is fully synced with this new content (any old files in `latest/` that aren’t in the new build will be removed) – this is fine because `latest` is supposed to track the current content exactly. The action uses the provided `GITHUB_TOKEN` (which is an automatically provided token with permissions to the repo) to authenticate the push. (No need to create a personal token for this, unless you prefer; the built-in token works for pushing to `gh-pages` on the same repo, given `contents: write` permission was set).
        
    *   **Versioned**: runs only on tag pushes. This one deploys to a folder named after the tag. GitHub Actions exposes the tag name in `github.ref_name` (for a tag ref `refs/tags/v1.2.0`, `ref_name` is `v1.2.0`). We use that as the folder. We set `clean: false` to avoid wiping other content on the branch. This means it will add/update the files in the `v1.2.0/` directory and leave everything else untouched – which is what we want for preserving older docs. We could additionally use `clean-exclude` if needed to be extra safe in preserving, but with `target-folder` and `clean:false`, it should only affect that subdirectory. After this step, the new version’s docs are published. We did not explicitly update “latest” here; if you want the tag deployment to also update the `latest` docs (assuming “latest” should always mirror the newest release), you could add another step in the tag workflow to copy the same files to `latest/`. In our example, if main is always ahead with potentially unreleased changes, you might keep latest tied to main, not to the last tag – this choice is up to your project’s versioning strategy.
        

This workflow approach uses the community action for convenience. It encapsulates the git clone/add/commit/push steps, so you don't need to maintain that logic. On each run, the action will output logs of its operation (cloning gh-pages, committing new files, etc.).

**Enabling GitHub Pages:** Remember to enable GitHub Pages in your repository settings to serve from the `gh-pages` branch. Go to **Settings > Pages**, and set the source to “Deploy from a branch”, then select `gh-pages` and root (or `gh-pages` and `/docs` if you put site in a docs folder on that branch; in our case it’s root). Once enabled, your pages will be live at the URL given. The workflow above even notes that you might need to run it once to create the `gh-pages` branch if it doesn’t exist[stackoverflow.com](https://stackoverflow.com/questions/62913488/how-can-i-publish-the-docs-to-github-pages-after-generating-it-via-dokka-kotlin#:~:text=BRANCH%3A%20gh), and then configure the Pages settings.

**Using the Python script in CI:** Alternatively, you could replace the deploy action steps with a call to the Python script we wrote. For example, install Python and any requirements in the workflow, then run `python publish_docs.py`. You’d need to supply credentials (perhaps by setting `GITHUB_TOKEN` or using a PAT) for the script’s git push. The deploy action simplifies this by using the provided token. Both approaches are valid; using the script might give you more control (e.g., updating the versions JSON, which the simple action approach above doesn’t do automatically). You could incorporate the JSON update logic into the workflow as well – for instance, after publishing, do a separate commit to add/update `versions.json`. Depending on your needs, choose the method you’re most comfortable with. The **official tools** (like the deploy Action or the Gradle plugin mentioned below) are robust and maintained, which reduces the chance of script errors.

Best Practices and Alternatives
-------------------------------

*   **Keep “latest” up to date**: If your project’s default branch (e.g. main) is where development happens, it’s useful to auto-publish those docs to “latest” on every push. That way, contributors or users can see documentation for the unreleased state. If you want “latest” instead to point to the most recent _release_, you can adjust your strategy: for example, only update “latest” when a tag is released (or have a “snapshot” vs “stable” distinction).
    
*   **Maintain older versions**: We addressed this, but always double-check that your automation script/action does not delete the existing version directories on gh-pages. When using the GitHub Pages Deploy Action, using `target-folder` for a subdirectory and `clean: false` is one way to ensure only that subfolder is touched. If writing your own script, be careful to not call `git push --force` on the entire branch in a way that resets history (prefer a regular commit that only adds the new files).
    
*   **Gradle plugin approach**: Instead of a custom Python script or GitHub Action, you can also consider the Gradle plugin **gradle-git-publish** (by ajoberstar). This plugin can automate publishing to a git branch as part of your Gradle build. For example, you can configure it to publish the contents of `build/docs/scaladoc` to `gh-pages`, and specify patterns to preserve certain files/folders[github.com](https://github.com/ajoberstar/gradle-git-publish#:~:text=%2F%2F%20what%20to%20keep%20in,exclude%20%271.0.0%2Ftemp.txt%27) (to avoid deleting older docs). Then you could run `./gradlew gitPublishPush` to push docs. This is a more “all-Gradle” solution. However, using it still requires providing credentials (which you’d do via environment variables for GH token or using your SSH agent), and in CI you’d hook it up similarly. Both approaches are valid; using the standalone script or action might be easier to understand and maintain for many.
    
*   **Testing the setup**: It’s a good idea to test the publishing process on a dummy repository or a personal fork first, especially the GitHub Actions workflow, to ensure everything works as expected (and the docs look correct on GitHub Pages). Once confirmed, you can integrate it into your main repo.
    
*   **Using custom domains or project pages**: If your GitHub Pages is using a custom domain or is the user/org page, the principle is the same — just be sure the links and JSON version URLs reflect the correct domain.
    

With this setup, every time you merge to main or push a new version tag, your Scaladoc will be generated and published automatically. The documentation site will be nicely themed (with your project’s branding) and users will be able to browse the API for the latest code as well as switch between versions. This provides a professional touch to your Scala project and reduces the manual work in keeping docs up-to-date. Enjoy your fully automated Scaladoc pipeline! 🚀

**Sources:**

*   Gradle Scala Plugin documentation – confirms the `scaladoc` task for generating Scala API docs[docs.gradle.org](https://docs.gradle.org/current/userguide/scala_plugin.html#:~:text=) and default output location[github.com](https://github.com/decisionbrain/cplex-scala#:~:text=To%20generate%20the%20scala%20docs%2C,do).
    
*   Scala 3 Scaladoc options – for theming (project logo, version, footer, etc.)[docs.scala-lang.org](https://docs.scala-lang.org/scala3/guides/scaladoc/settings.html#:~:text=%23%23%20) and version menu support[docs.scala-lang.org](https://docs.scala-lang.org/scala3/guides/scaladoc/settings.html#:~:text=%23%23%20)[docs.scala-lang.org](https://docs.scala-lang.org/scala3/guides/scaladoc/settings.html#:~:text=%7B%20,).
    
*   Example GitHub Actions usage of GitHub Pages Deploy Action[stackoverflow.com](https://stackoverflow.com/questions/62913488/how-can-i-publish-the-docs-to-github-pages-after-generating-it-via-dokka-kotlin#:~:text=,pages%20FOLDER%3A%20build%2Fdocs) and guidelines for tokens[stackoverflow.com](https://stackoverflow.com/questions/62913488/how-can-i-publish-the-docs-to-github-pages-after-generating-it-via-dokka-kotlin#:~:text=You%27ll%20need%20to%20adapt%20the,where%20the%20docs%20are%20generated).
    
*   Gradle Git Publish plugin example – shows preserving an older docs folder during publish[github.com](https://github.com/ajoberstar/gradle-git-publish#:~:text=%2F%2F%20what%20to%20keep%20in,exclude%20%271.0.0%2Ftemp.txt%27).
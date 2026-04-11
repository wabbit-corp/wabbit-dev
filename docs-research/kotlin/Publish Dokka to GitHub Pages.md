## Prompt:
how to publish dokka docs to github pages

## Response:
Thought about publishing Dokka documentation for 4 seconds

Below is a straightforward approach to generating Dokka documentation and then publishing those docs to a GitHub Pages site. The general steps:

1.  **Add Dokka to your build**
    
2.  **Configure Dokka as needed**
    
3.  **Generate the docs**
    
4.  **Publish the generated docs to GitHub Pages**
    

1\. Add Dokka to your build
---------------------------

If you use **Gradle (Kotlin DSL)**, in your `build.gradle.kts`:

```kotlin
plugins {
    id("org.jetbrains.dokka") version "<latest-version>"
    // ...
}
```

Or if you use **Gradle (Groovy DSL)**, in your `build.gradle`:

```groovy
plugins {
    id 'org.jetbrains.dokka' version '<latest-version>'
    // ...
}
```

Replace `"<latest-version>"` with the latest Dokka version found in [Dokka’s GitHub repo](https://github.com/Kotlin/dokka) or Gradle plugin portal.

2\. Configure Dokka
-------------------

Basic configuration in `build.gradle.kts` (Kotlin DSL):

```kotlin
dokkaHtml {
    outputDirectory.set(buildDir.resolve("dokka"))
    dokkaSourceSets {
        named("main") {
            // Configure per-source-set settings if needed
            // For example:
            // includes.from("docs/packages.md")
        }
    }
}
```

Or in `build.gradle` (Groovy DSL):

```groovy
dokkaHtml {
    outputDirectory = file("$buildDir/dokka")
    dokkaSourceSets {
        main {
            // Additional configuration here
        }
    }
}
```

Check Dokka configuration reference for available options, such as linking to external documentation, changing formats (e.g., `dokkaHtmlPartial`), etc.

3\. Generate the Docs
---------------------

Run:

```bash
./gradlew dokkaHtml
```

(or `dokkaHtml` in your Gradle tasks). The output will typically be in `build/dokka` (depending on how you configured it).

4\. Publish the Generated Docs to GitHub Pages
----------------------------------------------

### Option A: Manually push docs to `gh-pages` branch

1.  **Create (or use) a `gh-pages` branch** in your repository.
    
2.  **Generate Dokka docs** locally:
    
    ```bash
    ./gradlew dokkaHtml
    ```
    
3.  **Move into the build output directory** (for example, `build/dokka`) and copy or move the contents into a folder that you’ll commit to the `gh-pages` branch.
    
4.  **Commit and push** those files to the `gh-pages` branch.
    

Then, in your GitHub repo’s settings:

*   Go to **Settings** → **Pages** (or “Pages” in the left-hand side menu).
    
*   Under “Branch”, select `gh-pages` and click **Save**.
    
*   Your docs will typically be served at `https://<your-username>.github.io/<repo-name>/`.
    

### Option B: Use GitHub Actions to automate

You can add a GitHub Actions workflow to automatically build and publish the documentation each time you push to `main` (or any branch you specify). Create a file named `.github/workflows/dokka.yml` in your repo with something like:

```yaml
name: Publish Dokka to GitHub Pages

on:
  push:
    branches: [ "main" ]

jobs:
  build-and-publish:
    runs-on: ubuntu-latest

    steps:
      - name: Check out repository
        uses: actions/checkout@v3

      - name: Set up JDK
        uses: actions/setup-java@v3
        with:
          distribution: 'temurin'
          java-version: 17

      - name: Build with Gradle
        run: ./gradlew dokkaHtml

      - name: Deploy to GitHub Pages
        uses: peaceiris/actions-gh-pages@v3
        with:
          github_token: ${{ secrets.GITHUB_TOKEN }}
          publish_dir: ./build/dokka
          # If you'd like to publish to a subpath or need extra config, set them here.
```

Explanation:

1.  **Check out** the repo.
    
2.  **Set up Java** so Gradle can run Dokka.
    
3.  **Build** the docs with `dokkaHtml`.
    
4.  **Publish** the contents of `build/dokka` to GitHub Pages (by default, to the `gh-pages` branch).
    

This way, every time you push, your Dokka docs get updated on GitHub Pages automatically.

* * *

**That’s it!** You now have a basic flow for generating Dokka docs and publishing them to GitHub Pages—either manually by committing the generated documentation to the `gh-pages` branch or automatically using GitHub Actions.
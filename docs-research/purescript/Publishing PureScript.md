Publishing a PureScript library in 2025 is much simpler than it used to be. The community now uses the PureScript Registry (often called the “Spaghetti” package registry, managed via **Spago**) for publishing packages. This registry automates documentation uploads and package-set updates, so you no longer need to manually use Bower or Pursuit for new releases[github.com](https://github.com/purescript/registry#:~:text=,your%20package%20in%20the%20registry). In this tutorial, we’ll walk through every step to publish a publicly accessible PureScript package using Spago. We assume you already have a PureScript project (or are ready to create one), you own a domain name (with an email address on that domain for identity), and you want to make your library available to everyone. The guide will cover prerequisites, setting up package metadata, versioning, publishing to the registry, domain-based author verification, testing, and troubleshooting.

Prerequisites
-------------

Before you begin, make sure you have the following in place:

*   **PureScript Compiler** – Install the PureScript compiler (`purs`) version 0.15.x or later (e.g. via npm or your OS package manager). This is needed to build your package.
    
*   **Spago (Spaghetti Package Manager)** – Install Spago, which is PureScript’s build tool and package manager. The recommended way is via NPM: `npm install -g spago@next`[github.com](https://github.com/purescript/spago#:~:text=The%20recommended%20installation%20method%20for,latest%20releases%20on%20npm%20here). (The `@next` tag ensures you have the latest Spago with registry support.) Verify by running `spago --version`.
    
*   **Node.js and NPM** – Required for installing Spago (and possibly for running builds/tests if your library or tools require Node).
    
*   **Git** – Make sure Git is installed and your project is in a Git repository. You’ll use Git to tag releases and Spago/Registry will fetch your code from Git.
    
*   **GitHub Repository (or other Git hosting)** – For public packages, hosting your code on GitHub is easiest. The PureScript Registry by default uses a GitHub repo’s URL to fetch your package. (Other git servers are supported via custom URLs if needed[github.com](https://github.com/purescript/spago#:~:text=,name).) Ensure your repository is public.
    
*   **Domain Email Address** – Since you own a domain, prepare an email address on that domain (e.g. `you@your-domain.com`). You will use this as an identifier when setting up package ownership (this **does not** need to be verified via DNS, but using it helps tie the package to your domain).
    
*   **SSH Key (for author verification)** – It’s recommended to have an SSH key pair for signing your releases. If you don’t have one, generate a new key (for example, using `ssh-keygen -t ed25519 -C "you@your-domain.com"` to create an Ed25519 key with your domain email as a label). Keep the private key secure; we will use the public key to verify ownership of the package.
    

Step 1: Initialize Your PureScript Project (if not already)
-----------------------------------------------------------

If you already have a PureScript project you want to publish, you can skip initialization. Otherwise, to create a new project:

1.  **Create a project directory** – e.g. `mkdir purescript-myproject && cd purescript-myproject`.
    
2.  **Initialize with Spago** – Run `spago init`. This will set up a PureScript project with a `spago.dhall` or `spago.yaml` configuration (the new Spago uses a YAML config). It also creates a sample source file and a default package set.
    
3.  **Verify the setup** – Run `spago build` to compile the sample project. This ensures your compiler and Spago are working.
    

If your project was already set up with an older Spago (Dhall config), consider updating to the latest config format. Spago’s new version uses `spago.yaml` for configuration. You can run `spago upgrade-config` (if provided) or manually translate your `spago.dhall` to `spago.yaml`. Using the latest format is important because publishing to the registry requires certain fields in the config.

Step 2: Configure Package Metadata in `spago.yaml`
--------------------------------------------------

Next, you need to configure your package’s metadata in the Spago config. Spago’s config file declares your package name, dependencies, and crucial information for publishing. Open the `spago.yaml` file in your project (if it’s still `spago.dhall`, you can add similar fields there or upgrade).

**In the `spago.yaml`, add or update the following:**

*   **Package Name**: Under a top-level `package` section, set the `name` of your package. This is the name that will be used in the registry and by users to install your library. Choose a unique, descriptive name. (You no longer need the `purescript-` prefix in the name – the registry enforces uniqueness globally[github.com](https://github.com/purescript/registry-dev/issues/388#:~:text=What%20should%20we%20do%20about,json%20file%20or).) For example:
    
    ```yaml
    package:
      name: my-awesome-library
      dependencies:
        - prelude
        - effect
      description: "A library that does awesome things."
    ```
    
    Make sure to list all PureScript package dependencies under `dependencies`. Use the proper names as they appear in the package set or registry (e.g. `prelude`, `effect`, etc.). You can specify dependency versions or ranges if using the registry’s solver, but it’s common to just list names or use `*` for latest allowed[github.com](https://github.com/purescript/spago#:~:text=,package)[github.com](https://github.com/purescript/spago#:~:text=,range%3A%20%22%3E%3D1.1.1%20%3C2.0.0). (For instance, `some-package: "*"` would allow the latest version, or you can pin a range like `">=1.0.0 <2.0.0"`.)
    
*   **Publish Metadata**: Add a `publish` subsection inside `package` (this section is optional for local development but **mandatory** when you intend to publish[github.com](https://github.com/purescript/spago#:~:text=,Clause)):
    
    ```yaml
      publish:
        version: 0.1.0
        license: MIT
        repository: "https://github.com/your-user/your-repo.git"
        location:
          githubOwner: your-user
          githubRepo: your-repo
        # owners field will be added later by spago auth (see next step)
    ```
    
    Let’s break down these fields:
    
    *   **version** – The current version of your package, following semantic versioning (MAJOR.MINOR.PATCH). For an initial release, you might start with `0.1.0` (or `1.0.0` if it’s production-ready). Every time you publish a new version, this should be updated. _Note:_ Pre-release tags (like `-alpha`) are not supported by the registry; use plain SemVer numbers[github.com](https://github.com/purescript/spago#:~:text=,the%20Registry%20includes%20by%20default).
        
    *   **license** – The SPDX identifier for your project’s license (e.g. `MIT`, `BSD-3-Clause`, `Apache-2.0`, etc.). Ensure you have a `LICENSE` file in your repo corresponding to this. The registry requires a license field so users know the terms of use[github.com](https://github.com/purescript/spago#:~:text=,files).
        
    *   **repository** – (If using Spago Next, this might not be explicitly required if `location` is given, but it’s good practice to mention where the code lives.) This can be the Git URL of your repository. It’s mainly informational in the manifest, as the `location` field (next) is what the registry uses to fetch code.
        
    *   **location** – This tells the registry where to fetch your package’s source code. Since you’re using GitHub, provide the `githubOwner` (your GitHub username or org) and `githubRepo` (the repo name). Spago will use this to let the registry know how to clone your repo[github.com](https://github.com/purescript/spago#:~:text=,name). (If your PureScript package lives in a subdirectory of the repo, you can also specify `subdir`, but for most libraries it’s at the root.) For example, if your library is at `github.com/alice/purescript-foo`, use `githubOwner: alice` and `githubRepo: purescript-foo`. If you were hosting git elsewhere, you could use `url: git://...` instead.
        
    *   **(Optional) include/exclude** – You can specify file globs to include or exclude from the published tarball. By default, the registry will include your source files (`src/**/*.purs`), your README, LICENSE, and other essentials, and will exclude irrelevant files like your `output/` or Git metadata[github.com](https://github.com/purescript/spago#:~:text=,dev%2Fblob%2Fmaster%2FSPEC.md%23always)[github.com](https://github.com/purescript/spago#:~:text=excluded,to%20release%20the%20code%20without). If you want to include additional files (for example, example code or tests), you can list them under `publish.include`. If you want to omit something that would normally be included, list it under `publish.exclude`. In most cases, you don’t need to set these – the defaults are fine.
        
*   **Double-check dependencies and compiler compatibility**: Ensure your package’s dependencies are up-to-date and compatible with the latest PureScript compiler. The registry will attempt to compile your code with the compiler version you specify when publishing (if not specified, it uses the latest). For an initial publish, you can usually rely on the latest compiler (e.g. 0.15.**x**). If your library only works on an older compiler, you’ll need to indicate that during publishing (the `compiler` version is part of the publish process, which Spago will handle).
    

After editing `spago.yaml`, **save the file and commit the changes** to Git (e.g., `git add spago.yaml && git commit -m "Configure package metadata for publishing"`). This config now contains all the metadata the PureScript Registry needs to identify and catalog your package.

Step 3: Set Up Author Verification (Add Owners with your Domain Email)
----------------------------------------------------------------------

This step is about **proving ownership** of your package in the registry using your SSH key. While not strictly required for the first publish, adding yourself as an owner is highly recommended. It will allow you to perform future actions like transferring or unpublishing the package if necessary[github.com](https://github.com/purescript/registry#:~:text=The%20Registry%20API%20allows%20package,key%20is%20listed%20in%20the)[github.com](https://github.com/purescript/registry#:~:text=,ed25519%22%2C%20%22public). It also firmly attaches your identity (your email/domain) to the package record.

Here’s how to add the owners field:

1.  **Generate an SSH key** (if you haven’t already) with your domain email. For example:
    
    ```bash
    ssh-keygen -t ed25519 -C "you@your-domain.com"
    ```
    
    This creates a public/private key pair. The public key will contain a line like `ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIE... you@your-domain.com`. The email at the end is used as an identifier. (The registry doesn’t verify the email’s domain; it just checks that the email string matches the one in the key when you use the key[github.com](https://github.com/purescript/registry#:~:text=match%20at%20L357%20,ed25519%22%2C%20%22public). So it can be any string, but using your real email/domain is good documentation.)
    
2.  **Add your public key to Spago’s config** using the Spago `auth` command. Spago can update the config’s `owners` list for you. Run:
    
    ```bash
    spago auth --public-key path/to/your_id_ed25519.pub --private-key path/to/your_id_ed25519
    ```
    
    _(If you omit arguments, Spago may prompt for the key, or you can specify the key paths as shown.)_ This command will take your keys and add an entry in `package.publish.owners` in the `spago.yaml`. After running it, open `spago.yaml` to confirm under the `publish` section an `owners` field has appeared, for example:
    
    ```yaml
    publish:
      version: 0.1.0
      license: MIT
      repository: "https://github.com/your-user/your-repo.git"
      location:
        githubOwner: your-user
        githubRepo: your-repo
      owners:
        - email: "you@your-domain.com"
          keytype: "ssh-ed25519"
          public: "AAAAC3NzaC1lZDI1NTE5AAAAIEYourPublicKeyBytes123..."
    ```
    
    Spago populates `owners` with your public key info[github.com](https://github.com/purescript/registry#:~:text=,ed25519%22%2C%20%22public). The `email` here is taken from your key’s comment (so it should show your domain email), `keytype` is the type of key (e.g. `ssh-ed25519` or `ssh-rsa`), and `public` is the public key string. Note that the email in this field doesn’t have to be a working email address; it just needs to match the key’s identity string[github.com](https://github.com/purescript/registry#:~:text=,ed25519%22%2C%20%22public). In our case, it matches your domain email, which is perfect.
    
3.  **Commit the updated config**: `git add spago.yaml && git commit -m "Add owner public key for registry"`. The owners info will be published along with your package. With your key recorded as an owner, the registry will recognize your future signed requests (should you need to transfer or unpublish the package). Essentially, you’ve verified _you_ are the package author in a cryptographic way.
    

**No DNS TXT record or additional domain verification is required** beyond this. The presence of your domain email in the owners field is mostly for human identification. Ownership control is actually enforced by the SSH public key. So, you do not need to, for example, prove domain ownership via a DNS record – the SSH key is the proof of identity.

_(Optional)_: If you have multiple maintainers, you can add multiple owners (each with their own email and key) by running `spago auth` for each key, or by editing the YAML to include multiple entries under `owners`. Only listed owners (or registry trustees) can perform sensitive operations on the package later[github.com](https://github.com/purescript/registry#:~:text=The%20Registry%20API%20allows%20package,key%20is%20listed%20in%20the).

Step 4: Build and Test Your Package Locally
-------------------------------------------

Before releasing, it’s important to ensure that your library builds correctly and that all tests pass (if you have tests). This helps catch any issues early and gives confidence that the package will compile on the registry’s build servers.

*   **Clean and install deps**: It can help to start from a clean slate. If you previously built the project, you might remove any generated files: `rm -rf output/ .spago/`. Then ensure you have all dependencies: run `spago install` (for package-set mode) or `spago build` (which will also fetch dependencies if using the registry solver).
    
*   **Build the library**: Run `spago build`. This will compile your source. It should produce an `output/` directory with the compiled modules. If there are any compile errors or missing dependency issues, fix them now.
    
*   **Run tests** (if applicable): If you have a test suite, ensure it’s listed in your `spago.yaml` (often tests are separate or included via a `spago.test.dhall`). Run `spago test` to execute tests. All tests should pass.
    
*   **Preview documentation** (optional): You can generate docs locally to see how your documentation will look. Run `spago docs` which will produce documentation for your package. You can open the generated HTML in `generated-docs/` to review it. This isn’t required, but it’s a nice way to verify that module documentation and examples render as expected.
    

If both the build and tests succeed, you’re ready to publish. If you encounter any errors, resolve them before proceeding. Common issues might be:

*   Forgot to add a dependency in `spago.yaml`.
    
*   Warnings or deprecations (try to fix or at least note them).
    
*   Test failures or examples that need updating.
    

By the end of this step, you have a config ready for publishing and a verified working build of version 0.1.0 (as per our example).

Step 5: Bump the Version and Tag the Release
--------------------------------------------

When you’re satisfied with the state of your code, the next step is to finalize the version number and create a Git tag for the release. The PureScript Registry identifies releases by Git tags (e.g. `v0.1.0`). We already set `version: 0.1.0` in the config earlier; now we need to make sure the Git tag for this version exists and is pushed to the remote repository.

**Option A: Use Spago to bump version and tag automatically.** Spago provides a convenient command to bump the version and create a tag:

```bash
spago bump-version patch --no-dry-run
```

This command will:

*   Update the version in your `spago.yaml` (incrementing the patch part in this example; you could use `minor` or `major` for larger releases, or provide an explicit version number).
    
*   Commit the version change (if it hasn’t been committed).
    
*   Create a Git tag `v0.1.1` (or whatever the new version is) and by using `--no-dry-run`, actually apply it (without `--no-dry-run`, it would simulate the changes).
    
*   It may also generate a legacy `bower.json` for backward compatibility if needed, but with the registry, that’s less critical now[discourse.purescript.org](https://discourse.purescript.org/t/how-i-publish-a-purescript-package/2482#:~:text=2.%20%60spago%20bump).
    

After running this, check `git log` or `git tag` to ensure the new tag was created. If the tag was created locally, push it to GitHub:

```bash
git push origin v0.1.1
```

_(Replace `v0.1.1` with your tag name.)_ Pushing the tag is important because the registry will fetch the source code from the GitHub tag reference.

**Option B: Bump and tag manually.** If you prefer manual control or didn’t use `spago bump-version`:

*   Manually edit the `publish.version` in `spago.yaml` to the release number (ensure it matches the tag you plan to create).
    
*   Commit the change (`git commit -am "Bump version to 0.1.0"` if not already committed).
    
*   Create a git tag for the commit: `git tag -a v0.1.0 -m "Release v0.1.0"`.
    
*   Push the tag to the remote: `git push origin v0.1.0`.
    

Either way, at this point you should have a Git tag on your repository that corresponds to the version in your `spago.yaml`. For example, version `0.1.0` -> tag `v0.1.0`. The PureScript Registry will use this tag to fetch the code.

**Verify the tag on GitHub:** Go to your repository’s releases or tags page to confirm that `v0.1.0` (or your version) is present. If not, double-check the steps above.

Now you’re set to actually publish to the registry.

Step 6: Publish to the PureScript Registry
------------------------------------------

With everything prepared (metadata, version, tag, and owners), publishing the package is a one-command operation thanks to Spago’s registry integration.

Run the publish command in your project directory:

```bash
spago publish
```

Spago will use the information in `spago.yaml` to publish your library to the PureScript Registry[github.com](https://github.com/purescript/spago#:~:text=Publish%20my%20library). Here’s what happens during this step:

*   **Spago checks your config** – It will ensure that required fields are present (name, version, license, etc.) and that your working directory is clean. If something is missing (like no license specified) or you have uncommitted changes, it may warn or abort.
    
*   **Spago creates a registry request** – Under the hood, `spago publish` either interacts with the registry’s API directly or opens a GitHub issue on the registry repository with the package info. (As of now, Spago has official support to do this automatically[github.com](https://github.com/purescript/registry#:~:text=,your%20package%20in%20the%20registry), so you likely won’t need to open a browser manually.)
    
*   **The registry processes the publish request** – The PureScript Registry will receive your package metadata (package name, version, Git tag (ref), repository location, etc.) and begin validation. Specifically, it will fetch your repository at the given tag, verify that the package builds with the specified compiler, and register the package.
    
*   **Output and confirmation** – Spago will output status messages. If the process is fully automated, you might see a success message after a short wait. In some cases, Spago might give you a URL to a GitHub issue tracking the publish if manual confirmation is needed (for example, early versions of the registry used a GitHub Actions workflow to process publishes). If you see a link, open it to monitor progress. Otherwise, just wait for completion.
    

If all goes well, the package will be **registered** and the new version **published**. This means:

*   Your package **name** is now recorded in the PureScript Registry (locked to your GitHub repo location).
    
*   The version `v0.1.0` (or your version) is added with its metadata.
    
*   The registry will compile your package to ensure it’s compatible. If the compile fails, the publish will be rejected (you’d get an error log).
    
*   On success, the registry will automatically publish your package’s API docs to Pursuit (the online documentation site)[github.com](https://github.com/purescript/registry#:~:text=,your%20package%20in%20the%20registry). You don’t need to run `pulp publish` for docs – it’s handled for you.
    
*   The registry will attempt to add your package to the “package set” for the next release. This means if your package is compatible with the latest package set, it will be included so that Spago users (in package-sets mode) can install it easily[github.com](https://github.com/purescript/registry#:~:text=,your%20package%20in%20the%20registry). This is done automatically (usually within a day).
    
*   If this is a **new package** (first release), the registry now _registers_ the name. If it’s an update to an existing package, the registry links it to the existing entry.
    

Spago’s output or the linked issue will tell you if any step failed. Assuming success, congratulations – your package is now published! 🎉

_Important:_ The registry might use the PureScript compiler version you had in your config or the latest if not specified. If your code only works on a certain compiler (say 0.15.4), ensure you indicate that during publish. (Spago usually handles this by including the compiler version in the publish payload.)

Step 7: Verify the Published Package
------------------------------------

After publishing, it’s wise to verify that everything is in order:

*   **Check Pursuit Documentation**: Within a few minutes, your library’s documentation should appear on Pursuit (the PureScript package documentation site). Visit pursuit.purescript.org and search for your package name, or go directly to `https://pursuit.purescript.org/packages/your-package-name`. The docs should show the version you just released, along with your README and module documentation. (If you don’t see a README on Pursuit, ensure that a README.md exists in your repo at the tag. The registry will include it if present.)
    
*   **Try installing the package**: On a separate PureScript project (or a new test project), try to install your library as a dependency. For example, in an empty directory run:
    
    ```bash
    spago init
    spago install my-awesome-library
    ```
    
    Replace `my-awesome-library` with your package name. If the package was added to the latest package set, this should resolve and download your library. If the package set update hasn’t happened yet or if your package didn’t make it into the set immediately, you can still use the registry solver. Add to your `packages.dhall` (or `spago.yaml` workspace dependencies) an entry for your package with a version range, or use `spago install --resolver=registry`. In any case, by specifying the name and version, Spago should fetch it from the registry storage. Successful installation confirms the registry has your package. You can then `import Your.Module` in code to ensure it’s accessible.
    
*   **Review the registry metadata (optional)**: If curious, you can check the PureScript Registry GitHub repository’s `metadata/` folder for your package. It will have a JSON or Dhall manifest of your package version. This is not required, but it’s a way to confirm the registry entry. The registry’s index and storage are also publicly accessible (e.g., tarballs are stored at `packages.registry.purescript.org`).
    
*   **Package Sets**: The PureScript Registry publishes a new package set daily if any new packages or updates were added[discourse.purescript.org](https://discourse.purescript.org/t/registry-alpha-launched/3146#:~:text=1,repo%20to%20add%20your%20package)[discourse.purescript.org](https://discourse.purescript.org/t/registry-alpha-launched/3146#:~:text=The%20registry%20now%20publishes%20new,how%20to%20use%20the%20endpoint). Your package will be automatically included if possible. If your package had any compatibility issues (e.g., it depends on an older compiler or has a conflicting module name), the registry might skip adding it to the set and log an issue. But as long as you targeted the current compiler and have unique module names, you should be fine. The next day (or often sooner), your package will appear in the official package set used by Spago. You can verify this by checking the `packages.dhall` in the `purescript/package-sets` repo or simply by running an install as above without specifying versions.
    

Everything above confirms that your library is now publicly available for PureScript users. The heavy lifting (documentation publishing and package sets) is handled by the registry thanks to Spago’s integration[github.com](https://github.com/purescript/registry#:~:text=,your%20package%20in%20the%20registry).

Troubleshooting and Tips
------------------------

Even with the streamlined process, you might encounter some issues. Here are common problems and how to address them:

*   **Missing or Incorrect Metadata**: If `spago publish` fails immediately, read the error message. It could be due to missing required fields. For example, if you forgot to set a license or version in `spago.yaml`, Spago will complain. Fix the config and commit, then try again. _(Tip: The `publish` section in config is mandatory when publishing[github.com](https://github.com/purescript/spago#:~:text=,Clause).)_
    
*   **Uncommitted Changes**: Spago may refuse to publish if you have uncommitted changes in your working directory (to avoid publishing code that isn’t in Git). Make sure all your changes (especially the version bump and owners info) are committed before running `spago publish`. Similarly, ensure the Git tag for the version is pushed to the remote.
    
*   **Version Tag Mismatch**: The version in `spago.yaml` (and thus in the registry payload) must correspond to a Git tag in your repo. If you forget to create or push the tag, the registry won’t find your code. If `spago publish` reports something like “ref not found” or “could not fetch repository”, verify the tag on GitHub. You can fix this by pushing the tag and re-running the publish. In case you published with a wrong version by accident (say you had `0.1.0` in config but tag `v0.2.0`), you might need to unpublish or publish a corrected version (contact registry maintainers or use the `unpublish` API with your key if absolutely necessary[github.com](https://github.com/purescript/registry#:~:text=match%20at%20L364%20If%20your,short%20example%20of%20transferring%20a)).
    
*   **Name Already Taken**: If the registry rejects your package because the name is already in use, you’ll have to choose a new name. (This can happen if another library already claimed that name, possibly with a `purescript-` prefix in Bower days that now maps to the same name in the registry.) Consider incorporating your domain or a unique prefix in the name to avoid collision. Update `package.name` and try publishing again. You can search on Pursuit or the registry metadata to see existing package names.
    
*   **Compilation Fails on Registry**: It’s possible that your library built locally but fails in the registry’s build. The registry compiles your package as part of publishing to ensure it’s valid[github.com](https://github.com/purescript/registry#:~:text=The%20registry%20will%20fetch%20the,the%20day%27s%20package%20set%20batch). If it fails, the process won’t complete. The reasons could include:
    
    *   Using an outdated compiler version or features not available in the version you specified.
        
    *   Missing a dependency or a wrong version of a dependency. (The registry’s solver usually picks versions that satisfy your constraints; if it can’t, you might need to relax or adjust version bounds.)
        
    *   A module name conflict with another package in the package set (the registry checks for duplicate module names when adding to package sets[discourse.purescript.org](https://discourse.purescript.org/t/registry-vs-package-sets/3593#:~:text=There%20are%20many%20packages%20that,and%20that%20sort%20of%20thing)). If your module collides with another package’s module, the registry might include your package in the registry but omit it from the package set. The solution would be to rename the conflicting module in your library and publish a new version.
        
    
    If there is a failure, Spago (via the issue or output) will show you the error log (compiler error messages, etc.)[discourse.purescript.org](https://discourse.purescript.org/t/registry-vs-package-sets/3593#:~:text=,why%20a%20particular%20package%20failed)[discourse.purescript.org](https://discourse.purescript.org/t/registry-vs-package-sets/3593#:~:text=,it%20into%20the%20package%20sets). Use that to fix the problem in your code or config, then bump the version and publish again.
    
*   **Owners/SSH Issues**: If `spago auth` didn’t update the config or if you realize you published without adding the `owners` field, don’t worry. You can still add owners in a subsequent version. Just run `spago auth` now and then publish a patch version. If you have trouble with `spago auth`, you can manually add the owners section in `spago.yaml` as shown above (just be careful to format it correctly). Remember that the `email` in the owners must exactly match the one embedded in the public key[github.com](https://github.com/purescript/registry#:~:text=match%20at%20L357%20,ed25519%22%2C%20%22public) (check the output of `ssh-keygen -l -f yourkey.pub` to see the key’s email). If you use a passphrase on your SSH key, it doesn’t affect the publishing; the key is only used for verifying signatures when needed, not for logging in.
    
*   **No Domain Verification Needed**: To reiterate, you do not need to set up any DNS records or prove control of your domain for PureScript package publishing. The domain-based email is purely an identifier tied to your SSH key. Unlike some package ecosystems that use DNS (for example, Elm packages use a domain name in package coordinates), PureScript’s registry centralizes package names, so once you’ve registered the name, it’s yours. Your domain comes into play only through your email identity if you choose.
    
*   **Registry Issue Tracking**: If something goes wrong during publishing and you have to debug, check the GitHub issues on the `purescript/registry` repo. Spago might have opened an issue for your publish request (with a title like “Publish package X vY.Z.Z”). The CI comments on that issue often contain logs of what happened (success or failure)[discourse.purescript.org](https://discourse.purescript.org/t/registry-vs-package-sets/3593#:~:text=,why%20a%20particular%20package%20failed). This can be useful for troubleshooting if Spago’s CLI output was not enough. Once the publish succeeds, the issue is closed automatically by the registry.
    
*   **Subsequent Releases**: For future versions, the process is similar: update your code, bump the version in `spago.yaml`, commit, tag, and run `spago publish` again. One nice improvement is that after the first time, you usually won’t need to provide the `location` again (the registry remembers your repo)[github.com](https://github.com/purescript/registry#:~:text=). You also won’t need to modify owners unless adding/changing maintainers. So future publishes might be as simple as editing the version and changelog, tagging, and `spago publish`. Also note that once a package is registered, pushing a valid SemVer tag to GitHub will trigger the registry to auto-publish that version by the next daily run even if you don’t manually invoke `spago publish`[discourse.purescript.org](https://discourse.purescript.org/t/registry-alpha-launched/3146#:~:text=1,repo%20to%20add%20your%20package). However, using `spago publish` each time ensures immediate feedback and is the recommended workflow.
    
*   **Referencing Official Docs**: If in doubt, consult the official PureScript Registry README[github.com](https://github.com/purescript/registry#:~:text=The%20PureScript%20Registry%20stores%20PureScript,the%20registry%20via%20package%20managers) and Spago’s documentation. The Spago README has a section “Publish my library” which essentially says running `spago publish` is the way to go[github.com](https://github.com/purescript/spago#:~:text=Publish%20my%20library). The registry README details the JSON format and process (for manual publishing or just for understanding)[github.com](https://github.com/purescript/registry#:~:text=,coerce%22%2C%20%22ref%22%3A%20%22v12.0.0%22%2C%20%22compiler%22%3A%20%220.15.4)[github.com](https://github.com/purescript/registry#:~:text=The%20registry%20will%20fetch%20the,the%20day%27s%20package%20set%20batch). These can provide more insight if you run into edge cases.
    

By following these steps and tips, you should be able to publish your PureScript package for others to use. With your package on the registry, anyone can depend on it via Spago, and your documentation will be accessible on Pursuit. Happy coding and publishing!

**Sources:**

*   PureScript Registry README – _explains the registry’s purpose and how Spago integrates with it_[github.com](https://github.com/purescript/registry#:~:text=The%20PureScript%20Registry%20stores%20PureScript,the%20registry%20via%20package%20managers)[github.com](https://github.com/purescript/registry#:~:text=,your%20package%20in%20the%20registry).
    
*   Spago Documentation – _official guide for publishing PureScript libraries with Spago_[github.com](https://github.com/purescript/spago#:~:text=Publish%20my%20library)[github.com](https://github.com/purescript/spago#:~:text=,in%20the%20published%20archive%2C%20in).
    
*   PureScript Registry Spec (Registry owners) – _details on how package owners and keys are used for authenticated operations_[github.com](https://github.com/purescript/registry#:~:text=,ed25519%22%2C%20%22public).
    
*   PureScript Discourse – _announcement and discussions around the registry launch and package publishing_[discourse.purescript.org](https://discourse.purescript.org/t/registry-alpha-launched/3146#:~:text=1,repo%20to%20add%20your%20package).

## Prompt:
Publishing PureScript Packages with Spaghetti in 2025

Publishing PureScript Packages with the Spaghetti (Spago) Package Manager
=========================================================================

Publishing a PureScript library in 2025 is much simpler than it used to be. The community now uses the PureScript Registry (often called the “Spaghetti” package registry, managed via **Spago**) for publishing packages. This registry automates documentation uploads and package-set updates, so you no longer need to manually use Bower or Pursuit for new releases[github.com](https://github.com/purescript/registry#:~:text=,your%20package%20in%20the%20registry). In this tutorial, we’ll walk through every step to publish a publicly accessible PureScript package using Spago. We assume you already have a PureScript project (or are ready to create one), you own a domain name (with an email address on that domain for identity), and you want to make your library available to everyone. The guide will cover prerequisites, setting up package metadata, versioning, publishing to the registry, domain-based author verification, testing, and troubleshooting.

Prerequisites
-------------

Before you begin, make sure you have the following in place:

*   **PureScript Compiler** – Install the PureScript compiler (`purs`) version 0.15.x or later (e.g. via npm or your OS package manager). This is needed to build your package.
    
*   **Spago (Spaghetti Package Manager)** – Install Spago, which is PureScript’s build tool and package manager. The recommended way is via NPM: `npm install -g spago@next`[github.com](https://github.com/purescript/spago#:~:text=The%20recommended%20installation%20method%20for,latest%20releases%20on%20npm%20here). (The `@next` tag ensures you have the latest Spago with registry support.) Verify by running `spago --version`.
    
*   **Node.js and NPM** – Required for installing Spago (and possibly for running builds/tests if your library or tools require Node).
    
*   **Git** – Make sure Git is installed and your project is in a Git repository. You’ll use Git to tag releases and Spago/Registry will fetch your code from Git.
    
*   **GitHub Repository (or other Git hosting)** – For public packages, hosting your code on GitHub is easiest. The PureScript Registry by default uses a GitHub repo’s URL to fetch your package. (Other git servers are supported via custom URLs if needed[github.com](https://github.com/purescript/spago#:~:text=,name).) Ensure your repository is public.
    
*   **Domain Email Address** – Since you own a domain, prepare an email address on that domain (e.g. `you@your-domain.com`). You will use this as an identifier when setting up package ownership (this **does not** need to be verified via DNS, but using it helps tie the package to your domain).
    
*   **SSH Key (for author verification)** – It’s recommended to have an SSH key pair for signing your releases. If you don’t have one, generate a new key (for example, using `ssh-keygen -t ed25519 -C "you@your-domain.com"` to create an Ed25519 key with your domain email as a label). Keep the private key secure; we will use the public key to verify ownership of the package.
    

Step 1: Initialize Your PureScript Project (if not already)
-----------------------------------------------------------

If you already have a PureScript project you want to publish, you can skip initialization. Otherwise, to create a new project:

1.  **Create a project directory** – e.g. `mkdir purescript-myproject && cd purescript-myproject`.
    
2.  **Initialize with Spago** – Run `spago init`. This will set up a PureScript project with a `spago.dhall` or `spago.yaml` configuration (the new Spago uses a YAML config). It also creates a sample source file and a default package set.
    
3.  **Verify the setup** – Run `spago build` to compile the sample project. This ensures your compiler and Spago are working.
    

If your project was already set up with an older Spago (Dhall config), consider updating to the latest config format. Spago’s new version uses `spago.yaml` for configuration. You can run `spago upgrade-config` (if provided) or manually translate your `spago.dhall` to `spago.yaml`. Using the latest format is important because publishing to the registry requires certain fields in the config.

Step 2: Configure Package Metadata in `spago.yaml`
--------------------------------------------------

Next, you need to configure your package’s metadata in the Spago config. Spago’s config file declares your package name, dependencies, and crucial information for publishing. Open the `spago.yaml` file in your project (if it’s still `spago.dhall`, you can add similar fields there or upgrade).

**In the `spago.yaml`, add or update the following:**

*   **Package Name**: Under a top-level `package` section, set the `name` of your package. This is the name that will be used in the registry and by users to install your library. Choose a unique, descriptive name. (You no longer need the `purescript-` prefix in the name – the registry enforces uniqueness globally[github.com](https://github.com/purescript/registry-dev/issues/388#:~:text=What%20should%20we%20do%20about,json%20file%20or).) For example:
    
    ```yaml
    package:
      name: my-awesome-library
      dependencies:
        - prelude
        - effect
      description: "A library that does awesome things."
    ```
    
    Make sure to list all PureScript package dependencies under `dependencies`. Use the proper names as they appear in the package set or registry (e.g. `prelude`, `effect`, etc.). You can specify dependency versions or ranges if using the registry’s solver, but it’s common to just list names or use `*` for latest allowed[github.com](https://github.com/purescript/spago#:~:text=,package)[github.com](https://github.com/purescript/spago#:~:text=,range%3A%20%22%3E%3D1.1.1%20%3C2.0.0). (For instance, `some-package: "*"` would allow the latest version, or you can pin a range like `">=1.0.0 <2.0.0"`.)
    
*   **Publish Metadata**: Add a `publish` subsection inside `package` (this section is optional for local development but **mandatory** when you intend to publish[github.com](https://github.com/purescript/spago#:~:text=,Clause)):
    
    ```yaml
      publish:
        version: 0.1.0
        license: MIT
        repository: "https://github.com/your-user/your-repo.git"
        location:
          githubOwner: your-user
          githubRepo: your-repo
        # owners field will be added later by spago auth (see next step)
    ```
    
    Let’s break down these fields:
    
    *   **version** – The current version of your package, following semantic versioning (MAJOR.MINOR.PATCH). For an initial release, you might start with `0.1.0` (or `1.0.0` if it’s production-ready). Every time you publish a new version, this should be updated. _Note:_ Pre-release tags (like `-alpha`) are not supported by the registry; use plain SemVer numbers[github.com](https://github.com/purescript/spago#:~:text=,the%20Registry%20includes%20by%20default).
        
    *   **license** – The SPDX identifier for your project’s license (e.g. `MIT`, `BSD-3-Clause`, `Apache-2.0`, etc.). Ensure you have a `LICENSE` file in your repo corresponding to this. The registry requires a license field so users know the terms of use[github.com](https://github.com/purescript/spago#:~:text=,files).
        
    *   **repository** – (If using Spago Next, this might not be explicitly required if `location` is given, but it’s good practice to mention where the code lives.) This can be the Git URL of your repository. It’s mainly informational in the manifest, as the `location` field (next) is what the registry uses to fetch code.
        
    *   **location** – This tells the registry where to fetch your package’s source code. Since you’re using GitHub, provide the `githubOwner` (your GitHub username or org) and `githubRepo` (the repo name). Spago will use this to let the registry know how to clone your repo[github.com](https://github.com/purescript/spago#:~:text=,name). (If your PureScript package lives in a subdirectory of the repo, you can also specify `subdir`, but for most libraries it’s at the root.) For example, if your library is at `github.com/alice/purescript-foo`, use `githubOwner: alice` and `githubRepo: purescript-foo`. If you were hosting git elsewhere, you could use `url: git://...` instead.
        
    *   **(Optional) include/exclude** – You can specify file globs to include or exclude from the published tarball. By default, the registry will include your source files (`src/**/*.purs`), your README, LICENSE, and other essentials, and will exclude irrelevant files like your `output/` or Git metadata[github.com](https://github.com/purescript/spago#:~:text=,dev%2Fblob%2Fmaster%2FSPEC.md%23always)[github.com](https://github.com/purescript/spago#:~:text=excluded,to%20release%20the%20code%20without). If you want to include additional files (for example, example code or tests), you can list them under `publish.include`. If you want to omit something that would normally be included, list it under `publish.exclude`. In most cases, you don’t need to set these – the defaults are fine.
        
*   **Double-check dependencies and compiler compatibility**: Ensure your package’s dependencies are up-to-date and compatible with the latest PureScript compiler. The registry will attempt to compile your code with the compiler version you specify when publishing (if not specified, it uses the latest). For an initial publish, you can usually rely on the latest compiler (e.g. 0.15.**x**). If your library only works on an older compiler, you’ll need to indicate that during publishing (the `compiler` version is part of the publish process, which Spago will handle).
    

After editing `spago.yaml`, **save the file and commit the changes** to Git (e.g., `git add spago.yaml && git commit -m "Configure package metadata for publishing"`). This config now contains all the metadata the PureScript Registry needs to identify and catalog your package.

Step 3: Set Up Author Verification (Add Owners with your Domain Email)
----------------------------------------------------------------------

This step is about **proving ownership** of your package in the registry using your SSH key. While not strictly required for the first publish, adding yourself as an owner is highly recommended. It will allow you to perform future actions like transferring or unpublishing the package if necessary[github.com](https://github.com/purescript/registry#:~:text=The%20Registry%20API%20allows%20package,key%20is%20listed%20in%20the)[github.com](https://github.com/purescript/registry#:~:text=,ed25519%22%2C%20%22public). It also firmly attaches your identity (your email/domain) to the package record.

Here’s how to add the owners field:

1.  **Generate an SSH key** (if you haven’t already) with your domain email. For example:
    
    ```bash
    ssh-keygen -t ed25519 -C "you@your-domain.com"
    ```
    
    This creates a public/private key pair. The public key will contain a line like `ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIE... you@your-domain.com`. The email at the end is used as an identifier. (The registry doesn’t verify the email’s domain; it just checks that the email string matches the one in the key when you use the key[github.com](https://github.com/purescript/registry#:~:text=match%20at%20L357%20,ed25519%22%2C%20%22public). So it can be any string, but using your real email/domain is good documentation.)
    
2.  **Add your public key to Spago’s config** using the Spago `auth` command. Spago can update the config’s `owners` list for you. Run:
    
    ```bash
    spago auth --public-key path/to/your_id_ed25519.pub --private-key path/to/your_id_ed25519
    ```
    
    _(If you omit arguments, Spago may prompt for the key, or you can specify the key paths as shown.)_ This command will take your keys and add an entry in `package.publish.owners` in the `spago.yaml`. After running it, open `spago.yaml` to confirm under the `publish` section an `owners` field has appeared, for example:
    
    ```yaml
    publish:
      version: 0.1.0
      license: MIT
      repository: "https://github.com/your-user/your-repo.git"
      location:
        githubOwner: your-user
        githubRepo: your-repo
      owners:
        - email: "you@your-domain.com"
          keytype: "ssh-ed25519"
          public: "AAAAC3NzaC1lZDI1NTE5AAAAIEYourPublicKeyBytes123..."
    ```
    
    Spago populates `owners` with your public key info[github.com](https://github.com/purescript/registry#:~:text=,ed25519%22%2C%20%22public). The `email` here is taken from your key’s comment (so it should show your domain email), `keytype` is the type of key (e.g. `ssh-ed25519` or `ssh-rsa`), and `public` is the public key string. Note that the email in this field doesn’t have to be a working email address; it just needs to match the key’s identity string[github.com](https://github.com/purescript/registry#:~:text=,ed25519%22%2C%20%22public). In our case, it matches your domain email, which is perfect.
    
3.  **Commit the updated config**: `git add spago.yaml && git commit -m "Add owner public key for registry"`. The owners info will be published along with your package. With your key recorded as an owner, the registry will recognize your future signed requests (should you need to transfer or unpublish the package). Essentially, you’ve verified _you_ are the package author in a cryptographic way.
    

**No DNS TXT record or additional domain verification is required** beyond this. The presence of your domain email in the owners field is mostly for human identification. Ownership control is actually enforced by the SSH public key. So, you do not need to, for example, prove domain ownership via a DNS record – the SSH key is the proof of identity.

_(Optional)_: If you have multiple maintainers, you can add multiple owners (each with their own email and key) by running `spago auth` for each key, or by editing the YAML to include multiple entries under `owners`. Only listed owners (or registry trustees) can perform sensitive operations on the package later[github.com](https://github.com/purescript/registry#:~:text=The%20Registry%20API%20allows%20package,key%20is%20listed%20in%20the).

Step 4: Build and Test Your Package Locally
-------------------------------------------

Before releasing, it’s important to ensure that your library builds correctly and that all tests pass (if you have tests). This helps catch any issues early and gives confidence that the package will compile on the registry’s build servers.

*   **Clean and install deps**: It can help to start from a clean slate. If you previously built the project, you might remove any generated files: `rm -rf output/ .spago/`. Then ensure you have all dependencies: run `spago install` (for package-set mode) or `spago build` (which will also fetch dependencies if using the registry solver).
    
*   **Build the library**: Run `spago build`. This will compile your source. It should produce an `output/` directory with the compiled modules. If there are any compile errors or missing dependency issues, fix them now.
    
*   **Run tests** (if applicable): If you have a test suite, ensure it’s listed in your `spago.yaml` (often tests are separate or included via a `spago.test.dhall`). Run `spago test` to execute tests. All tests should pass.
    
*   **Preview documentation** (optional): You can generate docs locally to see how your documentation will look. Run `spago docs` which will produce documentation for your package. You can open the generated HTML in `generated-docs/` to review it. This isn’t required, but it’s a nice way to verify that module documentation and examples render as expected.
    

If both the build and tests succeed, you’re ready to publish. If you encounter any errors, resolve them before proceeding. Common issues might be:

*   Forgot to add a dependency in `spago.yaml`.
    
*   Warnings or deprecations (try to fix or at least note them).
    
*   Test failures or examples that need updating.
    

By the end of this step, you have a config ready for publishing and a verified working build of version 0.1.0 (as per our example).

Step 5: Bump the Version and Tag the Release
--------------------------------------------

When you’re satisfied with the state of your code, the next step is to finalize the version number and create a Git tag for the release. The PureScript Registry identifies releases by Git tags (e.g. `v0.1.0`). We already set `version: 0.1.0` in the config earlier; now we need to make sure the Git tag for this version exists and is pushed to the remote repository.

**Option A: Use Spago to bump version and tag automatically.** Spago provides a convenient command to bump the version and create a tag:

```bash
spago bump-version patch --no-dry-run
```

This command will:

*   Update the version in your `spago.yaml` (incrementing the patch part in this example; you could use `minor` or `major` for larger releases, or provide an explicit version number).
    
*   Commit the version change (if it hasn’t been committed).
    
*   Create a Git tag `v0.1.1` (or whatever the new version is) and by using `--no-dry-run`, actually apply it (without `--no-dry-run`, it would simulate the changes).
    
*   It may also generate a legacy `bower.json` for backward compatibility if needed, but with the registry, that’s less critical now[discourse.purescript.org](https://discourse.purescript.org/t/how-i-publish-a-purescript-package/2482#:~:text=2.%20%60spago%20bump).
    

After running this, check `git log` or `git tag` to ensure the new tag was created. If the tag was created locally, push it to GitHub:

```bash
git push origin v0.1.1
```

_(Replace `v0.1.1` with your tag name.)_ Pushing the tag is important because the registry will fetch the source code from the GitHub tag reference.

**Option B: Bump and tag manually.** If you prefer manual control or didn’t use `spago bump-version`:

*   Manually edit the `publish.version` in `spago.yaml` to the release number (ensure it matches the tag you plan to create).
    
*   Commit the change (`git commit -am "Bump version to 0.1.0"` if not already committed).
    
*   Create a git tag for the commit: `git tag -a v0.1.0 -m "Release v0.1.0"`.
    
*   Push the tag to the remote: `git push origin v0.1.0`.
    

Either way, at this point you should have a Git tag on your repository that corresponds to the version in your `spago.yaml`. For example, version `0.1.0` -> tag `v0.1.0`. The PureScript Registry will use this tag to fetch the code.

**Verify the tag on GitHub:** Go to your repository’s releases or tags page to confirm that `v0.1.0` (or your version) is present. If not, double-check the steps above.

Now you’re set to actually publish to the registry.

Step 6: Publish to the PureScript Registry
------------------------------------------

With everything prepared (metadata, version, tag, and owners), publishing the package is a one-command operation thanks to Spago’s registry integration.

Run the publish command in your project directory:

```bash
spago publish
```

Spago will use the information in `spago.yaml` to publish your library to the PureScript Registry[github.com](https://github.com/purescript/spago#:~:text=Publish%20my%20library). Here’s what happens during this step:

*   **Spago checks your config** – It will ensure that required fields are present (name, version, license, etc.) and that your working directory is clean. If something is missing (like no license specified) or you have uncommitted changes, it may warn or abort.
    
*   **Spago creates a registry request** – Under the hood, `spago publish` either interacts with the registry’s API directly or opens a GitHub issue on the registry repository with the package info. (As of now, Spago has official support to do this automatically[github.com](https://github.com/purescript/registry#:~:text=,your%20package%20in%20the%20registry), so you likely won’t need to open a browser manually.)
    
*   **The registry processes the publish request** – The PureScript Registry will receive your package metadata (package name, version, Git tag (ref), repository location, etc.) and begin validation. Specifically, it will fetch your repository at the given tag, verify that the package builds with the specified compiler, and register the package.
    
*   **Output and confirmation** – Spago will output status messages. If the process is fully automated, you might see a success message after a short wait. In some cases, Spago might give you a URL to a GitHub issue tracking the publish if manual confirmation is needed (for example, early versions of the registry used a GitHub Actions workflow to process publishes). If you see a link, open it to monitor progress. Otherwise, just wait for completion.
    

If all goes well, the package will be **registered** and the new version **published**. This means:

*   Your package **name** is now recorded in the PureScript Registry (locked to your GitHub repo location).
    
*   The version `v0.1.0` (or your version) is added with its metadata.
    
*   The registry will compile your package to ensure it’s compatible. If the compile fails, the publish will be rejected (you’d get an error log).
    
*   On success, the registry will automatically publish your package’s API docs to Pursuit (the online documentation site)[github.com](https://github.com/purescript/registry#:~:text=,your%20package%20in%20the%20registry). You don’t need to run `pulp publish` for docs – it’s handled for you.
    
*   The registry will attempt to add your package to the “package set” for the next release. This means if your package is compatible with the latest package set, it will be included so that Spago users (in package-sets mode) can install it easily[github.com](https://github.com/purescript/registry#:~:text=,your%20package%20in%20the%20registry). This is done automatically (usually within a day).
    
*   If this is a **new package** (first release), the registry now _registers_ the name. If it’s an update to an existing package, the registry links it to the existing entry.
    

Spago’s output or the linked issue will tell you if any step failed. Assuming success, congratulations – your package is now published! 🎉

_Important:_ The registry might use the PureScript compiler version you had in your config or the latest if not specified. If your code only works on a certain compiler (say 0.15.4), ensure you indicate that during publish. (Spago usually handles this by including the compiler version in the publish payload.)

Step 7: Verify the Published Package
------------------------------------

After publishing, it’s wise to verify that everything is in order:

*   **Check Pursuit Documentation**: Within a few minutes, your library’s documentation should appear on Pursuit (the PureScript package documentation site). Visit pursuit.purescript.org and search for your package name, or go directly to `https://pursuit.purescript.org/packages/your-package-name`. The docs should show the version you just released, along with your README and module documentation. (If you don’t see a README on Pursuit, ensure that a README.md exists in your repo at the tag. The registry will include it if present.)
    
*   **Try installing the package**: On a separate PureScript project (or a new test project), try to install your library as a dependency. For example, in an empty directory run:
    
    ```bash
    spago init
    spago install my-awesome-library
    ```
    
    Replace `my-awesome-library` with your package name. If the package was added to the latest package set, this should resolve and download your library. If the package set update hasn’t happened yet or if your package didn’t make it into the set immediately, you can still use the registry solver. Add to your `packages.dhall` (or `spago.yaml` workspace dependencies) an entry for your package with a version range, or use `spago install --resolver=registry`. In any case, by specifying the name and version, Spago should fetch it from the registry storage. Successful installation confirms the registry has your package. You can then `import Your.Module` in code to ensure it’s accessible.
    
*   **Review the registry metadata (optional)**: If curious, you can check the PureScript Registry GitHub repository’s `metadata/` folder for your package. It will have a JSON or Dhall manifest of your package version. This is not required, but it’s a way to confirm the registry entry. The registry’s index and storage are also publicly accessible (e.g., tarballs are stored at `packages.registry.purescript.org`).
    
*   **Package Sets**: The PureScript Registry publishes a new package set daily if any new packages or updates were added[discourse.purescript.org](https://discourse.purescript.org/t/registry-alpha-launched/3146#:~:text=1,repo%20to%20add%20your%20package)[discourse.purescript.org](https://discourse.purescript.org/t/registry-alpha-launched/3146#:~:text=The%20registry%20now%20publishes%20new,how%20to%20use%20the%20endpoint). Your package will be automatically included if possible. If your package had any compatibility issues (e.g., it depends on an older compiler or has a conflicting module name), the registry might skip adding it to the set and log an issue. But as long as you targeted the current compiler and have unique module names, you should be fine. The next day (or often sooner), your package will appear in the official package set used by Spago. You can verify this by checking the `packages.dhall` in the `purescript/package-sets` repo or simply by running an install as above without specifying versions.
    

Everything above confirms that your library is now publicly available for PureScript users. The heavy lifting (documentation publishing and package sets) is handled by the registry thanks to Spago’s integration[github.com](https://github.com/purescript/registry#:~:text=,your%20package%20in%20the%20registry).

Troubleshooting and Tips
------------------------

Even with the streamlined process, you might encounter some issues. Here are common problems and how to address them:

*   **Missing or Incorrect Metadata**: If `spago publish` fails immediately, read the error message. It could be due to missing required fields. For example, if you forgot to set a license or version in `spago.yaml`, Spago will complain. Fix the config and commit, then try again. _(Tip: The `publish` section in config is mandatory when publishing[github.com](https://github.com/purescript/spago#:~:text=,Clause).)_
    
*   **Uncommitted Changes**: Spago may refuse to publish if you have uncommitted changes in your working directory (to avoid publishing code that isn’t in Git). Make sure all your changes (especially the version bump and owners info) are committed before running `spago publish`. Similarly, ensure the Git tag for the version is pushed to the remote.
    
*   **Version Tag Mismatch**: The version in `spago.yaml` (and thus in the registry payload) must correspond to a Git tag in your repo. If you forget to create or push the tag, the registry won’t find your code. If `spago publish` reports something like “ref not found” or “could not fetch repository”, verify the tag on GitHub. You can fix this by pushing the tag and re-running the publish. In case you published with a wrong version by accident (say you had `0.1.0` in config but tag `v0.2.0`), you might need to unpublish or publish a corrected version (contact registry maintainers or use the `unpublish` API with your key if absolutely necessary[github.com](https://github.com/purescript/registry#:~:text=match%20at%20L364%20If%20your,short%20example%20of%20transferring%20a)).
    
*   **Name Already Taken**: If the registry rejects your package because the name is already in use, you’ll have to choose a new name. (This can happen if another library already claimed that name, possibly with a `purescript-` prefix in Bower days that now maps to the same name in the registry.) Consider incorporating your domain or a unique prefix in the name to avoid collision. Update `package.name` and try publishing again. You can search on Pursuit or the registry metadata to see existing package names.
    
*   **Compilation Fails on Registry**: It’s possible that your library built locally but fails in the registry’s build. The registry compiles your package as part of publishing to ensure it’s valid[github.com](https://github.com/purescript/registry#:~:text=The%20registry%20will%20fetch%20the,the%20day%27s%20package%20set%20batch). If it fails, the process won’t complete. The reasons could include:
    
    *   Using an outdated compiler version or features not available in the version you specified.
        
    *   Missing a dependency or a wrong version of a dependency. (The registry’s solver usually picks versions that satisfy your constraints; if it can’t, you might need to relax or adjust version bounds.)
        
    *   A module name conflict with another package in the package set (the registry checks for duplicate module names when adding to package sets[discourse.purescript.org](https://discourse.purescript.org/t/registry-vs-package-sets/3593#:~:text=There%20are%20many%20packages%20that,and%20that%20sort%20of%20thing)). If your module collides with another package’s module, the registry might include your package in the registry but omit it from the package set. The solution would be to rename the conflicting module in your library and publish a new version.
        
    
    If there is a failure, Spago (via the issue or output) will show you the error log (compiler error messages, etc.)[discourse.purescript.org](https://discourse.purescript.org/t/registry-vs-package-sets/3593#:~:text=,why%20a%20particular%20package%20failed)[discourse.purescript.org](https://discourse.purescript.org/t/registry-vs-package-sets/3593#:~:text=,it%20into%20the%20package%20sets). Use that to fix the problem in your code or config, then bump the version and publish again.
    
*   **Owners/SSH Issues**: If `spago auth` didn’t update the config or if you realize you published without adding the `owners` field, don’t worry. You can still add owners in a subsequent version. Just run `spago auth` now and then publish a patch version. If you have trouble with `spago auth`, you can manually add the owners section in `spago.yaml` as shown above (just be careful to format it correctly). Remember that the `email` in the owners must exactly match the one embedded in the public key[github.com](https://github.com/purescript/registry#:~:text=match%20at%20L357%20,ed25519%22%2C%20%22public) (check the output of `ssh-keygen -l -f yourkey.pub` to see the key’s email). If you use a passphrase on your SSH key, it doesn’t affect the publishing; the key is only used for verifying signatures when needed, not for logging in.
    
*   **No Domain Verification Needed**: To reiterate, you do not need to set up any DNS records or prove control of your domain for PureScript package publishing. The domain-based email is purely an identifier tied to your SSH key. Unlike some package ecosystems that use DNS (for example, Elm packages use a domain name in package coordinates), PureScript’s registry centralizes package names, so once you’ve registered the name, it’s yours. Your domain comes into play only through your email identity if you choose.
    
*   **Registry Issue Tracking**: If something goes wrong during publishing and you have to debug, check the GitHub issues on the `purescript/registry` repo. Spago might have opened an issue for your publish request (with a title like “Publish package X vY.Z.Z”). The CI comments on that issue often contain logs of what happened (success or failure)[discourse.purescript.org](https://discourse.purescript.org/t/registry-vs-package-sets/3593#:~:text=,why%20a%20particular%20package%20failed). This can be useful for troubleshooting if Spago’s CLI output was not enough. Once the publish succeeds, the issue is closed automatically by the registry.
    
*   **Subsequent Releases**: For future versions, the process is similar: update your code, bump the version in `spago.yaml`, commit, tag, and run `spago publish` again. One nice improvement is that after the first time, you usually won’t need to provide the `location` again (the registry remembers your repo)[github.com](https://github.com/purescript/registry#:~:text=). You also won’t need to modify owners unless adding/changing maintainers. So future publishes might be as simple as editing the version and changelog, tagging, and `spago publish`. Also note that once a package is registered, pushing a valid SemVer tag to GitHub will trigger the registry to auto-publish that version by the next daily run even if you don’t manually invoke `spago publish`[discourse.purescript.org](https://discourse.purescript.org/t/registry-alpha-launched/3146#:~:text=1,repo%20to%20add%20your%20package). However, using `spago publish` each time ensures immediate feedback and is the recommended workflow.
    
*   **Referencing Official Docs**: If in doubt, consult the official PureScript Registry README[github.com](https://github.com/purescript/registry#:~:text=The%20PureScript%20Registry%20stores%20PureScript,the%20registry%20via%20package%20managers) and Spago’s documentation. The Spago README has a section “Publish my library” which essentially says running `spago publish` is the way to go[github.com](https://github.com/purescript/spago#:~:text=Publish%20my%20library). The registry README details the JSON format and process (for manual publishing or just for understanding)[github.com](https://github.com/purescript/registry#:~:text=,coerce%22%2C%20%22ref%22%3A%20%22v12.0.0%22%2C%20%22compiler%22%3A%20%220.15.4)[github.com](https://github.com/purescript/registry#:~:text=The%20registry%20will%20fetch%20the,the%20day%27s%20package%20set%20batch). These can provide more insight if you run into edge cases.
    

By following these steps and tips, you should be able to publish your PureScript package for others to use. With your package on the registry, anyone can depend on it via Spago, and your documentation will be accessible on Pursuit. Happy coding and publishing!

**Sources:**

*   PureScript Registry README – _explains the registry’s purpose and how Spago integrates with it_[github.com](https://github.com/purescript/registry#:~:text=The%20PureScript%20Registry%20stores%20PureScript,the%20registry%20via%20package%20managers)[github.com](https://github.com/purescript/registry#:~:text=,your%20package%20in%20the%20registry).
    
*   Spago Documentation – _official guide for publishing PureScript libraries with Spago_[github.com](https://github.com/purescript/spago#:~:text=Publish%20my%20library)[github.com](https://github.com/purescript/spago#:~:text=,in%20the%20published%20archive%2C%20in).
    
*   PureScript Registry Spec (Registry owners) – _details on how package owners and keys are used for authenticated operations_[github.com](https://github.com/purescript/registry#:~:text=,ed25519%22%2C%20%22public).
    
*   PureScript Discourse – _announcement and discussions around the registry launch and package publishing_[discourse.purescript.org](https://discourse.purescript.org/t/registry-alpha-launched/3146#:~:text=1,repo%20to%20add%20your%20package).
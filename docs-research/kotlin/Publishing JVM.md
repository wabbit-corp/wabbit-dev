Publishing a library to **Maven Central** involves preparing your project with the correct metadata, signing your artifacts, and using Sonatype’s infrastructure (now the **Central Sonatype Portal**) to stage and release your components. This step-by-step guide will cover the **prerequisites** (account setup, domain and GPG key), the **Gradle configuration** (using Kotlin DSL in Gradle 8+), and the **publishing workflow** for both Kotlin and Scala projects. We will focus on manual/scriptable steps (suitable for running locally or via custom scripts) rather than CI-specific setups. All instructions reflect the latest process as of May 2025, when Sonatype has introduced a new Central Portal for publishing.

Prerequisites
-------------

Before you begin, ensure you have the following in place:

*   **Sonatype Central Account:** Create an account on the Sonatype Central Portal (if you haven’t already) by visiting **https://central.sonatype.com** and signing up (you can use email/password or a GitHub/Google login)[github.com](https://github.com/teamlead/java-maven-sonatype-starter#:~:text=This%20guide%20provides%20a%20comprehensive,refer%20to%20the%20Sonatype%20documentation)[central.sonatype.org](https://central.sonatype.org/register/central-portal/#:~:text=Create%20an%20Account%E2%9A%93%EF%B8%8E). Verify your email address as prompted.
    
*   **Verified Group/Namespace:** You must own a domain (e.g. `example.com`) or use an allowed open namespace (like GitHub) to serve as your Maven groupId. In the Sonatype portal, register a _Namespace_ corresponding to your domain (for example, if you own `example.com`, your groupId can be `com.example`). The portal will require you to **verify domain ownership** by adding a DNS TXT record with a verification token provided by Sonatype[central.sonatype.org](https://central.sonatype.org/register/namespace/#:~:text=Before%20Sonatype%20can%20grant%20you,web%20domain%20reflected%20by%20your). (Navigate to the “Namespaces” section of the portal, add your namespace, and follow the instructions to copy the token and create a TXT record in your DNS. The status will update to “Verified” once Sonatype detects the record[central.sonatype.org](https://central.sonatype.org/register/namespace/#:~:text=You%20can%20then%20use%20this,DNS%20registrars%20and%20hosting%20providers).) If you do not have a personal domain, Sonatype supports using certain code-hosting domains (e.g. `io.github.<YourUsername>` for GitHub, after creating a dummy repo to prove ownership)[github.com](https://github.com/teamlead/java-maven-sonatype-starter#:~:text=Step%202%3A%20Namespace%20Configuration%20and,Domain%20Validation)[medium.com](https://medium.com/@lionzxy/how-to-publish-a-library-to-the-maven-central-portal-in-2024-a64ad67751c9#:~:text=ones%20from%20the%20list%3A). **You need at least one verified namespace** in your account before you can publish.
    
*   **Java Development Kit (JDK):** Install JDK 8 or higher (Gradle 8 requires Java 11+). Ensure you can run `java` and `gradle` (or use the Gradle Wrapper in your project).
    
*   **GPG Key Pair:** Maven Central **requires all artifacts to be PGP-signed**[maven.apache.org](https://maven.apache.org/repository/guide-central-repository-upload.html#:~:text=Guide%20to%20uploading%20artifacts%20to,%C2%B7%20minimum%20POM%20information%3A). Generate a GPG key if you don’t have one:
    
    *   Install GPG (`gpg --version` to check). On Linux: `sudo apt-get install gnupg`; on macOS: `brew install gnupg`; Windows: install via Gpg4win.
        
    *   Generate a new key: `gpg --full-generate-key`. Choose RSA 4096, no expiry (recommended), and provide your name, email (use the same domain-associated email you have for Sonatype), and a secure passphrase.
        
    *   Find your key ID: run `gpg --list-keys` and note the 8 or 16-character hex key ID of your new key (e.g. `ABC1234F`).
        
    *   **Publish your public key** to a keyserver so that Maven Central users can obtain it to verify signatures. For example, send it to Ubuntu’s server: `gpg --keyserver keyserver.ubuntu.com --send-keys <YourKeyID>`[central.sonatype.org](https://central.sonatype.org/publish/requirements/gpg/#:~:text=Since%20other%20people%20need%20your,key%20to%20a%20key%20server)[central.sonatype.org](https://central.sonatype.org/publish/requirements/gpg/#:~:text=,edu). (Sonatype’s servers support `keyserver.ubuntu.com`, `keys.openpgp.org`, and `pgp.mit.edu` as of 2025[central.sonatype.org](https://central.sonatype.org/publish/requirements/gpg/#:~:text=Important).) You can verify it’s published by searching the key or using `--recv-keys` from the same server.
        
*   **Project Setup:** Have a Gradle project ready. If you have a **multi-module project**, decide on a consistent groupId (usually the verified domain namespace) for all modules, and a version number for the release. In a multi-module setup, it’s common to define the group and version in the root project so all submodules inherit it. For example, in your root `build.gradle.kts` you can set:
    
    ```kotlin
    allprojects {
        group = "com.example"       // your groupId (domain reversed)
        version = "1.0.0"           // your library version
    }
    ```
    
    Ensure your Gradle build is using **Kotlin DSL** (filename `build.gradle.kts` in each module). We will illustrate configurations for both a Kotlin library module and a Scala library module.
    

Gradle Configuration for Publishing
-----------------------------------

Gradle offers the _Maven Publish_ plugin to prepare and upload artifacts, and the _Signing_ plugin to sign them. We will configure these along with tasks for generating sources and documentation (KDoc/Scaladoc) jars and adding the required POM metadata (project info, license, etc.). All of this will be done in your Gradle build scripts. Below is a breakdown of the setup:

### 1\. Apply Plugins and Configure Plugins

In each module that you want to publish (or in the root build script if you configure all submodules together), apply the necessary plugins:

*   `maven-publish` – for publishing artifacts to Maven repositories.
    
*   `signing` – for GPG signing of the artifacts.
    
*   Language plugins:
    
    *   For Kotlin: `org.jetbrains.kotlin.jvm` (and optionally Dokka for KDoc).
        
    *   For Scala: `scala` (the Scala plugin will also apply the Java plugin since it extends it).
        

For example, in a **Kotlin library module’s** `build.gradle.kts`:

```kotlin
plugins {
    kotlin("jvm") version "1.9.0"
    `java-library`                      // include if not automatically applied by Kotlin plugin
    `maven-publish`
    `signing`
    id("org.jetbrains.dokka") version "1.8.20"  // Dokka for generating KDoc as Javadoc
}
```

And in a **Scala library module’s** `build.gradle.kts`:

```kotlin
plugins {
    scala
    `java-library`        // Scala plugin brings this in, but we ensure Java plugin is on
    `maven-publish`
    `signing`
}
```

We include `java-library` in both cases to ensure the Java component is present (Gradle’s publishing uses the Java component to gather outputs). The Dokka plugin (for Kotlin) will be used to generate documentation that we can package as a Javadoc jar.

### 2\. Group, Version, and Artifact Coordinates

Make sure the project’s **group** and **version** are set to your desired Maven coordinates:

*   `group` = your reversed domain (the namespace you verified, e.g. `"com.example.mylib"`).
    
*   `version` = the version number for this release (e.g. `"1.0.0"`). Use semantic versioning. **Do not use “-SNAPSHOT”** for a release (snapshots are handled separately).
    

If you set these in the root project (as shown earlier with `allprojects { ... }`), you don’t need to repeat in submodules. Otherwise, set them in each submodule’s build file:

```kotlin
group = "com.example.mylibrary"
version = "0.1.0"
```

Also choose an **artifactId** for each module. By default, Gradle uses the project name as artifactId. For example, if your subproject is named “core”, the artifactId will be “core”. You can override it by setting `project.name` in the subproject or in `settings.gradle.kts` when including the project.

### 3\. Generate Sources and Documentation JARs

Maven Central **requires** that for every main library JAR, you also upload a **\-sources.jar** (containing source code) and a **\-javadoc.jar** (containing API documentation)[central.sonatype.org](https://central.sonatype.org/publish/requirements/#:~:text=Projects%20with%20packaging%20other%20than,as%20for%20display%20and%20navigation). Gradle can create these for you:

**Sources JAR:** If you apply the Java plugin (which is applied via `java-library`), you can simply enable the sources Jar generation:

```kotlin
java {
    withSourcesJar()
}
```

This adds a task to build a sources JAR and automatically adds it to publications[docs.gradle.org](https://docs.gradle.org/current/samples/sample_building_scala_libraries.html#:~:text=java%20).

**Javadoc JAR:** Similarly, enable the Javadoc jar. For Java/Scala, Gradle will use the Javadoc or Scaladoc tool; for Kotlin, we’ll integrate Dokka:

```kotlin
java {
    withJavadocJar()
}
```

By default this creates a `javadocJar` task. However:

*   For **Kotlin**: The default Javadoc task will have no content (Kotlin code isn’t processed by the JDK javadoc). We will use Dokka to generate documentation from KDoc comments. Dokka’s Gradle plugin creates a `dokkaHtml` task (and also a `dokkaJavadoc` task if configured). We can use its output for our javadoc jar. For example:
    
    ```kotlin
    tasks.dokkaHtml.configure {
        outputDirectory.set(buildDir.resolve("dokka"))  // generate docs into build/dokka
    }
    tasks.named<Jar>("javadocJar").configure {
        dependsOn(tasks.dokkaHtml)
        from(buildDir.resolve("dokka"))                 // package the Dokka HTML as the javadoc jar
    }
    ```
    
    This ensures the `-javadoc.jar` will contain the KDoc HTML files generated by Dokka.
    
*   For **Scala**: The Scala plugin provides a `scaladoc` task that generates Scala API docs (similar to javadoc). Gradle’s `withJavadocJar()` will create a `javadocJar` task, but we need to attach the ScalaDoc output to it:
    
    ```kotlin
    tasks.named<Jar>("javadocJar").configure {
        dependsOn(tasks.named("scaladoc"))
        from(buildDir.resolve("docs/scaladoc"))  // ScalaDoc outputs to build/docs/scaladoc by default
    }
    ```
    
    This way, the ScalaDoc HTML files will be included in the Javadoc jar.
    

If for some reason you cannot generate real docs, Central allows placeholder jars (e.g., containing a README) just to fulfill the requirement[central.sonatype.org](https://central.sonatype.org/publish/requirements/#:~:text=your%20library), but it’s best to include actual documentation.

### 4\. Maven Publication Configuration (POM Metadata)

Next, configure the **publishing** settings to create a Maven publication from your library and add the required metadata. In Gradle Kotlin DSL:

```kotlin
publishing {
    publications {
        create<MavenPublication>("mavenCentral") {
            from(components["java"])  // publish the Java component (works for Kotlin/JVM and Scala)
            
            // Only needed if you need to attach additional artifacts manually:
            // artifact(tasks["sourcesJar"])
            // artifact(tasks["javadocJar"])
            
            pom {
                name.set("My Library")                                       // Project name
                description.set("A useful library that ...")                 // Short description
                url.set("https://github.com/yourname/yourproject")           // Project homepage
                
                licenses {
                    license {
                        name.set("The Apache License, Version 2.0")          // License name
                        url.set("https://www.apache.org/licenses/LICENSE-2.0.txt")
                    } 
                    // You can list multiple licenses if applicable
                }
                developers {
                    developer {
                        id.set("your-id")                   // e.g., GitHub username or any identifier
                        name.set("Your Name")
                        email.set("you@yourdomain.com")
                        organization.set("Your Organization")
                        organizationUrl.set("https://yourdomain.com")
                    }
                }
                scm {
                    connection.set("scm:git:git://github.com/yourname/yourproject.git")
                    developerConnection.set("scm:git:ssh://git@github.com/yourname/yourproject.git")
                    url.set("https://github.com/yourname/yourproject/tree/main")
                }
            }
        }
    }
    // Repositories for publishing will be configured later (in the Publishing to Sonatype section)
}
```

Let’s break down the important POM fields we set above:

*   **Name, Description, URL:** Maven Central requires that your POM contains a project name, a concise description, and a website URL[central.sonatype.org](https://central.sonatype.org/publish/requirements/#:~:text=Project%20Name%2C%20Description%20and%20URL%E2%9A%93%EF%B8%8E). The URL can be your source repo or project page.
    
*   **License:** You must declare at least one license under which the project is released[central.sonatype.org](https://central.sonatype.org/publish/requirements/#:~:text=License%20Information%E2%9A%93%EF%B8%8E). Use the official name and URL of the license text. (Common choices: Apache-2.0, MIT, etc.)
    
*   **Developers:** List at least one developer or maintainer with name and email[central.sonatype.org](https://central.sonatype.org/publish/requirements/#:~:text=Developer%20information%20is%20also%20required%3A). This personal info is expected in the POM so users know who’s behind the project.
    
*   **SCM (Source Control Management):** Provide the SCM connection info and a browsable URL[central.sonatype.org](https://central.sonatype.org/publish/requirements/#:~:text=SCM%20Information%E2%9A%93%EF%B8%8E). For GitHub, the format shown above is typical. This helps others locate the source code corresponding to the artifact.
    

Including all the above metadata is part of Central’s quality requirements[central.sonatype.org](https://central.sonatype.org/publish/requirements/#:~:text=Supply%20Javadoc%20and%20Sources%E2%9A%93%EF%B8%8E)[central.sonatype.org](https://central.sonatype.org/publish/requirements/#:~:text=Developer%20information%20is%20also%20required%3A). Gradle’s DSL makes it straightforward to set these fields. Ensure there are **no placeholders** like “TODO” left in these fields – Sonatype may reject releases if required POM info is missing or obviously incorrect.

If you have a **multi-module project**, you will typically create a publication for each module’s component (each subproject will have its own `publishing.publications` block as above). Make sure each module’s POM metadata is appropriate (they can often share the same license and developer info, and likely the same SCM if all in one repo). The groupId will be the same for all; the artifactId will differ per module.

### 5\. GPG Signing Configuration

Now configure Gradle’s Signing plugin to sign the artifacts. Maven Central requires that all uploaded artifact files (POM, JARs, etc.) have accompanying `.asc` signature files[maven.apache.org](https://maven.apache.org/repository/guide-central-repository-upload.html#:~:text=Guide%20to%20uploading%20artifacts%20to,%C2%B7%20minimum%20POM%20information%3A). The Signing plugin will generate these `.asc` files using your GPG key.

First, import or supply your GPG private key to Gradle:

*   **Option 1: Use an in-memory key** – suitable for automation (no need for a physical keyring file). You can export your private key in ASCII-armored format and supply it via Gradle properties or environment variables at build time. For example, export your key: `gpg --armor --export-secret-keys <KeyID> > privateKey.asc`. **Keep this file safe!** In your Gradle setup, you might not want to hardcode the key; instead, pass it in via a property. You can place the ASCII key and the passphrase in environment variables or `~/.gradle/gradle.properties` (which is not checked into VCS). For instance:
    
    ```properties
    # ~/.gradle/gradle.properties (do NOT commit this)
    signingKey=<the ASCII-armored private key text, all in one line>
    signingPassword=<your GPG key passphrase>
    ```
    
    Then in the Gradle `build.gradle.kts`:
    
    ```kotlin
    signing {
        useInMemoryPgpKeys(
            findProperty("signingKey") as String?, 
            findProperty("signingPassword") as String?
        )
        sign(publishing.publications["mavenCentral"])
    }
    ```
    
    This will load the key and password from the properties and use them in-memory[docs.gradle.org](https://docs.gradle.org/current/kotlin-dsl/gradle/org.gradle.plugins.signing/-signing-extension/use-in-memory-pgp-keys.html#:~:text=signing%20,useInMemoryPgpKeys%28secretKey%2C%20password%29). (If your key has subkeys, you may also specify the keyId in `useInMemoryPgpKeys` as a first parameter in the Gradle 6.0+ variant[docs.gradle.org](https://docs.gradle.org/current/kotlin-dsl/gradle/org.gradle.plugins.signing/-signing-extension/use-in-memory-pgp-keys.html#:~:text=open%20fun%20useInMemoryPgpKeys,source).)
    
*   **Option 2: Use GPG agent or keyring file** – If Gradle can access your GPG keyring, it can sign using it. For example, you can specify the old-style secret keyring file and key ID in `gradle.properties`:
    
    ```properties
    signing.keyId=ABC1234F
    signing.password=<yourPassphrase>
    signing.secretKeyRingFile=/path/to/secring.gpg
    ```
    
    And then just do `sign(publishing.publications)` in the signing block. However, modern GnuPG uses `~/.gnupg/private-keys-v1.d` instead of a single secring file, so this method may require you to create a legacy `secring.gpg` (as shown by exporting the key). The in-memory approach is often easier and more secure for CI.
    

In either case, **do not expose your private key or passphrase in your source repository**. Use environment variables or a Gradle properties file that's kept out of version control. When configured properly, running the `sign` task or any publish task will produce `.asc` signature files for each artifact. (Gradle will also automatically attach checksums – MD5 and SHA1 – or the Sonatype server will compute them, so you don’t need to handle checksums manually in most cases[central.sonatype.org](https://central.sonatype.org/publish/requirements/#:~:text=All%20files%20deployed%20need%20to,encoded%20checksum%20value).)

Finally, apply the signing to the publication:

```kotlin
signing {
    // key setup as above
    sign(publishing.publications["mavenCentral"])
}
```

This ensures that all artifacts in the publication (the main jar, sources jar, javadoc jar, and the POM) are signed with your key.

### 6\. Summary of Build Script

At this point, your Gradle module’s build script should have the following key parts configured:

*   Plugins (`kotlin("jvm")` or `scala`, plus `maven-publish` and `signing`, and Dokka for Kotlin).
    
*   Group and version (probably inherited from root).
    
*   `java { withSourcesJar(); withJavadocJar() }` and customizations for Dokka/Scaladoc tasks as needed.
    
*   `publishing { publications { ... pom { ... } } }` with all metadata.
    
*   `signing { ... }` to sign the publication.
    

Below is a **simplified example** for a **Kotlin library** module’s `build.gradle.kts` bringing it all together (Scala would be analogous, with the Scala plugin and ScalaDoc config instead of Dokka):

```kotlin
plugins {
    kotlin("jvm") version "1.9.0"
    `java-library`
    `maven-publish`
    `signing`
    id("org.jetbrains.dokka") version "1.8.20"
}

group = "com.example.mylib"
version = "1.0.0"

java {
    withSourcesJar()
    withJavadocJar()
}

// Dokka: generate documentation for Kotlin
tasks.dokkaHtml.configure {
    outputDirectory.set(buildDir.resolve("dokka"))
}
tasks.named<Jar>("javadocJar").configure {
    dependsOn(tasks.dokkaHtml)
    from(buildDir.resolve("dokka"))
}

publishing {
    publications {
        create<MavenPublication>("mavenCentral") {
            from(components["java"])
            pom {
                name.set("MyLib Kotlin")
                description.set("A Kotlin library that ...")
                url.set("https://github.com/yourname/mylib")
                licenses {
                    license {
                        name.set("MIT License")
                        url.set("https://opensource.org/licenses/MIT")
                    }
                }
                developers {
                    developer {
                        id.set("yourname")
                        name.set("Your Name")
                        email.set("you@yourdomain.com")
                    }
                }
                scm {
                    connection.set("scm:git:git://github.com/yourname/mylib.git")
                    developerConnection.set("scm:git:ssh://git@github.com/yourname/mylib.git")
                    url.set("https://github.com/yourname/mylib")
                }
            }
        }
    }
    repositories {
        // (Will configure Sonatype repository here in the next section)
    }
}

signing {
    useInMemoryPgpKeys(findProperty("signingKey") as String?, findProperty("signingPassword") as String?)
    sign(publishing.publications["mavenCentral"])
}
```

This script prepares everything for publishing but doesn’t yet specify _where_ to publish. Now we will configure the Sonatype (Maven Central) repository details and perform the publication.

Publishing to Sonatype OSSRH / Maven Central
--------------------------------------------

With your build configured, the publishing process consists of deploying your artifacts to Sonatype’s staging repository and then releasing them to Central. Sonatype has transitioned from the old OSSRH system to a new **Central Publisher Portal**, but the mechanism with Gradle is to use an endpoint that mimics the OSSRH staging for compatibility[central.sonatype.org](https://central.sonatype.org/publish/publish-portal-gradle/#:~:text=Currently%2C%20there%20is%20no%20official,support%20is%20on%20our%20roadmap)[central.sonatype.org](https://central.sonatype.org/publish/publish-portal-gradle/#:~:text=JReleaser%E2%9A%93%EF%B8%8E).

### 7\. Get Your Sonatype Publishing Credentials (User Token)

You will need credentials to upload to Sonatype. In the new system, this is a **User Token** (separate from your login password). Even if you have an older OSSRH account, the new portal uses token-based auth for deployment.

**Generate a user token** from the Sonatype Central Portal:

1.  Log in to central.sonatype.com and go to your account profile page (click your username -> **Account**).
    
2.  Click the **“Generate User Token”** button[central.sonatype.org](https://central.sonatype.org/publish/generate-portal-token/#:~:text=1,once%20it%20has%20been%20generated). Confirm the action – note that if you had an existing token, this regenerates a new one (invalidating the old).
    
3.  A modal will show you the **Token Username** and **Token Password** – copy both and store them securely[central.sonatype.org](https://central.sonatype.org/publish/generate-portal-token/#:~:text=3,your%20publishing%20setup%20%2090)[central.sonatype.org](https://central.sonatype.org/publish/generate-portal-token/#:~:text=4,once%20it%20has%20been%20generated). **You won’t be able to see this token again once the dialog closes**[central.sonatype.org](https://central.sonatype.org/publish/generate-portal-token/#:~:text=Token%20access), so make sure to save it (e.g., in a password manager or a secure note).
    

These token credentials will be used as `username` and `password` for the Maven repository. (They are essentially an API key – do not share them publicly.)

### 8\. Configure the Maven Central (Sonatype) Repository in Gradle

Add a repository entry under the `publishing.repositories` block in your Gradle build. Sonatype provides different repository URLs for **staging releases** and **snapshots**:

*   **Staging (Releases) Repository:** This is where release artifacts are deployed for review and release. With the new Central portal, a special endpoint is available that forwards to the portal. Use:
    
    ```kotlin
    publishing {
        repositories {
            maven {
                name = "SonatypeStaging"
                url = uri("https://ossrh-staging-api.central.sonatype.com/service/local/staging/deploy/maven2/")
                credentials {
                    username = findProperty("ossrhUsername") as String?  // your token username
                    password = findProperty("ossrhPassword") as String?  // your token password
                }
            }
        }
    }
    ```
    
    Here we assume you’ll provide `ossrhUsername` and `ossrhPassword` via Gradle properties or environment (similar to how we did for signing). For example, you can put them in `~/.gradle/gradle.properties`:
    
    ```properties
    ossrhUsername=YOUR_TOKEN_USERNAME
    ossrhPassword=YOUR_TOKEN_PASSWORD
    ```
    
    This endpoint (`ossrh-staging-api.central.sonatype.com`) is the **bridge to the new Central Portal**. It works like the old OSSRH Nexus API so that Gradle can upload files as if to Nexus[central.sonatype.org](https://central.sonatype.org/publish/publish-portal-ossrh-staging-api/#:~:text=Replace%20your%20existing%20OSSRH%20endpoint,project%20might%20be%20configured%20as)[central.sonatype.org](https://central.sonatype.org/publish/publish-portal-ossrh-staging-api/#:~:text=%2F%2F%20...%20repositories%20,api.central.sonatype.com%2Fservice%2Flocal%2Fstaging%2Fdeploy%2Fmaven2%2F%22).
    
*   **Snapshot Repository (optional):** If you want to publish snapshot versions (with version ending in `-SNAPSHOT`), you use Sonatype’s snapshot repository. Snapshots are not staged or released; they go live immediately on a special repository. The new Central portal’s snapshot repository URL is `https://central.sonatype.com/repository/maven-snapshots/` (or you can use `https://s01.oss.sonatype.org/content/repositories/snapshots` which is the older endpoint). For example:
    
    ```kotlin
    maven {
        name = "SonatypeSnapshots"
        url = uri("https://central.sonatype.com/repository/maven-snapshots/")
        credentials {
            username = findProperty("ossrhUsername") as String?
            password = findProperty("ossrhPassword") as String?
        }
    }
    ```
    
    Gradle (via the publishing plugin) will automatically choose this repo when you run a publish if your version is a snapshot (ends with "-SNAPSHOT"). You might include both repositories in the configuration, and Gradle will pick the appropriate one for each publication. (Alternatively, you can separate profile by checking `if (version.endsWith("SNAPSHOT"))` in the script.)
    

Make sure your credentials are **never checked into source control**. Using `findProperty` or environment variables (e.g., `ORG_GRADLE_PROJECT_ossrhUsername`) is a safe way to inject them at build time.

### 9\. Deploy (Publish) to Sonatype Staging

Everything is now set to publish. To perform the deployment, run Gradle with the `publish` task. It’s recommended to use the Gradle **Wrapper** (`./gradlew`) for consistency. For example, execute:

```bash
./gradlew publish
```

This will build the project, generate sources and javadoc jars, sign all artifacts, and upload them to the Sonatype repository configured. If you have multiple modules/publications, it will publish all of them. You should see in the console output the upload progress for each artifact (POM, jar, sources, javadoc, `.asc` files).

If the build finishes without errors, the artifacts are now in a **staging repository** on Sonatype’s OSSRH system (connected to the Central Portal). Each upload opens a staging repository under your namespace.

**Tip:** If you want to test the process without actually hitting Sonatype (to ensure all artifacts are assembled correctly), you can run `./gradlew publishToMavenLocal` first. This will put the artifacts and POM into your local Maven cache (`~/.m2/repository`) so you can inspect them.

### 10\. Release the Staging Repository to Maven Central

Uploading via Gradle places the files in a _closed_ (or open) staging repository on Sonatype. The final step is to **release** that staging repository, which moves the artifacts to Maven Central’s public repository.

With the new Central Portal:

*   Go to the **Sonatype Central Portal** website and log in. Navigate to the **“Publishing”** or **“Deployments”** section (the interface where you can see your recent deployments). You should see a listing for your newly uploaded version (it may be identified by your groupId and version as a “deployment” or a staging repository).
    
*   Review it if needed (ensure all artifacts and signatures are present). Then hit the **Release** button for that staging repository. Confirm the release. This action will synchronize the artifacts to Maven Central (the global repository).
    

_(Previously with OSSRH, one would “close” and then “release” via Nexus UI or a plugin. In the new portal, the process is streamlined – the upload plus a manual release click. The term “close” may not appear in the UI, but essentially the portal ensures the bundle is complete and then releases it.)_

If for some reason you find an issue and need to drop the staging repo, you can drop it in the portal instead of releasing, then fix your build and re-run `publish` to upload again.

**Note:** It’s also possible to trigger a release via REST API calls if you want to fully automate this without web UI. Sonatype’s portal provides a URL for releasing a deployment bundle via API[central.sonatype.org](https://central.sonatype.org/publish/publish-portal-ossrh-staging-api/#:~:text=Deploying%E2%9A%93%EF%B8%8E), but using the web interface is straightforward for manual publishing.

Once released, the artifacts will be available on Maven Central shortly. Maven Central sync is typically quick (a few minutes), but allow some time for indexing. You can verify by searching your artifact on search.maven.org or by adding it as a dependency in a test project (it may take ~10 minutes to appear).

Congratulations – your Kotlin/Scala library is now published on Maven Central! 🎉

11\. Additional Tips and References
-----------------------------------

*   **Coordinate Immutability:** Remember that once a version is released to Central, it **cannot be changed or deleted**[central.sonatype.org](https://central.sonatype.org/register/central-portal/#:~:text=As%20such%20you%20are%20bound,our%20full%20terms%20of%20service). If you discover an issue, you must release a new version. Double-check everything (especially groupId, artifactId, version) before releasing.
    
*   **Snapshots:** If you deployed a `-SNAPSHOT` version to the snapshots repository, it’s immediately available to users (from Sonatype’s snapshots repository). Snapshots don’t get released and synced to Central (Central only hosts release versions), so consumers need to use the Sonatype snapshot repo in their build tools to fetch it. Use snapshots for development or testing releases, but do an official versioned release for production use.
    
*   **Multi-module release:** When releasing multiple modules as part of one library (e.g., `mylib-core`, `mylib-utils` under the same group and version), it’s best to release them together. If you ran `publish` in the root, all submodules’ artifacts should be in the same staging repository. Releasing that staging repo publishes all of them atomically. This is preferable so that all modules of a given version appear on Maven Central at the same time.
    
*   **Troubleshooting:** If the `publish` task fails with errors:
    
    *   **401 Unauthorized**: Check that your Sonatype credentials (user token) are correct and not expired. Ensure you used the token’s username/password (not your account login)[central.sonatype.org](https://central.sonatype.org/publish/publish-portal-ossrh-staging-api/#:~:text=The%20OSSRH%20Staging%20API%20is,with%20Central%20Portal%20User%20Tokens).
        
    *   **403 Forbidden**: This could indicate you tried to deploy to a groupId that you don’t have permission for. Make sure the groupId exactly matches the namespace you verified (including subpackages). For example, if your namespace is `com.example`, you cannot publish `com.other` or even `com.example.something` unless `com.example.something` was implicitly covered or you verified that subdomain. Usually verifying `com.example` covers all sub-packages.
        
    *   **Javadoc/Sources not found**: If Sonatype reports missing javadoc or sources, ensure you applied `withJavadocJar()`/`withSourcesJar()` and that those artifacts are being published. According to Sonatype rules, non-pom artifacts must have sources and javadoc jars[central.sonatype.org](https://central.sonatype.org/publish/requirements/#:~:text=Projects%20with%20packaging%20other%20than,as%20for%20display%20and%20navigation), otherwise validation fails.
        
    *   **Signature errors**: If it complains about missing signatures, ensure the Signing plugin actually ran. You might need to ensure `sign(publishing.publications)` is configured _before_ publishing tasks execute. In Kotlin DSL, the configuration as shown should be fine. Also verify your `signingKey` and `signingPassword` are being found. You can add `-PsigningKey="...(key)..."` in the command to test quickly.
        
    *   For more, see Sonatype’s guide and FAQ for common errors[central.sonatype.org](https://central.sonatype.org/publish/publish-portal-ossrh-staging-api/#:~:text=,Manual)[central.sonatype.org](https://central.sonatype.org/publish/publish-portal-ossrh-staging-api/#:~:text=,SBT) or consult the community if something isn’t working.
        
*   **References:** Official Sonatype documentation for the new Central publishing process is available on their site. In particular, the requirements checklist is useful[central.sonatype.org](https://central.sonatype.org/publish/requirements/#:~:text=Supply%20Javadoc%20and%20Sources%E2%9A%93%EF%B8%8E), as well as the step-by-step guides on namespace setup and token generation (we cited those throughout). Gradle’s documentation on the Maven Publish and Signing plugins can provide more insight on customization.
    

By following this guide, you have set up a Gradle-based workflow to publish your Kotlin and Scala libraries to Maven Central. This process can be automated (for example, using a Python script or CI job to run the `gradlew publish` command and perhaps trigger a release via API), but even manually it should be straightforward after the initial configuration. Good luck with your library release on Maven Central!

**Sources:**

*   Sonatype OSSRH/Central documentation (2024–2025) for requirements and process[central.sonatype.org](https://central.sonatype.org/publish/requirements/#:~:text=Projects%20with%20packaging%20other%20than,as%20for%20display%20and%20navigation)[central.sonatype.org](https://central.sonatype.org/publish/requirements/#:~:text=Developer%20information%20is%20also%20required%3A)[central.sonatype.org](https://central.sonatype.org/publish/generate-portal-token/#:~:text=1,once%20it%20has%20been%20generated)[central.sonatype.org](https://central.sonatype.org/publish/publish-portal-ossrh-staging-api/#:~:text=%2F%2F%20...%20repositories%20,api.central.sonatype.com%2Fservice%2Flocal%2Fstaging%2Fdeploy%2Fmaven2%2F%22)
    
*   Gradle Documentation for publishing and signing plugins[docs.gradle.org](https://docs.gradle.org/current/samples/sample_building_scala_libraries.html#:~:text=java%20)[docs.gradle.org](https://docs.gradle.org/current/kotlin-dsl/gradle/org.gradle.plugins.signing/-signing-extension/use-in-memory-pgp-keys.html#:~:text=signing%20,useInMemoryPgpKeys%28secretKey%2C%20password%29)
    
*   PJ Fanning, _Publishing Your First Open Source Library with Gradle_, on including sources/javadoc and metadata[selectfrom.dev](https://selectfrom.dev/publishing-your-first-open-source-library-with-gradle-50bd0b1cd3af#:~:text=Sonatype%20requires%20that%20you%20include,in%20the%20excerpt%20above)[selectfrom.dev](https://selectfrom.dev/publishing-your-first-open-source-library-with-gradle-50bd0b1cd3af#:~:text=The%20publishing%20section%20specifies%20what,license%2C%20developers%2C%20and%20SCM%20links)
    
*   Nikita Kulikov (Medium, 2024), _Publishing to Maven Central Portal_ (insights on new portal usage)[medium.com](https://medium.com/@lionzxy/how-to-publish-a-library-to-the-maven-central-portal-in-2024-a64ad67751c9#:~:text=To%20verify%20domain%20ownership%20you,how%20to%20do%20this%20here)[medium.com](https://medium.com/@lionzxy/how-to-publish-a-library-to-the-maven-central-portal-in-2024-a64ad67751c9#:~:text=As%20of%2012%20March%202024%2C,publishing%20projects%20of%20new%20authors)

## Prompt:
Publishing Kotlin and Scala Packages to Maven Central with Gradle (2025)

Publishing Kotlin and Scala Libraries to Maven Central (Gradle 8+ Tutorial, 2025)
=================================================================================

Publishing a library to **Maven Central** involves preparing your project with the correct metadata, signing your artifacts, and using Sonatype’s infrastructure (now the **Central Sonatype Portal**) to stage and release your components. This step-by-step guide will cover the **prerequisites** (account setup, domain and GPG key), the **Gradle configuration** (using Kotlin DSL in Gradle 8+), and the **publishing workflow** for both Kotlin and Scala projects. We will focus on manual/scriptable steps (suitable for running locally or via custom scripts) rather than CI-specific setups. All instructions reflect the latest process as of May 2025, when Sonatype has introduced a new Central Portal for publishing.

Prerequisites
-------------

Before you begin, ensure you have the following in place:

*   **Sonatype Central Account:** Create an account on the Sonatype Central Portal (if you haven’t already) by visiting **https://central.sonatype.com** and signing up (you can use email/password or a GitHub/Google login)[github.com](https://github.com/teamlead/java-maven-sonatype-starter#:~:text=This%20guide%20provides%20a%20comprehensive,refer%20to%20the%20Sonatype%20documentation)[central.sonatype.org](https://central.sonatype.org/register/central-portal/#:~:text=Create%20an%20Account%E2%9A%93%EF%B8%8E). Verify your email address as prompted.
    
*   **Verified Group/Namespace:** You must own a domain (e.g. `example.com`) or use an allowed open namespace (like GitHub) to serve as your Maven groupId. In the Sonatype portal, register a _Namespace_ corresponding to your domain (for example, if you own `example.com`, your groupId can be `com.example`). The portal will require you to **verify domain ownership** by adding a DNS TXT record with a verification token provided by Sonatype[central.sonatype.org](https://central.sonatype.org/register/namespace/#:~:text=Before%20Sonatype%20can%20grant%20you,web%20domain%20reflected%20by%20your). (Navigate to the “Namespaces” section of the portal, add your namespace, and follow the instructions to copy the token and create a TXT record in your DNS. The status will update to “Verified” once Sonatype detects the record[central.sonatype.org](https://central.sonatype.org/register/namespace/#:~:text=You%20can%20then%20use%20this,DNS%20registrars%20and%20hosting%20providers).) If you do not have a personal domain, Sonatype supports using certain code-hosting domains (e.g. `io.github.<YourUsername>` for GitHub, after creating a dummy repo to prove ownership)[github.com](https://github.com/teamlead/java-maven-sonatype-starter#:~:text=Step%202%3A%20Namespace%20Configuration%20and,Domain%20Validation)[medium.com](https://medium.com/@lionzxy/how-to-publish-a-library-to-the-maven-central-portal-in-2024-a64ad67751c9#:~:text=ones%20from%20the%20list%3A). **You need at least one verified namespace** in your account before you can publish.
    
*   **Java Development Kit (JDK):** Install JDK 8 or higher (Gradle 8 requires Java 11+). Ensure you can run `java` and `gradle` (or use the Gradle Wrapper in your project).
    
*   **GPG Key Pair:** Maven Central **requires all artifacts to be PGP-signed**[maven.apache.org](https://maven.apache.org/repository/guide-central-repository-upload.html#:~:text=Guide%20to%20uploading%20artifacts%20to,%C2%B7%20minimum%20POM%20information%3A). Generate a GPG key if you don’t have one:
    
    *   Install GPG (`gpg --version` to check). On Linux: `sudo apt-get install gnupg`; on macOS: `brew install gnupg`; Windows: install via Gpg4win.
        
    *   Generate a new key: `gpg --full-generate-key`. Choose RSA 4096, no expiry (recommended), and provide your name, email (use the same domain-associated email you have for Sonatype), and a secure passphrase.
        
    *   Find your key ID: run `gpg --list-keys` and note the 8 or 16-character hex key ID of your new key (e.g. `ABC1234F`).
        
    *   **Publish your public key** to a keyserver so that Maven Central users can obtain it to verify signatures. For example, send it to Ubuntu’s server: `gpg --keyserver keyserver.ubuntu.com --send-keys <YourKeyID>`[central.sonatype.org](https://central.sonatype.org/publish/requirements/gpg/#:~:text=Since%20other%20people%20need%20your,key%20to%20a%20key%20server)[central.sonatype.org](https://central.sonatype.org/publish/requirements/gpg/#:~:text=,edu). (Sonatype’s servers support `keyserver.ubuntu.com`, `keys.openpgp.org`, and `pgp.mit.edu` as of 2025[central.sonatype.org](https://central.sonatype.org/publish/requirements/gpg/#:~:text=Important).) You can verify it’s published by searching the key or using `--recv-keys` from the same server.
        
*   **Project Setup:** Have a Gradle project ready. If you have a **multi-module project**, decide on a consistent groupId (usually the verified domain namespace) for all modules, and a version number for the release. In a multi-module setup, it’s common to define the group and version in the root project so all submodules inherit it. For example, in your root `build.gradle.kts` you can set:
    
    ```kotlin
    allprojects {
        group = "com.example"       // your groupId (domain reversed)
        version = "1.0.0"           // your library version
    }
    ```
    
    Ensure your Gradle build is using **Kotlin DSL** (filename `build.gradle.kts` in each module). We will illustrate configurations for both a Kotlin library module and a Scala library module.
    

Gradle Configuration for Publishing
-----------------------------------

Gradle offers the _Maven Publish_ plugin to prepare and upload artifacts, and the _Signing_ plugin to sign them. We will configure these along with tasks for generating sources and documentation (KDoc/Scaladoc) jars and adding the required POM metadata (project info, license, etc.). All of this will be done in your Gradle build scripts. Below is a breakdown of the setup:

### 1\. Apply Plugins and Configure Plugins

In each module that you want to publish (or in the root build script if you configure all submodules together), apply the necessary plugins:

*   `maven-publish` – for publishing artifacts to Maven repositories.
    
*   `signing` – for GPG signing of the artifacts.
    
*   Language plugins:
    
    *   For Kotlin: `org.jetbrains.kotlin.jvm` (and optionally Dokka for KDoc).
        
    *   For Scala: `scala` (the Scala plugin will also apply the Java plugin since it extends it).
        

For example, in a **Kotlin library module’s** `build.gradle.kts`:

```kotlin
plugins {
    kotlin("jvm") version "1.9.0"
    `java-library`                      // include if not automatically applied by Kotlin plugin
    `maven-publish`
    `signing`
    id("org.jetbrains.dokka") version "1.8.20"  // Dokka for generating KDoc as Javadoc
}
```

And in a **Scala library module’s** `build.gradle.kts`:

```kotlin
plugins {
    scala
    `java-library`        // Scala plugin brings this in, but we ensure Java plugin is on
    `maven-publish`
    `signing`
}
```

We include `java-library` in both cases to ensure the Java component is present (Gradle’s publishing uses the Java component to gather outputs). The Dokka plugin (for Kotlin) will be used to generate documentation that we can package as a Javadoc jar.

### 2\. Group, Version, and Artifact Coordinates

Make sure the project’s **group** and **version** are set to your desired Maven coordinates:

*   `group` = your reversed domain (the namespace you verified, e.g. `"com.example.mylib"`).
    
*   `version` = the version number for this release (e.g. `"1.0.0"`). Use semantic versioning. **Do not use “-SNAPSHOT”** for a release (snapshots are handled separately).
    

If you set these in the root project (as shown earlier with `allprojects { ... }`), you don’t need to repeat in submodules. Otherwise, set them in each submodule’s build file:

```kotlin
group = "com.example.mylibrary"
version = "0.1.0"
```

Also choose an **artifactId** for each module. By default, Gradle uses the project name as artifactId. For example, if your subproject is named “core”, the artifactId will be “core”. You can override it by setting `project.name` in the subproject or in `settings.gradle.kts` when including the project.

### 3\. Generate Sources and Documentation JARs

Maven Central **requires** that for every main library JAR, you also upload a **\-sources.jar** (containing source code) and a **\-javadoc.jar** (containing API documentation)[central.sonatype.org](https://central.sonatype.org/publish/requirements/#:~:text=Projects%20with%20packaging%20other%20than,as%20for%20display%20and%20navigation). Gradle can create these for you:

**Sources JAR:** If you apply the Java plugin (which is applied via `java-library`), you can simply enable the sources Jar generation:

```kotlin
java {
    withSourcesJar()
}
```

This adds a task to build a sources JAR and automatically adds it to publications[docs.gradle.org](https://docs.gradle.org/current/samples/sample_building_scala_libraries.html#:~:text=java%20).

**Javadoc JAR:** Similarly, enable the Javadoc jar. For Java/Scala, Gradle will use the Javadoc or Scaladoc tool; for Kotlin, we’ll integrate Dokka:

```kotlin
java {
    withJavadocJar()
}
```

By default this creates a `javadocJar` task. However:

*   For **Kotlin**: The default Javadoc task will have no content (Kotlin code isn’t processed by the JDK javadoc). We will use Dokka to generate documentation from KDoc comments. Dokka’s Gradle plugin creates a `dokkaHtml` task (and also a `dokkaJavadoc` task if configured). We can use its output for our javadoc jar. For example:
    
    ```kotlin
    tasks.dokkaHtml.configure {
        outputDirectory.set(buildDir.resolve("dokka"))  // generate docs into build/dokka
    }
    tasks.named<Jar>("javadocJar").configure {
        dependsOn(tasks.dokkaHtml)
        from(buildDir.resolve("dokka"))                 // package the Dokka HTML as the javadoc jar
    }
    ```
    
    This ensures the `-javadoc.jar` will contain the KDoc HTML files generated by Dokka.
    
*   For **Scala**: The Scala plugin provides a `scaladoc` task that generates Scala API docs (similar to javadoc). Gradle’s `withJavadocJar()` will create a `javadocJar` task, but we need to attach the ScalaDoc output to it:
    
    ```kotlin
    tasks.named<Jar>("javadocJar").configure {
        dependsOn(tasks.named("scaladoc"))
        from(buildDir.resolve("docs/scaladoc"))  // ScalaDoc outputs to build/docs/scaladoc by default
    }
    ```
    
    This way, the ScalaDoc HTML files will be included in the Javadoc jar.
    

If for some reason you cannot generate real docs, Central allows placeholder jars (e.g., containing a README) just to fulfill the requirement[central.sonatype.org](https://central.sonatype.org/publish/requirements/#:~:text=your%20library), but it’s best to include actual documentation.

### 4\. Maven Publication Configuration (POM Metadata)

Next, configure the **publishing** settings to create a Maven publication from your library and add the required metadata. In Gradle Kotlin DSL:

```kotlin
publishing {
    publications {
        create<MavenPublication>("mavenCentral") {
            from(components["java"])  // publish the Java component (works for Kotlin/JVM and Scala)
            
            // Only needed if you need to attach additional artifacts manually:
            // artifact(tasks["sourcesJar"])
            // artifact(tasks["javadocJar"])
            
            pom {
                name.set("My Library")                                       // Project name
                description.set("A useful library that ...")                 // Short description
                url.set("https://github.com/yourname/yourproject")           // Project homepage
                
                licenses {
                    license {
                        name.set("The Apache License, Version 2.0")          // License name
                        url.set("https://www.apache.org/licenses/LICENSE-2.0.txt")
                    } 
                    // You can list multiple licenses if applicable
                }
                developers {
                    developer {
                        id.set("your-id")                   // e.g., GitHub username or any identifier
                        name.set("Your Name")
                        email.set("you@yourdomain.com")
                        organization.set("Your Organization")
                        organizationUrl.set("https://yourdomain.com")
                    }
                }
                scm {
                    connection.set("scm:git:git://github.com/yourname/yourproject.git")
                    developerConnection.set("scm:git:ssh://git@github.com/yourname/yourproject.git")
                    url.set("https://github.com/yourname/yourproject/tree/main")
                }
            }
        }
    }
    // Repositories for publishing will be configured later (in the Publishing to Sonatype section)
}
```

Let’s break down the important POM fields we set above:

*   **Name, Description, URL:** Maven Central requires that your POM contains a project name, a concise description, and a website URL[central.sonatype.org](https://central.sonatype.org/publish/requirements/#:~:text=Project%20Name%2C%20Description%20and%20URL%E2%9A%93%EF%B8%8E). The URL can be your source repo or project page.
    
*   **License:** You must declare at least one license under which the project is released[central.sonatype.org](https://central.sonatype.org/publish/requirements/#:~:text=License%20Information%E2%9A%93%EF%B8%8E). Use the official name and URL of the license text. (Common choices: Apache-2.0, MIT, etc.)
    
*   **Developers:** List at least one developer or maintainer with name and email[central.sonatype.org](https://central.sonatype.org/publish/requirements/#:~:text=Developer%20information%20is%20also%20required%3A). This personal info is expected in the POM so users know who’s behind the project.
    
*   **SCM (Source Control Management):** Provide the SCM connection info and a browsable URL[central.sonatype.org](https://central.sonatype.org/publish/requirements/#:~:text=SCM%20Information%E2%9A%93%EF%B8%8E). For GitHub, the format shown above is typical. This helps others locate the source code corresponding to the artifact.
    

Including all the above metadata is part of Central’s quality requirements[central.sonatype.org](https://central.sonatype.org/publish/requirements/#:~:text=Supply%20Javadoc%20and%20Sources%E2%9A%93%EF%B8%8E)[central.sonatype.org](https://central.sonatype.org/publish/requirements/#:~:text=Developer%20information%20is%20also%20required%3A). Gradle’s DSL makes it straightforward to set these fields. Ensure there are **no placeholders** like “TODO” left in these fields – Sonatype may reject releases if required POM info is missing or obviously incorrect.

If you have a **multi-module project**, you will typically create a publication for each module’s component (each subproject will have its own `publishing.publications` block as above). Make sure each module’s POM metadata is appropriate (they can often share the same license and developer info, and likely the same SCM if all in one repo). The groupId will be the same for all; the artifactId will differ per module.

### 5\. GPG Signing Configuration

Now configure Gradle’s Signing plugin to sign the artifacts. Maven Central requires that all uploaded artifact files (POM, JARs, etc.) have accompanying `.asc` signature files[maven.apache.org](https://maven.apache.org/repository/guide-central-repository-upload.html#:~:text=Guide%20to%20uploading%20artifacts%20to,%C2%B7%20minimum%20POM%20information%3A). The Signing plugin will generate these `.asc` files using your GPG key.

First, import or supply your GPG private key to Gradle:

*   **Option 1: Use an in-memory key** – suitable for automation (no need for a physical keyring file). You can export your private key in ASCII-armored format and supply it via Gradle properties or environment variables at build time. For example, export your key: `gpg --armor --export-secret-keys <KeyID> > privateKey.asc`. **Keep this file safe!** In your Gradle setup, you might not want to hardcode the key; instead, pass it in via a property. You can place the ASCII key and the passphrase in environment variables or `~/.gradle/gradle.properties` (which is not checked into VCS). For instance:
    
    ```properties
    # ~/.gradle/gradle.properties (do NOT commit this)
    signingKey=<the ASCII-armored private key text, all in one line>
    signingPassword=<your GPG key passphrase>
    ```
    
    Then in the Gradle `build.gradle.kts`:
    
    ```kotlin
    signing {
        useInMemoryPgpKeys(
            findProperty("signingKey") as String?, 
            findProperty("signingPassword") as String?
        )
        sign(publishing.publications["mavenCentral"])
    }
    ```
    
    This will load the key and password from the properties and use them in-memory[docs.gradle.org](https://docs.gradle.org/current/kotlin-dsl/gradle/org.gradle.plugins.signing/-signing-extension/use-in-memory-pgp-keys.html#:~:text=signing%20,useInMemoryPgpKeys%28secretKey%2C%20password%29). (If your key has subkeys, you may also specify the keyId in `useInMemoryPgpKeys` as a first parameter in the Gradle 6.0+ variant[docs.gradle.org](https://docs.gradle.org/current/kotlin-dsl/gradle/org.gradle.plugins.signing/-signing-extension/use-in-memory-pgp-keys.html#:~:text=open%20fun%20useInMemoryPgpKeys,source).)
    
*   **Option 2: Use GPG agent or keyring file** – If Gradle can access your GPG keyring, it can sign using it. For example, you can specify the old-style secret keyring file and key ID in `gradle.properties`:
    
    ```properties
    signing.keyId=ABC1234F
    signing.password=<yourPassphrase>
    signing.secretKeyRingFile=/path/to/secring.gpg
    ```
    
    And then just do `sign(publishing.publications)` in the signing block. However, modern GnuPG uses `~/.gnupg/private-keys-v1.d` instead of a single secring file, so this method may require you to create a legacy `secring.gpg` (as shown by exporting the key). The in-memory approach is often easier and more secure for CI.
    

In either case, **do not expose your private key or passphrase in your source repository**. Use environment variables or a Gradle properties file that's kept out of version control. When configured properly, running the `sign` task or any publish task will produce `.asc` signature files for each artifact. (Gradle will also automatically attach checksums – MD5 and SHA1 – or the Sonatype server will compute them, so you don’t need to handle checksums manually in most cases[central.sonatype.org](https://central.sonatype.org/publish/requirements/#:~:text=All%20files%20deployed%20need%20to,encoded%20checksum%20value).)

Finally, apply the signing to the publication:

```kotlin
signing {
    // key setup as above
    sign(publishing.publications["mavenCentral"])
}
```

This ensures that all artifacts in the publication (the main jar, sources jar, javadoc jar, and the POM) are signed with your key.

### 6\. Summary of Build Script

At this point, your Gradle module’s build script should have the following key parts configured:

*   Plugins (`kotlin("jvm")` or `scala`, plus `maven-publish` and `signing`, and Dokka for Kotlin).
    
*   Group and version (probably inherited from root).
    
*   `java { withSourcesJar(); withJavadocJar() }` and customizations for Dokka/Scaladoc tasks as needed.
    
*   `publishing { publications { ... pom { ... } } }` with all metadata.
    
*   `signing { ... }` to sign the publication.
    

Below is a **simplified example** for a **Kotlin library** module’s `build.gradle.kts` bringing it all together (Scala would be analogous, with the Scala plugin and ScalaDoc config instead of Dokka):

```kotlin
plugins {
    kotlin("jvm") version "1.9.0"
    `java-library`
    `maven-publish`
    `signing`
    id("org.jetbrains.dokka") version "1.8.20"
}

group = "com.example.mylib"
version = "1.0.0"

java {
    withSourcesJar()
    withJavadocJar()
}

// Dokka: generate documentation for Kotlin
tasks.dokkaHtml.configure {
    outputDirectory.set(buildDir.resolve("dokka"))
}
tasks.named<Jar>("javadocJar").configure {
    dependsOn(tasks.dokkaHtml)
    from(buildDir.resolve("dokka"))
}

publishing {
    publications {
        create<MavenPublication>("mavenCentral") {
            from(components["java"])
            pom {
                name.set("MyLib Kotlin")
                description.set("A Kotlin library that ...")
                url.set("https://github.com/yourname/mylib")
                licenses {
                    license {
                        name.set("MIT License")
                        url.set("https://opensource.org/licenses/MIT")
                    }
                }
                developers {
                    developer {
                        id.set("yourname")
                        name.set("Your Name")
                        email.set("you@yourdomain.com")
                    }
                }
                scm {
                    connection.set("scm:git:git://github.com/yourname/mylib.git")
                    developerConnection.set("scm:git:ssh://git@github.com/yourname/mylib.git")
                    url.set("https://github.com/yourname/mylib")
                }
            }
        }
    }
    repositories {
        // (Will configure Sonatype repository here in the next section)
    }
}

signing {
    useInMemoryPgpKeys(findProperty("signingKey") as String?, findProperty("signingPassword") as String?)
    sign(publishing.publications["mavenCentral"])
}
```

This script prepares everything for publishing but doesn’t yet specify _where_ to publish. Now we will configure the Sonatype (Maven Central) repository details and perform the publication.

Publishing to Sonatype OSSRH / Maven Central
--------------------------------------------

With your build configured, the publishing process consists of deploying your artifacts to Sonatype’s staging repository and then releasing them to Central. Sonatype has transitioned from the old OSSRH system to a new **Central Publisher Portal**, but the mechanism with Gradle is to use an endpoint that mimics the OSSRH staging for compatibility[central.sonatype.org](https://central.sonatype.org/publish/publish-portal-gradle/#:~:text=Currently%2C%20there%20is%20no%20official,support%20is%20on%20our%20roadmap)[central.sonatype.org](https://central.sonatype.org/publish/publish-portal-gradle/#:~:text=JReleaser%E2%9A%93%EF%B8%8E).

### 7\. Get Your Sonatype Publishing Credentials (User Token)

You will need credentials to upload to Sonatype. In the new system, this is a **User Token** (separate from your login password). Even if you have an older OSSRH account, the new portal uses token-based auth for deployment.

**Generate a user token** from the Sonatype Central Portal:

1.  Log in to central.sonatype.com and go to your account profile page (click your username -> **Account**).
    
2.  Click the **“Generate User Token”** button[central.sonatype.org](https://central.sonatype.org/publish/generate-portal-token/#:~:text=1,once%20it%20has%20been%20generated). Confirm the action – note that if you had an existing token, this regenerates a new one (invalidating the old).
    
3.  A modal will show you the **Token Username** and **Token Password** – copy both and store them securely[central.sonatype.org](https://central.sonatype.org/publish/generate-portal-token/#:~:text=3,your%20publishing%20setup%20%2090)[central.sonatype.org](https://central.sonatype.org/publish/generate-portal-token/#:~:text=4,once%20it%20has%20been%20generated). **You won’t be able to see this token again once the dialog closes**[central.sonatype.org](https://central.sonatype.org/publish/generate-portal-token/#:~:text=Token%20access), so make sure to save it (e.g., in a password manager or a secure note).
    

These token credentials will be used as `username` and `password` for the Maven repository. (They are essentially an API key – do not share them publicly.)

### 8\. Configure the Maven Central (Sonatype) Repository in Gradle

Add a repository entry under the `publishing.repositories` block in your Gradle build. Sonatype provides different repository URLs for **staging releases** and **snapshots**:

*   **Staging (Releases) Repository:** This is where release artifacts are deployed for review and release. With the new Central portal, a special endpoint is available that forwards to the portal. Use:
    
    ```kotlin
    publishing {
        repositories {
            maven {
                name = "SonatypeStaging"
                url = uri("https://ossrh-staging-api.central.sonatype.com/service/local/staging/deploy/maven2/")
                credentials {
                    username = findProperty("ossrhUsername") as String?  // your token username
                    password = findProperty("ossrhPassword") as String?  // your token password
                }
            }
        }
    }
    ```
    
    Here we assume you’ll provide `ossrhUsername` and `ossrhPassword` via Gradle properties or environment (similar to how we did for signing). For example, you can put them in `~/.gradle/gradle.properties`:
    
    ```properties
    ossrhUsername=YOUR_TOKEN_USERNAME
    ossrhPassword=YOUR_TOKEN_PASSWORD
    ```
    
    This endpoint (`ossrh-staging-api.central.sonatype.com`) is the **bridge to the new Central Portal**. It works like the old OSSRH Nexus API so that Gradle can upload files as if to Nexus[central.sonatype.org](https://central.sonatype.org/publish/publish-portal-ossrh-staging-api/#:~:text=Replace%20your%20existing%20OSSRH%20endpoint,project%20might%20be%20configured%20as)[central.sonatype.org](https://central.sonatype.org/publish/publish-portal-ossrh-staging-api/#:~:text=%2F%2F%20...%20repositories%20,api.central.sonatype.com%2Fservice%2Flocal%2Fstaging%2Fdeploy%2Fmaven2%2F%22).
    
*   **Snapshot Repository (optional):** If you want to publish snapshot versions (with version ending in `-SNAPSHOT`), you use Sonatype’s snapshot repository. Snapshots are not staged or released; they go live immediately on a special repository. The new Central portal’s snapshot repository URL is `https://central.sonatype.com/repository/maven-snapshots/` (or you can use `https://s01.oss.sonatype.org/content/repositories/snapshots` which is the older endpoint). For example:
    
    ```kotlin
    maven {
        name = "SonatypeSnapshots"
        url = uri("https://central.sonatype.com/repository/maven-snapshots/")
        credentials {
            username = findProperty("ossrhUsername") as String?
            password = findProperty("ossrhPassword") as String?
        }
    }
    ```
    
    Gradle (via the publishing plugin) will automatically choose this repo when you run a publish if your version is a snapshot (ends with "-SNAPSHOT"). You might include both repositories in the configuration, and Gradle will pick the appropriate one for each publication. (Alternatively, you can separate profile by checking `if (version.endsWith("SNAPSHOT"))` in the script.)
    

Make sure your credentials are **never checked into source control**. Using `findProperty` or environment variables (e.g., `ORG_GRADLE_PROJECT_ossrhUsername`) is a safe way to inject them at build time.

### 9\. Deploy (Publish) to Sonatype Staging

Everything is now set to publish. To perform the deployment, run Gradle with the `publish` task. It’s recommended to use the Gradle **Wrapper** (`./gradlew`) for consistency. For example, execute:

```bash
./gradlew publish
```

This will build the project, generate sources and javadoc jars, sign all artifacts, and upload them to the Sonatype repository configured. If you have multiple modules/publications, it will publish all of them. You should see in the console output the upload progress for each artifact (POM, jar, sources, javadoc, `.asc` files).

If the build finishes without errors, the artifacts are now in a **staging repository** on Sonatype’s OSSRH system (connected to the Central Portal). Each upload opens a staging repository under your namespace.

**Tip:** If you want to test the process without actually hitting Sonatype (to ensure all artifacts are assembled correctly), you can run `./gradlew publishToMavenLocal` first. This will put the artifacts and POM into your local Maven cache (`~/.m2/repository`) so you can inspect them.

### 10\. Release the Staging Repository to Maven Central

Uploading via Gradle places the files in a _closed_ (or open) staging repository on Sonatype. The final step is to **release** that staging repository, which moves the artifacts to Maven Central’s public repository.

With the new Central Portal:

*   Go to the **Sonatype Central Portal** website and log in. Navigate to the **“Publishing”** or **“Deployments”** section (the interface where you can see your recent deployments). You should see a listing for your newly uploaded version (it may be identified by your groupId and version as a “deployment” or a staging repository).
    
*   Review it if needed (ensure all artifacts and signatures are present). Then hit the **Release** button for that staging repository. Confirm the release. This action will synchronize the artifacts to Maven Central (the global repository).
    

_(Previously with OSSRH, one would “close” and then “release” via Nexus UI or a plugin. In the new portal, the process is streamlined – the upload plus a manual release click. The term “close” may not appear in the UI, but essentially the portal ensures the bundle is complete and then releases it.)_

If for some reason you find an issue and need to drop the staging repo, you can drop it in the portal instead of releasing, then fix your build and re-run `publish` to upload again.

**Note:** It’s also possible to trigger a release via REST API calls if you want to fully automate this without web UI. Sonatype’s portal provides a URL for releasing a deployment bundle via API[central.sonatype.org](https://central.sonatype.org/publish/publish-portal-ossrh-staging-api/#:~:text=Deploying%E2%9A%93%EF%B8%8E), but using the web interface is straightforward for manual publishing.

Once released, the artifacts will be available on Maven Central shortly. Maven Central sync is typically quick (a few minutes), but allow some time for indexing. You can verify by searching your artifact on search.maven.org or by adding it as a dependency in a test project (it may take ~10 minutes to appear).

Congratulations – your Kotlin/Scala library is now published on Maven Central! 🎉

11\. Additional Tips and References
-----------------------------------

*   **Coordinate Immutability:** Remember that once a version is released to Central, it **cannot be changed or deleted**[central.sonatype.org](https://central.sonatype.org/register/central-portal/#:~:text=As%20such%20you%20are%20bound,our%20full%20terms%20of%20service). If you discover an issue, you must release a new version. Double-check everything (especially groupId, artifactId, version) before releasing.
    
*   **Snapshots:** If you deployed a `-SNAPSHOT` version to the snapshots repository, it’s immediately available to users (from Sonatype’s snapshots repository). Snapshots don’t get released and synced to Central (Central only hosts release versions), so consumers need to use the Sonatype snapshot repo in their build tools to fetch it. Use snapshots for development or testing releases, but do an official versioned release for production use.
    
*   **Multi-module release:** When releasing multiple modules as part of one library (e.g., `mylib-core`, `mylib-utils` under the same group and version), it’s best to release them together. If you ran `publish` in the root, all submodules’ artifacts should be in the same staging repository. Releasing that staging repo publishes all of them atomically. This is preferable so that all modules of a given version appear on Maven Central at the same time.
    
*   **Troubleshooting:** If the `publish` task fails with errors:
    
    *   **401 Unauthorized**: Check that your Sonatype credentials (user token) are correct and not expired. Ensure you used the token’s username/password (not your account login)[central.sonatype.org](https://central.sonatype.org/publish/publish-portal-ossrh-staging-api/#:~:text=The%20OSSRH%20Staging%20API%20is,with%20Central%20Portal%20User%20Tokens).
        
    *   **403 Forbidden**: This could indicate you tried to deploy to a groupId that you don’t have permission for. Make sure the groupId exactly matches the namespace you verified (including subpackages). For example, if your namespace is `com.example`, you cannot publish `com.other` or even `com.example.something` unless `com.example.something` was implicitly covered or you verified that subdomain. Usually verifying `com.example` covers all sub-packages.
        
    *   **Javadoc/Sources not found**: If Sonatype reports missing javadoc or sources, ensure you applied `withJavadocJar()`/`withSourcesJar()` and that those artifacts are being published. According to Sonatype rules, non-pom artifacts must have sources and javadoc jars[central.sonatype.org](https://central.sonatype.org/publish/requirements/#:~:text=Projects%20with%20packaging%20other%20than,as%20for%20display%20and%20navigation), otherwise validation fails.
        
    *   **Signature errors**: If it complains about missing signatures, ensure the Signing plugin actually ran. You might need to ensure `sign(publishing.publications)` is configured _before_ publishing tasks execute. In Kotlin DSL, the configuration as shown should be fine. Also verify your `signingKey` and `signingPassword` are being found. You can add `-PsigningKey="...(key)..."` in the command to test quickly.
        
    *   For more, see Sonatype’s guide and FAQ for common errors[central.sonatype.org](https://central.sonatype.org/publish/publish-portal-ossrh-staging-api/#:~:text=,Manual)[central.sonatype.org](https://central.sonatype.org/publish/publish-portal-ossrh-staging-api/#:~:text=,SBT) or consult the community if something isn’t working.
        
*   **References:** Official Sonatype documentation for the new Central publishing process is available on their site. In particular, the requirements checklist is useful[central.sonatype.org](https://central.sonatype.org/publish/requirements/#:~:text=Supply%20Javadoc%20and%20Sources%E2%9A%93%EF%B8%8E), as well as the step-by-step guides on namespace setup and token generation (we cited those throughout). Gradle’s documentation on the Maven Publish and Signing plugins can provide more insight on customization.
    

By following this guide, you have set up a Gradle-based workflow to publish your Kotlin and Scala libraries to Maven Central. This process can be automated (for example, using a Python script or CI job to run the `gradlew publish` command and perhaps trigger a release via API), but even manually it should be straightforward after the initial configuration. Good luck with your library release on Maven Central!

**Sources:**

*   Sonatype OSSRH/Central documentation (2024–2025) for requirements and process[central.sonatype.org](https://central.sonatype.org/publish/requirements/#:~:text=Projects%20with%20packaging%20other%20than,as%20for%20display%20and%20navigation)[central.sonatype.org](https://central.sonatype.org/publish/requirements/#:~:text=Developer%20information%20is%20also%20required%3A)[central.sonatype.org](https://central.sonatype.org/publish/generate-portal-token/#:~:text=1,once%20it%20has%20been%20generated)[central.sonatype.org](https://central.sonatype.org/publish/publish-portal-ossrh-staging-api/#:~:text=%2F%2F%20...%20repositories%20,api.central.sonatype.com%2Fservice%2Flocal%2Fstaging%2Fdeploy%2Fmaven2%2F%22)
    
*   Gradle Documentation for publishing and signing plugins[docs.gradle.org](https://docs.gradle.org/current/samples/sample_building_scala_libraries.html#:~:text=java%20)[docs.gradle.org](https://docs.gradle.org/current/kotlin-dsl/gradle/org.gradle.plugins.signing/-signing-extension/use-in-memory-pgp-keys.html#:~:text=signing%20,useInMemoryPgpKeys%28secretKey%2C%20password%29)
    
*   PJ Fanning, _Publishing Your First Open Source Library with Gradle_, on including sources/javadoc and metadata[selectfrom.dev](https://selectfrom.dev/publishing-your-first-open-source-library-with-gradle-50bd0b1cd3af#:~:text=Sonatype%20requires%20that%20you%20include,in%20the%20excerpt%20above)[selectfrom.dev](https://selectfrom.dev/publishing-your-first-open-source-library-with-gradle-50bd0b1cd3af#:~:text=The%20publishing%20section%20specifies%20what,license%2C%20developers%2C%20and%20SCM%20links)
    
*   Nikita Kulikov (Medium, 2024), _Publishing to Maven Central Portal_ (insights on new portal usage)[medium.com](https://medium.com/@lionzxy/how-to-publish-a-library-to-the-maven-central-portal-in-2024-a64ad67751c9#:~:text=To%20verify%20domain%20ownership%20you,how%20to%20do%20this%20here)[medium.com](https://medium.com/@lionzxy/how-to-publish-a-library-to-the-maven-central-portal-in-2024-a64ad67751c9#:~:text=As%20of%2012%20March%202024%2C,publishing%20projects%20of%20new%20authors)
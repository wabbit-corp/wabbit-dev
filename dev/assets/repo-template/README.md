![](./.meta/github-project-banner.png)

<p align=center>
    <a href="https://jitpack.io/#{{github-org}}/{{github-repo}}/"><img src="https://jitpack.io/v/{{github-org}}/{{github-repo}}.svg" alt="Release"></a>
    <a href="https://jitpack.io/#{{github-org}}/{{github-repo}}/"><img src="https://jitpack.io/v/{{github-org}}/{{github-repo}}/month.svg" alt="Monthly download statistics"></a>
</p>

<p align=center>
    <a href="https://github.com/{{github-org}}/{{github-repo}}/blob/main/LICENSE.md"><img src="https://img.shields.io/github/license/{{github-org}}/{{github-repo}}" alt="License"></a>
    <a href="https://github.com/{{github-org}}/{{github-repo}}"><img src="https://img.shields.io/github/languages/top/{{github-org}}/{{github-repo}}" alt="GitHub top language"></a>
</p>

---

{{elevator-pitch}}

```
{{usage-at-a-glance}}
```

## 🚀 Installation

Add the following dependency to your project:

{# If this is a gradle project #}
{% if gradle %}

If you are using Gradle, add the following to your `build.gradle.kts` file:
```kotlin
repositories {
    maven("https://jitpack.io")
}
dependencies {
    implementation("com.github.{{github-org}}:{{github-repo}}:{{project-version}}")
}
```

If you are using Maven, add the following to your `pom.xml` file:
```xml
<repositories>
    <repository>
        <id>jitpack.io</id>
        <url>https://jitpack.io</url>
    </repository>
</repositories>
<dependency>
    <groupId>com.github.{{github-org}}</groupId>
    <artifactId>{{github-repo}}</artifactId>
    <version>{{project-version}}</version>
</dependency>
```

If you are using SBT, add the following to your `build.sbt` file:
```scala
resolvers += "jitpack" at "https://jitpack.io"
libraryDependencies += "com.github.{{github-org}}" % "{{github-repo}}" % "{{project-version}}"
```

{% endif %}

{# If this is a Python project #}
{% if python %}

{%- endif %}



## 🚀 Usage

{{usage-information}}

## Licensing

This project is licensed under the [{{license-type}}](LICENSE.md) for open source use.

Additional license notices and custom license texts, when needed, live in
`NOTICE.md` and `LICENSES/`.

For commercial use, please contact {{ company_legal_name }} (at {{ legal_contact_email }}) for licensing terms.

## Contributing

Before we can accept your contributions, we kindly ask you to agree to our [Contributor License Agreement (CLA)](legal/cla/v1.0.0/CLA.md).

# Philosophy

This document defines the guiding principles for `root.clj`, project generation, and development modes in `app-wabbit-dev`.

## Core Principles

1. To the extent possible, everything is generated from `root.clj`.
   If something appears to need custom handwritten Gradle or project setup, the first question is whether it can be generalized so it works for all projects of that type and can therefore be modeled in `root.clj`.

2. `--prod` mode simulates how an outside user would work with a project after cloning it from its own repository.
   It should prefer the same dependency and plugin resolution paths that external consumers would rely on.

3. `--local` mode should provide the best possible local development experience.
   Projects should depend on each other based on their filesystem location so changes flow immediately across the workspace without requiring publishing steps.

4. `root.clj` syntax should optimize for ease of use.
   Defaults should be sane, repetition should be minimized, and common project shapes should be easy to express.

5. Everything must load correctly in IntelliJ and Rider.
   Generated Gradle settings and build files are not considered correct unless they work in the IDE as well as on the command line.

6. Builds should be fast.
   Fast local feedback matters, and generator decisions should favor quick configuration, quick compilation, and minimal unnecessary work.

## Consequences

- Local development support is a first-class requirement, including for compiler plugins and Gradle plugins.
- `mavenLocal` may be useful in specific workflows, but it must not become the default substitute for correct local composite-build behavior.
- If a project needs extra handwritten logic, the preferred path is:
  1. generalize it into the generator when that makes sense across the project type
  2. otherwise isolate the custom part in an explicit escape hatch such as an extra Gradle file

## Mode Intent

### `--prod`

`--prod` should answer the question: "Would this repository work for someone who cloned it independently?"

That means:

- dependencies and plugins should resolve the way outside consumers would expect
- generated files should resemble the standalone repository experience
- success in `--prod` is a correctness requirement, not an optional polish step

### `--local`

`--local` should answer the question: "What is the fastest, smoothest way to work on many related projects in one filesystem tree?"

That means:

- filesystem-based project linking is preferred
- local plugin development must work
- changes in one project should be visible to dependent projects immediately
- IDE import and sync must remain correct

## Possible Future Mode

### `--local-m2`

A future `--local-m2` mode may be worth adding if it serves a distinct purpose that neither `--local` nor `--prod` covers cleanly.

If added, it should be understood as:

- an explicit artifact-resolution workflow using local Maven publishing
- useful for testing publication and artifact-consumer behavior without going fully remote
- not a replacement for `--local`
- not an excuse to weaken direct local-development support

In other words, `--local-m2` is acceptable as an additional tool, but the main philosophy remains:

- `--prod` for outsider realism
- `--local` for best-in-class in-repo development


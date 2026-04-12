# Python Style Guide

This workspace prefers a typed, application-style Python rather than loose scripting.

The goal is not "clever Python". The goal is code that stays easy to refactor, type-check, test, and reason about as the project grows.

## Core Principles

- Prefer explicit data models over dynamic bags of values.
- Parse once at the boundary, then work with typed values.
- Keep side effects at the edges and keep core logic pure where possible.
- Make illegal states hard to represent.
- Optimize for maintainability and refactoring, not shortness.

## Typing

- Type-check with `pyright` in strict mode and keep the code genuinely type-safe.
- Do not use `Any`.
- Do not use `object` as a generic escape hatch.
  Use a specific union type instead, such as a `JSON` alias for JSON-shaped values.
- Do not use `cast(...)` unless there is no principled alternative.
- Do not use `getattr(...)` for normal control flow.
- Use `# type: ignore` only when the type system cannot express something real and localized.

Prefer these tools, in roughly this order:

1. dataclasses for concrete structured data
2. `TypedDict` for JSON-like records and external payloads
3. `Protocol` for structural interfaces, especially when wrapping external libraries
4. enums and literal-like tagged values for constrained states

## Data Modeling

Avoid these patterns:

- `dict[str, object]` for normal business logic
- `SimpleNamespace`
- untyped `Namespace` plumbing spreading through the codebase
- functions that accept or return "whatever"

Prefer:

- a dataclass for internal state
- a `TypedDict` for external payloads
- a small protocol for pluggable collaborators
- a dedicated JSON union for serialized values

Example JSON alias:

```python
from __future__ import annotations

type JSON = (
    None
    | bool
    | int
    | float
    | str
    | list["JSON"]
    | dict[str, "JSON"]
)
```

## Control Flow

- Prefer `match` when handling more than one meaningful case.
- Use `assert isinstance(...)` when you are proving a fact locally.
- Avoid long `if`/`elif` ladders over tagged data when pattern matching is clearer.
- Normalize input early so the rest of the function can work over fewer cases.

Example:

```python
match payload:
    case {"result": str() as result}:
        return result
    case {"error": str() as error}:
        raise ValueError(error)
    case _:
        raise ValueError("Invalid payload")
```

## CLI Style

Command code should be organized around typed commands, not around dynamically-probed parser state.

- Keep the command grammar in one place.
- Convert parser output into typed command values early.
- Pass around typed command objects or typed arguments, not raw `argparse.Namespace`.
- Prefer explicit subcommands over mode flags when the modes are conceptually different.
- Public CLI behavior, help, completion, and dispatch should all derive from the same command definition when possible.

The desired feel is closer to a small `kotlin-cli`-style command model than to an ad hoc argparse script.

## Boundaries and External APIs

At boundaries:

- validate early
- narrow types immediately
- convert external responses into internal typed forms

When wrapping external libraries:

- hide dynamic or weakly typed APIs behind small typed helpers
- use `Protocol` when tests need a fake client
- do not leak third-party dynamic response shapes through the whole codebase

## Tests

Tests should follow the same type discipline as production code.

- Do not rely on `SimpleNamespace` for rich test doubles.
- Prefer small dataclasses or typed fake classes.
- If tests need a private helper, first ask whether the production code should expose a small public wrapper instead.
- Avoid monkeypatching with untyped lambdas when a tiny named fake function or fake class is clearer.
- Type fixtures like `pytest.MonkeyPatch`, `pytest.CaptureFixture[str]`, and `pytest.LogCaptureFixture`.

## Functional Shape

Prefer functions that:

- take typed inputs
- return typed outputs
- do one thing
- separate transformation from effects

Avoid functions that:

- inspect the filesystem, parse config, mutate globals, and render output all at once
- return partially-structured values that callers have to rediscover

## Error Handling

- Raise or return errors that preserve structure and context.
- Prefer explicit error states over silent fallback.
- Do not hide type uncertainty behind broad exception handling.
- When a function can fail in an expected way, model that failure clearly.

## Naming

- Names should describe meaning, not mechanism.
- Prefer names that reflect the abstraction boundary.
- Avoid vague names like `data`, `obj`, `thing`, `misc`, or `native` when the actual boundary is more specific.

## Practical Rules

- If a value has a known shape, model the shape.
- If a function is branching on structure, consider `match`.
- If code reaches for `cast`, `getattr`, `Any`, or `object`, step back and redesign the boundary.
- If a test needs a weird fake, the production interface is probably too dynamic.
- If CLI code is passing `argparse.Namespace` deep into the program, the typing boundary is too late.

## Non-Goals

This style does not aim to:

- maximize cleverness
- use every advanced typing feature
- turn simple scripts into frameworks

It does aim to make medium-sized Python applications feel disciplined, explicit, and easy to evolve.

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CommandDocNode:
    name: str
    aliases: tuple[str, ...]
    children: tuple[str, ...]


def _typed_cli_path() -> Path:
    return Path(__file__).resolve().parents[1] / "dev" / "typed_cli.py"


def _commands_doc_path() -> Path:
    return Path(__file__).resolve().parents[1] / "docs" / "commands.md"


def _string_constant(node: ast.AST) -> str | None:
    match node:
        case ast.Constant(value=str(value)):
            return value
    return None


def _tuple_name_values(node: ast.AST) -> tuple[str, ...]:
    match node:
        case ast.Tuple(elts=elts) | ast.List(elts=elts):
            names: list[str] = []
            for element in elts:
                match element:
                    case ast.Name(id=name):
                        names.append(name)
            return tuple(names)
    return ()


def _alias_values(node: ast.AST) -> tuple[str, ...]:
    match node:
        case ast.Tuple(elts=elts) | ast.List(elts=elts):
            aliases: list[str] = []
            for element in elts:
                match element:
                    case ast.Call(func=ast.Name(id="CommandAlias"), args=args):
                        if not args:
                            continue
                        alias_name = _string_constant(args[0])
                        if alias_name is not None:
                            aliases.append(alias_name)
            return tuple(aliases)
    return ()


def _load_command_nodes() -> tuple[dict[str, CommandDocNode], tuple[str, ...]]:
    module = ast.parse(_typed_cli_path().read_text(encoding="utf-8"))
    nodes: dict[str, CommandDocNode] = {}
    root_children: tuple[str, ...] = ()

    for statement in ast.walk(module):
        match statement:
            case ast.Assign(
                targets=[ast.Name(id=variable_name)],
                value=ast.Call(func=ast.Name(id="Command"), keywords=keywords),
            ):
                name: str | None = None
                aliases: tuple[str, ...] = ()
                children: tuple[str, ...] = ()
                for keyword in keywords:
                    if keyword.arg == "name":
                        match keyword.value:
                            case ast.Name(id="prog") if variable_name == "root":
                                name = "dev"
                            case _:
                                name = _string_constant(keyword.value)
                    elif keyword.arg == "aliases":
                        aliases = _alias_values(keyword.value)
                    elif keyword.arg == "subcommands":
                        children = _tuple_name_values(keyword.value)
                if name is None:
                    continue
                nodes[variable_name] = CommandDocNode(name=name, aliases=aliases, children=children)
                if variable_name == "root":
                    root_children = children

    return nodes, root_children


def _command_paths() -> tuple[str, ...]:
    nodes, root_children = _load_command_nodes()
    assert root_children, "Failed to parse the root command tree from dev/typed_cli.py."

    paths: list[str] = []

    def walk(variable_name: str, prefix: tuple[str, ...]) -> None:
        node = nodes[variable_name]
        path = (*prefix, node.name)
        paths.append(" ".join(path[1:]))
        for alias in node.aliases:
            alias_path = (*path[1:-1], alias)
            paths.append(" ".join(alias_path))
        for child_name in node.children:
            walk(child_name, path)

    for child_name in root_children:
        walk(child_name, ("dev",))
    return tuple(paths)


def _docs_mentions_command(docs_text: str, command_path: str) -> bool:
    return (
        f"`{command_path}`" in docs_text
        or f"`dev {command_path}`" in docs_text
        or f"dev {command_path}" in docs_text
    )


def test_every_typed_cli_command_path_is_documented() -> None:
    docs_text = _commands_doc_path().read_text(encoding="utf-8")
    missing = [path for path in _command_paths() if not _docs_mentions_command(docs_text, path)]
    assert missing == [], "Undocumented command paths: " + ", ".join(missing)

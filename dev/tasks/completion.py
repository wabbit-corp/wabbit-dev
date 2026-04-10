from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from weakref import WeakKeyDictionary

from dev.config import Config, load_config
from dev.tasks.check import list_check_names
from dev.tasks.doctor import doctor_only_choices

_ALLOW_FILES_PREFIX = "__wabbit_dev_allow_files__="


@dataclass(frozen=True)
class CompletionActionMetadata:
    kind: str | None = None
    allow_files: bool = False
    blocks_positionals: bool = False


@dataclass(frozen=True)
class CompletionParserMetadata:
    hidden: bool = False


_DEFAULT_ACTION_METADATA = CompletionActionMetadata()
_DEFAULT_PARSER_METADATA = CompletionParserMetadata()
_ACTION_METADATA: WeakKeyDictionary[argparse.Action, CompletionActionMetadata] = WeakKeyDictionary()
_PARSER_METADATA: WeakKeyDictionary[argparse.ArgumentParser, CompletionParserMetadata] = WeakKeyDictionary()
_PARSER_CHILDREN: WeakKeyDictionary[argparse.ArgumentParser, dict[str, argparse.ArgumentParser]] = WeakKeyDictionary()


@dataclass(frozen=True)
class CompletionReply:
    candidates: tuple[str, ...]
    allow_files: bool = False


def register_action_metadata(
    action: argparse.Action,
    *,
    kind: str | None = None,
    allow_files: bool = False,
    blocks_positionals: bool = False,
) -> None:
    _ACTION_METADATA[action] = CompletionActionMetadata(
        kind=kind,
        allow_files=allow_files,
        blocks_positionals=blocks_positionals,
    )


def register_parser_metadata(parser: argparse.ArgumentParser, *, hidden: bool = False) -> None:
    _PARSER_METADATA[parser] = CompletionParserMetadata(hidden=hidden)


def register_parser_child(parent: argparse.ArgumentParser, name: str, child: argparse.ArgumentParser) -> None:
    children = _PARSER_CHILDREN.get(parent)
    if children is None:
        children = {}
        _PARSER_CHILDREN[parent] = children
    children[name] = child


def action_metadata(action: argparse.Action) -> CompletionActionMetadata:
    return _ACTION_METADATA.get(action, _DEFAULT_ACTION_METADATA)


def parser_metadata(parser: argparse.ArgumentParser) -> CompletionParserMetadata:
    return _PARSER_METADATA.get(parser, _DEFAULT_PARSER_METADATA)


def parser_children(parser: argparse.ArgumentParser) -> dict[str, argparse.ArgumentParser]:
    return _PARSER_CHILDREN.get(parser, {})


def _dedupe(values: list[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return tuple(result)


def _safe_load_config() -> Config | None:
    try:
        return load_config()
    except Exception:
        return None


def _configured_names(config: Config | None) -> tuple[str, ...]:
    if config is None:
        return ()
    return _dedupe([*config.defined_projects.keys(), *config.defined_repos.keys()])


def _check_target_candidates(config: Config | None) -> tuple[str, ...]:
    base = list(_configured_names(config))
    return _dedupe([":root", *base, *[f":{value}" for value in base]])


def _candidates_for_kind(kind: str | None, config: Config | None) -> tuple[str, ...]:
    if kind in {"project-target", "repo-target", "path-or-target"}:
        return _configured_names(config)
    if kind == "push-target":
        return _dedupe([".", *_configured_names(config)])
    if kind == "check-target":
        return _check_target_candidates(config)
    if kind == "check-name":
        return tuple(list_check_names(config))
    if kind == "doctor-only":
        return doctor_only_choices()
    return ()


def _visible_subcommands(parser: argparse.ArgumentParser) -> tuple[str, ...]:
    choices = parser_children(parser)
    if not choices:
        return ()
    candidates: list[str] = []
    for name, child in choices.items():
        if parser_metadata(child).hidden:
            continue
        candidates.append(name)
    return tuple(candidates)


def _visible_option_actions(parser: argparse.ArgumentParser) -> list[argparse.Action]:
    actions: list[argparse.Action] = []
    for action in parser._actions:
        if not action.option_strings:
            continue
        if action.help is argparse.SUPPRESS:
            continue
        actions.append(action)
    return actions


def _option_map(parser: argparse.ArgumentParser) -> dict[str, argparse.Action]:
    mapping: dict[str, argparse.Action] = {}
    for action in _visible_option_actions(parser):
        for option in action.option_strings:
            mapping[option] = action
    return mapping


def _visible_positional_actions(parser: argparse.ArgumentParser) -> list[argparse.Action]:
    actions: list[argparse.Action] = []
    for action in parser._actions:
        if action.option_strings:
            continue
        if parser_children(parser) and action.dest.endswith("command"):
            continue
        if action.help is argparse.SUPPRESS:
            continue
        actions.append(action)
    return actions


def _resolve_active_parser(parser: argparse.ArgumentParser, words: list[str]) -> tuple[argparse.ArgumentParser, int]:
    active = parser
    index = 1
    while True:
        choices = parser_children(active)
        if not choices or index >= len(words):
            return active, index
        token = words[index]
        if token.startswith("-") or token not in choices:
            return active, index
        active = choices[token]
        index += 1


def _normalize_completion_words(words: list[str], cword: int) -> tuple[list[str], int]:
    if len(words) < 2 or words[1] != "check":
        return words, cword
    if len(words) == 2:
        return words, cword
    if len(words) > 2 and words[2] in {"run", "list", "describe"}:
        return words, cword
    normalized = words[:2] + ["run"] + words[2:]
    adjusted_cword = cword + 1 if cword >= 2 else cword
    return normalized, adjusted_cword


def _action_expects_value(action: argparse.Action) -> bool:
    if not action.option_strings:
        return False
    return action.nargs != 0


def _current_positional_action(actions: list[argparse.Action], consumed_count: int) -> argparse.Action | None:
    remaining = consumed_count
    for index, action in enumerate(actions):
        nargs = action.nargs
        is_last = index == len(actions) - 1

        if nargs in (None, 1):
            if remaining == 0:
                return action
            remaining -= 1
            continue

        if nargs == "?":
            if remaining == 0:
                return action
            remaining -= 1
            continue

        if nargs in ("*", "+"):
            return action

        if isinstance(nargs, int):
            if remaining < nargs:
                return action
            remaining -= nargs
            continue

        if is_last:
            return action

    if actions and actions[-1].nargs in ("*", "+"):
        return actions[-1]
    return None


def get_completion_reply(
    parser: argparse.ArgumentParser,
    words: list[str],
    cword: int,
) -> CompletionReply:
    if len(words) >= 2 and words[1] == "check" and cword == 2:
        config = _safe_load_config()
        return CompletionReply(
            (
                "list",
                "describe",
                *_check_target_candidates(config),
            ),
            allow_files=True,
        )

    words, cword = _normalize_completion_words(words, cword)
    config = _safe_load_config()
    active_parser, arg_start = _resolve_active_parser(parser, words)

    if cword == arg_start:
        subcommands = _visible_subcommands(active_parser)
        if subcommands:
            return CompletionReply(subcommands)

    current = words[cword] if cword < len(words) else ""
    if current.startswith("-"):
        option_strings: list[str] = []
        for action in _visible_option_actions(active_parser):
            option_strings.extend(action.option_strings)
        return CompletionReply(_dedupe(option_strings))

    option_map = _option_map(active_parser)
    if cword > arg_start:
        previous = words[cword - 1]
        previous_action = option_map.get(previous)
        if previous_action is not None and _action_expects_value(previous_action):
            return CompletionReply(_candidates_for_kind(action_metadata(previous_action).kind, config))

    consumed_positionals = 0
    blocked_positionals = False
    index = arg_start
    while index < cword:
        token = words[index]
        if token.startswith("-"):
            matched_action: argparse.Action | None = option_map.get(token)
            if matched_action is None:
                index += 1
                continue
            if action_metadata(matched_action).blocks_positionals:
                blocked_positionals = True
            index += 2 if _action_expects_value(matched_action) else 1
            continue
        consumed_positionals += 1
        index += 1

    if blocked_positionals:
        return CompletionReply(())

    positional_action = _current_positional_action(_visible_positional_actions(active_parser), consumed_positionals)
    if positional_action is None:
        return CompletionReply(())

    metadata = action_metadata(positional_action)
    kind = metadata.kind
    allow_files = metadata.allow_files
    return CompletionReply(_candidates_for_kind(kind, config), allow_files=allow_files)


def _shell_function_name(prog: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_]+", "_", prog).strip("_")
    if not cleaned:
        cleaned = "wabbit_dev"
    return f"_{cleaned}_completion"


def bash_completion_script(prog: str) -> str:
    function_name = _shell_function_name(prog)
    return f"""# bash completion for {prog}
{function_name}() {{
    local raw line allow_files cur
    local -a candidates

    cur="${{COMP_WORDS[COMP_CWORD]}}"
    raw="$("${{COMP_WORDS[0]}}" completion query bash "$COMP_CWORD" "${{COMP_WORDS[@]}}" 2>/dev/null)" || return 0
    allow_files=0

    while IFS= read -r line; do
        if [[ "$line" == {_ALLOW_FILES_PREFIX}* ]]; then
            allow_files="${{line#{_ALLOW_FILES_PREFIX}}}"
            continue
        fi
        [[ -n "$line" ]] && candidates+=("$line")
    done <<< "$raw"

    COMPREPLY=()
    if (( ${{#candidates[@]}} )); then
        while IFS= read -r line; do
            COMPREPLY+=("$line")
        done < <(compgen -W "$(printf '%s\\n' "${{candidates[@]}}")" -- "$cur")
    fi
    if [[ "$allow_files" == "1" ]]; then
        while IFS= read -r line; do
            COMPREPLY+=("$line")
        done < <(compgen -f -- "$cur")
    fi
}}

complete -o bashdefault -o default -F {function_name} {prog}
"""


def zsh_completion_script(prog: str) -> str:
    function_name = _shell_function_name(prog)
    return f"""#compdef {prog}

{function_name}() {{
    emulate -L zsh
    setopt localoptions noshwordsplit

    local raw line allow_files
    local -a candidates

    raw="$(${{words[1]}} completion query zsh $((CURRENT - 1)) "${{words[@]}}" 2>/dev/null)" || return 1
    allow_files=0
    candidates=()

    while IFS= read -r line; do
        if [[ "$line" == {_ALLOW_FILES_PREFIX}* ]]; then
            allow_files="${{line#{_ALLOW_FILES_PREFIX}}}"
            continue
        fi
        [[ -n "$line" ]] && candidates+=("$line")
    done <<< "$raw"

    if (( ${{#candidates[@]}} )); then
        compadd -- "${{candidates[@]}}"
    fi
    if [[ "$allow_files" == "1" ]]; then
        _files
    fi
}}

compdef {function_name} {prog}
"""


def completion_script(shell: str, *, prog: str) -> str:
    if shell == "bash":
        return bash_completion_script(prog)
    if shell == "zsh":
        return zsh_completion_script(prog)
    raise ValueError(f"Unsupported shell: {shell}")


def print_completion_script(shell: str, *, prog: str) -> int:
    print(completion_script(shell, prog=prog), end="")
    return 0


def print_completion_query(
    parser: argparse.ArgumentParser,
    shell: str,
    cword: int,
    words: list[str],
) -> int:
    del shell
    reply = get_completion_reply(parser, words, cword)
    print(f"{_ALLOW_FILES_PREFIX}{1 if reply.allow_files else 0}")
    for candidate in reply.candidates:
        print(candidate)
    return 0


__all__ = [
    "CompletionReply",
    "action_metadata",
    "bash_completion_script",
    "completion_script",
    "get_completion_reply",
    "parser_children",
    "parser_metadata",
    "print_completion_query",
    "print_completion_script",
    "register_action_metadata",
    "register_parser_child",
    "register_parser_metadata",
    "zsh_completion_script",
]

from __future__ import annotations

import argparse
import os
import re
from dataclasses import dataclass
from pathlib import Path

from dev.cli import build_parser
from dev.config import Config, load_config
from dev.tasks.check import list_check_names

_ALLOW_FILES_PREFIX = "__wabbit_dev_allow_files__="


@dataclass(frozen=True)
class CompletionReply:
    candidates: tuple[str, ...]
    allow_files: bool = False


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
    current = Path.cwd()
    candidates = [current, *current.parents]

    for candidate in candidates:
        if not (candidate / "root.clj").exists():
            continue
        if not (candidate / "root.private.clj").exists():
            continue
        previous_cwd = Path.cwd()
        try:
            os.chdir(candidate)
            return load_config()
        except Exception:
            continue
        finally:
            os.chdir(previous_cwd)

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
    return ()


def _subparsers_action(parser: argparse.ArgumentParser) -> argparse._SubParsersAction[argparse.ArgumentParser] | None:
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return action
    return None


def _visible_subcommands(parser: argparse.ArgumentParser) -> tuple[str, ...]:
    action = _subparsers_action(parser)
    if action is None:
        return ()
    candidates: list[str] = []
    for name, child in action.choices.items():
        if getattr(child, "_completion_hidden", False):
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
        if isinstance(action, argparse._SubParsersAction):
            continue
        if action.help is argparse.SUPPRESS:
            continue
        actions.append(action)
    return actions


def _resolve_active_parser(parser: argparse.ArgumentParser, words: list[str]) -> tuple[argparse.ArgumentParser, int]:
    active = parser
    index = 1
    while True:
        subparsers = _subparsers_action(active)
        if subparsers is None or index >= len(words):
            return active, index
        token = words[index]
        if token.startswith("-") or token not in subparsers.choices:
            return active, index
        active = subparsers.choices[token]
        index += 1


def _action_expects_value(action: argparse.Action) -> bool:
    if not action.option_strings:
        return False
    if isinstance(action, (argparse._HelpAction, argparse._StoreTrueAction, argparse._StoreFalseAction)):
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


def get_completion_reply(words: list[str], cword: int) -> CompletionReply:
    parser, _commands = build_parser()
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
            kind = getattr(previous_action, "_completion_kind", None)
            return CompletionReply(_candidates_for_kind(kind, config))

    consumed_positionals = 0
    blocked_positionals = False
    index = arg_start
    while index < cword:
        token = words[index]
        if token.startswith("-"):
            action = option_map.get(token)
            if action is None:
                index += 1
                continue
            if getattr(action, "_completion_blocks_positionals", False):
                blocked_positionals = True
            index += 2 if _action_expects_value(action) else 1
            continue
        consumed_positionals += 1
        index += 1

    if blocked_positionals:
        return CompletionReply(())

    positional_action = _current_positional_action(_visible_positional_actions(active_parser), consumed_positionals)
    if positional_action is None:
        return CompletionReply(())

    kind = getattr(positional_action, "_completion_kind", None)
    allow_files = bool(getattr(positional_action, "_completion_allow_files", False))
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


def print_completion_query(shell: str, cword: int, words: list[str]) -> int:
    del shell
    reply = get_completion_reply(words, cword)
    print(f"{_ALLOW_FILES_PREFIX}{1 if reply.allow_files else 0}")
    for candidate in reply.candidates:
        print(candidate)
    return 0


__all__ = [
    "CompletionReply",
    "bash_completion_script",
    "completion_script",
    "get_completion_reply",
    "print_completion_query",
    "print_completion_script",
    "zsh_completion_script",
]

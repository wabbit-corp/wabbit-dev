from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from dev.config import GradleProject, PremakeProject, PythonProject, find_workspace_root, load_config
from dev.discoverability import did_you_mean_suffix
from dev.messages import warning
from dev.repo_resolution import inferred_project_targets, resolve_project_ids


@dataclass
class ClocStats:
    files: int
    blank: int
    comment: int
    code: int


def _merge_stats(
    target: defaultdict[str, ClocStats],
    source: defaultdict[str, ClocStats],
) -> None:
    for lang, stats in source.items():
        current = target[lang]
        current.files += stats.files
        current.blank += stats.blank
        current.comment += stats.comment
        current.code += stats.code


def _run_cloc(path: Path) -> defaultdict[str, ClocStats]:
    import subprocess

    # Ignore __pycache__ and .venv directories
    completed = subprocess.run(
        ["cloc", "--json", str(path), "--exclude-dir=__pycache__,.venv"],
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        warning(f"cloc failed for path '{path}': {completed.stderr}")
        return defaultdict(lambda: ClocStats(0, 0, 0, 0))

    import json

    data = json.loads(completed.stdout)
    stats_by_lang: defaultdict[str, ClocStats] = defaultdict(lambda: ClocStats(0, 0, 0, 0))
    for lang, stats in data.items():
        if lang == "header":
            continue
        stats_by_lang[lang] = ClocStats(
            files=stats.get("nFiles", 0),
            blank=stats.get("blank", 0),
            comment=stats.get("comment", 0),
            code=stats.get("code", 0),
        )
    return stats_by_lang


def _target_choices(config: object | None) -> list[str]:
    if config is None:
        return []
    return list(dict.fromkeys([*config.defined_projects.keys(), *config.defined_repos.keys()]))


def cloc(
    targets: str | list[str] | None = None,
) -> None:
    config = load_config() if find_workspace_root() is not None else None
    if config is None:
        warning("No config file found. Some checks may not have sufficient context to run.")

    requested_targets = [targets] if isinstance(targets, str) else targets
    project_names: list[str] = []
    direct_paths: list[Path] = []
    if not requested_targets:
        if config is not None:
            inferred_targets = inferred_project_targets(config)
            if inferred_targets is not None:
                project_names = resolve_project_ids(config, inferred_targets)
            else:
                project_names = list(config.defined_projects.keys())
        else:
            warning("No project specified and no config found. Nothing to do.")
            return
    else:
        seen_project_names: set[str] = set()
        seen_direct_paths: set[Path] = set()
        for target in requested_targets:
            if config is not None:
                try:
                    for project_name in resolve_project_ids(config, [target]):
                        if project_name in seen_project_names:
                            continue
                        seen_project_names.add(project_name)
                        project_names.append(project_name)
                    continue
                except ValueError:
                    pass

            direct_path = Path(target).absolute()
            if not direct_path.exists():
                suggestion = did_you_mean_suffix(target, _target_choices(config))
                warning(f"Path '{direct_path}' does not exist.{suggestion} Skipping.")
                continue
            if direct_path in seen_direct_paths:
                continue
            seen_direct_paths.add(direct_path)
            direct_paths.append(direct_path)

    combined_stats: defaultdict[str, defaultdict[str, ClocStats]] = defaultdict(
        lambda: defaultdict(lambda: ClocStats(0, 0, 0, 0))
    )

    for direct_path in direct_paths:
        combined_stats[direct_path.as_posix()] = _run_cloc(direct_path)

    for project in project_names:
        proj = config.defined_projects.get(project) if config else None
        if proj is None:
            warning(f"Project '{project}' not found in config. Skipping.")
            continue

        proj_path = Path(proj.path).absolute()
        if not proj_path.exists():
            warning(f"Project path '{proj_path}' does not exist. Skipping.")
            continue

        match proj:
            case GradleProject():
                # Count only src/main and src/test
                src_dirs = [
                    proj_path / "src" / "main",
                    proj_path / "src" / "test",
                ]
                for src_dir in src_dirs:
                    if src_dir.exists():
                        _merge_stats(combined_stats[proj.name], _run_cloc(src_dir))
            case PremakeProject():
                # Count only src
                src_dir = proj_path / "src"
                if src_dir.exists():
                    combined_stats[proj.name] = _run_cloc(src_dir)
            case PythonProject():
                # Count entire project
                combined_stats[proj.name] = _run_cloc(proj_path)
            case _:
                warning(f"Unsupported project type for cloc: {type(proj).__name__}")

    # Print results
    for proj_name, stats in combined_stats.items():
        print(f"Project: {proj_name}")
        for lang, lang_stats in stats.items():
            print(
                f"  {lang}:\n"
                f"    Files:   {lang_stats.files}\n"
                f"    Blank:   {lang_stats.blank}\n"
                f"    Comment: {lang_stats.comment}\n"
                f"    Code:    {lang_stats.code}\n"
            )
    if not combined_stats:
        print("No statistics collected.")

    # Totals
    total_stats: defaultdict[str, ClocStats] = defaultdict(lambda: ClocStats(0, 0, 0, 0))
    for stats in combined_stats.values():
        for lang, lang_stats in stats.items():
            total = total_stats[lang]
            total.files += lang_stats.files
            total.blank += lang_stats.blank
            total.comment += lang_stats.comment
            total.code += lang_stats.code
    print("Overall Totals:")
    for lang, lang_stats in total_stats.items():
        print(
            f"  {lang}:\n"
            f"    Files:   {lang_stats.files}\n"
            f"    Blank:   {lang_stats.blank}\n"
            f"    Comment: {lang_stats.comment}\n"
            f"    Code:    {lang_stats.code}\n"
        )

    # Totals for all languages
    grand_total = ClocStats(0, 0, 0, 0)
    for lang_stats in total_stats.values():
        grand_total.files += lang_stats.files
        grand_total.blank += lang_stats.blank
        grand_total.comment += lang_stats.comment
        grand_total.code += lang_stats.code
    print("Grand Total:")
    print(
        f"  Files:   {grand_total.files}\n"
        f"  Blank:   {grand_total.blank}\n"
        f"  Comment: {grand_total.comment}\n"
        f"  Code:    {grand_total.code}\n"
    )

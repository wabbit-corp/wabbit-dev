from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from dev.config import GradleProject, PremakeProject, PythonProject, load_config
from dev.messages import warning


@dataclass
class ClocStats:
    files: int
    blank: int
    comment: int
    code: int


def _run_cloc(path: Path) -> defaultdict[str, ClocStats]:
    import subprocess

    # Ignore __pycache__ and .venv directories
    result = subprocess.run(
        ["cloc", "--json", str(path), "--exclude-dir=__pycache__,.venv"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        warning(f"cloc failed for path '{path}': {result.stderr}")
        return defaultdict(lambda: ClocStats(0, 0, 0, 0))

    import json

    data = json.loads(result.stdout)
    result = defaultdict(lambda: ClocStats(0, 0, 0, 0))
    for lang, stats in data.items():
        if lang == "header":
            continue
        result[lang] = ClocStats(
            files=stats.get("nFiles", 0),
            blank=stats.get("blank", 0),
            comment=stats.get("comment", 0),
            code=stats.get("code", 0),
        )
    return result


def cloc(
    project_or_dir_or_file: str | None = None,
) -> None:
    config_path = Path("./root.clj").absolute()
    config = load_config() if config_path.exists() else None
    if config is None:
        warning("No config file found. Some checks may not have sufficient context to run.")

    # print(f"Running cloc for: {project_or_dir_or_file or 'all projects'}")
    # print(f"All projects: {list(config.defined_projects.keys()) if config else 'N/A'}")

    projects = []
    if project_or_dir_or_file is None:
        if config is not None:
            projects = list(config.defined_projects.keys())
        else:
            warning("No project specified and no config found. Nothing to do.")
            return
    else:
        if config is not None and project_or_dir_or_file in config.defined_projects:
            projects = [project_or_dir_or_file]
        else:
            projects = [project_or_dir_or_file]

    combined_stats: defaultdict[str, defaultdict[str, ClocStats]] = defaultdict(
        lambda: defaultdict(lambda: ClocStats(0, 0, 0, 0))
    )

    for project in projects:
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
                        combined_stats[proj.name] = _run_cloc(src_dir)
            case PremakeProject():
                # Count only src
                src_dir = proj_path / "src"
                if src_dir.exists():
                    combined_stats[proj.name] = _run_cloc(src_dir)
            case PythonProject():
                # Count entire project
                combined_stats[proj.name] = _run_cloc(proj_path)

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

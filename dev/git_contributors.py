from __future__ import annotations

import logging
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, order=True)
class GitContributor:
    name: str
    email: str

    def __str__(self) -> str:
        return f"{self.name} <{self.email}>"

    def __repr__(self) -> str:
        return f"GitContributor(name={self.name}, email={self.email})"


def _resolve_git_root(path: Path) -> Path:
    if not path.is_dir():
        raise ValueError(f"Path {path} is not a valid directory.")
    try:
        output = subprocess.check_output(["git", "-C", str(path), "rev-parse", "--show-toplevel"], text=True).strip()
    except subprocess.CalledProcessError as ex:
        raise ValueError(f"Path {path} is not a valid git repository.") from ex
    return Path(output)


def _git_output(repo_root: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(repo_root), *args], text=True).strip()


def list_git_contributors(path: Path) -> dict[GitContributor, int]:
    """
    List all git contributors in the current repository.
    """
    repo_root = _resolve_git_root(path)
    try:
        output = _git_output(repo_root, "shortlog", "-sne", "--all")
    except subprocess.CalledProcessError as e:
        LOGGER.warning("Could not list git contributors in %s: %s", repo_root, e)
        return {}
    except FileNotFoundError:
        LOGGER.warning("git command not found. Make sure git is installed.")
        return {}
    except Exception as e:
        LOGGER.warning("Unexpected error while listing git contributors in %s: %s", repo_root, e)
        return {}

    # Split the output into lines
    lines = output.strip().split("\n")

    # Parse the lines to extract contributors
    contributors: dict[GitContributor, int] = {}
    for line in lines:
        # Match the line with regex
        match = re.match(r"^\s*(\d+)\s+(.+?)\s+<(.+?)>", line)
        if match:
            commit_count = int(match.group(1))
            name = match.group(2).strip()
            email = match.group(3).strip()
            # Create a GitContributor object
            contributor = GitContributor(name, email)
            # Add the contributor to the dictionary
            if contributor in contributors:
                contributors[contributor] += commit_count
            else:
                contributors[contributor] = commit_count
    return contributors


def get_git_user_name(path: Path) -> str | None:
    """
    Get the git user name from the git configuration.
    """
    repo_root = _resolve_git_root(path)
    try:
        name = _git_output(repo_root, "config", "--get", "user.name")
        return name
    except subprocess.CalledProcessError:
        return None
    except FileNotFoundError:
        LOGGER.warning("git command not found. Make sure git is installed.")
        return None
    except Exception as e:
        LOGGER.warning("Unexpected error while reading git user.name in %s: %s", repo_root, e)
        return None


def get_git_user_email(path: Path) -> str | None:
    """
    Get the git user email from the git configuration.
    """
    repo_root = _resolve_git_root(path)
    try:
        email = _git_output(repo_root, "config", "--get", "user.email")
        return email
    except subprocess.CalledProcessError:
        return None
    except FileNotFoundError:
        LOGGER.warning("git command not found. Make sure git is installed.")
        return None
    except Exception as e:
        LOGGER.warning("Unexpected error while reading git user.email in %s: %s", repo_root, e)
        return None


def get_git_user(path: Path) -> GitContributor | None:
    """
    Get the git user name and email from the git configuration.
    """
    name = get_git_user_name(path)
    email = get_git_user_email(path)
    if name and email:
        return GitContributor(name, email)
    return None


if __name__ == "__main__":
    from dev.config import load_config

    # import argparse
    # parser = argparse.ArgumentParser(description="List git contributors.")
    # parser.add_argument(
    #     "path",
    #     type=str,
    #     help="Path to the git repository. If not provided, the current directory will be used.",
    #     default=os.getcwd(),
    #     nargs="?",
    # )
    # args = parser.parse_args()
    # path = Path(args.path)

    config = load_config()
    for project in config.defined_projects.values():
        path = project.effective_repo_root

        print(f"Checking {path}...")

        if not path.is_dir():
            print(f"Path {path} is not a valid directory.")
            exit(1)
        if not (path / ".git").exists():
            print(f"Path {path} is not a valid git repository.")
            exit(1)
        contributors = list_git_contributors(path)
        if contributors:
            print(f"Contributors in {path}:")
            for contributor, commit_count in sorted(contributors.items(), key=lambda x: x[1], reverse=True):
                print(f"{contributor}: {commit_count} commits")
        else:
            print(f"No contributors found in {path}.")

        print()


__all__ = [
    "GitContributor",
    "list_git_contributors",
    "get_git_user_name",
    "get_git_user_email",
    "get_git_user",
]

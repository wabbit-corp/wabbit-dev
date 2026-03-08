from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path


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


def list_git_contributors(path: Path) -> dict[GitContributor, int]:
    """
    List all git contributors in the current repository.
    """
    repo_root = _resolve_git_root(path)

    change_dir = os.getcwd()
    try:
        os.chdir(repo_root)
        # git shortlog -sne --all

        # Get the output of the git command
        try:
            output = subprocess.check_output(["git", "shortlog", "-sne", "--all"], text=True)
        except subprocess.CalledProcessError as e:
            print(f"Error: {e}")
            return {}
        except FileNotFoundError:
            print("Error: git command not found. Make sure git is installed.")
            return {}
        except Exception as e:
            print(f"An unexpected error occurred: {e}")
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
    finally:
        os.chdir(change_dir)


def get_git_user_name(path: Path) -> str | None:
    """
    Get the git user name from the git configuration.
    """
    repo_root = _resolve_git_root(path)

    change_dir = os.getcwd()
    try:
        os.chdir(repo_root)
        name = subprocess.check_output(["git", "config", "--get", "user.name"], text=True).strip()
        return name
    except subprocess.CalledProcessError:
        return None
    except FileNotFoundError:
        print("Error: git command not found. Make sure git is installed.")
        return None
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return None
    finally:
        os.chdir(change_dir)


def get_git_user_email(path: Path) -> str | None:
    """
    Get the git user email from the git configuration.
    """
    repo_root = _resolve_git_root(path)

    change_dir = os.getcwd()
    try:
        os.chdir(repo_root)
        email = subprocess.check_output(["git", "config", "--get", "user.email"], text=True).strip()
        return email
    except subprocess.CalledProcessError:
        return None
    except FileNotFoundError:
        print("Error: git command not found. Make sure git is installed.")
        return None
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return None
    finally:
        os.chdir(change_dir)


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

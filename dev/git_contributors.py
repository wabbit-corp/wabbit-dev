from __future__ import annotations
from typing import List, Tuple, Optional, Dict
from dataclasses import dataclass
import subprocess
import re
import os
from pathlib import Path

@dataclass(frozen=True, order=True)
class GitContributor:
    name: str
    email: str

    def __str__(self) -> str:
        return f"{self.name} <{self.email}>"

    def __repr__(self) -> str:
        return f"GitContributor(name={self.name}, email={self.email})"
    

def list_git_contributors(path: Path) -> Dict[GitContributor, int]:
    """
    List all git contributors in the current repository.
    """
    # Check if the path is a valid git repository
    if not path.is_dir():
        raise ValueError(f"Path {path} is not a valid directory.")
    if not (path / ".git").exists():
        raise ValueError(f"Path {path} is not a valid git repository.")

    change_dir = os.getcwd()
    try:
        os.chdir(path)
        # git shortlog -sne --all

        # Get the output of the git command
        try:
            output = subprocess.check_output(
                ["git", "shortlog", "-sne", "--all"], text=True
            )
        except subprocess.CalledProcessError as e:
            print(f"Error: {e}")
            return []
        except FileNotFoundError:
            print("Error: git command not found. Make sure git is installed.")
            return []
        except Exception as e:
            print(f"An unexpected error occurred: {e}")
            return []
        
        # Split the output into lines
        lines = output.strip().split("\n")

        # Parse the lines to extract contributors
        contributors = {}
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


def get_git_user_name(path: Path) -> Optional[str]:
    """
    Get the git user name from the git configuration.
    """

    if not path.is_dir():
        raise ValueError(f"Path {path} is not a valid directory.")
    if not (path / ".git").exists():
        raise ValueError(f"Path {path} is not a valid git repository.")

    change_dir = os.getcwd()
    try:
        os.chdir(path)
        name = subprocess.check_output(
            ["git", "config", "--get", "user.name"], text=True
        ).strip()
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
    

def get_git_user_email(path: Path) -> Optional[str]:
    """
    Get the git user email from the git configuration.
    """

    if not path.is_dir():
        raise ValueError(f"Path {path} is not a valid directory.")
    if not (path / ".git").exists():
        raise ValueError(f"Path {path} is not a valid git repository.")

    change_dir = os.getcwd()
    try:
        os.chdir(path)
        email = subprocess.check_output(
            ["git", "config", "--get", "user.email"], text=True
        ).strip()
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
    

def get_git_user() -> Optional[GitContributor]:
    """
    Get the git user name and email from the git configuration.
    """
    name = get_git_user_name()
    email = get_git_user_email()
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
    for project in config.defined_projects:
        path = project.path

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
            for contributor, commit_count in sorted(
                contributors.items(), key=lambda x: x[1], reverse=True
            ):
                print(f"{contributor}: {commit_count} commits")
        else:
            print(f"No contributors found in {path}.")

        print()
from typing import List, Dict, Any, Union

import git
import gitdb

def get_repository_changes(repo):
    """
    Get all changes in the repository including staged, unstaged and untracked files.
    Works for both repositories with and without commits.
    
    Args:
        repo: GitPython Repo object
    
    Returns:
        tuple: (staged_diffs, unstaged_diffs, untracked_files)
    """
    # Get untracked files first
    untracked_files = repo.untracked_files
    
    # Get staged changes
    staged_diffs = []
    try:
        if not repo.head.is_valid():
            # For new repositories without any commits
            staged_diffs = [item for item in repo.index.diff(None, create_patch=True)]
        else:
            # For repositories with commits
            staged_diffs = repo.index.diff('HEAD', create_patch=True)
    except (ValueError, gitdb.exc.BadName):
        # Fallback for any other edge cases
        staged_diffs = [item for item in repo.index.diff(None, create_patch=True)]

    
    # Get unstaged changes
    unstaged_diffs = repo.index.diff(None, create_patch=True)
    
    return staged_diffs, unstaged_diffs, untracked_files
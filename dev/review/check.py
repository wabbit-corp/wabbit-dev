from typing import List, Any, Dict, Tuple, Callable
import os
import re

import math

from dev.config import load_config, GradleProject
from dev.messages import error, info
from dev.io import walk_files, read_ignore_file
from pathlib import Path


##################################################################################################
# UUID/ULID checker
##################################################################################################

# "2ecbfb56-85d7-4e32-84cb-b2f175acf240"
UUID_PATTERN = re.compile(r"\"[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}\"")
# "01FY323KTHD29NRQC6D7BYBP51"
ULID_PATTERN = re.compile(r"\"01[A-Z0-9^LI]{23,25}\"")

SOURCE_FILE_EXTENSIONS = set([
    '.java', '.kt', '.kts', '.scala', '.groovy', '.gradle', '.clj', '.cljs', '.cljc', '.edn', '.yaml', '.yml', '.xml',
    '.json', '.properties', '.md', '.txt', '.sh', '.bat', '.cmd', '.ps1', '.py', '.rb', '.pl', '.php', '.c', '.cpp', '.h',
    '.hpp', '.cs', '.ts', '.js', '.html', '.css', '.scss', '.less', '.sass', '.php', '.php3', '.php4', '.php5', '.php7'])

IGNORE_FILES = set([
    '.DS_Store', 'Thumbs.db', 'desktop.ini'])

GRADLE_IGNORE_DIRS = set([
    '.gradle', '.idea'])

def check_unique_identifiers() -> None:
    config = load_config()

    seen_ulids: Dict[str, Tuple[str, int]] = {}
    seen_uuids: Dict[str, Tuple[str, int]] = {}

    def walk(base_path):
        for top_path, dirs, files in os.walk(base_path):
            # top_path_parts = os.path.normpath(top_path).split(os.sep)
            # if any(part in SKIP_DIR_NAMES for part in top_path_parts):
            #     continue

            for fn in files:
                path = os.path.join(top_path, fn)

                if not any(path.endswith(ext) for ext in SOURCE_FILE_EXTENSIONS):
                    continue

                # print(f"Checking {path}")
                with open(path, 'rt', encoding='utf-8') as fin:
                    for index, line in enumerate(fin):

                        for m in UUID_PATTERN.findall(line):
                            if m in seen_uuids:
                                other_path, other_line = seen_uuids[m]
                                print("COLLISION")
                                print(f'  at {path}:{index+1}')
                                print(f'  at {other_path}:{other_line+1}')
                            seen_uuids[m] = (path, index)

                        for m in ULID_PATTERN.findall(line):
                            if m in seen_ulids:
                                other_path, other_line = seen_ulids[m]
                                print("COLLISION")
                                print(f'  at {path}:{index+1}')
                                print(f'  at {other_path}:{other_line+1}')
                            seen_ulids[m] = (path, index)

    for name, project in config.defined_projects.items():
        if isinstance(project, GradleProject):
            walk(f'./{name}/src/main/scala/')
            walk(f'./{name}/src/main/kotlin/')
            walk(f'./{name}/src/main/java/')
            walk(f'./{name}/src/test/scala/')
            walk(f'./{name}/src/test/kotlin/')
            walk(f'./{name}/src/test/java/')

##################################################################################################
# High-entropy string search
##################################################################################################
BASE64_CHARS = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/="
HEX_CHARS    = "1234567890abcdefABCDEF"

TRUFFLEHOG_MIN_LENGTH = 20
b64_minimum = 4.5
hex_minimum = 3.0
verbose = True # Set to True for more detailed output

# Regex to find potential URLs. This is a common but not exhaustive pattern.
# It looks for common schemes or www. and captures characters typical in URLs.
URL_REGEX = re.compile(
    r"""\b((?:https?|ftp|file)://|www\.|ftp\.)[-a-zA-Z0-9+&@#/%?=~_|!:,.;]*[-a-zA-Z0-9+&@#/%=~_|]""", re.IGNORECASE)

# Regex for Base64 strings (at least TRUFFLEHOG_MIN_LENGTH long)
# Use re.escape to handle special characters like '+' and '/' in BASE64_CHARS
B64_REGEX = re.compile(f"[{re.escape(BASE64_CHARS)}]{{{TRUFFLEHOG_MIN_LENGTH},}}")

# Regex for Hex strings (at least TRUFFLEHOG_MIN_LENGTH long)
HEX_REGEX = re.compile(f"[{HEX_CHARS}]{{{TRUFFLEHOG_MIN_LENGTH},}}")

def check_overlap(secret_start: int, secret_end: int, url_spans: List[tuple[int, int]]) -> bool:
    """Check if the secret span overlaps with any of the URL spans."""
    for url_start, url_end in url_spans:
        # Check for any overlap:
        # Secret starts within URL OR URL starts within Secret
        if (url_start <= secret_start < url_end) or \
            (secret_start <= url_start < secret_end):
            return True
    return False

def shannon_entropy(data: str, iterator: str) -> float: # Changed type hint for data
    # import math # Already imported at top level
    """
    return the shannon entropy value for a given string (borrowed from trufflehog)
    Borrowed from http://blog.dkbza.org/2007/05/scanning-data-for-entropy-anomalies.html
    """
    if not data:
        return 0
    entropy: float = 0
    data_len = len(data) # Cache length
    for x in iterator:
        count = data.count(x) # Use str.count directly
        if count > 0:
            p_x = float(count)/data_len
            entropy += - p_x*math.log(p_x, 2)
    return entropy

def find_entropy(filename: Path):
    """
    Step through a file line by line, find potential secrets using regex,
    ignore those overlapping with URLs, and measure entropy of the rest.
    """
    strings_found = []  # store detected secrets (optional, maybe just use printable)
    line_counter = 0 # 1-based line number for reporting
    printable = [] # this will store the printable result

    try:
        with open(filename, 'rt', encoding='utf-8') as f:
            for line in f:
                line_counter += 1 # Increment line number at the start
                line = line.strip() # Keep stripped line for context if needed later
                original_line = line # Store original stripped line for output

                # 1. Find all URL spans in the current line
                url_spans = [(m.start(), m.end()) for m in URL_REGEX.finditer(line)]

                # 2. Find potential Base64 strings and check entropy if not in URL
                for match in B64_REGEX.finditer(line):
                    string = match.group(0)
                    start, end = match.span()

                    # 3. Check if this match overlaps with any found URL
                    if check_overlap(start, end, url_spans):
                        # print(f"Ignoring Base64 '{string}' as part of URL in line {line_counter}") # Debugging
                        continue # Skip this match, it's likely part of a URL

                    # 4. Calculate entropy only if it's not part of a URL
                    b64_entropy = shannon_entropy(string, BASE64_CHARS)

                    if b64_entropy > b64_minimum:
                        strings_found.append(string)
                        if verbose:
                            p = (f"\n-----------\nFile: {filename}\nLine: {line_counter}\nType: Base64\n"
                                    f"Shannon Entropy: {b64_entropy:.3f}\nSecret: {string}\nFull Line:\n\t{original_line}")
                        else:
                            p = f"{filename}:{line_counter}: {string}"
                        printable.append(p)

                # 5. Find potential Hex strings and check entropy if not in URL
                for match in HEX_REGEX.finditer(line):
                    string = match.group(0)
                    start, end = match.span()

                    # 6. Check if this match overlaps with any found URL
                    if check_overlap(start, end, url_spans):
                        # print(f"Ignoring Hex '{string}' as part of URL in line {line_counter}") # Debugging
                        continue # Skip this match, it's likely part of a URL

                    # 7. Calculate entropy only if it's not part of a URL
                    hex_entropy = shannon_entropy(string, HEX_CHARS)

                    if hex_entropy > hex_minimum:
                        strings_found.append(string)
                        if verbose:
                            p = (f"\n-----------\nFile: {filename}\nLine: {line_counter}\nType: HEX\n"
                                    f"Shannon Entropy: {hex_entropy:.3f}\nSecret: {string}\nFull Line:\n\t{original_line}")
                        else:
                            p = f"{filename}:{line_counter}: {string}"
                        printable.append(p)

        return printable
    except UnicodeDecodeError:
        # print(f"UnicodeDecodeError: {filename}") # Optional warning
        return []
    except FileNotFoundError:
        error(f"File not found: {filename}")
        return []
    except Exception as e:
        error(f"Error processing file {filename}: {e}")
        return []

def trufflehog() -> None:
    config = load_config()

    # --- Main loop remains similar ---
    final_err = False # Use a different variable name to avoid shadowing
    processed_files_with_secrets = set()

    for name, project in config.defined_projects.items():
        project_path = Path(project.path) # Ensure project path is a Path object
        ignore: Callable[[Path], bool]

        # Ensure ignore files are relative to the project path
        gitignore_path = project_path / '.gitignore'
        entropyignore_path = project_path / '.entropyignore'

        import pathspec

        # dir -> ignore list
        ignore_cache = {}
        # dir -> pathspec
        ignore_pathspec_cache = {}

        def get_ignore_set(path: Path) -> pathspec.PathSpec:
            assert path.is_dir(), f"Expected directory, got {path}"
            
            # Walk the path up to the project root
            # and build a pathspec for the ignore patterns

            if path in ignore_pathspec_cache:
                return ignore_pathspec_cache[path]
            if path in ignore_cache:
                return pathspec.PathSpec.from_lines(pathspec.patterns.GitWildMatchPattern, ignore_cache[path])
            
            current_path = path
            ignore_patterns = []
            while current_path != project_path:
                print(f"Checking {current_path} for ignore files") # Debugging
                # if current_path in ignore_cache:
                #     ignore_patterns.extend(ignore_cache[current_path])
                #     break
                # Check for .gitignore or .entropyignore
                if (current_path / '.gitignore').exists():
                    print(f"Found .gitignore at {current_path}") # Debugging
                    with open(current_path / '.gitignore', 'r') as f:
                        ignore_patterns.extend(f.readlines())
                if (current_path / '.entropyignore').exists():
                    print(f"Found .entropyignore at {current_path}")
                    with open(current_path / '.entropyignore', 'r') as f:
                        ignore_patterns.extend(f.readlines())
                
                # Move up the directory tree
                current_path = current_path.parent
                if current_path == current_path.parent:
                    break
            ignore_patterns = [i.strip() for i in ignore_patterns if i.strip() and not i.startswith("#")]
            ignore_cache[path] = ignore_patterns
            print(f"Ignore patterns for {path}: {ignore_patterns}") # Debugging
            ignore_pathspec = pathspec.PathSpec.from_lines(pathspec.patterns.GitWildMatchPattern, ignore_patterns)
            ignore_pathspec_cache[path] = ignore_pathspec
            return ignore_pathspec
        
        def combined_ignore(path: Path) -> bool:
            return get_ignore_set(path.parent).match_file(path.relative_to(project_path).as_posix())


        info(f'Checking {project_path} ({name})')
        found_secrets_in_project = False
        secrets_in_file = None # Track the last file with secrets found in this project

        for file in walk_files(project_path, predicate=lambda f: not combined_ignore(f)):
            # info(f"Checking {file}") # Can be noisy
            results = find_entropy(file)
            if results:
                for p in results:
                    error(p) # Print each found secret using error function
                found_secrets_in_project = True
                final_err = True # Set the overall error flag
                secrets_in_file = file # Record the file where secrets were found
                processed_files_with_secrets.add(file) # Add to set to avoid duplicate messages per file

        # Report only once per project if secrets were found
        if found_secrets_in_project and secrets_in_file:
             print(f"Found secrets in project '{name}'. Example file: {secrets_in_file}") # More informative message
             break

    # Final summary or exit based on final_err if needed
    if final_err:
        print(f"\nWarning: High entropy strings (potential secrets) found in {len(processed_files_with_secrets)} file(s).")
        # sys.exit(1) # Optional: exit with error code if secrets are found
#!/usr/bin/env bash
set -euo pipefail

repo_root="$(
  cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." >/dev/null 2>&1
  pwd
)"

python_bin="$repo_root/.venv/bin/python"
dev_py="$repo_root/dev.py"

if [[ ! -x "$python_bin" ]]; then
  echo "error: expected Python interpreter at $python_bin" >&2
  echo "Create or refresh the app-wabbit-dev virtualenv first." >&2
  exit 1
fi

if [[ ! -f "$dev_py" ]]; then
  echo "error: expected dev entrypoint at $dev_py" >&2
  exit 1
fi

pick_install_dir() {
  local candidate

  if [[ -n "${BIN_DIR:-}" ]]; then
    printf '%s\n' "$BIN_DIR"
    return 0
  fi

  for candidate in /opt/homebrew/bin /usr/local/bin "$HOME/.local/bin"; do
    if [[ ":$PATH:" == *":$candidate:"* ]] && [[ -d "$candidate" ]] && [[ -w "$candidate" ]]; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done

  IFS=':' read -r -a path_entries <<<"$PATH"
  for candidate in "${path_entries[@]}"; do
    [[ -z "$candidate" ]] && continue
    [[ "$candidate" == "~/"* ]] && candidate="$HOME/${candidate#~/}"
    if [[ -d "$candidate" ]] && [[ -w "$candidate" ]]; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done

  printf '%s\n' "$HOME/.local/bin"
}

install_dir="$(pick_install_dir)"
mkdir -p "$install_dir"

wabbit_dev_path="$install_dir/wabbit-dev"
dev_path="$install_dir/dev"

cat >"$wabbit_dev_path" <<EOF
#!/bin/sh
exec "$python_bin" "$dev_py" "\$@"
EOF

chmod +x "$wabbit_dev_path"
ln -sfn "$wabbit_dev_path" "$dev_path"

echo "Installed wrappers:"
echo "  $wabbit_dev_path"
echo "  $dev_path -> $wabbit_dev_path"

if [[ ":$PATH:" != *":$install_dir:"* ]]; then
  echo
  echo "warning: $install_dir is not currently on PATH" >&2
  echo "Add it to PATH before using dev or wabbit-dev." >&2
fi

echo
echo "Smoke test examples:"
echo "  dev where"
echo "  wabbit-dev where"
echo
echo "This install is tied to:"
echo "  $repo_root"

#!/usr/bin/env bash
# Runtime helper functions for the backend artifact manifest. scripts/manifest.sh
# remains the single source of truth; this file only turns that manifest into
# backup/deploy/restore operations.

_RUNTIME_MANIFEST_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=manifest.sh
source "${_RUNTIME_MANIFEST_DIR}/manifest.sh"

BACKEND_RUNTIME_ENTRIES=("__init__.py" "main.py")
BACKEND_RUNTIME_ENTRIES+=("${BACKEND_PY_LIBS[@]}")
BACKEND_RUNTIME_ENTRIES+=("${BACKEND_CORE_DIR}/")
BACKEND_RUNTIME_ENTRIES+=("${BACKEND_JS_FILES[@]}")

backend_runtime_manifest_print() {
  printf '%s\n' "${BACKEND_RUNTIME_ENTRIES[@]}"
}

_manifest_norm_entry() {
  local entry="$1"
  printf '%s' "${entry%/}"
}

backend_runtime_backup() {
  local serving_dir="$1"
  local backup_dir="$2"
  local backup_backend_dir="${backup_dir}/backend_runtime"

  rm -rf "$backup_backend_dir"
  mkdir -p "${backup_backend_dir}/.absent"
  backend_runtime_manifest_print > "${backup_backend_dir}/.manifest"

  local entry norm src dst marker
  for entry in "${BACKEND_RUNTIME_ENTRIES[@]}"; do
    norm="$(_manifest_norm_entry "$entry")"
    src="${serving_dir}/${norm}"
    dst="${backup_backend_dir}/${norm}"
    marker="${backup_backend_dir}/.absent/${norm}"

    if [[ -d "$src" ]]; then
      mkdir -p "$dst"
      rsync -a --delete "${src}/" "${dst}/"
    elif [[ -f "$src" ]]; then
      mkdir -p "$(dirname "$dst")"
      cp "$src" "$dst"
    else
      mkdir -p "$(dirname "$marker")"
      touch "$marker"
    fi
  done
}

backend_runtime_deploy() {
  local repo_backend_dir="$1"
  local serving_dir="$2"

  local entry norm src dst
  for entry in "${BACKEND_RUNTIME_ENTRIES[@]}"; do
    norm="$(_manifest_norm_entry "$entry")"
    src="${repo_backend_dir}/${norm}"
    dst="${serving_dir}/${norm}"

    if [[ -d "$src" ]]; then
      rm -rf "$dst"
      mkdir -p "$dst"
      rsync -a --delete "${src}/" "${dst}/"
    elif [[ -f "$src" ]]; then
      mkdir -p "$(dirname "$dst")"
      cp "$src" "$dst"
    else
      echo "ОШИБКА: runtime manifest entry отсутствует в repo backend: $src" >&2
      return 1
    fi
  done
}

backend_runtime_restore() {
  local backup_dir="$1"
  local serving_dir="$2"
  local backup_backend_dir="${backup_dir}/backend_runtime"
  local manifest="${backup_backend_dir}/.manifest"

  if [[ ! -f "$manifest" ]]; then
    echo "ОШИБКА: нет runtime manifest в backup: $manifest" >&2
    return 1
  fi

  local entry norm src dst marker
  while IFS= read -r entry; do
    [[ -z "$entry" ]] && continue
    norm="$(_manifest_norm_entry "$entry")"
    src="${backup_backend_dir}/${norm}"
    dst="${serving_dir}/${norm}"
    marker="${backup_backend_dir}/.absent/${norm}"

    if [[ -e "$marker" && ! -e "$src" ]]; then
      rm -rf "$dst"
    elif [[ -d "$src" ]]; then
      rm -rf "$dst"
      mkdir -p "$dst"
      rsync -a --delete "${src}/" "${dst}/"
    elif [[ -f "$src" ]]; then
      mkdir -p "$(dirname "$dst")"
      cp "$src" "$dst"
    else
      echo "ОШИБКА: backup не содержит runtime entry и absent-marker: $entry" >&2
      return 1
    fi
  done < "$manifest"
}

backend_runtime_syntax_check() {
  local backend_dir="$1"
  local py_files=()
  local js_files=()
  local entry norm path f

  for entry in "${BACKEND_RUNTIME_ENTRIES[@]}"; do
    norm="$(_manifest_norm_entry "$entry")"
    path="${backend_dir}/${norm}"
    if [[ -d "$path" ]]; then
      while IFS= read -r -d '' f; do
        case "$f" in
          *.py) py_files+=("$f") ;;
          *.js) js_files+=("$f") ;;
        esac
      done < <(find "$path" -type f \( -name '*.py' -o -name '*.js' \) -print0)
    elif [[ -f "$path" ]]; then
      case "$path" in
        *.py) py_files+=("$path") ;;
        *.js) js_files+=("$path") ;;
      esac
    fi
  done

  if [[ ${#py_files[@]} -gt 0 ]]; then
    python3 -m py_compile "${py_files[@]}"
  fi
  if [[ ${#js_files[@]} -gt 0 ]]; then
    local js
    for js in "${js_files[@]}"; do
      node --check "$js"
    done
  fi
}

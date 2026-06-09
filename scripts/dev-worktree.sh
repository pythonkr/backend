#!/usr/bin/env bash
# Spin up / tear down a per-branch git worktree with its own Postgres DB
# so multiple branches can run migrations & tests without colliding.
#
#   scripts/dev-worktree.sh add <branch> [worktree-dir]
#   scripts/dev-worktree.sh remove <worktree-dir>
#
# Reads envfile/.env.local for Postgres credentials; the new worktree
# gets a copy with only DATABASE_NAME rewritten.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_REL="envfile/.env.local"
SRC_ENV="$REPO_ROOT/$ENV_REL"

usage() {
  awk 'NR>1 && /^[^#]/ {exit} NR>1 {sub(/^# ?/, ""); print}' "$0"
  exit "${1:-0}"
}

die() { echo "error: $*" >&2; exit 1; }

load_db_env() {
  local f="$1"
  [ -f "$f" ] || die "env file not found: $f"
  unset DB_HOST DB_PORT DB_USER DB_PASSWORD DB_NAME
  local key val
  while IFS='=' read -r key val; do
    case "$key" in
      DATABASE_HOST)     DB_HOST="$val" ;;
      DATABASE_PORT)     DB_PORT="$val" ;;
      DATABASE_USER)     DB_USER="$val" ;;
      DATABASE_PASSWORD) DB_PASSWORD="$val" ;;
      DATABASE_NAME)     DB_NAME="$val" ;;
    esac
  done < "$f"
  local v
  for v in DB_HOST DB_PORT DB_USER DB_PASSWORD DB_NAME; do
    [ -n "${!v:-}" ] || die "$f: missing DATABASE_${v#DB_}"
  done
}

pg() {
  PGPASSWORD="$DB_PASSWORD" "$1" -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" "${@:2}"
}

sanitize() {
  printf '%s' "$1" | tr '[:upper:]' '[:lower:]' \
    | sed -E 's/[^a-z0-9]+/_/g; s/^_+|_+$//g'
}

cmd_add() {
  local branch="${1:-}"; [ -n "$branch" ] || usage 1
  local slug; slug=$(sanitize "$branch")
  local wt_dir="${2:-$REPO_ROOT/.worktrees/$slug}"

  load_db_env "$SRC_ENV"
  # PG identifier limit is 63 chars; pytest-django auto-creates test_<dbname>,
  # so reserve 5 more for that prefix.
  local db_prefix="${DB_NAME}__"
  local max_db_slug=$((63 - 5 - ${#db_prefix}))
  [ "$max_db_slug" -ge 10 ] \
    || die "DATABASE_NAME '$DB_NAME' leaves <10 chars for a worktree slug"
  local db_slug="$slug"
  if [ "${#db_slug}" -gt "$max_db_slug" ]; then
    local hash; hash=$(printf '%s' "$branch" | shasum | cut -c1-6)
    db_slug="${db_slug:0:$((max_db_slug - 7))}_${hash}"
  fi
  local new_db="${db_prefix}${db_slug}"
  [ "$new_db" != "$DB_NAME" ] || die "computed db name collides with source"

  echo "→ worktree dir : $wt_dir"
  echo "→ branch       : $branch"
  echo "→ database     : $new_db"
  [ "$db_slug" = "$slug" ] \
    || echo "  (slug truncated for PG 63-char limit: $slug → $db_slug)"

  if [ -d "$wt_dir" ]; then
    echo "  worktree dir already exists — skipping git worktree add"
  elif git -C "$REPO_ROOT" show-ref --verify --quiet "refs/heads/$branch"; then
    git -C "$REPO_ROOT" worktree add "$wt_dir" "$branch"
  else
    git -C "$REPO_ROOT" worktree add -b "$branch" "$wt_dir"
  fi

  local new_env="$wt_dir/$ENV_REL"
  mkdir -p "$(dirname "$new_env")"
  awk -v line="DATABASE_NAME=$new_db" '
    /^DATABASE_NAME=/ { print line; seen=1; next }
    { print }
    END { if (!seen) print line }
  ' "$SRC_ENV" > "$new_env"

  # pytest-django will derive test_<name> on first run
  local err
  if err=$(pg createdb "$new_db" 2>&1); then
    echo "  created db $new_db"
  elif printf '%s' "$err" | grep -q "already exists"; then
    echo "  db $new_db already exists — skipping createdb"
  else
    printf '%s\n' "$err" >&2
    exit 1
  fi

  cat <<EOF

next:
  cd "$wt_dir"
  uv sync
  uv run python app/manage.py migrate
  uv run pytest        # will auto-create test_$new_db
EOF
}

cmd_remove() {
  local wt_dir="${1:-}"; [ -n "$wt_dir" ] || usage 1
  [ -d "$wt_dir" ] || die "not a directory: $wt_dir"
  local wt_env="$wt_dir/$ENV_REL"

  load_db_env "$SRC_ENV"
  local src_host="$DB_HOST" src_port="$DB_PORT" src_user="$DB_USER" src_db="$DB_NAME"
  load_db_env "$wt_env"
  [ "$DB_HOST:$DB_PORT:$DB_USER" = "$src_host:$src_port:$src_user" ] \
    || die "worktree Postgres ($DB_HOST:$DB_PORT/$DB_USER) differs from source; refusing"
  [ "$DB_NAME" != "$src_db" ] || die "worktree db equals source db ($src_db); refusing"

  echo "→ drop db      : $DB_NAME (+ test_$DB_NAME)"
  echo "→ remove wt    : $wt_dir"
  read -r -p "proceed? [y/N] " ans
  [ "$ans" = "y" ] || [ "$ans" = "Y" ] || { echo "aborted"; exit 0; }

  pg dropdb --if-exists "$DB_NAME"
  pg dropdb --if-exists "test_$DB_NAME"
  # --force: envfile/.env.local is tracked but rewritten with a per-worktree
  # DATABASE_NAME on add, and the tree may contain .venv/__pycache__/coverage
  # artifacts. The y/N prompt above is the safety gate.
  git -C "$REPO_ROOT" worktree remove --force "$wt_dir"
}

main() {
  local sub="${1:-}"; shift || true
  case "$sub" in
    add)         cmd_add "$@" ;;
    remove|rm)   cmd_remove "$@" ;;
    -h|--help|"") usage 0 ;;
    *) usage 1 ;;
  esac
}

main "$@"

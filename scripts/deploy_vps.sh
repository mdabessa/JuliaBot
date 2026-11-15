#!/usr/bin/env bash
#
# Deploy JuliaBot on the VPS.
#
# Installed as /usr/local/bin/juliabot-deploy, this is the forced command of a
# restricted SSH key, so CI can run this and nothing else on the host:
#
#     ssh deploy@host "juliabot-deploy sha-1a2b3c4"
#
# APP_DIR is a clone of the repository (compose.yml at its root) with an
# untracked .env beside it. It has no default: it is set in
# /etc/default/juliabot-deploy, because deploying in the wrong directory is
# worse than refusing to deploy.
#
# Overrides: APP_DIR, HEALTH_TIMEOUT, AUTO_ROLLBACK (set 0 to disable).

set -euo pipefail

log() { printf '%s juliabot-deploy: %s\n' "$(date -Is)" "$*" >&2; }

# Host-specific settings live outside the repository so this script stays
# generic. The file must be root-owned and not writable by the deploy user.
if [ -r /etc/default/juliabot-deploy ]; then
  set -a
  # shellcheck disable=SC1091
  . /etc/default/juliabot-deploy
  set +a
fi

# Required, never defaulted: deploying in the wrong directory is worse than
# failing here.
APP_DIR="${APP_DIR:-}"
HEALTH_TIMEOUT="${HEALTH_TIMEOUT:-180}"
AUTO_ROLLBACK="${AUTO_ROLLBACK:-1}"

previous=""
if [ -n "$APP_DIR" ] && [ -f "$APP_DIR/.deployed_tag" ]; then
  previous="$(awk 'NR == 1 {print $2}' "$APP_DIR/.deployed_tag")"
fi

fail() {
  log "ERROR: $*"
  if [ -n "$previous" ]; then
    log "the previous tag was '$previous'; roll back with: juliabot-deploy $previous"
  fi
  exit 1
}
trap 'fail "unexpected failure on line $LINENO"' ERR

# Re-exec from a copy, because the git sync below can rewrite this file while
# bash is still reading it.
if [ -z "${JULIABOT_DEPLOY_REEXEC:-}" ]; then
  self="$(mktemp /tmp/juliabot-deploy.XXXXXXXX)"
  cp "$0" "$self"
  chmod 700 "$self"
  JULIABOT_DEPLOY_REEXEC=1 exec "$self" "$@"
fi

TAG=""
if [ "$#" -gt 0 ]; then
  TAG="${!#}"
elif [ -n "${SSH_ORIGINAL_COMMAND:-}" ]; then
  # A forced command does not receive arguments; sshd passes the requested
  # command line in SSH_ORIGINAL_COMMAND instead.
  # shellcheck disable=SC2086
  set -- $SSH_ORIGINAL_COMMAND
  if [ "$#" -gt 0 ]; then
    TAG="${!#}"
  fi
fi

# Validated before it reaches compose as an image tag.
[[ "$TAG" =~ ^(latest|sha-[0-9a-f]{7})$ ]] ||
  fail "expected an image tag such as 'sha-1a2b3c4', got '${TAG}'"

[ -n "$APP_DIR" ] ||
  fail "APP_DIR is not set; define it in /etc/default/juliabot-deploy"
[ -d "$APP_DIR" ] || fail "APP_DIR '$APP_DIR' is not a directory"
cd "$APP_DIR"

exec 9>"$APP_DIR/.deploy.lock"
flock -n 9 || fail "another deploy is already running"

log "syncing $APP_DIR to origin/main"
git fetch --quiet origin main || fail "git fetch failed"
git reset --quiet --hard FETCH_HEAD || fail "git reset failed"

# The compose file is part of the repository, so deployments cannot drift from
# what the repo declares.
[ -f compose.yml ] || fail "compose.yml is missing from $APP_DIR"

compose() { docker compose "$@"; }

# Bring a tag up and wait for the bot's own ready log line. Process state is not
# enough: a container that crashes on startup reports "running" for a moment and
# "restarting" after that, because of restart: unless-stopped.
start_bot() {
  local tag="$1" started cid status logged deadline
  export JULIABOT_TAG="$tag"

  log "recreating the bot container from $tag"
  started="$(date +%s)"
  compose up -d --no-deps --force-recreate juliabot || return 1

  cid="$(compose ps -q juliabot)"
  [ -n "$cid" ] || { log "no container found for service juliabot"; return 1; }

  deadline=$((SECONDS + HEALTH_TIMEOUT))
  while [ "$SECONDS" -lt "$deadline" ]; do
    status="$(docker inspect -f '{{.State.Status}}' "$cid" 2>/dev/null || echo missing)"
    case "$status" in
      running)
        logged="$(docker logs --since "$started" "$cid" 2>&1 || true)"
        if printf '%s' "$logged" | grep -q "Bot já esta ativo!"; then
          log "another instance still holds the heartbeat row"
          return 1
        fi
        if printf '%s' "$logged" | grep -q "Pronto!"; then
          return 0
        fi
        ;;
      exited | dead | restarting)
        docker logs --tail 60 "$cid" >&2 || true
        log "the container is '$status' during startup"
        return 1
        ;;
    esac
    sleep 2
  done

  docker logs --tail 60 "$cid" >&2 || true
  log "the bot was not ready after ${HEALTH_TIMEOUT}s"
  return 1
}

export JULIABOT_TAG="$TAG"

# Pull first, so a tag that does not exist fails before the running bot is
# touched.
log "pulling $TAG"
compose pull --quiet juliabot ||
  fail "docker pull failed for $TAG (can this host read the GHCR package? see README)"

# Migrations run against the running database before the bot is recreated, so a
# broken migration fails the deploy with the old bot still serving.
log "applying schema migrations with $TAG"
compose run --rm --no-deps juliabot python -m juliabot.migrations upgrade ||
  fail "migrations failed; the running bot was left untouched"

if start_bot "$TAG"; then
  printf 'deployed %s %s\n' "$TAG" "$(date -Is)" >"$APP_DIR/.deployed_tag"
  log "deployed $TAG successfully"
  exit 0
fi

# Rollback assumes an expand-only schema, which is what this repository uses.
# A destructive migration would need AUTO_ROLLBACK=0 and a manual restore.
if [ "$AUTO_ROLLBACK" = "1" ] && [ -n "$previous" ] && [ "$previous" != "$TAG" ]; then
  rolled_back="$previous"
  log "deploy of $TAG failed; rolling back to $rolled_back"
  if start_bot "$rolled_back"; then
    # Already rolled back, so the generic "roll back with" hint would mislead.
    previous=""
    fail "deploy of $TAG failed and was rolled back to $rolled_back"
  fi
  fail "deploy of $TAG failed and the rollback to $rolled_back also failed"
fi

fail "deploy of $TAG failed"

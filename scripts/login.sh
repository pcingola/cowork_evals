#!/usr/bin/env bash
#
# Log in to Claude Code once, in a container, for the login this package owns.
#
# A wrapper over `cowork_evals login --docker`. The verb owns the conditions, the messages
# and the exit codes; this passes its arguments through and adds nothing. See docs/cli.md.
#
# A host on `docker.credential: bedrock` has no login to make, and the verb refuses there.
# See docs/docker.md.
#
#   (no args)     log in, or report the login already there
#   --check       report whether a login is present, no writes
#   --force       log in again over a login that is already there
#
# It needs a terminal and a browser. Run it before the integration tier: those tests read
# the credential and never create one.
set -euo pipefail
# shellcheck source=lib.sh
. "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
need uv
need docker

case "${1-}" in
  "" | --check | --force) ;;
  -h | --help) usage ;;
  *) die "unknown argument '$1' (expected --check, --force or none)" ;;
esac

exec uv run --project "$ROOT" cowork_evals login --docker "$@"

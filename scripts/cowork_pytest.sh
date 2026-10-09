#!/usr/bin/env bash
#
# Build and verify the test image, cowork-evals-test:<digest>, and run a consumer's
# pytest suite inside it.
#
# It is scripts/image.sh for the image pytest runs in: the eval image plus pytest and
# the four packages it needs. The digest covers the base image's digest too, so a
# rebuilt base is a different tag. See docs/cowork_test.md.
#
#   (no args)            build the image for docker.platform
#   --check              verify the current digest is present, no writes
#   --recreate           build with --no-cache
#   <path> [-- <args>]   run pytest over <path> in the container, <args> appended
#
# The exit code of a run is pytest's, unchanged. Nothing is added to the pytest
# command line: whatever `pytest <path>` does on a laptop is what it does here.
set -euo pipefail
# shellcheck source=lib.sh
. "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
need uv
need docker

build() {
  exec uv run --project "$ROOT" python3 -c "
from cowork_evals.docker.pytest_image import PytestImage

image = PytestImage()
print(f'building {image.tag} over {image.docker.tag} for {image.platform}')
image.build(no_cache=$1)
print(f'OK: {image.tag}')
"
}

# The unmet condition, or nothing. check() reports at most one, each carrying the
# command that fixes it.
unmet() {
  uv run --project "$ROOT" python3 -c "
from cowork_evals.docker.pytest_image import PytestImage

print('\n'.join(line.message for line in PytestImage().check()), end='')
"
}

case "${1-}" in
  "") build False ;;
  --recreate) build True ;;
  --check)
    UNMET="$(unmet)"
    [ -z "$UNMET" ] || die "$UNMET"
    exec uv run --project "$ROOT" python3 -c "
from cowork_evals.docker.pytest_image import PytestImage

print(f'OK: {PytestImage().tag} is present')
"
    ;;
  -h | --help) usage ;;
  -*) die "unknown argument '$1' (expected --check, --recreate, a path or none)" ;;
esac

TARGET="$1"
shift
if [ "$#" -gt 0 ]; then
  [ "$1" = "--" ] || die "unexpected argument '$1' (a pytest tail follows --)"
  shift
fi

UNMET="$(unmet)"
[ -z "$UNMET" ] || die "$UNMET"

exec uv run --project "$ROOT" python3 - "$TARGET" "$@" << 'PY'
import sys

from cowork_evals.docker.pytest_image import PytestImage

sys.exit(PytestImage().run(sys.argv[1], pytest_args=tuple(sys.argv[2:])))
PY

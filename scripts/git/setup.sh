#!/bin/bash
# One-time git setup for this repository.
#
# `.gitattributes` alone does not enable a merge driver: the driver's command
# lives in .git/config, which is not versioned.  Without this step git ignores
# the `merge=buildnumber` attribute and web/BUILD_NUMBER conflicts as before.
# The failure direction is safe -- an unconfigured clone conflicts exactly like
# it always did, it never produces a wrong merge -- but the conflict is the
# whole reason this driver exists.
#
# Worktrees share .git/config, so running this once covers every worktree of
# this repository.  A fresh clone starts unconfigured and needs it again.
set -eu

common_dir=$(git rev-parse --git-common-dir)
case "$common_dir" in
	/*) ;;
	*) common_dir="$(pwd)/$common_dir" ;;
esac
# Anchor the driver in the main checkout, not in whichever worktree happens to
# run this: linked worktrees get deleted, and a dangling driver path silently
# brings the conflicts back.  Before this branch is merged the main checkout has
# no copy yet, so fall back to this script's own directory and say so.
main_checkout=$(cd "$common_dir/.." && pwd)
here=$(cd "$(dirname "$0")" && pwd)
driver="$main_checkout/scripts/git/build-number-merge.sh"
if [ ! -x "$driver" ]; then
	driver="$here/build-number-merge.sh"
	echo "setup.sh: main checkout has no driver yet; anchoring to $here" >&2
	echo "setup.sh: re-run this from the main checkout once the branch is merged" >&2
fi

if [ ! -x "$driver" ]; then
	echo "setup.sh: driver not found or not executable: $driver" >&2
	exit 1
fi

git config merge.buildnumber.name 'keep the larger web/BUILD_NUMBER'
git config merge.buildnumber.driver "$driver %A %O %B"

echo "configured merge.buildnumber.driver = $driver %A %O %B"
echo "verify with: git config --get merge.buildnumber.driver"

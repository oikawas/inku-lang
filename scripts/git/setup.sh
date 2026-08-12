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

# Deliberately no `merge.buildnumber.name`.  With a name but no driver git does
# not fall back to the text merge -- it aborts the whole merge with
# "fatal: custom merge driver buildnumber lacks command line" (measured
# 2026-08-01).  With neither key set, the attribute names an unknown driver and
# git quietly does what it did before this branch.  Keeping only the driver key
# means every way of losing the configuration fails in the safe direction.
git config --unset merge.buildnumber.name 2>/dev/null || true
git config merge.buildnumber.driver "$driver %A %O %B"

echo "configured merge.buildnumber.driver = $driver %A %O %B"
echo "verify with: git config --get merge.buildnumber.driver"

# --- pre-commit secret guard (ledger I-193) -------------------------------
#
# `add -f` is the only way to put anything under `no-git-sync/` into the
# private overlay, and `-f` is exactly the flag that disables every exclude
# rule.  A guard therefore has to sit after the index.  Installed here rather
# than kept by hand because a hand-placed hook lives in .git/hooks, which is
# not versioned: re-clone the repository and the guard is gone with no sign
# that it ever existed.
#
# The hook is a two-line wrapper that execs the versioned guard, so the rules
# live in exactly one file and never go stale in one repository while the other
# is current.  The wrapper, not a symlink, because git does NOT fail a commit
# when the hook cannot be run: measured 2026-08-12, a dangling symlink at
# .git/hooks/pre-commit let a commit through silently.  A guard that disappears
# without a sound is the failure this whole step exists to prevent, so the
# wrapper checks the target itself and refuses the commit when it is gone.
# Hooks live in the common dir, so one install covers every worktree.
guard="$main_checkout/no-git-sync/scripts/inku-local-pre-commit.py"
[ -f "$guard" ] || guard="$here/../../no-git-sync/scripts/inku-local-pre-commit.py"

if [ ! -d "$main_checkout/no-git-sync" ] && [ ! -d "$here/../../no-git-sync" ]; then
	# A public clone has no `no-git-sync/` at all -- the guard is versioned in
	# the private overlay only.  Nothing is missing, so say nothing.
	:
elif [ ! -f "$guard" ]; then
	echo "setup.sh: secret guard not found, skipped: $guard" >&2
else
	chmod +x "$guard"
	guard=$(cd "$(dirname "$guard")" && pwd)/$(basename "$guard")

	install_guard() {
		hooks_dir=$1
		[ -d "$hooks_dir" ] || { echo "setup.sh: no hooks dir, skipped: $hooks_dir" >&2; return 0; }
		target="$hooks_dir/pre-commit"
		if [ -e "$target" ] || [ -L "$target" ]; then
			# Never clobber a hook this script did not write.
			if ! grep -q "inku-secret-guard" "$target" 2>/dev/null; then
				echo "setup.sh: a different pre-commit hook is already there, left alone: $target" >&2
				return 0
			fi
			rm -f "$target"
		fi
		cat > "$target" <<-EOF
			#!/bin/sh
			# inku-secret-guard v1 -- written by scripts/git/setup.sh (ledger I-193)
			# Rules live in the target, not here.  Re-run setup.sh if the checkout moves.
			guard="$guard"
			if [ ! -f "\$guard" ]; then
				echo "pre-commit: 番人が見つからない: \$guard" >&2
				echo "pre-commit: commit を中止した。scripts/git/setup.sh を回し直すこと。" >&2
				exit 1
			fi
			exec python3 "\$guard" "\$@"
		EOF
		chmod +x "$target"
		echo "installed secret guard: $target -> $guard"
	}

	install_guard "$common_dir/hooks"
	install_guard "$HOME/.inku-local.git/hooks"
	echo "verify with: ls -l \"$common_dir/hooks/pre-commit\" \"\$HOME/.inku-local.git/hooks/pre-commit\""
fi

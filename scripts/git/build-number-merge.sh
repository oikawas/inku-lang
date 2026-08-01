#!/bin/bash
# Merge driver for web/BUILD_NUMBER: keep the numerically larger side.
# BUILD_NUMBER is a shared counter, so "both sides bumped it" is never a real
# disagreement -- the larger number is always the answer.
# $1=%A (ours, and the output path)  $2=%O (base)  $3=%B (theirs)
ours=$(tr -dc '0-9' < "$1"); theirs=$(tr -dc '0-9' < "$3")
if [ "${theirs:-0}" -gt "${ours:-0}" ]; then
	printf '%s\n' "$theirs" > "$1"
else
	printf '%s\n' "${ours:-0}" > "$1"
fi
exit 0

#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROMPTS_FILE="${PROMPTS_FILE:-}"
OUT_DIR="${OUT_DIR:-/tmp/inku-headless}"
BATCH_ID="${BATCH_ID:-batch-$(date +%Y%m%d-%H%M%S)}"
RUN_PREFIX="${RUN_PREFIX:-compare}"
BATCH_RETRIES="${BATCH_RETRIES:-1}"
PNG_REVIEW="${PNG_REVIEW:-true}"
PNG_SIZE="${PNG_SIZE:-1024}"

if [[ -z "$PROMPTS_FILE" ]]; then
  echo "PROMPTS_FILE is required." >&2
  exit 2
fi
if [[ ! -f "$PROMPTS_FILE" ]]; then
  echo "PROMPTS_FILE does not exist: $PROMPTS_FILE" >&2
  exit 2
fi

batch_dir="$OUT_DIR/$BATCH_ID"
mkdir -p "$batch_dir"
cp "$PROMPTS_FILE" "$batch_dir/prompts.txt"

index=0
while IFS= read -r prompt || [[ -n "$prompt" ]]; do
  [[ -z "$prompt" ]] && continue
  index=$((index + 1))
  run_id="${RUN_PREFIX}-$(printf '%03d' "$index")"
  echo "[$index] $prompt"
  attempt=0
  success=0
  while [[ "$attempt" -le "$BATCH_RETRIES" ]]; do
    log_suffix=""
    if [[ "$attempt" -gt 0 ]]; then
      log_suffix=".retry-$attempt"
      echo "[$index] retry $attempt"
    fi
    if TEXT="$prompt" RUN_ID="$run_id" OUT_DIR="$batch_dir" "$SCRIPT_DIR/headless_render_compare.sh" \
      > "$batch_dir/$run_id$log_suffix.log" < /dev/null; then
      success=1
      break
    fi
    attempt=$((attempt + 1))
  done
  if [[ "$success" -ne 1 ]]; then
    mkdir -p "$batch_dir/$run_id"
    jq -n \
      --arg run_id "$run_id" \
      --arg prompt "$prompt" \
      --arg out_dir "$batch_dir/$run_id" \
      --arg log "$batch_dir/$run_id.retry-$BATCH_RETRIES.log" \
      '{
        run_id: $run_id,
        out_dir: $out_dir,
        prompt: $prompt,
        status: "error",
        error_log: $log,
        android: null,
        web: null,
        same_render_hash: false,
        same_ddl: false
      }' > "$batch_dir/$run_id/summary.json"
  fi
done < "$PROMPTS_FILE"

if [[ "$index" -eq 0 ]]; then
  echo "PROMPTS_FILE contains no non-empty prompts." >&2
  exit 2
fi

jq -s \
  --arg batch_id "$BATCH_ID" \
  --arg batch_dir "$batch_dir" \
  '{
    batch_id: $batch_id,
    out_dir: $batch_dir,
    count: length,
    success_count: map(select(.status != "error")) | length,
    error_count: map(select(.status == "error")) | length,
    same_render_hash_count: map(select(.same_render_hash == true)) | length,
    same_ddl_count: map(select(.same_ddl == true)) | length,
    items: map({
      run_id,
      status: (.status // "ok"),
      android_short: .android.short,
      server_short: .web.short,
      android_history_id: .android.history_id,
      server_history_id: .web.history_id,
      android_catalog_id: .android.render_color_catalog_id,
      png_review: .png_review,
      same_render_hash,
      same_ddl,
      android_ddl: .android.ddl,
      server_ddl: .web.ddl,
      error_log
    })
  }' "$batch_dir"/*/summary.json > "$batch_dir/batch-summary.json"

cat "$batch_dir/batch-summary.json"

if [[ "$PNG_REVIEW" == "true" || "$PNG_REVIEW" == "1" ]]; then
  CLI_DIR="${CLI_DIR:-$(cd "$SCRIPT_DIR/../.." && pwd)/cli}"
  (
    cd "$CLI_DIR"
    UV_CACHE_DIR="${UV_CACHE_DIR:-/tmp/inku-uv-cache}" \
    UV_PYTHON_INSTALL_DIR="${UV_PYTHON_INSTALL_DIR:-$HOME/.local/share/uv/python}" \
    uv run python ../android/scripts/render_png_review.py "$batch_dir" --batch --size "$PNG_SIZE"
  ) > "$batch_dir/png-review-output.json"
fi

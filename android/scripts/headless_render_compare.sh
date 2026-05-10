#!/usr/bin/env bash
set -euo pipefail

APP_ID="${APP_ID:-app.inku.mobile}"
DEVICE="${ANDROID_SERIAL:-}"
WEB_BASE_URL="${WEB_BASE_URL:-http://127.0.0.1:5173}"
OUT_DIR="${OUT_DIR:-/tmp/inku-headless}"
RUN_ID="${RUN_ID:-run-$(date +%Y%m%d-%H%M%S)}"
TEXT="${TEXT:-}"
TEXT_FILE="${TEXT_FILE:-}"
INPUT_MODE="${INPUT_MODE:-paint}"
ORIGINAL_TEXT="${ORIGINAL_TEXT:-}"
STAGE1_MODEL="${STAGE1_MODEL:-}"
STAGE2_MODEL="${STAGE2_MODEL:-}"
CATALOG_ID="${CATALOG_ID:-}"
CANVAS_ASPECT="${CANVAS_ASPECT:-}"
AUTO_REPAIR="${AUTO_REPAIR:-true}"
SAVE_HISTORY="${SAVE_HISTORY:-false}"
HEADLESS_AUTH_TOKEN="${HEADLESS_AUTH_TOKEN:-}"
COMPARE_WEB="${COMPARE_WEB:-1}"
CLI_SAVE_HISTORY="${CLI_SAVE_HISTORY:-true}"
CLI_DIR="${CLI_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)/cli}"
INKU_CLI_TIMEOUT_SECONDS="${INKU_CLI_TIMEOUT_SECONDS:-600}"
PNG_REVIEW="${PNG_REVIEW:-true}"
PNG_SIZE="${PNG_SIZE:-1024}"

adb_cmd=(adb)
if [[ -n "$DEVICE" ]]; then
  adb_cmd+=( -s "$DEVICE" )
fi

if [[ -z "$TEXT" && -n "$TEXT_FILE" ]]; then
  TEXT="$(cat "$TEXT_FILE")"
fi
if [[ -z "$TEXT" ]]; then
  echo "TEXT or TEXT_FILE is required." >&2
  exit 2
fi

mkdir -p "$OUT_DIR/$RUN_ID/android" "$OUT_DIR/$RUN_ID/web"

start_args=(
  shell am start -W
  -n "$APP_ID/.HeadlessRenderActivity"
  --es run_id "$RUN_ID"
  --es input_mode "$INPUT_MODE"
  --ez auto_repair "$AUTO_REPAIR"
  --ez save_history "$SAVE_HISTORY"
)

if [[ -z "$HEADLESS_AUTH_TOKEN" ]]; then
  HEADLESS_AUTH_TOKEN="$("${adb_cmd[@]}" exec-out run-as "$APP_ID" cat "files/headless-auth-token" 2>/dev/null || true)"
  HEADLESS_AUTH_TOKEN="$(printf '%s' "$HEADLESS_AUTH_TOKEN" | tr -d '\r\n')"
fi
if [[ -z "$HEADLESS_AUTH_TOKEN" ]]; then
  "${adb_cmd[@]}" shell am start -W -n "$APP_ID/.HeadlessRenderActivity" >/dev/null 2>&1 || true
  HEADLESS_AUTH_TOKEN="$("${adb_cmd[@]}" exec-out run-as "$APP_ID" cat "files/headless-auth-token" 2>/dev/null || true)"
  HEADLESS_AUTH_TOKEN="$(printf '%s' "$HEADLESS_AUTH_TOKEN" | tr -d '\r\n')"
fi
if [[ -n "$HEADLESS_AUTH_TOKEN" ]]; then
  start_args+=(--es auth_token "$HEADLESS_AUTH_TOKEN")
fi

if [[ "$INPUT_MODE" == "score" ]]; then
  host_input_file="$OUT_DIR/$RUN_ID/score-input.json"
  printf '%s\n' "$TEXT" > "$host_input_file"
  "${adb_cmd[@]}" shell run-as "$APP_ID" mkdir -p "files/headless-inputs" >/dev/null
  "${adb_cmd[@]}" exec-in run-as "$APP_ID" sh -c "cat > files/headless-inputs/$RUN_ID.txt" < "$host_input_file"
  start_args+=(--es text_file "app:headless-inputs/$RUN_ID.txt")
else
  start_args+=(--es text "$TEXT")
fi
if [[ -n "$ORIGINAL_TEXT" ]]; then start_args+=(--es original_text "$ORIGINAL_TEXT"); fi
if [[ -n "$STAGE1_MODEL" ]]; then start_args+=(--es stage1_model "$STAGE1_MODEL"); fi
if [[ -n "$STAGE2_MODEL" ]]; then start_args+=(--es stage2_model "$STAGE2_MODEL"); fi
if [[ -n "$CATALOG_ID" ]]; then start_args+=(--es catalog_id "$CATALOG_ID"); fi
if [[ -n "$CANVAS_ASPECT" ]]; then start_args+=(--es canvas_aspect "$CANVAS_ASPECT"); fi

"${adb_cmd[@]}" "${start_args[@]}" >/dev/null

android_result=""
for _ in $(seq 1 720); do
  status_json="$("${adb_cmd[@]}" exec-out run-as "$APP_ID" cat "files/headless/$RUN_ID/status.json" 2>/dev/null || true)"
  status="$(printf '%s' "$status_json" | jq -r '.status // empty' 2>/dev/null || true)"
  if [[ "$status" == "ok" || "$status" == "error" ]]; then
    android_result="$("${adb_cmd[@]}" exec-out run-as "$APP_ID" cat "files/headless/$RUN_ID/result.json" 2>/dev/null || true)"
    if printf '%s' "$android_result" | jq -e '.status' >/dev/null 2>&1; then
      break
    fi
  fi
  sleep 1
done

if [[ -z "$android_result" ]]; then
  echo "Android headless result timed out: $RUN_ID" >&2
  exit 1
fi

printf '%s\n' "$android_result" > "$OUT_DIR/$RUN_ID/android/result.json"
"${adb_cmd[@]}" exec-out run-as "$APP_ID" cat "files/headless/$RUN_ID/score.json" > "$OUT_DIR/$RUN_ID/android/score.json" 2>/dev/null || true
"${adb_cmd[@]}" exec-out run-as "$APP_ID" cat "files/headless/$RUN_ID/output.svg" > "$OUT_DIR/$RUN_ID/android/output.svg" 2>/dev/null || true
"${adb_cmd[@]}" exec-out run-as "$APP_ID" cat "files/headless/$RUN_ID/normalized.ddl" > "$OUT_DIR/$RUN_ID/android/normalized.ddl" 2>/dev/null || true
"${adb_cmd[@]}" exec-out run-as "$APP_ID" cat "files/headless/$RUN_ID/metadata.json" > "$OUT_DIR/$RUN_ID/android/metadata.json" 2>/dev/null || true

android_status="$(jq -r '.status' "$OUT_DIR/$RUN_ID/android/result.json")"
if [[ "$android_status" != "ok" ]]; then
  cat "$OUT_DIR/$RUN_ID/android/result.json"
  exit 1
fi

if [[ "$COMPARE_WEB" == "1" ]]; then
  web_stage1="$STAGE1_MODEL"
  web_stage2="$STAGE2_MODEL"
  if [[ -z "$web_stage1" ]]; then web_stage1="$(jq -r '.stage1_model' "$OUT_DIR/$RUN_ID/android/result.json")"; fi
  if [[ -z "$web_stage2" ]]; then web_stage2="$(jq -r '.stage2_model' "$OUT_DIR/$RUN_ID/android/result.json")"; fi
  web_catalog="$CATALOG_ID"
  web_canvas="$CANVAS_ASPECT"
  if [[ -z "$web_catalog" ]]; then web_catalog="$(jq -r '.catalog_id' "$OUT_DIR/$RUN_ID/android/result.json")"; fi
  if [[ -z "$web_canvas" ]]; then web_canvas="$(jq -r '.canvas_aspect' "$OUT_DIR/$RUN_ID/android/result.json")"; fi
  web_stage1_provider=""
  web_stage2_provider=""
  if [[ "$web_stage1" == *:* ]]; then
    web_stage1_provider="${web_stage1%%:*}"
    web_stage1="${web_stage1#*:}"
  fi
  if [[ "$web_stage2" == *:* ]]; then
    web_stage2_provider="${web_stage2%%:*}"
    web_stage2="${web_stage2#*:}"
  fi
  if [[ -n "${WEB_USERNAME:-}" && -n "${WEB_PASSWORD:-}" ]]; then
    (
      cd "$CLI_DIR"
      UV_CACHE_DIR="${UV_CACHE_DIR:-/tmp/inku-uv-cache}" \
      UV_PYTHON_INSTALL_DIR="${UV_PYTHON_INSTALL_DIR:-$HOME/.local/share/uv/python}" \
      uv run inku-cli login --base-url "$WEB_BASE_URL" --timeout-seconds "$INKU_CLI_TIMEOUT_SECONDS" \
        --username "$WEB_USERNAME" --password "$WEB_PASSWORD" >/dev/null
    )
  fi
  if [[ "$INPUT_MODE" == "score" ]]; then
    score_input="$OUT_DIR/$RUN_ID/score-input.json"
    printf '%s\n' "$TEXT" > "$score_input"
    cli_args=(
      render-score
      --file "$score_input"
      --base-url "$WEB_BASE_URL"
      --timeout-seconds "$INKU_CLI_TIMEOUT_SECONDS"
      --out-dir "$OUT_DIR/$RUN_ID/web"
      --prefix web
      --color-catalog "$web_catalog"
      --canvas-aspect "$web_canvas"
      --full-json
    )
  else
    cli_args=(
      paint "$TEXT"
      --base-url "$WEB_BASE_URL"
      --timeout-seconds "$INKU_CLI_TIMEOUT_SECONDS"
      --no-progress
      --out-dir "$OUT_DIR/$RUN_ID/web"
      --prefix web
      --color-catalog "$web_catalog"
      --input-mode "$INPUT_MODE"
      --full-json
    )
  fi
  if [[ "$PNG_REVIEW" == "true" || "$PNG_REVIEW" == "1" ]]; then
    cli_args+=(--png)
  fi
  if [[ -n "$ORIGINAL_TEXT" && "$INPUT_MODE" != "score" ]]; then cli_args+=(--original-text "$ORIGINAL_TEXT"); fi
  if [[ "$INPUT_MODE" != "score" && ( "$CLI_SAVE_HISTORY" == "true" || "$CLI_SAVE_HISTORY" == "1" ) ]]; then
    cli_args+=(--save-history)
  fi
  if [[ "$INPUT_MODE" != "score" ]]; then
    if [[ -n "$web_stage1_provider" ]]; then cli_args+=(--stage1-provider "$web_stage1_provider"); fi
    if [[ -n "$web_stage1" && "$web_stage1" != "null" ]]; then cli_args+=(--stage1-model "$web_stage1"); fi
    if [[ -n "$web_stage2_provider" ]]; then cli_args+=(--stage2-provider "$web_stage2_provider"); fi
    if [[ -n "$web_stage2" && "$web_stage2" != "null" ]]; then cli_args+=(--stage2-model "$web_stage2"); fi
  fi
  (
    cd "$CLI_DIR"
    UV_CACHE_DIR="${UV_CACHE_DIR:-/tmp/inku-uv-cache}" \
    UV_PYTHON_INSTALL_DIR="${UV_PYTHON_INSTALL_DIR:-$HOME/.local/share/uv/python}" \
    uv run inku-cli "${cli_args[@]}"
  ) > "$OUT_DIR/$RUN_ID/web/cli-output.txt"
  cp "$OUT_DIR/$RUN_ID/web/web.json" "$OUT_DIR/$RUN_ID/web/result.json"
  jq '.score' "$OUT_DIR/$RUN_ID/web/result.json" > "$OUT_DIR/$RUN_ID/web/score.json"
  cp "$OUT_DIR/$RUN_ID/web/web.svg" "$OUT_DIR/$RUN_ID/web/output.svg"
  jq -r '.ddl' "$OUT_DIR/$RUN_ID/web/result.json" > "$OUT_DIR/$RUN_ID/web/normalized.ddl"
fi

png_metrics_file="/dev/null"
if [[ "$PNG_REVIEW" == "true" || "$PNG_REVIEW" == "1" ]]; then
  (
    cd "$CLI_DIR"
    UV_CACHE_DIR="${UV_CACHE_DIR:-/tmp/inku-uv-cache}" \
    UV_PYTHON_INSTALL_DIR="${UV_PYTHON_INSTALL_DIR:-$HOME/.local/share/uv/python}" \
    uv run python ../android/scripts/render_png_review.py "$OUT_DIR/$RUN_ID" --size "$PNG_SIZE"
  ) > "$OUT_DIR/$RUN_ID/png-review-output.json"
  png_metrics_file="$OUT_DIR/$RUN_ID/png-review/metrics.json"
fi

summary="$OUT_DIR/$RUN_ID/summary.json"
web_result_file="$OUT_DIR/$RUN_ID/web/result.json"
if [[ ! -s "$web_result_file" ]]; then
  web_result_file="/dev/null"
fi
jq -n \
  --arg run_id "$RUN_ID" \
  --arg out_dir "$OUT_DIR/$RUN_ID" \
  --slurpfile android "$OUT_DIR/$RUN_ID/android/result.json" \
  --slurpfile web "$web_result_file" \
  --slurpfile png "$png_metrics_file" \
  '{
    run_id: $run_id,
    out_dir: $out_dir,
    android: {
      status: $android[0].status,
      hash: $android[0].render_hash,
      short: $android[0].render_hash_short,
      history_id: $android[0].history_id,
      input_mode: $android[0].input_mode,
      render_color_catalog_id: $android[0].render_color_catalog_id,
      render_color_catalog_name: $android[0].render_color_catalog_name,
      render_color_map: $android[0].render_color_map,
      stage1_model: $android[0].stage1_model,
      stage2_model: $android[0].stage2_model,
      ddl: $android[0].normalized_ddl
    },
    web: (if ($web|length) > 0 then {
      hash: $web[0].render_hash,
      short: $web[0].render_hash_short,
      history_id: $web[0].history_id,
      stage1_model: $web[0].stage1_model,
      stage2_model: $web[0].stage2_model,
      ddl: $web[0].ddl
    } else null end),
    same_render_hash: (if ($web|length) > 0 then $android[0].render_hash == $web[0].render_hash else null end),
    same_ddl: (if ($web|length) > 0 then $android[0].normalized_ddl == $web[0].ddl else null end),
    png_review: (if ($png|length) > 0 then $png[0] else null end)
  }' > "$summary"

cat "$summary"

"""Verified model metadata measured against NVIDIA NIM on 2026-07-20 and 2026-07-21.

Three benchmark runs (midday, evening and late night, three LLM attempts plus
one Vision attempt each) replaced the earlier single-run estimates.
Recommendations are split by purpose because the two are judged differently:
LLM use on whether a model succeeds every attempt without breaking the score
schema and with few corrections, Vision use on how much of a known image it
actually reports.

Speed labels name every run. NIM latency for the same model swung between 221s
and 114s on one day, so a single number would misrepresent it.

`eol` marks a model the provider has retired. Retired models stay listed so an
artwork that names one still shows a meaningful label, but they cannot be
selected for a new drawing. Models an artwork names are kept listed even when
they scored badly or could not be measured, for the same reason.

Method and rubric: no-git-sync/fable5/mode-api-claude/SCORING-DESIGN.md
"""

MODEL_CONFIG_VERSION = "2.3.0"
MODEL_CONFIG_LAST_UPDATED = "2026-07-29T11:00:00Z"

VERIFIED_NVIDIA_MODELS: list[dict[str, object]] = [
    {"id": "mistralai/mistral-nemotron", "label": "mistralai/mistral-nemotron", "purposes": ["llm"], "recommendation_llm": 4, "speed_class": "ultra-fast", "speed_label": "昼 121s / 夕 10s / 深夜 8s", "comment_ja": "実測 9/9 成功。スキーマ違反なし。補正発火 平均 5.0。応答中央値 昼 121s / 夕 10s / 深夜 8s。", "comment_en": "9 of 9 attempts succeeded; no schema violations; 5.0 corrections on average; median response midday 121s / evening 10s / late night 8s."},
    {"id": "meta/llama-3.1-70b-instruct", "label": "meta/llama-3.1-70b-instruct", "purposes": ["llm"], "recommendation_llm": 4, "speed_class": "fast", "speed_label": "昼 52s / 夕 29s / 深夜 64s", "comment_ja": "実測 9/9 成功。スキーマ違反なし。補正発火 平均 5.8。応答中央値 昼 52s / 夕 29s / 深夜 64s。", "comment_en": "9 of 9 attempts succeeded; no schema violations; 5.8 corrections on average; median response midday 52s / evening 29s / late night 64s."},
    {"id": "meta/llama-3.2-3b-instruct", "label": "meta/llama-3.2-3b-instruct", "purposes": ["llm"], "recommendation_llm": 4, "speed_class": "fast", "speed_label": "昼 121s / 夕 13s / 深夜 121s", "comment_ja": "実測 9/9 成功。スキーマ違反なし。補正発火 平均 5.9。応答中央値 昼 121s / 夕 13s / 深夜 121s。", "comment_en": "9 of 9 attempts succeeded; no schema violations; 5.9 corrections on average; median response midday 121s / evening 13s / late night 121s."},
    {"id": "qwen/qwen3-next-80b-a3b-instruct", "label": "qwen/qwen3-next-80b-a3b-instruct", "purposes": ["llm"], "recommendation_llm": 4, "speed_class": "ultra-fast", "speed_label": "昼 7s / 夕 7s / 深夜 8s", "comment_ja": "実測 9/9 成功。スキーマ違反なし。補正発火 平均 6.0。応答中央値 昼 7s / 夕 7s / 深夜 8s。", "comment_en": "9 of 9 attempts succeeded; no schema violations; 6.0 corrections on average; median response midday 7s / evening 7s / late night 8s."},
    {"id": "poolside/laguna-xs-2.1", "label": "poolside/laguna-xs-2.1", "purposes": ["llm"], "recommendation_llm": 4, "speed_class": "ultra-fast", "speed_label": "昼 4s / 夕 4s / 深夜 4s", "comment_ja": "実測 9/9 成功。スキーマ違反なし。補正発火 平均 7.2。応答中央値 昼 4s / 夕 4s / 深夜 4s。", "comment_en": "9 of 9 attempts succeeded; no schema violations; 7.2 corrections on average; median response midday 4s / evening 4s / late night 4s."},
    {"id": "nvidia/ising-calibration-1-35b-a3b", "label": "nvidia/ising-calibration-1-35b-a3b", "purposes": ["llm"], "recommendation_llm": 3, "speed_class": "fast", "speed_label": "昼 12s / 夕 22s / 深夜 13s", "comment_ja": "実測 9/9 成功。スキーマ違反なし。補正発火 平均 14.4。応答中央値 昼 12s / 夕 22s / 深夜 13s。", "comment_en": "9 of 9 attempts succeeded; no schema violations; 14.4 corrections on average; median response midday 12s / evening 22s / late night 13s."},
    {"id": "nvidia/llama-3.3-nemotron-super-49b-v1", "label": "nvidia/llama-3.3-nemotron-super-49b-v1", "purposes": ["llm"], "recommendation_llm": 5, "speed_class": "fast", "speed_label": "昼 24s / 夕 57s / 深夜 44s", "comment_ja": "実測 8/8 成功。スキーマ違反なし。補正発火 平均 4.6。混雑時の Stage 1 無応答 1 回。応答中央値 昼 24s / 夕 57s / 深夜 44s。", "comment_en": "8 of 8 attempts succeeded; no schema violations; 4.6 corrections on average; Stage 1 silent once under load; median response midday 24s / evening 57s / late night 44s."},
    {"id": "nvidia/nemotron-nano-12b-v2-vl", "label": "nvidia/nemotron-nano-12b-v2-vl", "purposes": ["llm", "vision"], "recommendation_llm": 3, "recommendation_vision": 4, "speed_class": "fast", "speed_label": "昼 19s / 夕 29s / 深夜 16s", "comment_ja": "実測 8/8 成功。スキーマ違反なし。補正発火 平均 8.4。応答中央値 昼 19s / 夕 29s / 深夜 16s。Vision 再現率 0.89。", "comment_en": "8 of 8 attempts succeeded; no schema violations; 8.4 corrections on average; median response midday 19s / evening 29s / late night 16s; Vision recall 0.89."},
    {"id": "google/gemma-4-31b-it", "label": "Google Gemma 4 31B Instruct", "purposes": ["llm", "vision"], "recommendation_llm": 4, "recommendation_vision": 5, "speed_class": "medium", "speed_label": "昼 221s / 夕 114s / 深夜 199s", "comment_ja": "実測 7/7 成功。スキーマ違反なし。補正発火 平均 5.9。混雑時の Stage 1 無応答 1 回。応答中央値 昼 221s / 夕 114s / 深夜 199s。Vision 再現率 1.00。", "comment_en": "7 of 7 attempts succeeded; no schema violations; 5.9 corrections on average; Stage 1 silent once under load; median response midday 221s / evening 114s / late night 199s; Vision recall 1.00."},
    {"id": "meta/llama-3.3-70b-instruct", "label": "Meta Llama 3.3 70B Instruct", "purposes": ["llm"], "recommendation_llm": 4, "speed_class": "slow", "speed_label": "昼 174s / 夕 149s / 深夜 180s", "comment_ja": "実測 6/6 成功。スキーマ違反なし。補正発火 平均 6.7。混雑時の Stage 1 無応答 2 回。応答中央値 昼 174s / 夕 149s / 深夜 180s。", "comment_en": "6 of 6 attempts succeeded; no schema violations; 6.7 corrections on average; Stage 1 silent 2 times under load; median response midday 174s / evening 149s / late night 180s."},
    {"id": "mistralai/mistral-large-3-675b-instruct-2512", "label": "mistralai/mistral-large-3-675b-instruct-2512", "purposes": ["llm"], "recommendation_llm": 3, "speed_class": "slow", "speed_label": "昼 165s / 夕 156s / 深夜 158s", "comment_ja": "実測 6/6 成功。スキーマ違反なし。補正発火 平均 8.0。混雑時の Stage 1 無応答 3 回。応答中央値 昼 165s / 夕 156s / 深夜 158s。", "comment_en": "6 of 6 attempts succeeded; no schema violations; 8.0 corrections on average; Stage 1 silent 3 times under load; median response midday 165s / evening 156s / late night 158s."},
    {"id": "qwen/qwen3.5-397b-a17b", "label": "qwen/qwen3.5-397b-a17b", "purposes": ["llm"], "recommendation_llm": 5, "speed_class": "slow", "speed_label": "昼 190s / 深夜 162s", "comment_ja": "実測 5/5 成功。スキーマ違反なし。補正発火 平均 3.8。混雑時の Stage 1 無応答 4 回。応答中央値 昼 190s / 深夜 162s。", "comment_en": "5 of 5 attempts succeeded; no schema violations; 3.8 corrections on average; Stage 1 silent 4 times under load; median response midday 190s / late night 162s."},
    {"id": "z-ai/glm-5.2", "label": "z-ai/glm-5.2", "purposes": ["llm"], "recommendation_llm": 5, "speed_class": "medium", "speed_label": "夕 148s / 深夜 110s", "comment_ja": "実測 5/5 成功。スキーマ違反なし。補正発火 平均 4.2。混雑時の Stage 1 無応答 1 回。応答中央値 夕 148s / 深夜 110s。", "comment_en": "5 of 5 attempts succeeded; no schema violations; 4.2 corrections on average; Stage 1 silent once under load; median response evening 148s / late night 110s."},
    {"id": "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning", "label": "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning", "purposes": ["llm", "vision"], "recommendation_llm": 3, "recommendation_vision": 4, "speed_class": "medium", "speed_label": "昼 119s / 夕 70s / 深夜 153s", "comment_ja": "実測 4/4 成功。スキーマ違反なし。補正発火 平均 7.8。応答中央値 昼 119s / 夕 70s / 深夜 153s。Vision 再現率 0.89。", "comment_en": "4 of 4 attempts succeeded; no schema violations; 7.8 corrections on average; median response midday 119s / evening 70s / late night 153s; Vision recall 0.89."},
    {"id": "deepseek-ai/deepseek-v4-flash", "label": "deepseek-ai/deepseek-v4-flash", "purposes": ["llm"], "recommendation_llm": 3, "speed_class": "fast", "speed_label": "昼 16s / 深夜 101s", "comment_ja": "実測 3/3 成功。スキーマ違反なし。補正発火 平均 9.3。応答中央値 昼 16s / 深夜 101s。", "comment_en": "3 of 3 attempts succeeded; no schema violations; 9.3 corrections on average; median response midday 16s / late night 101s."},
    {"id": "openai/gpt-oss-120b", "label": "openai/gpt-oss-120b", "purposes": ["llm"], "recommendation_llm": 2, "speed_class": "ultra-fast", "speed_label": "昼 13s / 夕 10s / 深夜 11s", "comment_ja": "実測 6/7 成功。スキーマ違反 1 回。補正発火 平均 3.5。混雑時の Stage 1 無応答 2 回。応答中央値 昼 13s / 夕 10s / 深夜 11s。", "comment_en": "6 of 7 attempts succeeded; 1 score schema violations; 3.5 corrections on average; Stage 1 silent 2 times under load; median response midday 13s / evening 10s / late night 11s."},
    {"id": "nvidia/llama-3.3-nemotron-super-49b-v1.5", "label": "nvidia/llama-3.3-nemotron-super-49b-v1.5", "purposes": ["llm"], "recommendation_llm": 4, "speed_class": "slow", "speed_label": "昼 136s", "comment_ja": "実測 1/1 成功。スキーマ違反なし。補正発火 平均 1.0。混雑時の Stage 1 無応答 1 回。応答中央値 昼 136s。", "comment_en": "1 of 1 attempts succeeded; no schema violations; 1.0 corrections on average; Stage 1 silent once under load; median response midday 136s."},
    {"id": "minimaxai/minimax-m3", "label": "minimaxai/minimax-m3", "purposes": ["llm"], "recommendation_llm": 2, "speed_class": "medium", "speed_label": "昼 132s / 夕 53s", "comment_ja": "実測 6/9 成功。tool calling の引数不正 3 回。補正発火 平均 6.3。応答中央値 昼 132s / 夕 53s。", "comment_en": "6 of 9 attempts succeeded; 3 malformed tool calls; 6.3 corrections on average; median response midday 132s / evening 53s."},
    {"id": "nvidia/llama-3.1-nemotron-nano-vl-8b-v1", "label": "nvidia/llama-3.1-nemotron-nano-vl-8b-v1", "purposes": ["llm", "vision"], "recommendation_llm": 2, "recommendation_vision": 3, "speed_class": "slow", "speed_label": "昼 122s / 夕 122s / 深夜 122s", "comment_ja": "実測 6/9 成功。スキーマ違反 3 回。補正発火 平均 6.3。応答中央値 昼 122s / 夕 122s / 深夜 122s。Vision 再現率 0.67。", "comment_en": "6 of 9 attempts succeeded; 3 score schema violations; 6.3 corrections on average; median response midday 122s / evening 122s / late night 122s; Vision recall 0.67."},
    {"id": "deepseek-ai/deepseek-v4-pro", "label": "deepseek-ai/deepseek-v4-pro", "purposes": ["llm"], "recommendation_llm": 2, "speed_class": "fast", "speed_label": "昼 16s / 夕 28s", "comment_ja": "実測 6/9 成功。tool calling の引数不正 3 回。補正発火 平均 7.8。応答中央値 昼 16s / 夕 28s。", "comment_en": "6 of 9 attempts succeeded; 3 malformed tool calls; 7.8 corrections on average; median response midday 16s / evening 28s."},
    {"id": "minimaxai/minimax-m2.7", "label": "minimaxai/minimax-m2.7", "purposes": ["llm"], "recommendation_llm": 2, "speed_class": "fast", "speed_label": "昼 22s / 夕 74s / 深夜 33s", "comment_ja": "実測 6/9 成功。スキーマ違反 3 回。補正発火 平均 8.5。応答中央値 昼 22s / 夕 74s / 深夜 33s。", "comment_en": "6 of 9 attempts succeeded; 3 score schema violations; 8.5 corrections on average; median response midday 22s / evening 74s / late night 33s."},
    {"id": "nvidia/nemotron-3-super-120b-a12b", "label": "nvidia/nemotron-3-super-120b-a12b", "purposes": ["llm"], "recommendation_llm": 2, "speed_class": "fast", "speed_label": "昼 21s / 夕 35s / 深夜 23s", "comment_ja": "実測 5/9 成功。スキーマ違反 4 回。補正発火 平均 10.4。応答中央値 昼 21s / 夕 35s / 深夜 23s。", "comment_en": "5 of 9 attempts succeeded; 4 score schema violations; 10.4 corrections on average; median response midday 21s / evening 35s / late night 23s."},
    {"id": "bytedance/seed-oss-36b-instruct", "label": "bytedance/seed-oss-36b-instruct", "purposes": ["llm"], "recommendation_llm": 2, "speed_class": "medium", "speed_label": "昼 95s", "comment_ja": "実測 1/2 成功。tool calling の引数不正 1 回。補正発火 平均 10.0。混雑時の Stage 1 無応答 5 回。応答中央値 昼 95s。", "comment_en": "1 of 2 attempts succeeded; 1 malformed tool calls; 10.0 corrections on average; Stage 1 silent 5 times under load; median response midday 95s."},
    {"id": "nvidia/nvidia-nemotron-nano-9b-v2", "label": "nvidia/nvidia-nemotron-nano-9b-v2", "purposes": ["llm"], "recommendation_llm": 2, "speed_class": "fast", "speed_label": "昼 73s / 深夜 40s", "comment_ja": "実測 2/4 成功。tool calling の引数不正 2 回。補正発火 平均 2.5。応答中央値 昼 73s / 深夜 40s。", "comment_en": "2 of 4 attempts succeeded; 2 malformed tool calls; 2.5 corrections on average; median response midday 73s / late night 40s."},
    {"id": "meta/llama-3.1-8b-instruct", "label": "meta/llama-3.1-8b-instruct", "purposes": ["llm"], "recommendation_llm": 2, "speed_class": "ultra-fast", "speed_label": "昼 3s / 夕 4s / 深夜 13s", "comment_ja": "実測 4/9 成功。スキーマ違反 5 回。補正発火 平均 3.5。応答中央値 昼 3s / 夕 4s / 深夜 13s。", "comment_en": "4 of 9 attempts succeeded; 5 score schema violations; 3.5 corrections on average; median response midday 3s / evening 4s / late night 13s."},
    {"id": "mistralai/mistral-medium-3.5-128b", "label": "mistralai/mistral-medium-3.5-128b", "purposes": ["llm", "vision"], "recommendation_llm": 2, "recommendation_vision": 4, "speed_class": "medium", "speed_label": "昼 128s / 夕 168s / 深夜 92s", "comment_ja": "実測 4/9 成功。スキーマ違反 5 回。補正発火 平均 3.8。応答中央値 昼 128s / 夕 168s / 深夜 92s。Vision 再現率 0.94。", "comment_en": "4 of 9 attempts succeeded; 5 score schema violations; 3.8 corrections on average; median response midday 128s / evening 168s / late night 92s; Vision recall 0.94."},
    {"id": "mistralai/mistral-small-4-119b-2603", "label": "mistralai/mistral-small-4-119b-2603", "purposes": ["llm", "vision"], "recommendation_llm": 2, "recommendation_vision": 4, "speed_class": "ultra-fast", "speed_label": "昼 3s / 夕 6s / 深夜 4s", "comment_ja": "実測 4/9 成功。スキーマ違反 5 回。補正発火 平均 5.5。応答中央値 昼 3s / 夕 6s / 深夜 4s。Vision 再現率 0.94。", "comment_en": "4 of 9 attempts succeeded; 5 score schema violations; 5.5 corrections on average; median response midday 3s / evening 6s / late night 4s; Vision recall 0.94."},
    {"id": "nvidia/nemotron-3-ultra-550b-a55b", "label": "nvidia/nemotron-3-ultra-550b-a55b", "purposes": ["llm"], "recommendation_llm": 2, "speed_class": "fast", "speed_label": "昼 40s / 夕 95s / 深夜 38s", "comment_ja": "実測 3/7 成功。スキーマ違反 4 回。補正発火 平均 10.3。応答中央値 昼 40s / 夕 95s / 深夜 38s。", "comment_en": "3 of 7 attempts succeeded; 4 score schema violations; 10.3 corrections on average; median response midday 40s / evening 95s / late night 38s."},
    {"id": "mistralai/mixtral-8x7b-instruct-v0.1", "label": "mistralai/mixtral-8x7b-instruct-v0.1", "purposes": ["llm"], "recommendation_llm": 2, "speed_class": "slow", "speed_label": "昼 125s / 夕 236s / 深夜 125s", "comment_ja": "実測 3/9 成功。スキーマ違反 6 回。補正発火 平均 1.0。応答中央値 昼 125s / 夕 236s / 深夜 125s。", "comment_en": "3 of 9 attempts succeeded; 6 score schema violations; 1.0 corrections on average; median response midday 125s / evening 236s / late night 125s."},
    {"id": "openai/gpt-oss-20b", "label": "openai/gpt-oss-20b", "purposes": ["llm"], "recommendation_llm": 2, "speed_class": "fast", "speed_label": "深夜 14s", "comment_ja": "実測 1/5 成功。スキーマ違反 4 回。補正発火 平均 1.0。混雑時の Stage 1 無応答 4 回。応答中央値 深夜 14s。", "comment_en": "1 of 5 attempts succeeded; 4 score schema violations; 1.0 corrections on average; Stage 1 silent 4 times under load; median response late night 14s."},
    {"id": "stepfun-ai/step-3.7-flash", "label": "stepfun-ai/step-3.7-flash", "purposes": ["llm"], "recommendation_llm": 2, "speed_class": "medium", "speed_label": "夕 43s", "comment_ja": "実測 1/6 成功。スキーマ違反 5 回。補正発火 平均 3.0。混雑時の Stage 1 無応答 3 回。応答中央値 夕 43s。", "comment_en": "1 of 6 attempts succeeded; 5 score schema violations; 3.0 corrections on average; Stage 1 silent 3 times under load; median response evening 43s."},
    {"id": "google/gemma-3n-e2b-it", "label": "google/gemma-3n-e2b-it", "purposes": ["vision"], "recommendation_vision": 4, "speed_class": "unknown", "speed_label": "Vision 12s", "comment_ja": "実測 0/9 成功。tool calling の引数不正 9 回。応答中央値 Vision 12s。Vision 再現率 0.94。", "comment_en": "0 of 9 attempts succeeded; 9 malformed tool calls; median response Vision 12s; Vision recall 0.94."},
    {"id": "google/gemma-3n-e4b-it", "label": "google/gemma-3n-e4b-it", "purposes": ["vision"], "recommendation_vision": 4, "speed_class": "unknown", "speed_label": "Vision 15s", "comment_ja": "実測 0/9 成功。tool calling の引数不正 9 回。応答中央値 Vision 15s。Vision 再現率 0.94。", "comment_en": "0 of 9 attempts succeeded; 9 malformed tool calls; median response Vision 15s; Vision recall 0.94."},
    {"id": "meta/llama-3.2-11b-vision-instruct", "label": "meta/llama-3.2-11b-vision-instruct", "purposes": ["vision"], "recommendation_vision": 4, "speed_class": "unknown", "speed_label": "Vision 9s", "comment_ja": "実測 0/9 成功。スキーマ違反 9 回。応答中央値 Vision 9s。Vision 再現率 0.94。", "comment_en": "0 of 9 attempts succeeded; 9 score schema violations; median response Vision 9s; Vision recall 0.94."},
    {"id": "nvidia/nemotron-3-nano-30b-a3b", "label": "nvidia/nemotron-3-nano-30b-a3b", "purposes": ["llm"], "recommendation_llm": 1, "speed_class": "unknown", "speed_label": "未計測", "comment_ja": "実測 0/9 成功。スキーマ違反 9 回。", "comment_en": "0 of 9 attempts succeeded; 9 score schema violations."},
    {"id": "meta/llama-3.2-1b-instruct", "label": "meta/llama-3.2-1b-instruct", "purposes": ["llm"], "speed_class": "unknown", "speed_label": "未計測", "comment_ja": "提供は継続中。2026-07-20 の 2 回の計測では 9 回とも Stage 1 が 120 秒以内に応答せず、品質を測定できなかった。混雑の影響とみられる。", "comment_en": "Still offered. In both 2026-07-20 runs Stage 1 did not answer within 120 seconds, so nothing about its quality was measured. Consistent with provider load."},
    {"id": "meta/llama-3.2-90b-vision-instruct", "label": "Llama 3.2 90B Vision Instruct", "purposes": ["vision"], "speed_class": "unknown", "speed_label": "未計測", "comment_ja": "提供は継続中。2026-07-20 の 2 回の計測では 9 回とも Stage 1 が 120 秒以内に応答せず、品質を測定できなかった。混雑の影響とみられる。", "comment_en": "Still offered. In both 2026-07-20 runs Stage 1 did not answer within 120 seconds, so nothing about its quality was measured. Consistent with provider load."},
    {"id": "meta/llama-4-maverick-17b-128e-instruct", "label": "meta/llama-4-maverick-17b-128e-instruct", "purposes": ["llm"], "speed_class": "unknown", "speed_label": "未計測", "comment_ja": "提供は継続中。2026-07-20 の 2 回の計測では 9 回とも Stage 1 が 120 秒以内に応答せず、品質を測定できなかった。混雑の影響とみられる。", "comment_en": "Still offered. In both 2026-07-20 runs Stage 1 did not answer within 120 seconds, so nothing about its quality was measured. Consistent with provider load."},
    {"id": "mistralai/ministral-14b-instruct-2512", "label": "mistralai/ministral-14b-instruct-2512", "purposes": ["llm"], "speed_class": "unknown", "speed_label": "未計測", "comment_ja": "提供は継続中。2026-07-20 の 2 回の計測では 9 回とも Stage 1 が 120 秒以内に応答せず、品質を測定できなかった。混雑の影響とみられる。", "comment_en": "Still offered. In both 2026-07-20 runs Stage 1 did not answer within 120 seconds, so nothing about its quality was measured. Consistent with provider load."},
    {"id": "nvidia/llama-3.1-nemotron-nano-8b-v1", "label": "nvidia/llama-3.1-nemotron-nano-8b-v1", "purposes": ["llm"], "speed_class": "unknown", "speed_label": "未計測", "comment_ja": "提供は継続中。2026-07-20 の 2 回の計測では 9 回とも Stage 1 が 120 秒以内に応答せず、品質を測定できなかった。混雑の影響とみられる。", "comment_en": "Still offered. In both 2026-07-20 runs Stage 1 did not answer within 120 seconds, so nothing about its quality was measured. Consistent with provider load."},
    {"id": "stepfun-ai/step-3.5-flash", "label": "stepfun-ai/step-3.5-flash", "purposes": ["llm"], "speed_class": "unknown", "speed_label": "未計測", "comment_ja": "提供は継続中。2026-07-20 の 2 回の計測では 9 回とも Stage 1 が 120 秒以内に応答せず、品質を測定できなかった。混雑の影響とみられる。", "comment_en": "Still offered. In both 2026-07-20 runs Stage 1 did not answer within 120 seconds, so nothing about its quality was measured. Consistent with provider load."},
    {"id": "thinkingmachines/inkling", "label": "thinkingmachines/inkling", "purposes": ["llm"], "speed_class": "unknown", "speed_label": "未計測", "comment_ja": "提供は継続中。2026-07-20 の 2 回の計測では 9 回とも Stage 1 が 120 秒以内に応答せず、品質を測定できなかった。混雑の影響とみられる。", "comment_en": "Still offered. In both 2026-07-20 runs Stage 1 did not answer within 120 seconds, so nothing about its quality was measured. Consistent with provider load."},
    {"id": "qwen/qwen3.5-122b-a10b", "label": "qwen/qwen3.5-122b-a10b", "purposes": ["llm"], "eol": True, "eol_date": "2026-07-20", "speed_class": "unknown", "speed_label": "提供終了", "comment_ja": "提供終了。過去の作品は保存済みの Score と SVG で閲覧できるが、再描画はできない。", "comment_en": "Retired by the provider. Existing artworks still render from their stored score and SVG, but cannot be redrawn."},
    {"id": "qwen/qwen3-coder-480b-a35b-instruct", "label": "qwen/qwen3-coder-480b-a35b-instruct", "purposes": ["llm"], "eol": True, "eol_date": "2026-07-20", "speed_class": "unknown", "speed_label": "提供終了", "comment_ja": "提供終了。過去の作品は保存済みの Score と SVG で閲覧できるが、再描画はできない。", "comment_en": "Retired by the provider. Existing artworks still render from their stored score and SVG, but cannot be redrawn."},
]


# Ollama Cloud (ollama.com), listed 2026-07-27. A separate provider from the local
# Ollama one on purpose: the weights share a name but the two are not interchangeable.
# Cloud runs models far larger than a laptop holds, and it sends the description off
# the machine, which is the one thing the local setup exists to avoid. Every comment
# says so, because the tooltip is where a reader decides which of the two they picked.
#
# Two behaviours were measured on 2026-07-27 and shape how the provider is wired:
# structured output is ignored in all three of its forms (native `format`, OpenAI
# `response_format` strict and non-strict), while tool calling works — so Stage 2 must
# keep using tools here. And the free tier is limited by concurrency rather than
# volume: eight simultaneous requests returned 429 while 7.6% of the weekly allowance
# was spent. `max_concurrency` on the provider definition holds the line at 2.
#
# Recommendation levels are deliberately absent. Only gemma4:31b has been run, and one
# model's Stage 1 pass is not enough to place anything on the 1-5 scale that
# SCORING-DESIGN.md defines. They arrive with the local-model scoring work.
_OLLAMA_CLOUD_NOTICE_JA = "記述は ollama.com へ送られる。同じ名前でもローカルの Ollama とは別物。"
_OLLAMA_CLOUD_NOTICE_EN = (
    "The description is sent to ollama.com. Despite the shared name this is not the local Ollama model."
)

_OLLAMA_CLOUD_UNMEASURED = [
    "deepseek-v4-flash",
    "deepseek-v4-pro",
    "glm-5.1",
    "glm-5.2",
    "gpt-oss:20b",
    "gpt-oss:120b",
    "kimi-k2.5",
    "kimi-k2.6",
    "kimi-k2.7-code",
    "minimax-m2.5",
    "minimax-m2.7",
    "minimax-m3",
    "mistral-large-3:675b",
    "nemotron-3-nano:30b",
    "nemotron-3-super",
    "nemotron-3-ultra",
    "qwen3.5:397b",
]

VERIFIED_OLLAMA_CLOUD_MODELS: list[dict[str, object]] = [
    {
        "id": "gemma4:31b",
        "label": "gemma4:31b",
        "purposes": ["llm"],
        "speed_class": "unknown",
        "speed_label": "1〜110s",
        "comment_ja": _OLLAMA_CLOUD_NOTICE_JA
        + "第一段階は実測 6/6 応答。第二段階は tool calling で通る (構造化出力の指定は無視される)。"
        + "同じ要求の所要が 1 秒から 110 秒まで振れるため、待ち時間は約束できない。",
        "comment_en": _OLLAMA_CLOUD_NOTICE_EN
        + " Stage 1 answered 6 of 6 attempts; Stage 2 works through tool calling, since structured output"
        + " requests are ignored. The same request took anywhere from 1 to 110 seconds, so no wait can be promised.",
    },
    *[
        {
            "id": model_id,
            "label": model_id,
            "purposes": ["llm"],
            "speed_class": "unknown",
            "speed_label": "未計測",
            "comment_ja": _OLLAMA_CLOUD_NOTICE_JA + "品質は未計測。",
            "comment_en": _OLLAMA_CLOUD_NOTICE_EN + " Its quality has not been measured.",
        }
        for model_id in _OLLAMA_CLOUD_UNMEASURED
    ],
]


# Local Ollama, measured 2026-07-27 and 2026-07-29 on a GPU-less machine with eight
# threads and 62GB of RAM. Every model here was run against the same frozen prompts:
# Stage 1 in Japanese and English (6 cases each, read and judged), Stage 2 through the
# production path (8 cases; `response_format` plus `reasoning_effort="none"`, the shape
# Build 748 and 749 gave local Ollama).
#
# Recommendation levels are deliberately absent, for the same reason they are absent
# from the cloud list: SCORING-DESIGN.md defines the 1-5 scale on success rate, schema
# violations and correction count measured over nine attempts against NIM, and none of
# those axes were measured here. What was measured is written out instead.
#
# The two stages want different models, so each entry says which stage it is for.
# Stage 1 asks for prose that stays inside the vocabulary; Stage 2 asks for a Score
# that covers every sentence. The models that win are not the same, and neither is the
# largest: qwen3.5:4b is the only small model whose Stage 1 passed in both languages,
# while ministral-3:8b carried the most sentences into Stage 2 of anything measured.
#
# `coverage` in the comments is the number of instructions produced for the five
# complex cases (28 sentences) over 28. It counts instructions, not sentences matched.
#
# Timings are for that one machine and say nothing about anyone else's. They exclude
# the first request against a freshly loaded model, which pays for the load and the
# 12-14k token prompt evaluation and ran 344s to 2116s.
_OLLAMA_LOCAL_NOTICE_JA = "計測は GPU なし 8 スレッドの機体。所要はその機体のもので、他所の機体には当てはまらない。"
_OLLAMA_LOCAL_NOTICE_EN = (
    "Measured on a GPU-less eight-thread machine. The timings are that machine's and do not carry over."
)

VERIFIED_OLLAMA_LOCAL_MODELS: list[dict[str, object]] = [
    {
        "id": "qwen3.5:4b-q4_K_M",
        "label": "qwen3.5:4b-q4_K_M (3.4GB)",
        "purposes": ["llm"],
        "speed_class": "fast",
        "speed_label": "1 件 39〜73s",
        "comment_ja": "第一段階の推奨。日本語・英語とも 6/6 が正規化 DDL として成立した唯一の小型モデルで、"
        "しかも候補中の最小。明文規則の違反は英語 6 件中 0 件。"
        "第二段階では被覆 9/28 と低いので、そちらは別のモデルに任せる。" + _OLLAMA_LOCAL_NOTICE_JA,
        "comment_en": "Recommended for Stage 1. The only small model whose 6 Japanese and 6 English"
        " attempts all came back as usable normalized DDL, and the smallest candidate at that;"
        " zero explicit-rule violations in English. Its Stage 2 coverage is 9 of 28, so leave that"
        " stage to another model. " + _OLLAMA_LOCAL_NOTICE_EN,
    },
    {
        "id": "ministral-3:8b-instruct-2512-q4_K_M",
        "label": "ministral-3:8b-instruct-2512-q4_K_M (6.0GB)",
        "purposes": ["llm"],
        "speed_class": "slow",
        "speed_label": "1 件 50〜576s",
        "comment_ja": "第二段階の推奨。被覆 20/28 は計測した中で最も高く、8 件とも Score になった。"
        "思考する機能を持たないので、思考が予算を食い切って何も返らない失敗を構造的に踏まない。"
        "第一段階は日本語 6/6 が成立するが、英語で座標を直書きして崩れる。" + _OLLAMA_LOCAL_NOTICE_JA,
        "comment_en": "Recommended for Stage 2. Its coverage of 20 of 28 is the highest measured, and all"
        " eight cases produced a Score. It has no thinking capability, so it cannot fail the way models"
        " do when thinking eats the whole token budget. Stage 1 holds up in Japanese but breaks down in"
        " English, where it writes raw coordinates. " + _OLLAMA_LOCAL_NOTICE_EN,
    },
    {
        "id": "gemma4:e4b-it-q4_K_M",
        "label": "gemma4:e4b-it-q4_K_M (9.6GB)",
        "purposes": ["llm"],
        "speed_class": "fast",
        "speed_label": "1 件 9〜141s",
        "comment_ja": "第二段階の被覆 18/28。8 件とも Score になり、所要は計測した中で最も短い。"
        "第一段階は日本語 6/6 が成立するが、英語で説明の文を 5 件付け、数量が落ちる"
        "（「七つ」が several になる）。" + _OLLAMA_LOCAL_NOTICE_JA,
        "comment_en": "Stage 2 coverage 18 of 28, all eight cases producing a Score, and the shortest"
        " times measured. Stage 1 holds up in Japanese but in English it adds explanatory sentences"
        " in 5 of 6 cases and drops counts (\"seven\" becomes \"several\"). " + _OLLAMA_LOCAL_NOTICE_EN,
    },
    {
        "id": "gemma4:31b-it-q4_K_M",
        "label": "gemma4:31b-it-q4_K_M (19GB)",
        "purposes": ["llm"],
        "speed_class": "unknown",
        "speed_label": "第二段階は未計測",
        "comment_ja": "第一段階は日本語・英語とも計測した中で最良。説明の文も灰背景の指示も 0 件で、"
        "「地: 生成りの紙。」の固定形を正しく使う唯一のモデル。"
        "第二段階の被覆 18/28 は Build 748/749 より前の経路で採った数字で、他の行とは条件が違う。"
        + _OLLAMA_LOCAL_NOTICE_JA,
        "comment_en": "The best Stage 1 measured in either language: no explanatory sentences, no gray"
        " background, and the only model that uses the fixed ground form correctly. Its Stage 2 coverage"
        " of 18 of 28 was taken on the path that preceded Build 748 and 749, so it is not comparable with"
        " the other entries here. " + _OLLAMA_LOCAL_NOTICE_EN,
    },
    {
        "id": "gemma4:12b-it-q4_K_M",
        "label": "gemma4:12b-it-q4_K_M (7.6GB)",
        "purposes": ["llm"],
        "speed_class": "medium",
        "speed_label": "1 件 18〜110s",
        "comment_ja": "第二段階の被覆 14/28。8 件とも Score になった。"
        "第一段階は英語が 6/6 成立して説明の文も 0 件だが、日本語で助詞が壊れる"
        "（「水たまりを楕円を七つ並べる」・「三ひゃく七十本」）。" + _OLLAMA_LOCAL_NOTICE_JA,
        "comment_en": "Stage 2 coverage 14 of 28, all eight cases producing a Score. Its English Stage 1"
        " is clean across all 6 cases with no explanatory sentences, but its Japanese breaks grammatically"
        " and mangles a numeral. " + _OLLAMA_LOCAL_NOTICE_EN,
    },
    {
        "id": "qwen3.5:27b-q4_K_M",
        "label": "qwen3.5:27b-q4_K_M (17GB)",
        "purposes": ["llm"],
        "speed_class": "slow",
        "speed_label": "1 件 224〜410s",
        "comment_ja": "第一段階は日本語 6/6・英語 6/6 が成立する。"
        "第二段階の被覆は 10/28 で、5 分の 1 の大きさの qwen3.5:4b（9/28）とほとんど変わらない。"
        "同じ系統では規模を上げても被覆が伸びず、所要だけが伸びる。" + _OLLAMA_LOCAL_NOTICE_JA,
        "comment_en": "Stage 1 holds up across all 6 Japanese and all 6 English cases. Its Stage 2"
        " coverage of 10 of 28 is barely above qwen3.5:4b at 9 of 28, a model a fifth its size: within"
        " this family, size buys time rather than coverage. " + _OLLAMA_LOCAL_NOTICE_EN,
    },
    {
        "id": "qwen3.5:9b-q4_K_M",
        "label": "qwen3.5:9b-q4_K_M (6.6GB)",
        "purposes": ["llm"],
        "speed_class": "medium",
        "speed_label": "1 件 67〜114s",
        "comment_ja": "第二段階の被覆 8/28 は、半分の大きさの qwen3.5:4b（9/28）を下回る。"
        "複雑な 5 件のうち 4 件で指示を 1 本しか出さない。"
        "第一段階は日本語 6/6 が成立するが、英語で説明の文を 4 件付ける。" + _OLLAMA_LOCAL_NOTICE_JA,
        "comment_en": "Stage 2 coverage of 8 of 28 falls below qwen3.5:4b at 9 of 28, half its size; on"
        " four of the five complex cases it emits a single instruction. Stage 1 holds up in Japanese but"
        " adds explanatory sentences in 4 English cases. " + _OLLAMA_LOCAL_NOTICE_EN,
    },
    {
        "id": "granite4.1:8b-q4_K_M",
        "label": "granite4.1:8b-q4_K_M (5.3GB)",
        "purposes": ["llm"],
        "speed_class": "unknown",
        "speed_label": "第二段階は未計測",
        "comment_ja": "第一段階が日本語 6 件中 4 件で成立しない。感情語「静かに」が残り、"
        "禁止された動詞を 3 回使い、1 件は「面:」の誤用で図形の指示が 1 つも出ない。"
        "第二段階は測っていない。" + _OLLAMA_LOCAL_NOTICE_JA,
        "comment_en": "Stage 1 fails on 4 of 6 Japanese cases: an emotional adverb survives, three"
        " forbidden verbs appear, and one case produces no shape instruction at all through misuse of the"
        " surface form. Stage 2 was not measured. " + _OLLAMA_LOCAL_NOTICE_EN,
    },
    {
        "id": "qwen3.5:2b-q4_K_M",
        "label": "qwen3.5:2b-q4_K_M (1.9GB)",
        "purposes": ["llm"],
        "speed_class": "unknown",
        "speed_label": "第二段階は未計測",
        "comment_ja": "第一段階が日本語 6 件中 3 件で成立しない。同じ段落を 3 回繰り返す 1 件と、"
        "図形を表す語が抜けて配置の句だけが並ぶ 2 件。第二段階は測っていない。" + _OLLAMA_LOCAL_NOTICE_JA,
        "comment_en": "Stage 1 fails on 3 of 6 Japanese cases: one repeats the same paragraph three times,"
        " two list placements with the shape word missing. Stage 2 was not measured. "
        + _OLLAMA_LOCAL_NOTICE_EN,
    },
    {
        "id": "qwen3.5:0.8b-q8_0",
        "label": "qwen3.5:0.8b-q8_0 (1.0GB)",
        "purposes": ["llm"],
        "speed_class": "unknown",
        "speed_label": "第二段階は未計測",
        "comment_ja": "第一段階が日本語 6 件中 3 件で成立しない。述語のない断片（「中央付近に。」）と、"
        "入力の情景語をそのまま写した 2 件。第二段階は測っていない。" + _OLLAMA_LOCAL_NOTICE_JA,
        "comment_en": "Stage 1 fails on 3 of 6 Japanese cases: a fragment with no predicate, and two that"
        " copy the scenic nouns of the input straight through without normalizing them. Stage 2 was not"
        " measured. " + _OLLAMA_LOCAL_NOTICE_EN,
    },
]

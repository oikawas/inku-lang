# Count fidelity stage 5 benchmark

Date: 2026-07-26

This stage measured ruling 1 and ruling 2 together at commit `d85cef5`, using the isolated Stage 2 API and `google/gemma-4-31b-it`. The benchmark used `--input-mode ddl`, `--continue-on-error`, no original text, no saved history, and three independent runs per language. It did not use the deployed pentala application tree or its systemd services.

All six runs produced 29 results and no failed requests. English run 3 line 6 and Japanese run 3 line 10 retained the CLI fallback result after the final hard-timeout retry also timed out.

## Target-count result

| Band | Japanese | English | Combined | Acceptance | Result |
|---|---:|---:|---:|---:|---|
| 2–11 | 100% (12/12) | 100% (12/12) | 100% (24/24) | 100% | pass |
| 12–49 | 78% (21/27) | 78% (21/27) | 78% (42/54) | at least 95% | fail |
| 50–119 | 43% (9/21) | 19% (4/21) | 31% (13/42) | at least 90% | fail |
| 120–239 | 41% (11/27) | 15% (4/27) | 28% (15/54) | at least 90% | fail |
| 240–299 | 33% represented (3/9) | 0% represented (0/9) | 17% represented (3/18) | at least 95% represented | fail |
| 300+ | 100% represented (9/9) | 0% represented (0/9) | 50% represented (9/18) | at least 95% represented | fail |

The Japanese/English gaps were 0, 0, 24, 26, 33, and 100 points. The last four bands exceeded the 10-point limit.

Compared with stage 3 (ruling 2 only), the combined band rates changed by 0, -11, +2, +13, -1, and +6 points. Ruling 1 did not bring the measured final Score to the acceptance thresholds.

## Post-LLM count rewriting

The failed final-Score rates do not measure only the Stage 2 model. Existing `coerce_score` processing rewrote counts after the model response. For example, Japanese line 11 retained `original count 74` in `color_hint`, returned count 64, and recorded `with_context_density_governor=1`.

Across the 104 failed target-count judgments, 51 had a same-target `original count` marker proving that the requested literal count was present before coerce. Further represented inputs had original counts in the permitted 80–120 range before coerce but were subsequently reduced to 48 or 64.

Using final counts plus the recorded original-count markers to reconstruct the immediately pre-coerce result gives:

| Band | Japanese before coerce | English before coerce |
|---|---:|---:|
| 2–11 | 100% (12/12) | 100% (12/12) |
| 12–49 | 78% (21/27) | 81% (22/27) |
| 50–119 | 86% (18/21) | 100% (21/21) |
| 120–239 | 56% (15/27) | 74% (20/27) |
| 240–299 | 100% represented (9/9) | 67% represented (6/9) |
| 300+ | 100% represented (9/9) | 89% represented (8/9) |

This reconstruction is diagnostic only; acceptance uses the final Score. The contract forbids adding a count-correction branch under `coerce/` and excludes deterministic compose-side enforcement, so no out-of-scope enforcement was added. The unmet result is recorded as required by section 8 of the contract.

## Sticky values

For inputs whose requested groups were all literal and whose total did not exceed 400, final Score occurrences were:

| Language | count 110 | count 64 | count 48 |
|---|---:|---:|---:|
| Japanese | 3 | 12 | 0 |
| English | 1 | 14 | 12 |

The Japanese 110 and 64 counts were below the stage 0 Japanese observations of 24 and 16 respectively, so the stated Japanese attraction check passed. English remained strongly attracted to 64 and 48.

## Discriminating cases

- Boundary 239/240 did not pass in the final Score. Count 239 remained literal in Japanese 2/3 and English 1/3. Count 240 was represented in neither language (0/3 each).
- For line 26 (40/80/120), Japanese collapsed the three requested ellipse groups to one original group of 120 in all runs, which coerce then reduced to 64. English emitted three separate ellipse groups with original counts 40, 80, and 120 in all runs; coerce retained 40 but reduced 80 and 120.
- Line 29 (180+150+130) did not consistently apply the specified largest-first budget rule. No final run preserved the required smaller literal groups. One Japanese run entered `with_total_density_budget`; the other five did not produce the required pre-budget grouping.

## Stage 2 elapsed time

The timings below sum `elapsed_total_ms` for each DDL-mode compose result, the same recorded measure used for stage 3.

| Run | Success / failure | Total |
|---|---:|---:|
| `713-v2.7.4-count-stage5-ja-r1` | 29 / 0 | 1,210,495 ms |
| `713-v2.7.4-count-stage5-ja-r2` | 29 / 0 | 1,059,861 ms |
| `713-v2.7.4-count-stage5-ja-r3` | 29 / 0 | 1,236,440 ms |
| `713-v2.7.4-count-stage5-en-r1` | 29 / 0 | 1,192,727 ms |
| `713-v2.7.4-count-stage5-en-r2` | 29 / 0 | 832,256 ms |
| `713-v2.7.4-count-stage5-en-r3` | 29 / 0 | 1,087,860 ms |

Total recorded time was 6,619,639 ms (110.33 minutes) for 174 results. Stage 3 recorded 6,634,770 ms (110.58 minutes) for 173 successful samples and one failed request. Stage 0 recorded approximately two hours for 170 successful samples and four failures without per-run totals.

## Run directories

- `cli/out2/713-v2.7.4-count-stage5-ja-r1`
- `cli/out2/713-v2.7.4-count-stage5-ja-r2`
- `cli/out2/713-v2.7.4-count-stage5-ja-r3`
- `cli/out2/713-v2.7.4-count-stage5-en-r1`
- `cli/out2/713-v2.7.4-count-stage5-en-r2`
- `cli/out2/713-v2.7.4-count-stage5-en-r3`

## Production difference

This is an isolated Stage 2 measurement. Production goes through Stage 1, supplies `original_text`, and may apply `tenkei`. DDL mode still runs Stage 1.5 expansion. Therefore these rates are not production adherence rates.

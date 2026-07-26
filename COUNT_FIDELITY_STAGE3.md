# Count fidelity — stage 3 benchmark

Date: 2026-07-26
Implementation commit: `f328e02` (ruling 2 only)
Model: `google/gemma-4-31b-it`

## Conditions

- Three runs per language, 29 DDL inputs per run.
- `--input-mode ddl`; Stage 1 was not used.
- `--continue-on-error`; history saving was not enabled.
- The benchmark used an isolated Uvicorn process on pentala with the branch package under `/tmp`; the persistent systemd service and deployed source tree were not changed.
- The production path differs: it passes through Stage 1, supplies `original_text`, and may apply `tenkei`. These figures isolate Stage 2 and are not production-wide adherence rates.

## Results by language

Japanese: 87 successful samples, 0 failures.

| Requested-count band | Exact | Representative | Noncompliant | Total | Adherence |
|---|---:|---:|---:|---:|---:|
| 2–11 | 12 | 0 | 0 | 12 | 100% |
| 12–49 | 24 | 0 | 3 | 27 | 89% |
| 50–119 | 8 | 0 | 13 | 21 | 38% |
| 120–239 | 6 | 0 | 21 | 27 | 22% |
| 240–299 | 0 | 3 | 6 | 9 | 33% |
| 300+ | 0 | 8 | 1 | 9 | 89% |

English: 86 successful samples, 1 provider failure (run 1, line 20, requested count 240).

| Requested-count band | Exact | Representative | Noncompliant | Total | Adherence |
|---|---:|---:|---:|---:|---:|
| 2–11 | 12 | 0 | 0 | 12 | 100% |
| 12–49 | 24 | 0 | 3 | 27 | 89% |
| 50–119 | 4 | 0 | 17 | 21 | 19% |
| 120–239 | 2 | 0 | 25 | 27 | 7% |
| 240–299 | 0 | 0 | 8 | 8 | 0% |
| 300+ | 0 | 0 | 9 | 9 | 0% |

## Combined comparison with stage 0

| Requested-count band | Stage 0 | Stage 3 | Change |
|---|---:|---:|---:|
| 2–11 | 100% | 100% | 0 pt |
| 12–49 | 76% | 89% | +13 pt |
| 50–119 | 29% | 29% | 0 pt |
| 120–239 | 20% | 15% | −5 pt |
| 240–299 | 20% | 18% | −2 pt |
| 300+ | 50% | 44% | −6 pt |

The language gap was 0, 0, 19, 15, 33, and 89 points respectively. Ruling 2 alone did not satisfy the final acceptance thresholds.

The three-group input at line 26 (40 / 80 / 120) was not reliably preserved as three separate count groups. Japanese outputs missed all three requested values in every run (`[3,16]` once and `[3,64]` twice). English retained 40 but missed 80 and 120 in all three runs (`[1,3,40,64]`).

## Stage 2 elapsed time

| Run | Success / failure | Total |
|---|---:|---:|
| `713-v2.7.4-count-stage3-ja-r1` | 29 / 0 | 1,178,081 ms |
| `713-v2.7.4-count-stage3-ja-r2` | 29 / 0 | 1,208,397 ms |
| `713-v2.7.4-count-stage3-ja-r3` | 29 / 0 | 899,558 ms |
| `713-v2.7.4-count-stage3-en-r1` | 28 / 1 | 1,169,065 ms |
| `713-v2.7.4-count-stage3-en-r2` | 29 / 0 | 952,577 ms |
| `713-v2.7.4-count-stage3-en-r3` | 29 / 0 | 1,227,092 ms |

Total recorded Stage 2 time was 6,634,770 ms (110.58 minutes) for 173 successful samples and one failed request. The stage 0 report recorded approximately two hours for 170 successful samples and four failures, without per-run totals.

## Run directories

- `cli/out2/713-v2.7.4-count-stage3-ja-r1`
- `cli/out2/713-v2.7.4-count-stage3-ja-r2`
- `cli/out2/713-v2.7.4-count-stage3-ja-r3`

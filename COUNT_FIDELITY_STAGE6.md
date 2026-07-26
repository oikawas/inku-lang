# Count fidelity stage 6 perturbation tests

Date: 2026-07-26

The perturbations used committed implementation state only. Temporary reversions were made in isolated copies under `/tmp`; the working tree and deployed pentala application were not changed.

## A — revert ruling 1 count guidance

Stage 3 is the exact required perturbation: it contains ruling 2 but predates the ruling 1 count-section rewrite. Its combined final-Score rate for the 50–119 band was 29% (8/27 Japanese, 4/21 English; 12/42 combined), equal to the stage 0 baseline of 29%.

The final stage 5 implementation also measured 29% combined (9/21 Japanese, 3/21 English; 12/42 combined). Therefore reverting ruling 1 did not produce an additional drop: the expected discriminating fall was not observed because the final Score was already at baseline. Existing post-LLM density governance dominated the final measurement.

## B — revert ruling 2 guidance

A temporary package copied from commit `01ffd69` reverted only the four ruling 2 guidance locations, including their Japanese/English forms:

- the system-prompt repeated-group rule;
- the Arrangement count schema description;
- the Instruction arrangement schema description;
- the compact retry rule.

The corrected examples and ruling 1 count section remained in place. The isolated API ran on port 18103. The 40/80/120 three-group input was run three times per language.

| Language | Result before the recorded coerce rewrite | Final Score | Expected exact sum |
|---|---|---|---|
| Japanese | one ellipse instruction, original count 240, in 3/3 | ellipse count 64 in 3/3 | met in 3/3 |
| English | one ellipse instruction, original count 120, in 3/3 | ellipse count 64 in 3/3 | not met; collapse occurred without summing |

The perturbation demonstrated the intended failure mode exactly in Japanese. In English it still collapsed three groups to one, but selected the largest group count rather than their sum. By comparison, the final corrected English prompt emitted three separate ellipse groups with original counts 40, 80, and 120 in 3/3 stage 5 runs, before coerce reduced 80 and 120. The final corrected Japanese prompt had already collapsed to one original group of 120 in 3/3, so ruling 2 remained ineffective for Japanese under this input.

Run directories:

- `cli/out2/713-v2.7.4-count-perturb-b-ja-r1` — 1/0, 44,744 ms
- `cli/out2/713-v2.7.4-count-perturb-b-ja-r2` — 1/0, 8,367 ms
- `cli/out2/713-v2.7.4-count-perturb-b-ja-r3` — 1/0, 7,416 ms
- `cli/out2/713-v2.7.4-count-perturb-b-en-r1` — 1/0, 6,828 ms
- `cli/out2/713-v2.7.4-count-perturb-b-en-r2` — 1/0, 8,297 ms
- `cli/out2/713-v2.7.4-count-perturb-b-en-r3` — 1/0, 11,825 ms

## C — boundary 239 / 240

The final Score did not satisfy the boundary perturbation:

- 239 remained literal in Japanese 2/3 and English 1/3.
- 240 was represented in Japanese 0/3 and English 0/3 in the final Score.
- Before coerce, Japanese emitted representative count 110 in 3/3. English emitted 110 in 2/3 and literal 240 in 1/3.
- Existing context-density governance reduced every line-20 result to 64.

Thus the requested 239-literal / 240-represented distinction was not reliable in the model result and was absent from the final Score.

## D — total literal count above 400

Line 29 requests groups 180, 150, and 130, totaling 460. The required behavior is to represent the largest group and retain the smaller 150 and 130 groups literally.

No final run satisfied this rule:

- Japanese: two runs represented all three groups as 110; one run emitted literal groups before `with_total_density_budget` changed all groups.
- English: all three runs emitted original groups 180, 150, and 130, then `with_context_density_governor` changed each to 64.
- No run represented only 180 while leaving 150 and 130 literal.

The expected largest-first behavior was therefore not observed.

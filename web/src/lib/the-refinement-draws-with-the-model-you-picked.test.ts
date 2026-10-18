// Run with: npm run test:unit  (node:test, no test dependency)
//
// The AI refinement dialog asks which vision model to use, and the model it was
// given reached exactly one call: the one that looks at the picture and suggests
// a direction. Every generation the dialog then drew went out under the page's
// own Stage 1 and Stage 2 -- and the run status printed those, so the dialog
// said one model and drew with another while the reader watched.
//
// Nothing was dropped on the wire and nothing 400s, which is why no gate caught
// it: the selection was carried faithfully to the one place it had ever been
// wired to. That is the shape to watch for -- a value that arrives intact at a
// destination too small for what it was asked to decide.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';

const MODAL = readFileSync(new URL('./components/AIRefineModal.svelte', import.meta.url), 'utf-8');
const PAGE = readFileSync(new URL('../routes/+page.svelte', import.meta.url), 'utf-8');
const RUN_OWNER = readFileSync(new URL('./features/run/current-work.ts', import.meta.url), 'utf-8');

test('T-164  paintOne takes a model for one run, and prefers it over the page setting', () => {
	// Declared on the options bag, so every caller may pass one...
	assert.match(RUN_OWNER, /\n\tstage1Model\?: string;\n\tstage2Model\?: string;/);
	// ...and read with ??, so a caller that passes nothing is unaffected and an
	// empty string is not silently swapped for the page's model.
	assert.match(RUN_OWNER, /const resolvedStage1Model = options\.stage1Model \?\? defaults\.stage1Model/);
	assert.match(RUN_OWNER, /const resolvedStage2Model = options\.stage2Model \?\? defaults\.stage2Model/);
	// The page resolves its ordinary settings before crossing the narrow run
	// boundary, so route state does not leak into the canonical owner.
	assert.match(PAGE, /stage1Model: qualifiedModelId\(stage1Provider, stage1Model\)/);
	assert.match(PAGE, /stage2Model: qualifiedModelId\(stage2Provider, stage2Model\)/);
});

test('T-165  the refinement sends the picked model with every generation it draws', () => {
	// The override rides in the same options bag as the run's other conditions,
	// so it cannot be attached to the advice call and forgotten on the paint.
	assert.match(
		MODAL,
		/\.\.\.\(paintModelOverride \? \{ stage1Model: paintModelOverride, stage2Model: paintModelOverride \} : \{\}\),/
	);
	// And it is still the model the advice call is given, which was already true.
	assert.match(MODAL, /onVisionAdvice\(historyId, selectedVisionModel,/);
});

test('T-166  the run status names the model the run is drawing with', () => {
	// Naming the page's model while drawing with another is how this looked from
	// the outside before it was true, so the label follows the same value.
	assert.match(MODAL, /stage1Model=\{paintModelOverride \? selectedVisionLabel : stage1ModelLabel\}/);
	assert.match(MODAL, /stage2Model=\{paintModelOverride \? selectedVisionLabel : stage2ModelLabel\}/);
});

test('T-167  the picker is always offered, and the run draws with the model it names', () => {
	// Random refinement was removed (the author, 2026-10-18): Vision is the only
	// method, so the picker is no longer behind a method choice.
	assert.match(MODAL, /const paintModelOverride = \$derived\(selectedVisionModel \|\| null\);/);
	assert.match(MODAL, /\n\s*<ModelCardPicker label=\{t\(\)\.aiRefineVisionModel\}/);
	assert.doesNotMatch(MODAL, /\{#if mode === 'vision'\}/);
});

test('a work its edited DDL holds offers the Vision method too (the author, 2026-10-14)', () => {
	// Every generation is drawn from the parent's DDL and Vision only picks the
	// element, so holding the description is no reason to withhold Vision. With
	// no method to choose, the hold only adds its note and disables nothing.
	assert.match(MODAL, /\{#if held\}<p class="held-note">\{t\(\)\.aiRefineHeldNote\}<\/p>\{\/if\}/);
	const start = MODAL.match(/<button class="confirm-action"[^>]*>/)?.[0] ?? '';
	assert.ok(start, 'the start button was not found');
	assert.doesNotMatch(start, /held/);
});

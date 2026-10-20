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

test('T-165  the run the Server takes is started with the picked model', () => {
	// Since the Server takes the run (2026-10-21) the one model chooses the
	// sentence, takes the laws stage and draws every child; it reaches the Server
	// in the request that starts the run, or nowhere.
	assert.match(MODAL, /autonomousRuns\.start\(\{[\s\S]*?model: selectedModel,[\s\S]*?\}\)/);
});

test('T-167  the picker is always offered', () => {
	assert.match(MODAL, /\n\s*<ModelCardPicker label=\{t\(\)\.aiRefineModel\}/);
	assert.doesNotMatch(MODAL, /\{#if mode === 'vision'\}/);
});

test('a work its edited DDL holds is offered the run too, with a note (2026-10-21)', () => {
	// It takes no sentence, so its run takes laws moves; the hold only adds its
	// note and disables nothing.
	assert.match(MODAL, /\{#if held\}<p class="ai-refine-note">\{t\(\)\.aiRefineHeldNote\}<\/p>\{\/if\}/);
	const start = MODAL.match(/<button type="button" class="ai-refine-primary" disabled=\{starting[^>]*>/)?.[0] ?? '';
	assert.ok(start, 'the start button was not found');
	assert.doesNotMatch(start, /held/);
});

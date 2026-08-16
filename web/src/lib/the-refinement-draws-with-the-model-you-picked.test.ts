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

test('T-164  paintOne takes a model for one run, and prefers it over the page setting', () => {
	// Declared on the options bag, so every caller may pass one...
	assert.match(PAGE, /\n\t\tstage1Model\?: string;\n\t\tstage2Model\?: string;/);
	// ...and read with ??, so a caller that passes nothing is unaffected and an
	// empty string is not silently swapped for the page's model.
	assert.match(PAGE, /const resolvedStage1Model = options\.stage1Model \?\? qualifiedModelId\(/);
	assert.match(PAGE, /const resolvedStage2Model = options\.stage2Model \?\? qualifiedModelId\(/);
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

test('T-167  random mode is left alone, because it never offered a choice', () => {
	// The picker only exists in vision mode. Overriding the models in random
	// mode would change what that mode draws with, which nobody asked for.
	assert.match(MODAL, /refineMode === 'vision' && selectedVisionModel \? selectedVisionModel : null/);
	assert.match(MODAL, /\{#if refineMode === 'vision'\}<ModelCardPicker/);
});

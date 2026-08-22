// Run with: npm run test:unit  (node:test, no test dependency)
//
// T-127: the limits panel converts the total into the weight of a work.
//
// The stepper counts marks. What reaches a reader is a file, and the panel is
// the only place where the person raising the ceiling can be told what they are
// raising it to. The conversion belongs under the TOTAL and nowhere else: the
// other eight numbers are per-instruction bounds, legibility thresholds and
// typo guards, and a megabyte figure under any of them would describe a
// quantity that number does not govern.
//
// The field region is cut on purpose. Matching the file as a whole would stay
// green with the line moved to a neighbouring field, which is exactly the
// mistake worth catching.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { test } from 'node:test';

import { WEIGHTED_LIMIT_FIELD, markWeight } from '../markWeight.ts';

const COMPONENTS_DIR = dirname(fileURLToPath(import.meta.url));
const panel = readFileSync(join(COMPONENTS_DIR, '../features/settings/RenderLimitsSettings.svelte'), 'utf8');

// The measured cost of one mark, as the server sends it.
const BYTES_PER_MARK = { pen: 12924, brush_thick: 16138 };

const OTHER_FIELDS = [
	'max_expanded_per_instruction',
	'max_instructions',
	'literal_count_threshold',
	'represented_count_min',
	'represented_count_max',
	'ddl_count_max',
	'ddl_count_max_grid',
	'schema_count_max'
];

test('the total says what a work will weigh, and says it in the tools spread', () => {
	assert.equal(WEIGHTED_LIMIT_FIELD, 'max_expanded_primitives');

	// The default: 400 marks is 5.17 MB with a pen and 6.46 with a thick brush.
	const at400 = markWeight(WEIGHTED_LIMIT_FIELD, 400, BYTES_PER_MARK);
	assert.deepEqual(at400, { low: 5.2, high: 6.5 });

	// It follows the number on the stepper, so raising the ceiling says so.
	assert.deepEqual(markWeight(WEIGHTED_LIMIT_FIELD, 1200, BYTES_PER_MARK), {
		low: 15.5,
		high: 19.4
	});
});

test('no other row carries a weight, because no other row governs one', () => {
	// The control for the check above: a conversion that answered for every
	// field would pass the first test and fail here.
	for (const field of OTHER_FIELDS) {
		assert.equal(markWeight(field, 400, BYTES_PER_MARK), null, field);
	}
});

test('it stays quiet rather than guessing when the server sent no costs', () => {
	assert.equal(markWeight(WEIGHTED_LIMIT_FIELD, 400, undefined), null);
	assert.equal(markWeight(WEIGHTED_LIMIT_FIELD, 400, {}), null);
	assert.equal(markWeight(WEIGHTED_LIMIT_FIELD, undefined, BYTES_PER_MARK), null);
});

test('the panel draws it inside the limits field, from the value and the sent costs', () => {
	// The region: one `limits-field` block, cut from the opening div to the end
	// of the loop body. The two checks above would pass over a decision the
	// panel never reaches, and a whole-file match would pass with the line moved.
	const start = panel.indexOf('<div class="limits-field">');
	assert.ok(start > 0, 'the limits field block is where the panel puts each row');
	const end = panel.indexOf('{/each}', start);
	assert.ok(end > start);
	const field = panel.slice(start, end);

	assert.match(field, /markWeight\(\s*field,/);
	assert.match(field, /status\.limits\[field\]/);
	assert.match(field, /status\.bytes_per_mark/);
	assert.match(field, /settingsRenderLimitsWeight\(weight\.low, weight\.high\)/);

	// And the panel reads the cost from the response rather than keeping a copy:
	// a number written in the browser would be frozen on the day it was written.
	assert.equal(panel.includes('12924'), false, 'the per-mark cost is the server’s');
	assert.equal(panel.includes('16138'), false, 'the per-mark cost is the server’s');
});

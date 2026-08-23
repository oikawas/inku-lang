import assert from 'node:assert/strict';
import test from 'node:test';

import type { HistoryItem } from '../../historyManagerState.svelte.ts';
import { projectHistoryCurrentWork } from './current-work.ts';

test('T-295: current-work projection preserves saved source, render identity, seeds, and sketch state', () => {
	const item: HistoryItem = {
		id: 'work-1',
		input: 'legacy input',
		source_text: 'canonical source',
		ddl: 'input ddl',
		expanded_ddl: 'expanded ddl',
		thinking: 'thinking',
		score: { instructions: [], canvas: 'portrait' },
		svg: '<svg/>',
		at: 10,
		elapsed_ms: 31,
		render_engine_id: 'default',
		render_engine_version: '2',
		render_seed: '17',
		composition_seed: '23',
		variation_seed: '29',
		lineage_node_id: 'node-1',
		lineage_parent_node_id: 'node-0',
		derivation_kind: 'replay',
		derivation_metadata: { from: 'work-0' },
		sketch_text: 'sketch prose',
		sketch_grain: 'coarse',
		sketch_state: 'used'
	};
	const projection = projectHistoryCurrentWork(item);

	assert.equal(projection.sourceText, 'canonical source');
	assert.equal(projection.ddl, 'input ddl');
	assert.equal(projection.expandedDdl, 'expanded ddl');
	assert.equal(projection.sketchText, 'sketch prose');
	assert.equal(projection.sketchGrain, 'coarse');
	assert.equal(projection.sketchState, 'used');
	assert.equal(projection.result.render_seed, 17);
	assert.equal(projection.result.composition_seed, 23);
	assert.equal(projection.result.variation_seed, 29);
	assert.equal(projection.result.lineage_node_id, 'node-1');
	assert.equal(projection.result.derivation_kind, 'replay');
	assert.equal(projection.result.elapsed_total_ms, 31);
	assert.equal(projection.result.tokens_in_stage1, null);
});

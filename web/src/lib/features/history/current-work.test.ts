import assert from 'node:assert/strict';
import test from 'node:test';
import { readFileSync } from 'node:fs';

import { hasDdlBody } from '../../ddl-source.ts';
import type { HistoryItem } from '../../historyManagerState.svelte.ts';
import { projectHistoryCurrentWork } from './current-work.ts';

test('T-295: current-work projection preserves saved source, render identity, seeds, and sketch state', () => {
	const item: HistoryItem = {
		id: 'work-1',
		input: 'legacy input',
		source_text: 'canonical source',
		ddl: 'saved ddl',
		ddl_source_origin: 'legacy_expanded',
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
		variation_amplitude: 'small',
		focus: 'center',
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
	assert.equal(projection.ddl, 'saved ddl');
	assert.equal('expandedDdl' in projection, false);
	assert.equal(projection.sketchText, 'sketch prose');
	assert.equal(projection.sketchGrain, 'coarse');
	assert.equal(projection.sketchState, 'used');
	assert.equal(projection.result.render_seed, '17');
	assert.equal(projection.result.composition_seed, '23');
	assert.equal(projection.result.variation_seed, 29);
	assert.equal(projection.result.variation_amplitude, 'small');
	assert.equal(projection.result.focus, 'center');
	assert.equal(projection.result.lineage_node_id, 'node-1');
	assert.equal(projection.result.derivation_kind, 'replay');
	assert.equal(projection.result.elapsed_total_ms, 31);
	assert.equal(projection.result.tokens_in_stage1, null);
});

test('I-706: the single source is replayed and fixed-contract whitespace has no body', () => {
	for (const value of [null, undefined, '', '\t\r\n \u0085\u00a0\u1680\u2000\u200a\u2028\u2029\u202f\u205f\u3000']) {
		assert.equal(hasDdlBody(value), false);
	}
	for (const value of ['\u3000saved ddl\r\n', '\u001c', '\ufeff']) {
		assert.equal(hasDdlBody(value), true);
	}
	const read = (path: string) => readFileSync(new URL(path, import.meta.url), 'utf8');
	const state = read('../work/state.svelte.ts');
	assert.match(state, /if \(!ddl \|\| !hasDdlBody\(ddl\) \|\| reloading\) return/);
	assert.match(state, /const view = await authorDdl\(ddl, /);
	assert.doesNotMatch(state, /expandedDdl|source_ddl/);
	const viewer = read('../../components/DdlViewer.svelte');
	assert.match(viewer, /highlightDDL\(ddl\)/);
	assert.match(viewer, /paintDisabled \|\| !hasDdlBody\(ddl\)/);
	assert.doesNotMatch(viewer, /legacyExpandedOnly|expandedDdl/);
});

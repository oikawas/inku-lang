import assert from 'node:assert/strict';
import { test } from 'node:test';

import type { HistoryItem } from '../../historyManagerState.svelte.ts';
import type { VariationCandidate } from './refinement-session.svelte.ts';
import {
	projectRefinementCandidate,
	saveRefinementCandidates
} from './refinement-actions.ts';

function candidate(
	id: string,
	overrides: Partial<VariationCandidate['result']> = {}
): VariationCandidate {
	return {
		id,
		label: id,
		selected: true,
		result: {
			svg: `<svg id="${id}"/>`,
			score: { instructions: [], canvas: 'portrait' },
			ddl: `${id} expanded`,
			thinking: `${id} thinking`,
			stage1_model: 'provider/stage-1',
			stage2_model: 'provider/stage-2',
			lineage_parent_node_id: 'parent-1',
			derivation_kind: 'variation',
			derivation_metadata: { candidate: id },
			elapsed_stage1_ms: 11,
			elapsed_stage2_ms: 13,
			elapsed_total_ms: 24,
			tokens_in_stage1: 2,
			tokens_out_stage1: 0,
			tokens_in_stage2: 3,
			tokens_out_stage2: 0,
			...overrides
		}
	};
}

test('T-315: candidate projection keeps source DDL fallback and result identity', () => {
	const withSource = candidate('source', { source_ddl: 'source ddl' });
	const sourceProjection = projectRefinementCandidate(withSource);
	assert.equal(sourceProjection.ddl, 'source ddl');
	assert.equal(sourceProjection.expandedDdl, 'source expanded');
	assert.equal(sourceProjection.thinking, 'source thinking');
	assert.equal(sourceProjection.result, withSource.result);

	const withoutSource = candidate('fallback', { source_ddl: null });
	assert.equal(projectRefinementCandidate(withoutSource).ddl, 'fallback expanded');
});

test('T-316/T-318: candidates save sequentially with canonical fields and only current identity adopts', async () => {
	const first = candidate('first', { render_color_catalog_id: null });
	const current = candidate('current', { render_color_catalog_id: 'candidate-catalog' });
	const events: string[] = [];
	const calls: Array<{ item: HistoryItem; options: Record<string, unknown> }> = [];
	const times = [101, 202];
	const sourceTexts = ['source one', 'source two'];

	const outcome = await saveRefinementCandidates({
		candidates: [first, current],
		sourceText: () => sourceTexts.shift() ?? '',
		fallbackCatalogId: () => 'fallback-catalog'
	}, {
		now: () => times.shift() ?? 0,
		saveHistory: async (item, options) => {
			events.push(`save:${item.ddl}`);
			calls.push({ item, options });
			return { ...item, id: `saved-${String(item.ddl)}`, at: item.at };
		},
		isCurrentContext: () => true,
		markSaved: (id) => { events.push(`mark:${id}`); },
		isCurrentResult: (result) => result === current.result,
		adoptSavedIdentity: (_result, saved) => { events.push(`adopt:${saved.id}`); }
	});

	assert.equal(outcome, 'complete');
	assert.deepEqual(events, [
		'save:first expanded',
		'mark:first',
		'save:current expanded',
		'mark:current',
		'adopt:saved-current expanded'
	]);
	assert.deepEqual(
		{
			input: calls[0]?.item.input,
			ddl: calls[0]?.item.ddl,
			at: calls[0]?.item.at,
			elapsed: calls[0]?.item.elapsed_ms,
			tokensIn: calls[0]?.item.tokens_in,
			tokensOut: calls[0]?.item.tokens_out,
			catalogId: calls[0]?.item.catalog_id
		},
		{
			input: 'source one',
			ddl: 'first expanded',
			at: 101,
			elapsed: 24,
			tokensIn: 5,
			tokensOut: null,
			catalogId: 'fallback-catalog'
		}
	);
	assert.deepEqual(calls[0]?.options, {
		countGeneration: true,
		sourceText: 'source one',
		lineageParentNodeId: 'parent-1',
		derivationKind: 'variation',
		derivationMetadata: { candidate: 'first' }
	});
	assert.equal(calls[1]?.item.at, 202);
	assert.equal(calls[1]?.item.input, 'source two');
	assert.equal(calls[1]?.item.catalog_id, 'candidate-catalog');
});

test('T-317: stale context stops before mark, adoption, or the next save', async () => {
	const first = candidate('first');
	const second = candidate('second');
	const events: string[] = [];
	let current = true;

	const outcome = await saveRefinementCandidates({
		candidates: [first, second],
		sourceText: () => 'source',
		fallbackCatalogId: () => 'catalog'
	}, {
		saveHistory: async (item) => {
			events.push(`save:${item.ddl}`);
			current = false;
			return { ...item, id: 'saved-first' };
		},
		isCurrentContext: () => current,
		markSaved: (id) => { events.push(`mark:${id}`); },
		isCurrentResult: () => true,
		adoptSavedIdentity: () => { events.push('adopt'); }
	});

	assert.equal(outcome, 'stale');
	assert.deepEqual(events, ['save:first expanded']);
});

// Run with: npm run test:unit  (node:test, no test dependency)
import assert from 'node:assert/strict';
import { test } from 'node:test';

import { aiMoveOf, chunkMoveText, sharePercent } from './ai-move.ts';

test('a chunk move reads as its move, the chunks it took and a redrawn chunk\'s new title', () => {
	const words = {
		aiRefineChunkMoveName: (move: string) => ({ simplify: '単純にする', merge: '溶かす' }[move] ?? move),
		aiRefineChunkMove: (name: string, targets: string[], title: string | null) =>
			`${name}${targets.map((target) => `『${target}』`).join('')}${title ? `→『${title}』` : ''}`
	};
	assert.equal(chunkMoveText(words, 'simplify', ['富士の高嶺'], '重なる斜面'), '単純にする『富士の高嶺』→『重なる斜面』');
	assert.equal(chunkMoveText(words, 'merge', ['雲', '山'], ' 霞む稜線 '), '溶かす『雲』『山』→『霞む稜線』');
	// A failed try names its move only; a laws or juxtaposition try has none.
	assert.equal(chunkMoveText(words, 'simplify', null, null), '単純にする');
	assert.equal(chunkMoveText(words, null, ['雲'], null), null);
});

test('a lineage edge reads its AI move field by field, and an edge with no known move reads as none', () => {
	const chunks = aiMoveOf({ ai_move: {
		kind: 'chunks', turn: 2, visible: { share: 0.0123, passes: false, gate: false },
		chunks: { move: 'place', targets: ['月'], params: { at: 'center' }, reason: '月を中心へ', tries: 1 }
	} });
	assert.deepEqual(chunks, {
		kind: 'chunks', turn: 2, share: 0.0123, reason: '月を中心へ', mainLaw: null, sentence: null,
		move: 'place', targets: ['月'], title: null
	});
	const laws = aiMoveOf({ ai_move: { kind: 'laws', visible: {}, laws: { main_law: '対比', reason: '明暗を強める' } } });
	assert.equal(laws?.mainLaw, '対比');
	assert.equal(laws?.share, null);
	assert.equal(aiMoveOf({ juxtaposition: { sentence: '画面から足した一文' } }), null);
	assert.equal(aiMoveOf({ ai_move: { kind: 'touch' } }), null);
	assert.equal(aiMoveOf(undefined), null);
});

test('the change from the parent prints as a whole percent', () => {
	assert.deepEqual([0.184, 0.5, null, Number.NaN].map(sharePercent), ['18', '50', null, null]);
});

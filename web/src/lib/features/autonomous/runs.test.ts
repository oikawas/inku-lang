// Run with: npm run test:unit  (node:test, no test dependency)
import assert from 'node:assert/strict';
import { test } from 'node:test';

import { aiMoveOf, chunkMoveText, kindsOf, runToResume, sharePercent, triesOf, type AutonomousRun } from './runs.ts';

function run(id: string, state: AutonomousRun['state'], turns: AutonomousRun['turns'] = []): AutonomousRun {
	return {
		id, history_id: 'work', state, stopping: false, turns, created_at: 1, updated_at: 1,
		settings: { moves: 5, kinds: ['laws', 'juxtaposition'], model: 'chatgpt:gpt-6-luna', language: 'ja' }
	};
}

test('a work opened again shows the run still going, not the last one that ended', () => {
	// Failure: the dialog offered a new run beside the one going on, which the Server refuses (409).
	assert.equal(runToResume([run('older-done', 'done'), run('going', 'running')])?.id, 'going');
	assert.equal(runToResume([run('stopped', 'stopped'), run('cut', 'interrupted')]), null);
});

test('the tries read in the order taken, each with its turn and its share in whole percent', () => {
	const taken = triesOf(run('r', 'done', [
		{ attempts: [{ attempt: 1, kind: 'juxtaposition', outcome: 'not_visible', share: 0.184 },
			{ attempt: 2, kind: 'laws', outcome: 'kept', share: 0.5 }] },
		{ attempts: [{ attempt: 1, kind: 'juxtaposition', outcome: 'unavailable', reason: 'description_locked' }] }
	]));
	assert.deepEqual(taken.map(({ turn, attempt }) => [turn, attempt.kind, attempt.outcome]), [
		[1, 'juxtaposition', 'not_visible'], [1, 'laws', 'kept'], [2, 'juxtaposition', 'unavailable']
	]);
	assert.deepEqual(taken.map(({ attempt }) => sharePercent(attempt.share)), ['18', '50', null]);
});

test('the chunk move starts alone, whatever else is ticked', () => {
	// Failure: the Server refuses chunks beside the other moves (422 autonomous_chunks_alone).
	assert.deepEqual(kindsOf({ laws: true, juxtaposition: true, chunks: true }), ['chunks']);
	assert.deepEqual(kindsOf({ laws: true, juxtaposition: true, chunks: false }), ['laws', 'juxtaposition']);
	assert.deepEqual(kindsOf({ laws: false, juxtaposition: false, chunks: false }), []);
});

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

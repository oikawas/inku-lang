// Run with: npm run test:unit  (node:test, no test dependency)
//
// "Check the result" is for a run that stopped. A Stage 1 result waiting to be
// saved also carries a reason (`stage1_generated`), and showing it put the
// line on screen for the moment every drawing was being saved.
import assert from 'node:assert/strict';
import { test } from 'node:test';

import { pipelineAttentionReason } from './attention.ts';

test('a result waiting to be saved is not a reason to stop', () => {
	assert.equal(pipelineAttentionReason({ tag: 'awaiting_visible_ddl_commit', reason: 'stage1_generated' }), null);
	assert.equal(pipelineAttentionReason({ tag: 'awaiting_visible_ddl_commit', reason: 'stage1_residual_execution' }), null);
});

test('a run that needs the author or failed still says why', () => {
	assert.equal(pipelineAttentionReason({ tag: 'needs_user_edit', reason: 'stage1_failed' }), 'stage1_failed');
	assert.equal(pipelineAttentionReason({ tag: 'failed', reason: 'compiler_boundary_failed' }), 'compiler_boundary_failed');
});

test('no phase, or a phase without a reason, shows nothing', () => {
	assert.equal(pipelineAttentionReason(null), null);
	assert.equal(pipelineAttentionReason(undefined), null);
	assert.equal(pipelineAttentionReason({ tag: 'awaiting_llm' }), null);
	assert.equal(pipelineAttentionReason({ tag: 'needs_user_edit' }), null);
});

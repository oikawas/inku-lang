import assert from 'node:assert/strict';
import { test } from 'node:test';
import { interpretFallbackReason } from './composeFallback.ts';

test('saved fallback takes precedence; a new result supplies its reason', () => {
	assert.equal(interpretFallbackReason({ interpret_fallback: null }, { interpret_fallback_used: true }), null);
	assert.equal(interpretFallbackReason({ interpret_fallback: 'saved' }, null), 'saved');
	assert.equal(interpretFallbackReason(null, { interpret_fallback_used: true, interpret_fallback_reasons: ['reason'] }), 'reason');
	assert.equal(interpretFallbackReason(null, { interpret_fallback_used: true }), 'stage1_fallback');
	assert.equal(interpretFallbackReason(null, { interpret_fallback_used: false }), null);
});

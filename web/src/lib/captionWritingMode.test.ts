import assert from 'node:assert/strict';
import { test } from 'node:test';

import { normalizeCaptionPosition, normalizeCaptionWritingMode, supportsVerticalCaption } from './captionWritingMode.ts';

test('vertical writing is available for Japanese and mixed headnotes only', () => {
	assert.equal(supportsVerticalCaption('朝霧の山'), true);
	assert.equal(supportsVerticalCaption('mist over 山'), true);
	assert.equal(supportsVerticalCaption('mist over a mountain'), false);
	assert.equal(supportsVerticalCaption(''), false);
	assert.equal(supportsVerticalCaption('1234'), false);
});

test('caption writing mode defaults safely to horizontal', () => {
	assert.equal(normalizeCaptionWritingMode('vertical'), 'vertical');
	for (const value of ['horizontal', 'diagonal', '', null, undefined, 1]) {
		assert.equal(normalizeCaptionWritingMode(value), 'horizontal');
	}
});

test('caption position defaults safely to left', () => {
	assert.equal(normalizeCaptionPosition('right'), 'right');
	for (const value of ['left', 'center', '', null, undefined, 1]) {
		assert.equal(normalizeCaptionPosition(value), 'left');
	}
});

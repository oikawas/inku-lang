import assert from 'node:assert/strict';
import test from 'node:test';
import { runningStageLabel } from '../../paintStream.ts';
import { ja } from '../../i18n/ja.ts';
import { en } from '../../i18n/en.ts';

test('image writing, compiler correction, and visual review name their actual work', () => {
	for (const strings of [ja, en]) {
		const attempt = { action: 'write_image_ddl', attempt: 1, max_attempts: 4 };
		assert.equal(runningStageLabel('previous stage', attempt, strings), strings.imageWritingDdl);
		assert.equal(runningStageLabel('previous stage', { ...attempt, asked_again: true }, strings), strings.imageRevisingDdl);
		assert.equal(runningStageLabel('previous stage', { ...attempt, action: 'review_image_ddl' }, strings), strings.imageReviewingDdl);
		assert.equal(runningStageLabel('previous stage', { ...attempt, action: 'select_image_catalog' }, strings), strings.imageSelectingCatalog);
	}
});

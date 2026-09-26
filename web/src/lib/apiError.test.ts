import assert from 'node:assert/strict';
import test from 'node:test';

import { describeApiErrorDetail } from './apiError.ts';
import { ja } from './i18n/ja.ts';

test('a failed pipeline action uses its saved phase instead of inventing a provider error', () => {
	const actual = describeApiErrorDetail({
		code: 'pipeline_author_action_required',
		message: 'pipeline author action required',
		current_view: {
			phase: { tag: 'failed', reason: 'stage1_failed' },
			document: null,
			delivery: null,
			result: null,
		},
	}, 409, ja);

	assert.equal(actual, '処理の結果を確認してください。 理由: 記述の解釈を完了できませんでした');
	assert.doesNotMatch(actual, /undefined|モデル提供元|pipeline author action required/);
});

test('a stage whose every model call timed out says so, and how often it tried', () => {
	// A run whose four Stage 1 attempts all timed out ended with only "the
	// description could not be interpreted".
	const failed = (stage: string) => describeApiErrorDetail({
		code: 'pipeline_author_action_required',
		current_view: {
			phase: { tag: 'failed', reason: 'stage1_failed' },
			provider_failure: { failure: 'transport_timeout', stage, attempt: 4, elapsed_ms: 300000 },
		},
	}, 409, ja);

	assert.equal(failed('stage1'), '処理の結果を確認してください。 理由: 記述の解釈を完了できませんでした（モデルの応答が制限時間内に返りませんでした。4回試しました）');
	// Another stage's failure does not explain this one.
	assert.equal(failed('stage2'), '処理の結果を確認してください。 理由: 記述の解釈を完了できませんでした');
});

test('a required pipeline patch points to the existing approval view', () => {
	const actual = describeApiErrorDetail({
		code: 'pipeline_patch_approval_required',
		message: 'pipeline patch approval required',
		current_view: { phase: { tag: 'awaiting_patch_approval' } },
	}, 409, ja);

	assert.equal(actual, ja.pipelinePatchHint);
});

test('a real provider failure keeps its localized stage, status, and provider message', () => {
	const actual = describeApiErrorDetail({
		code: 'provider_error',
		stage: 'interpret',
		provider_status: 502,
		message: 'upstream disconnected',
	}, 500, ja);

	assert.equal(actual, '解釈のモデル提供元がエラーを返しました（HTTP 502）。\nupstream disconnected');
});

test('the account deletions the server refuses read in the page language', () => {
	assert.equal(describeApiErrorDetail('user has history', 409, ja), ja.errorUserHasWorks);
	assert.equal(
		describeApiErrorDetail("other accounts' works derive from this user's works", 409, ja),
		ja.errorUserIsLineageOrigin
	);
});

test('the last administrator and a withheld model read in the page language', () => {
	assert.equal(describeApiErrorDetail('the last administrator cannot be removed', 409, ja), ja.errorLastAdministrator);
	// The same refusal arrives as a string from the routes that call a model and
	// as a code from the authoring pipeline.
	assert.equal(describeApiErrorDetail('model is not offered on this server', 403, ja), ja.errorModelNotOffered);
	assert.equal(
		describeApiErrorDetail({ code: 'model_not_offered', message: 'model not offered' }, 403, ja),
		ja.errorModelNotOffered
	);
});

test('a Score the server refuses reads with its headline in the page language', () => {
	assert.equal(
		describeApiErrorDetail('score is invalid: instructions.0: bad shape', 422, ja),
		ja.errorScoreInvalid('instructions.0: bad shape')
	);
	assert.equal(
		describeApiErrorDetail('score cannot be rendered: mark bounds exceed eight canvases', 422, ja),
		ja.errorScoreNotRenderable('mark bounds exceed eight canvases')
	);
});

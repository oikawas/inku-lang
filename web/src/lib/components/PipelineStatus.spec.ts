// @ts-nocheck -- this focused component test runs under Vitest, not svelte-check.
import assert from 'node:assert/strict';
import { render } from 'svelte/server';
import PipelineStatus from './PipelineStatus.svelte';
import { setLang } from '../i18n/index.svelte';
import { ja } from '../i18n/ja';
import { en } from '../i18n/en';

function view(patch: { tag: string; candidate: { source: string }; unread_words_not_kept?: { hole_id: string; words: string[] }[] } | null) {
	return render(PipelineStatus, { props: {
		patch, committedDdl: 'original', diagnostics: [], diagnosticsUnavailable: false,
		busy: false, reason: null, onApprove: () => {}, onDecline: () => {},
	} }).body;
}

for (const [language, strings, separator] of [['ja', ja, '、'], ['en', en, ', ']] as const) {
	test(`${language}: unread words appear in author order between comparison and actions`, () => {
		setLang(language);
		const html = view({ tag: 'awaiting_patch_approval', candidate: { source: 'proposal' }, unread_words_not_kept: [
			{ hole_id: 'one', words: ['青い', '<b>作者</b>'] },
			{ hole_id: 'two', words: ['  unchanged  '] },
		] });
		assert.ok(html.includes(strings.pipelineUnreadNotKeptTitle));
		assert.ok(html.includes(strings.pipelineUnreadNotKeptHint));
		const code = html.match(/<code(?:\s[^>]*)?>(.*?)<\/code>/s)?.[1];
		assert.ok(code);
		assert.ok(!code.includes('<b>'));
		assert.equal(code.replaceAll('&lt;', '<').replaceAll('&gt;', '>').replaceAll('&amp;', '&'),
			`青い${separator}<b>作者</b>${separator}  unchanged  `);
		assert.ok(html.indexOf('pipeline-comparison') < html.indexOf('pipeline-unread-not-kept'));
		assert.ok(html.indexOf('pipeline-unread-not-kept') < html.indexOf('pipeline-actions'));
	});

	test(`${language}: absent or empty unread words add no notice`, () => {
		setLang(language);
		for (const unread of [undefined, [], [{ hole_id: 'one', words: [] }]]) {
			const html = view({ tag: 'awaiting_patch_approval', candidate: { source: 'proposal' }, unread_words_not_kept: unread });
			assert.ok(!html.includes('pipeline-unread-not-kept'));
			assert.ok(!html.includes(strings.pipelineUnreadNotKeptTitle));
		}
		assert.ok(!view(null).includes('pipeline-unread-not-kept'));
	});
}

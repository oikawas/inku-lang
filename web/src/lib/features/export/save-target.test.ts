import assert from 'node:assert/strict';
import { test } from 'node:test';

import {
	triggerBrowserDownload,
	type BrowserDownloadEnvironment,
	type DownloadAnchor
} from './save-target.ts';

test('browser download keeps its object URL alive through the click task', () => {
	const events: string[] = [];
	const deferred: Array<() => void> = [];
	const anchor: DownloadAnchor = {
		href: '',
		download: '',
		hidden: false,
		click: () => events.push('click'),
		remove: () => events.push('remove')
	};
	const environment: BrowserDownloadEnvironment = {
		createObjectURL: () => {
			events.push('create');
			return 'blob:download';
		},
		revokeObjectURL: (url) => events.push(`revoke:${url}`),
		createAnchor: () => anchor,
		appendAnchor: () => events.push('append'),
		defer: (callback) => {
			events.push('defer');
			deferred.push(callback);
		}
	};

	triggerBrowserDownload(new Blob(['drawing']), 'drawing.svg', environment);

	assert.equal(anchor.href, 'blob:download');
	assert.equal(anchor.download, 'drawing.svg');
	assert.equal(anchor.hidden, true);
	assert.deepEqual(events, ['create', 'append', 'click', 'remove', 'defer']);
	assert.equal(deferred.length, 1);

	deferred[0]();
	assert.deepEqual(events, ['create', 'append', 'click', 'remove', 'defer', 'revoke:blob:download']);
});

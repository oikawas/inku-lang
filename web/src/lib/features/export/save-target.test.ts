import assert from 'node:assert/strict';
import { test } from 'node:test';

import {
	saveBlob,
	triggerBrowserDownload,
	type BrowserDownloadEnvironment,
	type DownloadAnchor
} from './save-target.ts';

test('explicit directory takes precedence and writes the blob there', async () => {
	const events: string[] = [];
	const blob = new Blob(['animation']);
	let writtenBlob: Blob | undefined;
	const directory = {
		name: 'Animation exports',
		queryPermission: async () => {
			events.push('query');
			return 'granted' as PermissionState;
		},
		requestPermission: async () => {
			events.push('request');
			return 'granted' as PermissionState;
		},
		getFileHandle: async (filename: string, options: { create?: boolean }) => {
			events.push(`file:${filename}:${String(options.create)}`);
			return {
				createWritable: async () => ({
					write: async (value: Blob) => {
						events.push('write');
						writtenBlob = value;
					},
					close: async () => events.push('close')
				})
			};
		}
	} as unknown as FileSystemDirectoryHandle;

	const outcome = await saveBlob(blob, 'animation.png', {
		enabled: false,
		directory
	});

	assert.deepEqual(outcome, { kind: 'folder', folderName: 'Animation exports' });
	assert.equal(writtenBlob, blob);
	assert.deepEqual(events, ['query', 'file:animation.png:true', 'write', 'close']);
});

test('explicit directory permission denial rejects without a browser fallback', async () => {
	let requested = false;
	let fileRequested = false;
	const directory = {
		name: 'Animation exports',
		queryPermission: async () => 'denied' as PermissionState,
		requestPermission: async () => {
			requested = true;
			return 'denied' as PermissionState;
		},
		getFileHandle: async () => {
			fileRequested = true;
			throw new Error('file access should not be attempted');
		}
	} as unknown as FileSystemDirectoryHandle;

	await assert.rejects(
		saveBlob(new Blob(['animation']), 'animation.png', { directory }),
		/permission was denied/i
	);
	assert.equal(requested, true);
	assert.equal(fileRequested, false);
});

test('explicit directory write failure is propagated without a browser fallback', async () => {
	const writeError = new Error('disk full');
	let closed = false;
	let aborted = false;
	const directory = {
		name: 'Animation exports',
		queryPermission: async () => 'granted' as PermissionState,
		getFileHandle: async () => ({
			createWritable: async () => ({
				write: async () => { throw writeError; },
				close: async () => { closed = true; },
				abort: async () => { aborted = true; }
			})
		})
	} as unknown as FileSystemDirectoryHandle;

	await assert.rejects(
		saveBlob(new Blob(['animation']), 'animation.png', { directory }),
		(error) => error === writeError
	);
	assert.equal(closed, false);
	assert.equal(aborted, true);
});

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

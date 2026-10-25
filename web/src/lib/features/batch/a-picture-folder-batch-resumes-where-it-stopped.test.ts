import assert from 'node:assert/strict';
import { test } from 'node:test';

const identity = <T>(value: T): T => value;
const stateShim = identity as (<T>(value: T) => T) & { raw: <T>(value: T) => T };
stateShim.raw = identity;
const runeHost = globalThis as unknown as Record<string, unknown>;
runeHost.$state = stateShim;
runeHost.$derived = identity;

const { ImageFolderBatch } = await import('./image-folder.svelte.ts');
const {
	folderNameOf, loadFolderHistory, pictureKey, picturesOfFolder, rememberFolder, saveFolderHistory,
	IMAGE_FOLDER_HISTORY_LIMIT,
} = await import('./image-folder.ts');
type ImageFolderRecord = import('./image-folder.ts').ImageFolderRecord;
type BatchSource = import('./image-folder.ts').BatchSource;
type FolderFile = import('./image-folder.ts').FolderFile;

function file(path: string, size = 100, lastModified = 1): FolderFile {
	return { name: path.split('/').at(-1) ?? path, size, lastModified, webkitRelativePath: path };
}

function memoryStore(history: ImageFolderRecord[] = []) {
	const saved = { history, source: 'text' as BatchSource, writes: 0 };
	return {
		saved,
		store: {
			loadHistory: () => saved.history,
			saveHistory: (next: readonly ImageFolderRecord[]) => { saved.history = [...next]; saved.writes += 1; },
			loadSource: () => saved.source,
			saveSource: (source: BatchSource) => { saved.source = source; },
		},
	};
}

const neverLost = { stopsTheRun: () => false, describe: (cause: unknown) => String(cause) };

test('a picked folder keeps only its pictures, in the order Finder shows them', () => {
	const files = [
		file('trip/10.jpg'), file('trip/2.JPG'), file('trip/notes.txt'), file('trip/.DS_Store'),
		file('trip/._2.jpg'), file('trip/b/1.png'), file('trip/1.tiff'), file('trip/.hidden/3.gif'),
	];
	assert.deepEqual(picturesOfFolder(files).map((item) => item.webkitRelativePath),
		['trip/1.tiff', 'trip/2.JPG', 'trip/10.jpg', 'trip/b/1.png']);
	assert.equal(folderNameOf(files), 'trip');
});

test('the same path with another size or time is another picture', () => {
	assert.notEqual(pictureKey(file('trip/1.jpg', 100, 1)), pictureKey(file('trip/1.jpg', 101, 1)));
	assert.notEqual(pictureKey(file('trip/1.jpg', 100, 1)), pictureKey(file('trip/1.jpg', 100, 2)));
});

test('the history keeps one entry per folder, newest first, at most ten', () => {
	let history: ImageFolderRecord[] = [];
	for (let index = 0; index < 12; index += 1) {
		history = rememberFolder(history, { name: `f${index}`, total: 1, done: [], failures: [], updatedAt: index });
	}
	history = rememberFolder(history, { name: 'f5', total: 2, done: [], failures: [], updatedAt: 99 });
	assert.equal(history.length, IMAGE_FOLDER_HISTORY_LIMIT);
	assert.deepEqual(history.slice(0, 3).map((item) => item.name), ['f5', 'f11', 'f10']);
	assert.equal(history.filter((item) => item.name === 'f5').length, 1);
});

test('a stored history that is broken or missing reads as empty, and a full store does not throw', () => {
	assert.deepEqual(loadFolderHistory({ getItem: () => '{not json', setItem: () => {} }), []);
	assert.deepEqual(loadFolderHistory({ getItem: () => JSON.stringify([{ name: 1 }]), setItem: () => {} }), []);
	assert.deepEqual(loadFolderHistory(null), []);
	saveFolderHistory([], { getItem: () => null, setItem: () => { throw new Error('quota'); } });
});

test('a stopped run resumes from the next picture after the folder is picked again', async () => {
	const { saved, store } = memoryStore();
	const folder = new ImageFolderBatch<FolderFile>(store);
	const files = [file('trip/1.jpg'), file('trip/2.jpg'), file('trip/3.jpg')];
	folder.pick(files);
	const painted: string[] = [];
	await folder.run({
		...neverLost, fromStart: true,
		paintPicture: async (picture) => {
			painted.push(picture.webkitRelativePath ?? '');
			if (painted.length === 2) folder.stop();
		},
	});
	// The second picture finished before the stop was seen; it is saved, so done.
	assert.deepEqual(painted, ['trip/1.jpg', 'trip/2.jpg']);
	assert.equal(folder.interrupted, true);
	assert.equal(saved.history[0].done.length, 2);

	// A reload: a new owner reads the history, and the author picks the folder again.
	const again = new ImageFolderBatch<FolderFile>(store);
	again.pick(files);
	assert.equal(again.doneCount, 2);
	assert.deepEqual(again.pending.map((item) => item.webkitRelativePath), ['trip/3.jpg']);
	const resumed: string[] = [];
	await again.run({ ...neverLost, fromStart: false, paintPicture: async (picture) => { resumed.push(picture.webkitRelativePath ?? ''); } });
	assert.deepEqual(resumed, ['trip/3.jpg']);
	assert.equal(again.interrupted, false);
	assert.equal(again.pending.length, 0);
});

test('a picture that fails is reported, the run goes on, and resume paints it again', async () => {
	const { store } = memoryStore();
	const folder = new ImageFolderBatch<FolderFile>(store);
	folder.pick([file('f/1.jpg'), file('f/2.jpg'), file('f/3.jpg')]);
	await folder.run({
		...neverLost, fromStart: true,
		paintPicture: async (picture) => { if (picture.name === '2.jpg') throw new Error('no instructions'); },
	});
	assert.equal(folder.success, 2);
	assert.deepEqual(folder.failures.map((item) => [item.path, item.message]), [['f/2.jpg', 'Error: no instructions']]);
	assert.deepEqual(folder.pending.map((item) => item.name), ['2.jpg']);

	await folder.run({ ...neverLost, fromStart: false, paintPicture: async () => {} });
	assert.deepEqual(folder.failures, []);
	assert.equal(folder.pending.length, 0);
});

test('a lost Server stops the run at that picture instead of failing it', async () => {
	const { store } = memoryStore();
	const folder = new ImageFolderBatch<FolderFile>(store);
	folder.pick([file('f/1.jpg'), file('f/2.jpg'), file('f/3.jpg')]);
	const tried: string[] = [];
	await folder.run({
		fromStart: true,
		stopsTheRun: (cause) => cause instanceof TypeError,
		describe: () => 'Failed to fetch',
		paintPicture: async (picture) => {
			tried.push(picture.name);
			if (picture.name === '2.jpg') throw new TypeError('Failed to fetch');
		},
	});
	assert.deepEqual(tried, ['1.jpg', '2.jpg']);
	assert.equal(folder.interrupted, true);
	assert.equal(folder.stopReason, 'Failed to fetch');
	assert.deepEqual(folder.failures, []);
	assert.deepEqual(folder.pending.map((item) => item.name), ['2.jpg', '3.jpg']);
});

test('painting from the start forgets the done pictures of that folder only', async () => {
	const other: ImageFolderRecord = { name: 'other', total: 1, done: ['x'], failures: [], updatedAt: 1 };
	const { saved, store } = memoryStore([other]);
	const folder = new ImageFolderBatch<FolderFile>(store);
	const files = [file('f/1.jpg'), file('f/2.jpg')];
	folder.pick(files);
	await folder.run({ ...neverLost, fromStart: true, paintPicture: async () => {} });
	const painted: string[] = [];
	await folder.run({ ...neverLost, fromStart: true, paintPicture: async (picture) => { painted.push(picture.name); } });
	assert.deepEqual(painted, ['1.jpg', '2.jpg']);
	assert.deepEqual(saved.history.find((item) => item.name === 'other')?.done, ['x']);
});

test('the switch is remembered and does not move during a run', async () => {
	const { saved, store } = memoryStore();
	const folder = new ImageFolderBatch<FolderFile>(store);
	folder.setSource('image');
	assert.equal(saved.source, 'image');
	folder.pick([file('f/1.jpg')]);
	let release = () => {};
	const run = folder.run({ ...neverLost, fromStart: true, paintPicture: () => new Promise<void>((resolve) => { release = resolve; }) });
	folder.setSource('text');
	assert.equal(folder.source, 'image');
	release();
	await run;
});

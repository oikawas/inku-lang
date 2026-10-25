// Run with: node --import ./scripts/ts-extensionless-resolve.mjs --test src/lib/features/image-provenance/image-provenance.test.ts
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';

import { readExifFacts } from './exif.ts';
import { imageProvenanceText, parseImageProvenanceOptions } from './provenance.ts';

const LABELS = { fileName: 'ファイル名', takenAt: '撮影日時', camera: 'カメラ', lens: 'レンズ', exposure: '露出' };
const ALL = { includeFileName: true, includeExif: true };

type Field = { tag: number; type: number; count: number; data: number[] };

/** A TIFF with IFD0 (+ an Exif IFD, + a GPS IFD) in the given byte order. */
function tiff(little: boolean, ifd0: Field[], exif: Field[], gps: Field[] = []): Uint8Array {
	const out: number[] = [];
	const u16 = (v: number) => (little ? [v & 0xff, v >> 8] : [v >> 8, v & 0xff]);
	const u32 = (v: number) => (little
		? [v & 0xff, (v >> 8) & 0xff, (v >> 16) & 0xff, (v >>> 24) & 0xff]
		: [(v >>> 24) & 0xff, (v >> 16) & 0xff, (v >> 8) & 0xff, v & 0xff]);
	const ifdSize = (n: number) => 2 + n * 12 + 4;
	const ifd0Fields = [...ifd0, { tag: 0x8769, type: 4, count: 1, data: [] }, ...(gps.length ? [{ tag: 0x8825, type: 4, count: 1, data: [] }] : [])];
	const ifd0At = 8;
	const exifAt = ifd0At + ifdSize(ifd0Fields.length);
	const gpsAt = exifAt + ifdSize(exif.length);
	let dataAt = gpsAt + (gps.length ? ifdSize(gps.length) : 0);
	const data: number[] = [];
	const writeIfd = (fields: Field[]) => {
		out.push(...u16(fields.length));
		for (const field of fields) {
			out.push(...u16(field.tag), ...u16(field.type), ...u32(field.count));
			if (field.tag === 0x8769) out.push(...u32(exifAt));
			else if (field.tag === 0x8825) out.push(...u32(gpsAt));
			else if (field.data.length <= 4) out.push(...field.data, ...Array(4 - field.data.length).fill(0));
			else { out.push(...u32(dataAt)); data.push(...field.data); dataAt += field.data.length; }
		}
		out.push(...u32(0));
	};
	out.push(...(little ? [0x49, 0x49] : [0x4d, 0x4d]), ...u16(42), ...u32(ifd0At));
	writeIfd(ifd0Fields);
	writeIfd(exif);
	if (gps.length) writeIfd(gps);
	out.push(...data);
	return new Uint8Array(out);
}

function ascii(text: string): number[] { return [...new TextEncoder().encode(text), 0]; }
function rational(little: boolean, n: number, d: number): number[] {
	const u32 = (v: number) => (little
		? [v & 0xff, (v >> 8) & 0xff, (v >> 16) & 0xff, (v >>> 24) & 0xff]
		: [(v >>> 24) & 0xff, (v >> 16) & 0xff, (v >> 8) & 0xff, v & 0xff]);
	return [...u32(n), ...u32(d)];
}
function short(little: boolean, v: number): number[] { return little ? [v & 0xff, v >> 8] : [v >> 8, v & 0xff]; }

function camera(little: boolean, withGps = false): Uint8Array {
	const text = (tag: number, value: string): Field => ({ tag, type: 2, count: ascii(value).length, data: ascii(value) });
	return tiff(
		little,
		[text(0x010f, 'Apple'), text(0x0110, 'iPhone 15 Pro'), text(0x0132, '2026:10:21 09:00:00')],
		[
			{ tag: 0x829a, type: 5, count: 1, data: rational(little, 1, 120) },
			{ tag: 0x829d, type: 5, count: 1, data: rational(little, 178, 100) },
			{ tag: 0x8827, type: 3, count: 1, data: short(little, 64) },
			text(0x9003, '2026:10:20 14:32:05'),
			{ tag: 0x920a, type: 5, count: 1, data: rational(little, 686, 100) },
			text(0xa434, 'iPhone 15 Pro back camera 6.86mm f/1.78'),
		],
		withGps ? [{ tag: 0x0002, type: 5, count: 3, data: [...rational(little, 35, 1), ...rational(little, 40, 1), ...rational(little, 52, 1)] }] : [],
	);
}

function jpeg(exif: Uint8Array): ArrayBuffer {
	const payload = [0x45, 0x78, 0x69, 0x66, 0, 0, ...exif];
	const length = payload.length + 2;
	// SOI, an APP0 to skip, APP1 Exif, then SOS.
	const bytes = [0xff, 0xd8, 0xff, 0xe0, 0, 4, 0, 0, 0xff, 0xe1, length >> 8, length & 0xff, ...payload, 0xff, 0xda, 0, 2];
	return new Uint8Array(bytes).buffer;
}

function png(exif: Uint8Array): ArrayBuffer {
	const be32 = (v: number) => [(v >>> 24) & 0xff, (v >> 16) & 0xff, (v >> 8) & 0xff, v & 0xff];
	const chunk = (type: string, body: number[]) => [...be32(body.length), ...new TextEncoder().encode(type), ...body, 0, 0, 0, 0];
	return new Uint8Array([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, ...chunk('IHDR', Array(13).fill(0)), ...chunk('eXIf', [...exif]), ...chunk('IEND', [])]).buffer;
}

const EXPECTED = {
	takenAt: '2026:10:20 14:32:05',
	make: 'Apple',
	model: 'iPhone 15 Pro',
	lens: 'iPhone 15 Pro back camera 6.86mm f/1.78',
	fNumber: 1.78,
	exposureTime: 1 / 120,
	iso: 64,
	focalLength: 6.86,
};

test('the shooting facts are read from a JPEG in either byte order, a PNG eXIf chunk and a TIFF', () => {
	assert.deepEqual(readExifFacts(jpeg(camera(false))), EXPECTED);
	assert.deepEqual(readExifFacts(jpeg(camera(true))), EXPECTED);
	assert.deepEqual(readExifFacts(png(camera(false))), EXPECTED);
	const file = camera(true);
	assert.deepEqual(readExifFacts(file.buffer.slice(file.byteOffset, file.byteOffset + file.byteLength)), EXPECTED);
});

test('the location never reaches the facts, even when the image carries GPS', () => {
	const facts = readExifFacts(jpeg(camera(false, true)));
	assert.deepEqual(facts, EXPECTED);
	const text = imageProvenanceText('a.jpg', facts, ALL, LABELS);
	assert.doesNotMatch(text, /35|139|GPS|位置/);
});

test('an image without Exif, or bytes that are not an image, give no facts rather than an error', () => {
	assert.equal(readExifFacts(new Uint8Array([0x47, 0x49, 0x46, 0x38, 0x39, 0x61, 0, 0]).buffer), null);
	assert.equal(readExifFacts(new Uint8Array([0xff, 0xd8, 0xff, 0xda, 0, 2, 0, 0]).buffer), null);
	assert.equal(readExifFacts(new Uint8Array([1, 2, 3]).buffer), null);
	// A truncated APP1 is not read past its end.
	const broken = new Uint8Array(jpeg(camera(false))).slice(0, 40).buffer;
	assert.equal(readExifFacts(broken), null);
});

test('the note has the file name first, then one line per shooting fact', () => {
	const facts = readExifFacts(jpeg(camera(false)));
	assert.equal(
		imageProvenanceText('IMG_1234.jpg', facts, ALL, LABELS),
		[
			'ファイル名: IMG_1234.jpg',
			'撮影日時: 2026:10:20 14:32:05',
			'カメラ: Apple iPhone 15 Pro',
			'レンズ: iPhone 15 Pro back camera 6.86mm f/1.78',
			'露出: f/1.8 · 1/120 s · ISO 64 · 6.9 mm',
		].join('\n'),
	);
	// A model that already names the maker does not repeat it.
	assert.equal(imageProvenanceText('x.jpg', { make: 'Canon', model: 'Canon EOS R5' }, ALL, LABELS), 'ファイル名: x.jpg\nカメラ: Canon EOS R5');
	assert.equal(imageProvenanceText('x.jpg', { exposureTime: 2 }, ALL, LABELS), 'ファイル名: x.jpg\n露出: 2 s');
});

test('each setting leaves its part out, and with both off the note stays empty', () => {
	const facts = readExifFacts(jpeg(camera(false)));
	assert.doesNotMatch(imageProvenanceText('IMG_1234.jpg', facts, { includeFileName: false, includeExif: true }, LABELS), /ファイル名/);
	assert.equal(imageProvenanceText('IMG_1234.jpg', facts, { includeFileName: true, includeExif: false }, LABELS), 'ファイル名: IMG_1234.jpg');
	assert.equal(imageProvenanceText('IMG_1234.jpg', facts, { includeFileName: false, includeExif: false }, LABELS), '');
	assert.equal(imageProvenanceText('IMG_1234.jpg', null, ALL, LABELS), 'ファイル名: IMG_1234.jpg');
});

test('both settings default on, and a damaged stored value falls back to the defaults', () => {
	assert.deepEqual(parseImageProvenanceOptions(null), ALL);
	assert.deepEqual(parseImageProvenanceOptions('{'), ALL);
	assert.deepEqual(parseImageProvenanceOptions('{"includeExif":false}'), { includeFileName: true, includeExif: false });
	assert.deepEqual(parseImageProvenanceOptions('{"includeFileName":"no"}'), ALL);
});

test('a chosen image fills the note unless the author typed one, and the settings page is a browser-only tab', () => {
	const read = (path: string) => readFileSync(new URL(path, import.meta.url), 'utf8');
	const state = read('../work/state.svelte.ts');
	assert.match(state, /void fillImageProvenance\(file, ordinal\);/);
	assert.match(state, /if \(ordinal !== imageUploadOrdinal \|\| \(imageProvenanceTyped && imageProvenance\.trim\(\)\)\) return;/);
	assert.match(state, /imageProvenanceTyped = false;/);
	assert.match(read('../../components/InputPanel.svelte'), /oninput=\{\(\) => onImageProvenanceInput\?\.\(\)\}/);
	const navigation = read('../settings/navigation-state.svelte.ts');
	assert.match(navigation, /const BROWSER_ONLY_SETTINGS_TABS: readonly SettingsTab\[\] = \['image'\];/);
	assert.match(read('../../components/SettingsModal.svelte'), /\{:else if settingsTab === 'image'\}\s*<ImageSettings \/>/);
});

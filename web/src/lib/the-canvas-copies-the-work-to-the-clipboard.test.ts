// Run with: npm run test:unit  (node:test, no test dependency)
//
// The canvas copies the work on it to the clipboard as a bitmap: the picture
// alone or the share card, at the height chosen in Settings > Export >
// Clipboard. The browser allows it only on a secure connection.
import assert from 'node:assert/strict';
import { test } from 'node:test';

import {
	CLIPBOARD_HEIGHT_MAX,
	CLIPBOARD_HEIGHT_MIN,
	clipboardUnavailableReason,
	DEFAULT_CLIPBOARD_EXPORT_SETTINGS,
	normalizeClipboardExportSettings,
	parseClipboardExportSettings
} from './clipboardExport.ts';
import { cardExportRequestBody, DEFAULT_CARD_EXPORT_SETTINGS } from './cardExportRequest.ts';

test('a browser that never chose copies the picture alone at 1080 px', () => {
	assert.deepEqual(DEFAULT_CLIPBOARD_EXPORT_SETTINGS, { format: 'image', height: 1080 });
	assert.deepEqual(parseClipboardExportSettings(null), DEFAULT_CLIPBOARD_EXPORT_SETTINGS);
	assert.deepEqual(parseClipboardExportSettings('not json'), DEFAULT_CLIPBOARD_EXPORT_SETTINGS);
});

test('a stored choice is kept, and a height out of range is brought into it', () => {
	assert.deepEqual(normalizeClipboardExportSettings({ format: 'card', height: 2048 }), { format: 'card', height: 2048 });
	assert.equal(normalizeClipboardExportSettings({ height: 10 }).height, CLIPBOARD_HEIGHT_MIN);
	assert.equal(normalizeClipboardExportSettings({ height: 100000 }).height, CLIPBOARD_HEIGHT_MAX);
	assert.equal(normalizeClipboardExportSettings({ format: 'poster' }).format, 'image');
});

test('an insecure page is told why it cannot copy', () => {
	// The page the author uses (http://192.168.0.89:5173) is this case.
	assert.equal(clipboardUnavailableReason({ isSecureContext: false, canWrite: false, hasClipboardItem: false }), 'insecure');
	assert.equal(clipboardUnavailableReason({ isSecureContext: true, canWrite: false, hasClipboardItem: true }), 'unsupported');
	assert.equal(clipboardUnavailableReason({ isSecureContext: true, canWrite: true, hasClipboardItem: true }), null);
});

test('the card request carries the chosen height, and a download sends none', () => {
	assert.deepEqual(cardExportRequestBody('w', DEFAULT_CARD_EXPORT_SETTINGS, 1600), { id: 'w', layout: 'square', seal: true, height: 1600 });
	assert.deepEqual(cardExportRequestBody('w', DEFAULT_CARD_EXPORT_SETTINGS), { id: 'w', layout: 'square', seal: true });
});

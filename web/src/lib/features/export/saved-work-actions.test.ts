import assert from 'node:assert/strict';
import { existsSync } from 'node:fs';
import { registerHooks } from 'node:module';
import { test } from 'node:test';
import { ExportSaveError, exportFallbackReason, exportSaveFailure } from './save-result.ts';
import { snapshotSavedWorkExport } from './saved-work.ts';
import type { SaveOutcome } from './save-target.ts';

// Exercise the real action chain. Replace only browser/file/network boundaries
// and contact-sheet rasterization; no image generation or real download occurs.
const saves: Array<{ filename: string; options: unknown }> = [];
const outcomes: SaveOutcome[] = [];
let contactSheetFailure: Error | null = null;
Object.assign(globalThis, {
	__exportContactSheetFailure: () => contactSheetFailure,
	__exportSave: async (_blob: Blob, filename: string, options: unknown) => {
		saves.push({ filename, options });
		assert.ok(outcomes.length, 'each save must have a supplied outcome');
		return outcomes.shift();
	},
	document: { createElement: () => ({
		getContext: () => ({ drawImage() {}, fillRect() {} }),
		toBlob: (done: (blob: Blob) => void) => done(new Blob(['png'], { type: 'image/png' })),
	}) },
	Image: class {
		onload?: () => void;
		set src(_value: string) { this.onload?.(); }
	},
});
const moduleUrl = (source: string) => `data:text/javascript,${encodeURIComponent(source)}`;
const stubs = new Map([
	['$lib/i18n/index.svelte', 'export const t = () => ({ savedWorkExportUnavailable: "unavailable", historyContactSheetTitle: "Works", historyContactSheetSubtitle: () => "Works" });'],
	['$lib/features/export/settings.svelte', 'export const exportSettings = { pngAlphaWhite: false, card: {} };'],
	['./settings.svelte', 'export const exportSettings = { pngAlphaWhite: false, card: {} };'],
	['$lib/features/export/download-folder.svelte', 'export const downloadFolderSettings = { enabled: true };'],
	['./download-folder.svelte', 'export const downloadFolderSettings = { enabled: true };'],
	['./features/export/download-folder.svelte.ts', 'export const downloadFolderSettings = { enabled: true };'],
	['$lib/features/export/save-target', 'export const saveBlob = (...args) => globalThis.__exportSave(...args);'],
	['./save-target', 'export const saveBlob = (...args) => globalThis.__exportSave(...args);'],
	['./features/export/save-target.ts', 'export const saveBlob = (...args) => globalThis.__exportSave(...args);'],
	['$lib/pngMetadata', 'export const withPngCaptureDate = async blob => blob;'],
	['$lib/plugins/system/canvas-aspect', 'export const DEFAULT_CANVAS_ASPECT_ID = "square"; export const normalizeCanvasAspectId = () => "square"; export const getCanvasAspectOption = () => ({ ratioW: 1, ratioH: 1 });'],
	['$lib/features/contact-sheet/run', 'export async function runContactSheet(_variant, deps) { await deps.save(new Blob(["sheet"]), "sheet.png"); const error = globalThis.__exportContactSheetFailure(); if (error) throw error; await deps.save(new Blob(["notes"]), "notes.md"); }'],
]);
const hooks = registerHooks({
	resolve(specifier, context, nextResolve) {
		const source = stubs.get(specifier);
		if (source) return { url: moduleUrl(source), shortCircuit: true };
		if (specifier.startsWith('$lib/')) {
			const base = new URL(`../../${specifier.slice(5)}`, import.meta.url);
			const url = existsSync(new URL(`${base.href}.ts`)) ? `${base.href}.ts` : `${base.href}/index.ts`;
			return nextResolve(url, context);
		}
		return nextResolve(specifier, context);
	},
});
const { makeSavedWorkExportActions } = await import('./saved-work-actions.ts');
const { DEFAULT_ANIMATION_EXPORT_SETTINGS } = await import('../../animationExport.ts');
hooks.deregister();

test('all saved-work export formats carry folder fallback outcomes to their menu caller', async () => {
	const item = { id: 'saved', at: 1, input: 'Work', svg: '<svg />', score: {} };
	const snapshot = snapshotSavedWorkExport({ kind: 'current', works: [item] });
	assert.ok(snapshot);
	const actions = makeSavedWorkExportActions({
		apiFetch: async (path) => path.includes('/lineage?')
			? Response.json({ nodes: [{ history: item }] })
			: path.endsWith('/ddl-export') ? Response.json({ ddl: 'work' }) : new Response('file'),
		catalogName: () => '', formatDate: () => '', previewText: (text) => text,
	});
	const formats = [
		() => actions.onDownloadSVG('display', snapshot),
		() => actions.onDownloadPNG(1080, snapshot),
		() => actions.onDownloadDdl(snapshot),
		() => actions.onDownloadCard('saved', snapshot),
		() => actions.onDownloadAnimation(snapshot, DEFAULT_ANIMATION_EXPORT_SETTINGS),
	];
	for (const reason of ['denied', 'failed'] as const) {
		for (const run of formats) {
			outcomes.push({ kind: 'browser', reason });
			assert.equal(exportFallbackReason(await run()), reason);
		}
		outcomes.push({ kind: 'browser', reason }, { kind: 'folder', folderName: 'Exports' });
		const result = await actions.onDownloadContactSheet(snapshot, 'ai');
		assert.equal(result.length, 2);
		assert.equal(exportFallbackReason(result), reason);
	}
	assert.equal(outcomes.length, 0);
	assert.equal(saves.length, 14);
	assert.ok(saves.every((save) => (save.options as { enabled: boolean }).enabled));
});

test('a later contact-sheet page failure keeps the earlier fallback and original error for the menu', async () => {
	const items = Array.from({ length: 29 }, (_, index) => ({
		id: `saved-${index}`, at: index, input: 'Work', svg: '<svg />', score: {},
	}));
	const snapshot = snapshotSavedWorkExport({ kind: 'selection', works: items });
	assert.ok(snapshot);
	const actions = makeSavedWorkExportActions({
		apiFetch: async (path) => Response.json({ nodes: [{ history: items.find((item) => path.includes(`/history/${item.id}/lineage?`)) }] }),
		catalogName: () => '', formatDate: () => '', previewText: (text) => text,
	});
	const cause = new Error('failed to rasterise artwork svg');
	contactSheetFailure = cause;
	try {
		for (const reason of ['denied', 'failed'] as const) {
			outcomes.push({ kind: 'browser', reason });
			await assert.rejects(actions.onDownloadContactSheet(snapshot, 'review'), (error) => {
				assert.ok(error instanceof ExportSaveError);
				assert.equal(error.cause, cause);
				assert.deepEqual(exportSaveFailure(error), { error: cause.message, fallbackReason: reason });
				assert.deepEqual(error.outcomes, [{ kind: 'browser', reason }]);
				return true;
			});
		}
	} finally {
		contactSheetFailure = null;
	}
	assert.equal(outcomes.length, 0);
});

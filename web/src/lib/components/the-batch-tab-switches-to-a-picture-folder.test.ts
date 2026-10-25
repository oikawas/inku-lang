// Run with: npm run test:unit  (node:test, no DOM dependency)
//
// The batch tab's switch between descriptions and a picture folder. The run
// itself is driven in features/batch/a-picture-folder-batch-resumes-where-it-stopped.test.ts;
// this reads the wiring that puts it on the screen.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';

const INPUT_PANEL = readFileSync(new URL('./InputPanel.svelte', import.meta.url), 'utf8');
const FOLDER_PANEL = readFileSync(new URL('./ImageFolderBatchPanel.svelte', import.meta.url), 'utf8');
const WORK = readFileSync(new URL('../features/work/state.svelte.ts', import.meta.url), 'utf8');

test('the batch tab has a switch, and the description side is the panel it always was', () => {
	assert.match(INPUT_PANEL, /role="switch"[\s\S]*?aria-checked=\{imageFolder\.source === 'image'\}/);
	assert.match(INPUT_PANEL, /\{#if imageFolder\.source === 'image'\}\s*<ImageFolderBatchPanel[\s\S]*?\{:else\}\s*<BatchPanel/);
	assert.match(INPUT_PANEL, /disabled=\{batchRunning \|\| batchResuming \|\| folderRunning\}/);
});

test('the picture side shows the picture tab settings', () => {
	assert.match(INPUT_PANEL, /pictureConditions = \$derived\(inputMode === 'image' \|\| \(inputMode === 'batch' && imageFolder\.source === 'image'\)\)/);
	assert.match(FOLDER_PANEL, /\{@render settings\?\.\(\)\}/);
	assert.match(INPUT_PANEL, /<ImageFolderBatchPanel[\s\S]*?settings=\{inputConditionRows\}/);
});

test('a folder is picked in the browser dialog, not typed as a path', () => {
	assert.match(FOLDER_PANEL, /type="file"\s*multiple\s*\{\.\.\.\{ webkitdirectory: true \}\}/);
	assert.doesNotMatch(FOLDER_PANEL, /type="text"/);
});

test('each picture goes the picture tab way, with its settings', () => {
	const paint = WORK.slice(WORK.indexOf('async function paintPictureFile'), WORK.indexOf('function pictureRunLost'));
	assert.match(paint, /provenanceOfFile\(file\)/);
	assert.match(paint, /uploadImage\(file, signal\)/);
	assert.match(paint, /visionProvider\(\), deps\.models\.visionModel\(\)/);
	assert.match(paint, /pipelineController\.fromImage\(image\.image_id, provenance, imageCanvasAspectId/);
	assert.match(paint, /canvas_aspect: imageCanvasAspectId === 'image' \? image\.nearest_format_id : imageCanvasAspectId/);
});

test('the stop button stops the picture batch', () => {
	assert.match(WORK, /if \(activeRunMode === 'image-batch'\) \{\s*imageFolder\.stop\(\);/);
});

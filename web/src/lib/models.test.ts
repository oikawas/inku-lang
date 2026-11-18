// Run with: npm run test:unit  (node:test, no test dependency)
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';

import { modelCardName, modelDisplayName, modelShortName, modelStripName, pickerSelection, splitModelReference, type ProviderGroup } from './models.ts';

const GROUPS: ProviderGroup[] = [
	{
		id: 'nim',
		label: 'NVIDIA NIM (Cloud)',
		models: [
			{ id: 'google/gemma-4-31b-it', label: 'google/gemma-4-31b-it', qualified_id: 'nim:google/gemma-4-31b-it' },
			{ id: 'plain-model', label: 'Plain Model', qualified_id: 'nim:plain-model' },
		],
	} as ProviderGroup,
];

test('a disconnected ChatGPT reference stays qualified even with an empty explicit catalog', () => {
	assert.deepEqual(splitModelReference('chatgpt:model', []), { provider: 'chatgpt', model: 'model' });
	assert.equal(pickerSelection(GROUPS, 'chatgpt:plain-model').selected, null);
});

test('the display name comes from core and the short name is the API id', () => {
	const long = modelDisplayName('nim:plain-model', GROUPS);
	const short = modelShortName('nim:plain-model', GROUPS);
	assert.equal(long, 'NVIDIA NIM (Cloud) / plain-model');
	assert.equal(short, 'plain-model');
});

test('Sign in with ChatGPT uses the core display and history labels', () => {
	assert.equal(modelDisplayName('chatgpt:model'), 'SIWC / model');
	assert.equal(modelShortName('chatgpt:model'), 'model');
	assert.equal(modelStripName('chatgpt:model'), 'SIWC model');
});

test('library cards show the provider and complete API id without spaces', async () => {
	assert.equal(modelCardName('chatgpt:model'), 'SIWC/model');
	assert.equal(modelCardName('nim:google/gemma-4-31b-it'), 'NVIDIA NIM (Cloud)/google/gemma-4-31b-it');
	const { configureModelReferences, loadModelReferences } = await import('./modelReferences.ts');
	configureModelReferences(async () => Response.json({results:[
		{outcome:'ok', provider:'anthropic', model:'claude-opus-4-7', provider_label:'Claude API'},
		{outcome:'ok', provider:'chatgpt', model:'gpt-6.1-sol', provider_label:'Sign in with ChatGPT', provider_abbreviation:'SIWC'},
	]}));
	await loadModelReferences([{action:'resolve_display',ref:'anthropic:claude-opus-4-7'}, {action:'resolve_display',ref:'chatgpt:gpt-6.1-sol'}]);
	assert.equal(modelCardName('anthropic:claude-opus-4-7'), 'Claude API/claude-opus-4-7');
	assert.equal(modelCardName('chatgpt:gpt-6.1-sol'), 'SIWC/gpt-6.1-sol');
});

test('model selection and administration show ids instead of saved labels', () => {
	const paths = ['./components/ModelCardPicker.svelte', './features/settings/ModelSelectionSettings.svelte',
		'./features/settings/ModelAdministrationSettings.svelte', './features/model-inspection/state.svelte.ts'];
	for (const path of paths) {
		const source = readFileSync(new URL(path, import.meta.url), 'utf8');
		assert.doesNotMatch(source, /\{(?:selected\?\.model|model)\.label\}/, path);
		assert.doesNotMatch(source, /label:\s*model\.label/, path);
		assert.doesNotMatch(source, /\.models\.find\([^\n]+\)\?\.label/, path);
		assert.doesNotMatch(source, /aria-label=\{`\$\{model\.label\}/, path);
		assert.match(source, /model\.id/, path);
	}
});

test('the vendor prefix of a served id is retained', () => {
	assert.equal(modelShortName('nim:google/gemma-4-31b-it', GROUPS), 'google/gemma-4-31b-it');
});

test('all slashes in a served id are retained', () => {
	assert.equal(modelShortName('nim:a/b/c', GROUPS), 'a/b/c');
});

test('nothing in, nothing out', () => {
	assert.equal(modelShortName(''), '');
	assert.equal(modelShortName(null), '');
	assert.equal(modelShortName(undefined), '');
	assert.equal(modelShortName('   '), '');
});

test('the name is never truncated', () => {
	// Two models that differ only in their tail must not come back equal: a
	// truncating short name would make gemma-4-31b-it and gemma-4-31b-it-v2 the
	// same word on the card.
	const a = modelShortName('nim:google/gemma-4-31b-it', GROUPS);
	const b = modelShortName('nim:google/gemma-4-31b-it-v2', GROUPS);
	assert.notEqual(a, b);
	assert.equal(b, 'google/gemma-4-31b-it-v2');
});

test('I-297: the picker knows when it has nothing to offer, and when the stored id is not offered', () => {
	const empty = [{ id: 'nim', label: 'NVIDIA NIM (Cloud)', models: [] } as unknown as ProviderGroup];
	assert.deepEqual(pickerSelection(empty, 'nim:google/gemma-4-31b-it'), { groups: [], selected: null, notInList: true });
	assert.deepEqual(pickerSelection([], ''), { groups: [], selected: null, notInList: false });

	const found = pickerSelection(GROUPS, 'nim:google/gemma-4-31b-it');
	assert.equal(found.selected?.model.id, 'google/gemma-4-31b-it');
	assert.equal(found.notInList, false);
	assert.equal(pickerSelection(GROUPS, 'plain-model').selected?.model.label, 'Plain Model');

	// Unpublished, retired, or from a provider no longer listed: named as it stands, marked.
	const gone = pickerSelection(GROUPS, 'nim:google/gemma-3-27b-it');
	assert.equal(gone.selected, null);
	assert.equal(gone.notInList, true);
	assert.equal(gone.groups.length, GROUPS.filter((group) => group.models.length > 0).length);
});

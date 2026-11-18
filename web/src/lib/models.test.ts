// Run with: npm run test:unit  (node:test, no test dependency)
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';

import { modelReadiness, missingApiKey } from './model-readiness.ts';
import { modelDisplayName, modelShortName, modelStripName, pickerSelection, splitModelReference, type ProviderGroup } from './models.ts';

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

test('drawing readiness distinguishes unpublished models, missing keys, sign-in and loading', () => {
 const groups = [{id:'openai', label:'OpenAI', requires_api_key:true, api_key_set:false, models:[{id:'example', label:'example', qualified_id:'openai:example'}]}, {id:'local', label:'Local', requires_api_key:false, api_key_set:false, models:[{id:'local', label:'local', qualified_id:'local:local'}]}] as ProviderGroup[];
 assert.equal(missingApiKey(groups[0]), true);
 assert.equal(missingApiKey(groups[1]), false);
 assert.deepEqual(modelReadiness('ready', groups, 'openai:example', true, false), {kind:'missing_key_admin',action:'settings',provider:'openai'});
 assert.deepEqual(modelReadiness('ready', groups, 'openai:example', false, false), {kind:'missing_key_user',action:'choose',provider:'openai'});
 assert.equal(modelReadiness('loading', groups, 'openai:example', true, false), null);
 assert.deepEqual(modelReadiness('ready', groups, 'chatgpt:example', true, false), {kind:'chatgpt_unavailable',action:null});
 assert.deepEqual(modelReadiness('ready', groups, 'missing:example', true, false), {kind:'unavailable',action:'choose'});
 assert.deepEqual(modelReadiness('ready', [], '', false, false), {kind:'no_models_user',action:null});
});

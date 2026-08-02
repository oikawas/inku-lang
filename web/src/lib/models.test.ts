// Run with: npm run test:unit  (node:test, no test dependency)
import assert from 'node:assert/strict';
import { test } from 'node:test';

import { modelDisplayName, modelShortName, type ProviderGroup } from './models.ts';

const GROUPS: ProviderGroup[] = [
	{
		id: 'nim',
		label: 'NVIDIA NIM (Cloud)',
		models: [
			{ id: 'google/gemma-4-31b-it', label: 'google/gemma-4-31b-it' },
			{ id: 'plain-model', label: 'Plain Model' },
		],
	} as ProviderGroup,
];

test('the short name drops the provider the long name carries', () => {
	const long = modelDisplayName('nim:plain-model', GROUPS);
	const short = modelShortName('nim:plain-model', GROUPS);
	assert.equal(long, 'NVIDIA NIM (Cloud) / Plain Model');
	assert.equal(short, 'Plain Model');
});

test('the vendor prefix of a served id is dropped', () => {
	assert.equal(modelShortName('nim:google/gemma-4-31b-it', GROUPS), 'gemma-4-31b-it');
});

test('only the first slash is a vendor prefix', () => {
	// A label with more than one slash keeps everything after the first.
	assert.equal(modelShortName('nim:a/b/c', GROUPS), 'b/c');
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
	assert.equal(b, 'gemma-4-31b-it-v2');
});

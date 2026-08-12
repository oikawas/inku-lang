// Run with: npm run test:unit  (node:test, no test dependency)
//
// A stored identity is `<scheme>:<digest>`. The scheme is one of the fields
// that goes into the digest, so it is a property of the value rather than a
// part of it, and nothing in the product takes a prefixed string as input --
// the only lookup is the four-character suffix search. What is measured here is
// that one module makes that decision, and that the surfaces read it from the
// value rather than from a constant.
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

import {
	hashDigest,
	hashSchemeLabel,
	shortHashDigest,
	splitHashIdentity
} from './hashIdentity.ts';

const LINEAGE = fileURLToPath(new URL('./components/LineagePanel.svelte', import.meta.url));
const PAGE = fileURLToPath(new URL('../routes/+page.svelte', import.meta.url));

const RH3 = 'rh3:ee53a79aac960695b8dd5d79d06e02d473e4de0fc5f73f5a46a70794377a0c75';
const DH1 = 'dh1:bf821355c572fd5646f998ce634d92851471e8359036b11015a79c37d3894996';
// A work saved before the schemes were written down. Measured on build 892:
// the lineage panel shows such rows with no prefix at all.
const BARE = 'bf61b9151863aa0d8c0d5c2ef1b3f1a0d3d1c0b9a8f7e6d5c4b3a291807f6e5d';

test('the scheme is split off, and a value without one is all digest', () => {
	assert.deepEqual(splitHashIdentity(RH3), { scheme: 'rh3', digest: RH3.slice(4) });
	assert.deepEqual(splitHashIdentity(DH1), { scheme: 'dh1', digest: DH1.slice(4) });
	assert.deepEqual(splitHashIdentity(BARE), { scheme: null, digest: BARE });
	// Absent is its own answer: "no hash" is not "a hash with no scheme".
	assert.equal(splitHashIdentity(null), null);
	assert.equal(splitHashIdentity(''), null);
});

test('only the first colon splits, so a digest keeps everything after it', () => {
	assert.deepEqual(splitHashIdentity('rh9:a:b'), { scheme: 'rh9', digest: 'a:b' });
});

test('what a copy button hands over is the digest alone', () => {
	assert.equal(hashDigest(RH3), RH3.slice(4));
	assert.equal(hashDigest(RH3).length, 64);
	assert.doesNotMatch(hashDigest(RH3), /:/);
	// The bare value is copied whole rather than becoming empty.
	assert.equal(hashDigest(BARE), BARE);
	assert.equal(hashDigest(null), '');
});

test('the label is the scheme the value names, and falls back to the family', () => {
	assert.equal(hashSchemeLabel(RH3, 'rh'), 'rh3');
	assert.equal(hashSchemeLabel(DH1, 'dh'), 'dh1');
	// No scheme is not rh3: the fallback says the family and claims nothing
	// about how the value was made.
	assert.equal(hashSchemeLabel(BARE, 'rh'), 'rh');
	assert.equal(hashSchemeLabel(null, 'rh'), 'rh');
});

test('the shortened form shows the digest, not the scheme', () => {
	assert.equal(shortHashDigest(RH3), `${RH3.slice(4, 16)}…`);
	assert.doesNotMatch(shortHashDigest(RH3), /rh3/);
	assert.equal(shortHashDigest(null), '—');
});

test('the surfaces read the scheme from the value, not from a constant', () => {
	const lineage = readFileSync(LINEAGE, 'utf8');
	// A row labelled with a literal is the defect this replaced: it went on
	// saying rh2 while the works below it were being saved as rh3.
	assert.doesNotMatch(lineage, /<dt>rh\d<\/dt>/);
	assert.doesNotMatch(lineage, /<dt>dh\d<\/dt>/);
	assert.match(lineage, /hashSchemeLabel\(node\.render_hash, 'rh'\)/);
	assert.match(lineage, /hashSchemeLabel\(node\.description_hash, 'dh'\)/);

	// Both copy buttons go through the one decision.
	assert.match(lineage, /hashDigest\(node\.render_hash\)/);
	assert.match(readFileSync(PAGE, 'utf8'), /statusHashFull = \$derived\(hashDigest\(/);
});

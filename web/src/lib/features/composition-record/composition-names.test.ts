// Run with: npm run test:unit  (node:test, no test dependency)
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';

import { COMPOSITION_NAMES } from '../../composition-names.generated.ts';
import {
	atName, colorLawName, colorLawNameWithCode, formDescription, formName, kindName, lawName, lawNameWithCode, placeName, roleName
} from './composition-names.ts';

const FIXTURE = JSON.parse(readFileSync(new URL('../../../../../server/tests/data/composition-names-v1.json', import.meta.url), 'utf8'));

test('the generated table is the shared fixture the core writes', () => {
	// Failure: the core's names move and the Web keeps showing the old ones.
	assert.deepEqual(JSON.parse(JSON.stringify(COMPOSITION_NAMES)), FIXTURE);
	assert.equal(FIXTURE.schema, 'inku.composition-names.v1');
});

test('each kind of name is looked up from the table, in both languages', () => {
	const [form] = FIXTURE.forms, [law] = FIXTURE.laws, [color] = FIXTURE.color_laws;
	assert.equal(formName(form.id, true), form.name.ja);
	assert.equal(formName(form.id, false), form.name.en);
	assert.equal(formDescription(form.id, true), form.description.ja);
	assert.equal(lawName(law.code, true), law.name.ja);
	assert.equal(colorLawName(color.code, false), color.name.en);
	assert.equal(roleName(FIXTURE.roles[0].id, true), FIXTURE.roles[0].name.ja);
	assert.equal(kindName(FIXTURE.kinds[0].id, true), FIXTURE.kinds[0].name.ja);
	assert.equal(atName(FIXTURE.at[0].id, false), FIXTURE.at[0].name.en);
	assert.equal(placeName(FIXTURE.places[0].id, true), FIXTURE.places[0].name.ja);
});

test('a key the table does not know reads as itself, and the details keep the code after the name', () => {
	assert.equal(formName('a_new_form', true), 'a_new_form');
	assert.equal(lawName('Z9', true), 'Z9');
	assert.equal(lawNameWithCode('Z9', true), 'Z9');
	const golden = FIXTURE.laws.find((row: { code: string }) => row.code === 'B1');
	assert.equal(lawNameWithCode('B1', true), `${golden.name.ja}（B1）`);
	assert.equal(lawNameWithCode('B1', false), `${golden.name.en} (B1)`);
	const color = FIXTURE.color_laws[0];
	assert.equal(colorLawNameWithCode(color.code, true), `${color.name.ja}（${color.code}）`);
});

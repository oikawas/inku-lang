import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { modelReference } from '../src/lib/modelReferences.ts';
import { qualifiedModelRef, splitModelReference, modelDisplayName, modelShortName, pickerSelection } from '../src/lib/models.ts';
const fixture = JSON.parse(readFileSync(new URL('../src/lib/model-reference-test-fixtures.json', import.meta.url), 'utf8'));
let checks = 0;
for (let i = 0; i < fixture.queries.length; i++) {
  assert.deepEqual(modelReference(fixture.queries[i]), fixture.results[i]); checks++;
}
assert.deepEqual(splitModelReference('chatgpt:model'), {provider:'chatgpt',model:'model'}); checks++;
assert.equal(qualifiedModelRef('nim','plain-model'), 'nim:plain-model'); checks++;
assert.equal(modelDisplayName('nim:plain-model'), 'NVIDIA NIM (Cloud) / Plain Model'); checks++;
assert.equal(modelShortName('nim:google/gemma-4-31b-it'), 'gemma-4-31b-it'); checks++;
const groups=[{id:'nim',label:'NVIDIA NIM (Cloud)',models:[{id:'plain-model',label:'Plain Model',qualified_id:'nim:plain-model'}]}];
assert.equal(pickerSelection(groups,'nim:plain-model').selected?.model.id,'plain-model'); checks++;
const source=readFileSync(new URL('../src/lib/models.ts',import.meta.url),'utf8');
for (const old of ['PROVIDER_GROUPS','RETIRED_PROVIDER_GROUPS','function splitModelRef(', 'function qualifiedModelId(', 'function resolveModelRef(']) { assert.equal(source.includes(old),false); checks++; }
console.log(`model-ref-check: ${checks} checks passed`);

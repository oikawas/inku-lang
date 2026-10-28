import assert from 'node:assert/strict';
import { test } from 'node:test';
import { clearChatGPTReferences, clearModelReferences, configureModelReferences, disableModelReferences, loadModelReferences, modelReference } from './modelReferences';

test('reference requests use server answers and preserve the query order', async () => {
	clearModelReferences();
	const seen: unknown[] = [];
	configureModelReferences(async (_path, init) => {
		const { queries } = JSON.parse(String(init?.body));
		seen.push(...queries);
		return Response.json({ results: [{outcome:'ok', ref:'remote:resolved'}, {outcome:'ok',provider:'remote',model:'resolved'}] });
	});
	const queries = [{action:'qualify_ref',provider:'remote',ref:'raw'}, {action:'split_ref',ref:'remote:resolved'}] as const;
	await loadModelReferences([...queries]);
	assert.deepEqual(seen, queries);
	assert.equal(modelReference(queries[0])?.ref, 'remote:resolved');
	assert.deepEqual(modelReference(queries[1]), {outcome:'ok',provider:'remote',model:'resolved'});
});

test('a failed reference request can be retried and never caches the failed answer', async () => {
	clearModelReferences();
	let calls = 0;
	configureModelReferences(async () => ++calls === 1 ? new Response('', {status:503}) : Response.json({results:[{outcome:'ok',ref:'provider:model'}]}));
	const query = {action:'qualify_ref',provider:'provider',ref:'model'} as const;
	await assert.rejects(loadModelReferences([query]), /503/);
	await loadModelReferences([query]);
	assert.equal(modelReference(query)?.ref, 'provider:model');
	assert.equal(calls, 2);
});

test('clearing a ChatGPT registration drops its names but keeps unrelated references', async () => {
	clearModelReferences();
	configureModelReferences(async () => Response.json({results:[
		{outcome:'ok', provider:'chatgpt', model:'private', provider_label:'ChatGPT plan', model_label:'Private'},
		{outcome:'ok', provider:'openai', model:'public', provider_label:'OpenAI', model_label:'Public'}
	]}));
	const privateRef = {action:'resolve_display',ref:'chatgpt:private'} as const;
	const publicRef = {action:'resolve_display',ref:'openai:public'} as const;
	await loadModelReferences([privateRef, publicRef]);
	clearChatGPTReferences();
	assert.equal(modelReference(publicRef)?.model_label, 'Public');
	assert.equal(modelReference(privateRef), undefined);
});

test('signed-out lookups do not send a reference request', async () => {
	let calls = 0;
	configureModelReferences(async () => { calls++; return Response.json({results:[]}); });
	disableModelReferences();
	assert.equal(modelReference({action:'split_ref',ref:'private:model'}), undefined);
	await Promise.resolve();
	assert.equal(calls, 0);
});

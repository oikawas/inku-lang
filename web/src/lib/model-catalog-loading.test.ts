import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import ts from 'typescript';

const page = readFileSync(new URL('../routes/+page.svelte', import.meta.url), 'utf8');
const source = page.slice(page.indexOf('\tasync function loadAvailableModels()'), page.indexOf('\n\tlet compositionRanges'));
assert.ok(source.startsWith('\tasync function loadAvailableModels()'));
const moduleSource = `export function create(fetcher) {
  let modelCatalogRequest = 0, modelCatalogStatus = 'ready', availableModelsLoaded = true;
  let availableModelCatalog = [{id:'stale',models:[]}], availableVisionModelCatalog = [], demoPromptModelCatalog = [];
  let chatgptPlanAvailable = false, modelCatalogOwner, stage1Provider = 'openai', stage1Model = 'x', stage2Provider = 'openai', stage2Model = 'x', visionProvider = 'openai', visionModel = 'x', okugakiModel = 'openai:x';
  const session = {currentUser:{id:'actor'}}, apiFetch = fetcher;
  const console = {warn() {}};
  const clearModelReferences = () => {}, configureModelReferences = () => {}, loadModelReferences = async () => {}, setModelLabelTable = () => {};
  const qualifiedModelRef = (provider, model) => provider + ':' + model, demoInstructionModelGroups = groups => groups;
  const applyUserModelSettings = () => {}, modelsFor = () => [{id:'x'}], visionModelsFor = () => [{id:'x'}];
  const demo = {reconcilePromptModel() {}};
  ${source}
  return {load:loadAvailableModels, state:() => ({status:modelCatalogStatus, loaded:availableModelsLoaded, groups:availableModelCatalog})};
}`;
const compiled = ts.transpileModule(moduleSource, {compilerOptions:{target:ts.ScriptTarget.ESNext,module:ts.ModuleKind.ESNext}}).outputText;
const {create} = await import(`data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`);

test('model list shows loading, then a failure, and can be loaded again', async () => {
  let finish!: (response: Response) => void;
  let attempts = 0;
  const harness = create(() => ++attempts === 1 ? new Promise<Response>((resolve) => {finish = resolve;}) : Promise.resolve(Response.json({
    catalog:[{id:'openai',label:'OpenAI',models:[{id:'x',label:'X'}]}], settings:{}
  })));
  const first = harness.load();
  assert.deepEqual(harness.state(), {status:'loading',loaded:false,groups:[]});
  finish(new Response('', {status:503}));
  await first;
  assert.deepEqual(harness.state(), {status:'error',loaded:false,groups:[]});
  await harness.load();
  assert.equal(harness.state().status, 'ready');
  assert.equal(harness.state().loaded, true);
  assert.deepEqual(harness.state().groups.map((group: {id:string}) => group.id), ['openai']);
});

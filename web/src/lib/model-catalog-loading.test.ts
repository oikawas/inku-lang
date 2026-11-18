import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import ts from 'typescript';

const page = readFileSync(new URL('../routes/+page.svelte', import.meta.url), 'utf8');
const selection = readFileSync(new URL('./features/settings/ModelSelectionSettings.svelte', import.meta.url), 'utf8');
const source = page.slice(page.indexOf('\tasync function loadAvailableModels()'), page.indexOf('\n\tlet compositionRanges'));
const restoreSource = page.slice(page.indexOf('\tfunction restoreModelSelection()'), page.indexOf('\n\tfunction openCatalogModal()'));
assert.ok(source.startsWith('\tasync function loadAvailableModels()'));
const moduleSource = `export function create(fetcher) {
  let modelCatalogRequest = 0, modelCatalogStatus = 'ready', availableModelsLoaded = true;
  let refinementModelSelection = false;
  let modelSelectionReference = null, modelSelectionOwner = 'actor', modelSelectionEdited = false, modelSelectionVisionOnly = false;
  let pendingModelSettings = null;
  let modelSelectionSnapshot = {stage1Provider:'openai',stage1Model:'x',stage2Provider:'openai',stage2Model:'x',visionProvider:'openai',visionModel:'x'};
  let acceptRefinementModel = null;
  const settings = {opened:false,mode:'settings'};
  let availableModelCatalog = [{id:'stale',models:[]}], availableVisionModelCatalog = [], demoPromptModelCatalog = [];
  let chatgptPlanAvailable = false, chatgptUsageUrl = null, modelCatalogOwner = 'actor', stage1Provider = 'openai', stage1Model = 'x', stage2Provider = 'openai', stage2Model = 'x', visionProvider = 'openai', visionModel = 'x', okugakiModel = 'openai:x';
  const session = {currentUser:{id:'actor'}}, apiFetch = fetcher;
  const console = {warn() {}};
  const clearModelReferences = () => {}, configureModelReferences = () => {}, loadModelReferences = async () => {}, refreshModelReferences = async () => {}, setModelLabelTable = () => {};
  const getLang = () => 'en';
  const qualifiedModelRef = (provider, model) => provider + ':' + model, demoInstructionModelGroups = groups => groups;
  const splitModelReference = ref => { const index = ref.indexOf(':'); return index < 0 ? {provider:null, model:ref} : {provider:ref.slice(0,index),model:ref.slice(index+1)}; };
  const applyUserModelSettings = () => { stage1Model = stage2Model = 'saved'; }, modelsFor = () => [{id:'x'}], visionModelsFor = () => [{id:'x'}];
  const demo = {reconcilePromptModel() {}};
  ${source}
  ${restoreSource}
  return {load:loadAvailableModels, state:() => ({status:modelCatalogStatus, loaded:availableModelsLoaded, groups:availableModelCatalog}),
    chooseRefinement: () => { refinementModelSelection = true; stage1Model = stage2Model = 'chosen'; },
    openDrawing: ref => { settings.opened = true; settings.mode = 'model'; modelSelectionReference = ref; },
    choose: model => { modelSelectionEdited = true; stage1Model = stage2Model = model; },
    pending: () => pendingModelSettings,
    close: () => { restoreModelSelection(); settings.opened = false; },
    switchUser: () => { session.currentUser = {id:'other'}; },
    models: () => [stage1Model, stage2Model]};
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
  assert.deepEqual(harness.state(), {status:'loading',loaded:false,groups:[{id:'stale',models:[]}]});
  finish(new Response('', {status:503}));
  await first;
  assert.deepEqual(harness.state(), {status:'error',loaded:false,groups:[{id:'stale',models:[]}]});
  await harness.load();
  assert.equal(harness.state().status, 'ready');
  assert.equal(harness.state().loaded, true);
  assert.deepEqual(harness.state().groups.map((group: {id:string}) => group.id), ['openai']);
});

test('an open selection is not replaced by saved settings or fallback', async () => {
  const harness = create(async () => Response.json({catalog:[{id:'openai',label:'OpenAI',models:[{id:'x',label:'X'}]}], settings:{model_settings:{stage1_model:'saved'}}}));
  harness.openDrawing(null);
  harness.choose('chosen');
  await harness.load();
  assert.deepEqual(harness.models(), ['chosen', 'chosen']);
  assert.equal(harness.pending().owner, 'actor');
  harness.close();
  assert.deepEqual(harness.models(), ['saved', 'saved']);
});

test('closing after an account change does not restore the previous account', async () => {
  const harness = create(async () => Response.json({catalog:[{id:'openai',label:'OpenAI',models:[{id:'x',label:'X'}]}], settings:{model_settings:{stage1_model:'saved'}}}));
  harness.openDrawing(null);
  harness.choose('new-account-choice');
  await harness.load();
  harness.switchUser();
  harness.close();
  assert.deepEqual(harness.models(), ['new-account-choice', 'new-account-choice']);
  assert.equal(harness.pending(), null);
});

test('a drawing reference is split after loading, unless the author has chosen a card', async () => {
  let finish!: (response: Response) => void;
  const response = () => Response.json({catalog:[{id:'chatgpt',label:'ChatGPT',models:[{id:'gpt-6.1-sol',label:'GPT-6.1-Sol'}]}], settings:{}});
  const untouched = create(() => new Promise<Response>((resolve) => { finish = resolve; }));
  untouched.openDrawing('chatgpt:gpt-6.1-sol');
  const first = untouched.load();
  finish(response());
  await first;
  assert.deepEqual(untouched.models(), ['gpt-6.1-sol', 'gpt-6.1-sol']);
  const edited = create(() => new Promise<Response>((resolve) => { finish = resolve; }));
  edited.openDrawing('chatgpt:gpt-6.1-sol');
  const second = edited.load();
  edited.choose('other');
  finish(response());
  await second;
  assert.deepEqual(edited.models(), ['other', 'other']);
});

test('confirm keeps the chosen drawing model when deferred defaults are applied', async () => {
  const confirm = page.slice(page.indexOf('\tasync function confirmModelSelection()'), page.indexOf('\n\tfunction restoreModelSelection()'));
  const code = `export function make() {
    let acceptRefinementModel = null, modelSelectionForDrawing = true, modelSelectionVisionOnly = false;
    let stage1Provider = 'chatgpt', stage1Model = 'gpt-6.1-sol', visionProvider = '', visionModel = '';
    const work = {drawOptions:{models:{stage1:'old',stage2:'old'}}, invalidateWorkOptions() {}};
    const qualifiedModelRef = (provider, model) => provider + ':' + model;
    const restoreModelSelection = () => { work.drawOptions.models = {stage1:'saved-default',stage2:'saved-default'}; stage1Provider = 'other'; stage1Model = 'other'; };
    const settings = {finishModelSelection() {}}, persistModelSelection = async () => {};
    let modelSelectionSnapshot = null;
    ${confirm}
    return {confirm:confirmModelSelection, models:() => work.drawOptions.models};
  }`;
  const output = ts.transpileModule(code, {compilerOptions:{target:ts.ScriptTarget.ESNext,module:ts.ModuleKind.ESNext}}).outputText;
  const { make } = await import(`data:text/javascript;base64,${Buffer.from(output).toString('base64')}`);
  const harness = make();
  await harness.confirm();
  assert.deepEqual(harness.models(), {stage1:'chatgpt:gpt-6.1-sol',stage2:'chatgpt:gpt-6.1-sol'});
});

test('the selection waits for the catalog before reporting availability or confirming', () => {
  assert.match(selection, /catalogLoad\?\.status\(\) === 'loading'/);
  assert.match(selection, /catalogLoad\?\.status\(\) === 'error'/);
  assert.match(selection, /catalogLoad\.retry\(\)/);
  assert.match(selection, /catalogReady && !visionOnlySelection && stage1Provider === 'chatgpt'/);
  assert.match(selection, /onclick=\{onConfirm\} disabled=\{!catalogReady\}/);
});

test('refreshing the catalog does not replace a refinement model in progress', async () => {
  let finish!: (response: Response) => void;
  const harness = create(() => new Promise<Response>((resolve) => { finish = resolve; }));
  harness.chooseRefinement();
  const pending = harness.load();
  finish(Response.json({catalog:[{id:'openai',label:'OpenAI',models:[{id:'x',label:'X'}]}], settings:{model_settings:{stage1_model:'saved'}}}));
  await pending;
  assert.equal(harness.state().status, 'ready');
  assert.deepEqual(harness.models(), ['chosen', 'chosen']);
});

 test('changing accounts clears the previous catalog while the new one loads', async () => {
  let finish!: (response: Response) => void;
  const harness = create(() => new Promise<Response>(resolve => { finish = resolve; }));
  harness.switchUser();
  const pending = harness.load();
  assert.deepEqual(harness.state().groups, []);
  finish(Response.json({catalog:[], settings:{}}));
  await pending;
 });

// Run with the focused Stage 2B command in the contract.
//
// This source-level seam keeps model-provider administration in the existing
// route-instance Settings owner without absorbing drawing-time model selection
// or the modal's input-level API-key draft.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';

const read = (path: string) => readFileSync(new URL(path, import.meta.url), 'utf8');
const OWNER = read('./state.svelte.ts');
const MODEL_OWNER = read('./model-administration.svelte.ts');
const PAGE = read('../../../routes/+page.svelte');
const MODAL = read('../../components/SettingsModal.svelte');
const MODEL_VIEW = read('./ModelAdministrationSettings.svelte');
const PROPS = MODAL.slice(MODAL.indexOf('type Props'), MODAL.indexOf('}: Props = $props()'));

test('Stage 2B moves every model-provider administration writer into the Settings owner', () => {
	for (const name of ['modelSettings', 'modelSettingsStatus', 'modelFetchResults', 'modelSettingsLoading', 'modelCatalog']) {
		assert.doesNotMatch(PAGE, new RegExp(`let ${name}\\s*=\\s*\\$state`), name);
		assert.match(MODEL_OWNER, new RegExp(`let ${name}\\s*=\\s*\\$state`), name);
	}
	for (const name of [
		'loadModelSettings',
		'updateModelProvider',
		'addModelProvider',
		'askDeleteModelProvider',
		'deleteModelProvider',
		'fetchProviderModels',
		'askClearModelApiKey',
		'clearModelApiKey',
		'saveModelProviderName',
		'saveModelProviderMemo',
		'saveModelProvider',
		'saveModelSettings'
	]) {
		assert.doesNotMatch(PAGE, new RegExp(`(?:async\\s+)?function ${name}\\(`), name);
		assert.match(MODEL_OWNER, new RegExp(`(?:async\\s+)?function ${name}\\(`), name);
	}
	assert.doesNotMatch(PAGE, /\/api\/settings\/models/);
	assert.match(MODEL_OWNER, /\/api\/settings\/models/);
});

test('model administration types and Modal boundary are canonical on SettingsController', () => {
	for (const typeName of ['ModelProviderSetting', 'ModelSettings', 'ModelFetchResult']) {
		assert.match(MODEL_OWNER, new RegExp(`export type ${typeName}`));
		assert.doesNotMatch(PAGE, new RegExp(`type ${typeName}`));
		assert.doesNotMatch(MODAL, new RegExp(`type ${typeName}`));
	}
	for (const prop of [
		'modelSettings:',
		'modelSettingsStatus:',
		'modelFetchResults:',
		'modelSettingsLoading:',
		'onUpdateModelProvider:',
		'onAddModelProvider:',
		'onFetchModelList:',
		'onSaveModelSettings:',
		'onLoadModelSettings:'
	]) {
		assert.doesNotMatch(PROPS, new RegExp(prop), prop);
	}
	assert.match(MODEL_VIEW, /const modelSettings = \$derived\(administration\.modelSettings\)/);
	assert.match(MODEL_VIEW, /administration\.updateModelProvider/);
	assert.match(MODEL_VIEW, /administration\.saveModelProvider/);
});

test('drawing-time selection and input-level secret drafts stay at their narrow owners', () => {
	for (const name of ['availableModelCatalog', 'availableVisionModelCatalog', 'availableModelsLoaded']) {
		assert.match(PAGE, new RegExp(`let ${name}\\s*=\\s*\\$state`), name);
		assert.doesNotMatch(MODEL_OWNER, new RegExp(name), name);
	}
	assert.match(PAGE, /async function loadAvailableModels\(/);
	assert.match(PAGE, /\/api\/models/);
	assert.doesNotMatch(MODEL_OWNER, /\/api\/models/);
	assert.match(MODEL_VIEW, /let newProviderApiKey = \$state\(''\)/);
	assert.doesNotMatch(MODEL_OWNER, /newProviderApiKey/);
});

test('page wiring keeps registry reads typed and confirmation capability narrow', () => {
	assert.match(PAGE, /registerModelCatalog\(settings\.modelCatalog\)/);
	assert.match(PAGE, /providerGroups=\{settings\.mode === 'model' \? availableModelCatalog : settings\.modelCatalog\}/);
	assert.match(MODEL_OWNER, /requestConfirmation:/);
	assert.match(MODEL_OWNER, /deps\.requestConfirmation\(\{/);
	assert.doesNotMatch(MODEL_OWNER, /confirmAction/);
	assert.doesNotMatch(OWNER, /export const settings\s*=/);
});

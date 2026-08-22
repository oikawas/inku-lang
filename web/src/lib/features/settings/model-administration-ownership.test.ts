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
const PAGE = read('../../../routes/+page.svelte');
const MODAL = read('../../components/SettingsModal.svelte');
const PROPS = MODAL.slice(MODAL.indexOf('type Props'), MODAL.indexOf('}: Props = $props()'));

test('Stage 2B moves every model-provider administration writer into the Settings owner', () => {
	for (const name of ['modelSettings', 'modelSettingsStatus', 'modelFetchResults', 'modelSettingsLoading', 'modelCatalog']) {
		assert.doesNotMatch(PAGE, new RegExp(`let ${name}\\s*=\\s*\\$state`), name);
		assert.match(OWNER, new RegExp(`let ${name}\\s*=\\s*\\$state`), name);
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
		assert.match(OWNER, new RegExp(`(?:async\\s+)?function ${name}\\(`), name);
	}
	assert.doesNotMatch(PAGE, /\/api\/settings\/models/);
	assert.match(OWNER, /\/api\/settings\/models/);
});

test('model administration types and Modal boundary are canonical on SettingsController', () => {
	for (const typeName of ['ModelProviderSetting', 'ModelSettings', 'ModelFetchResult']) {
		assert.match(OWNER, new RegExp(`export type ${typeName}`));
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
	assert.match(MODAL, /const modelSettings = \$derived\(settings\.modelSettings\)/);
	assert.match(MODAL, /settings\.updateModelProvider/);
	assert.match(MODAL, /settings\.saveModelProvider/);
});

test('drawing-time selection and input-level secret drafts stay at their narrow owners', () => {
	for (const name of ['availableModelCatalog', 'availableVisionModelCatalog', 'availableModelsLoaded']) {
		assert.match(PAGE, new RegExp(`let ${name}\\s*=\\s*\\$state`), name);
		assert.doesNotMatch(OWNER, new RegExp(name), name);
	}
	assert.match(PAGE, /async function loadAvailableModels\(/);
	assert.match(PAGE, /\/api\/models/);
	assert.doesNotMatch(OWNER, /\/api\/models/);
	assert.match(MODAL, /let newProviderApiKey = \$state\(''\)/);
	assert.doesNotMatch(OWNER, /newProviderApiKey/);
});

test('page wiring keeps registry reads typed and confirmation capability narrow', () => {
	assert.match(PAGE, /registerModelCatalog\(settings\.modelCatalog\)/);
	assert.match(PAGE, /providerGroups=\{settings\.mode === 'model' \? availableModelCatalog : settings\.modelCatalog\}/);
	assert.match(OWNER, /requestConfirmation:/);
	assert.match(OWNER, /deps\.requestConfirmation\(\{/);
	assert.doesNotMatch(OWNER, /confirmAction/);
	assert.doesNotMatch(OWNER, /export const settings\s*=/);
});

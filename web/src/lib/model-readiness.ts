import type { ProviderGroup } from './models';
import { isModelUnselectable } from './modelMeta';

export function missingApiKey(group: ProviderGroup): boolean {
	return group.id !== 'chatgpt' && group.requires_api_key === true && group.api_key_set === false;
}
export type ModelReadiness = { kind: 'no_models_admin' | 'no_models_user' | 'unavailable' | 'missing_key_admin' | 'missing_key_user' | 'chatgpt_unavailable'; action: 'settings' | 'choose' | null; provider?: string } | null;
export function modelReadiness(status: 'loading' | 'ready' | 'error', groups: ProviderGroup[], selected: string, admin: boolean, chatgptAvailable: boolean): ModelReadiness {
	if (status !== 'ready') return null;
	const models = groups.flatMap(group => group.models.map(model => ({group, model})));
	if (!models.length) return {kind: admin ? 'no_models_admin' : 'no_models_user', action: admin ? 'settings' : null};
	const chosen = models.find(({model}) => model.qualified_id === selected);
	if (selected.startsWith('chatgpt:') && (!chatgptAvailable || !chosen)) return {kind: 'chatgpt_unavailable', action: null};
	if (!chosen) return {kind: 'unavailable', action: 'choose'};
	if (missingApiKey(chosen.group)) return {kind: admin ? 'missing_key_admin' : 'missing_key_user', action: admin ? 'settings' : models.some(({group, model}) => group.id !== chosen.group.id && !missingApiKey(group) && !isModelUnselectable(model) && (group.id !== 'chatgpt' || chatgptAvailable)) ? 'choose' : null, provider: chosen.group.id};
	return null;
}

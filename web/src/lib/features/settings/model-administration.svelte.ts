import { t } from '$lib/i18n/index.svelte';
import { PROVIDER_GROUPS, type ModelOption, type Provider, type ProviderGroup } from '$lib/models';
import type { ApiFetch } from '$lib/transport/api-fetch';
import type { SettingsActor } from './navigation-state.svelte';

export type ModelProviderSetting = {
	label?: string;
	kind?: string;
	default_base_url?: string;
	requires_api_key?: boolean;
	memo?: string;
	models?: ModelOption[];
	delete?: boolean;
	base_url: string;
	api_key_set: boolean;
	api_key_hint: string | null;
	api_key?: string;
	clear_api_key?: boolean;
	enabled_models?: Record<string, boolean>;
};

export type ModelSettings = {
	providers: Record<string, ModelProviderSetting>;
};

export type ModelFetchResult = {
	type: 'success' | 'error';
	message: string;
};

export type SettingsConfirmation = {
	message: string;
	run: () => void;
	destructive?: boolean;
	runLabel?: string;
};

type ModelAdministrationDeps<TActor extends SettingsActor> = {
	apiFetch: ApiFetch;
	currentUser: () => TActor | null;
	loadAvailableModels: () => void | Promise<void>;
	requestConfirmation: (confirmation: SettingsConfirmation) => void;
	describeApiError: (detail: unknown, status: number) => string;
};

export type ModelAdministration = {
	readonly modelSettings: ModelSettings | null;
	readonly modelSettingsStatus: string | null;
	readonly modelFetchResults: Record<string, ModelFetchResult>;
	readonly modelSettingsLoading: boolean;
	readonly modelCatalog: ProviderGroup[];
	updateModelProvider: (provider: Provider, patch: Partial<ModelProviderSetting>) => void;
	addModelProvider: (provider: Provider, patch: Partial<ModelProviderSetting>) => Promise<void>;
	askDeleteModelProvider: (provider: Provider) => void;
	fetchProviderModels: (provider: Provider) => Promise<void>;
	askClearModelApiKey: (provider: Provider) => void;
	saveModelProviderName: (provider: Provider, label: string) => Promise<void>;
	saveModelProviderMemo: (provider: Provider, memo: string) => Promise<void>;
	saveModelProvider: (provider: Provider, patch?: Partial<ModelProviderSetting>) => Promise<void>;
	saveModelSettings: () => Promise<void>;
	loadModelSettings: () => Promise<void>;
};

export function createModelAdministration<TActor extends SettingsActor>(
	deps: ModelAdministrationDeps<TActor>
): ModelAdministration {
	let modelSettings = $state<ModelSettings | null>(null);
	let modelSettingsStatus = $state<string | null>(null);
	let modelFetchResults = $state<Record<string, ModelFetchResult>>({});
	let modelSettingsLoading = $state(false);
	let modelCatalog = $state<ProviderGroup[]>(PROVIDER_GROUPS.filter((group) => group.id !== 'nvidia'));

	function isAdministrator(): boolean {
		return deps.currentUser()?.permission_groups?.includes('admins') === true;
	}

	// The Server response is authoritative for both catalog metadata and stored
	// provider settings; never retain a locally assembled approximation after a save.
	function acceptModelResponse(data: { catalog: ProviderGroup[]; settings: ModelSettings }, status: string): void {
		modelCatalog = data.catalog;
		modelSettings = data.settings;
		modelSettingsStatus = status;
	}

	async function loadModelSettings(): Promise<void> {
		if (!isAdministrator()) {
			modelSettings = null;
			modelSettingsStatus = t().settingsAdminOnlyMessage;
			return;
		}
		modelSettingsLoading = true;
		try {
			const response = await deps.apiFetch('/api/settings/models', { cache: 'no-store' });
			if (!response.ok) throw new Error(`HTTP ${response.status}`);
			acceptModelResponse(await response.json(), '');
			modelSettingsStatus = null;
		} catch (error) {
			modelSettingsStatus = error instanceof Error ? error.message : String(error);
		} finally {
			modelSettingsLoading = false;
		}
	}

	function updateModelProvider(provider: Provider, patch: Partial<ModelProviderSetting>): void {
		if (!modelSettings) return;
		const current = modelSettings.providers[provider] ?? { base_url: '', api_key_set: false, api_key_hint: null };
		modelSettings = {
			...modelSettings,
			providers: { ...modelSettings.providers, [provider]: { ...current, ...patch } }
		};
	}

	async function addModelProvider(provider: Provider, patch: Partial<ModelProviderSetting>): Promise<void> {
		if (!modelSettings || !provider || !isAdministrator()) return;
		modelSettingsLoading = true;
		try {
			const response = await deps.apiFetch('/api/settings/models', {
				method: 'PUT',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ providers: { [provider]: {
					label: patch.label ?? provider,
					kind: patch.kind,
					requires_api_key: patch.requires_api_key,
					memo: patch.memo,
					models: patch.models ?? [],
					base_url: patch.base_url ?? patch.default_base_url ?? '',
					api_key: patch.api_key || undefined,
					enabled_models: patch.enabled_models ?? {}
				} } })
			});
			if (!response.ok) throw new Error(`HTTP ${response.status}`);
			acceptModelResponse(await response.json(), t().settingsModelSaved);
			await deps.loadAvailableModels();
		} catch (error) {
			modelSettingsStatus = error instanceof Error ? error.message : String(error);
			throw error;
		} finally {
			modelSettingsLoading = false;
		}
	}

	function askDeleteModelProvider(provider: Provider): void {
		const label = modelCatalog.find((item) => item.id === provider)?.label ?? provider;
		deps.requestConfirmation({
			message: t().settingsModelDeleteServiceConfirm(label),
			destructive: true,
			run: () => { void deleteModelProvider(provider); }
		});
	}

	async function deleteModelProvider(provider: Provider): Promise<void> {
		if (!isAdministrator()) return;
		modelSettingsLoading = true;
		try {
			const response = await deps.apiFetch('/api/settings/models', {
				method: 'PUT',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ providers: { [provider]: { delete: true } } })
			});
			if (!response.ok) throw new Error(`HTTP ${response.status}`);
			acceptModelResponse(await response.json(), t().settingsModelSaved);
			await deps.loadAvailableModels();
		} catch (error) {
			modelSettingsStatus = error instanceof Error ? error.message : String(error);
		} finally {
			modelSettingsLoading = false;
		}
	}

	async function fetchProviderModels(provider: Provider): Promise<void> {
		if (!isAdministrator()) return;
		modelSettingsLoading = true;
		const nextResults = { ...modelFetchResults };
		delete nextResults[provider];
		modelFetchResults = nextResults;
		try {
			const response = await deps.apiFetch(`/api/settings/models/${encodeURIComponent(provider)}/fetch-models`, { method: 'POST' });
			if (!response.ok) {
				const body = await response.json().catch(() => ({})) as { detail?: unknown };
				throw new Error(deps.describeApiError(body.detail, response.status));
			}
			acceptModelResponse(await response.json(), t().settingsModelFetchModelsSaved);
			modelFetchResults = { ...modelFetchResults, [provider]: { type: 'success', message: t().settingsModelFetchModelsSaved } };
			await deps.loadAvailableModels();
		} catch (error) {
			const message = error instanceof Error ? error.message : String(error);
			modelFetchResults = { ...modelFetchResults, [provider]: { type: 'error', message } };
			modelSettingsStatus = message;
		} finally {
			modelSettingsLoading = false;
		}
	}

	function askClearModelApiKey(provider: Provider): void {
		const label = modelCatalog.find((item) => item.id === provider)?.label ?? provider;
		deps.requestConfirmation({
			message: t().settingsModelClearApiKeyConfirm(label),
			destructive: true,
			runLabel: t().settingsModelClearApiKey,
			run: () => { void clearModelApiKey(provider); }
		});
	}

	async function clearModelApiKey(provider: Provider): Promise<void> {
		if (!isAdministrator()) return;
		modelSettingsLoading = true;
		try {
			const current = modelSettings?.providers[provider];
			const response = await deps.apiFetch('/api/settings/models', {
				method: 'PUT',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ providers: { [provider]: {
					base_url: current?.base_url,
					clear_api_key: true,
					enabled_models: current?.enabled_models ?? {}
				} } })
			});
			if (!response.ok) throw new Error(`HTTP ${response.status}`);
			acceptModelResponse(await response.json(), t().settingsModelApiKeyCleared);
		} catch (error) {
			modelSettingsStatus = error instanceof Error ? error.message : String(error);
		} finally {
			modelSettingsLoading = false;
		}
	}

	// Catalog metadata and the modal draft form one provider payload. Secret
	// input is used only here and is never copied into confirmation or error state.
	function modelProviderPayload(id: string, provider: ModelProviderSetting, labelOverride?: string, memoOverride?: string) {
		const catalogProvider = modelCatalog.find((item) => item.id === id);
		return {
			label: labelOverride ?? catalogProvider?.label,
			kind: catalogProvider?.kind,
			requires_api_key: catalogProvider?.requires_api_key,
			memo: memoOverride ?? catalogProvider?.memo,
			models: provider.models ?? catalogProvider?.models ?? [],
			base_url: provider.base_url,
			api_key: provider.api_key || undefined,
			clear_api_key: !!provider.clear_api_key,
			enabled_models: provider.enabled_models ?? {}
		};
	}

	async function saveProviderPayload(provider: Provider, payload: ReturnType<typeof modelProviderPayload>): Promise<void> {
		const response = await deps.apiFetch('/api/settings/models', {
			method: 'PUT',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({ providers: { [provider]: payload } })
		});
		if (!response.ok) throw new Error(`HTTP ${response.status}`);
		acceptModelResponse(await response.json(), t().settingsModelSaved);
		await deps.loadAvailableModels();
	}

	async function saveModelProviderName(provider: Provider, label: string): Promise<void> {
		if (!modelSettings || !isAdministrator()) return;
		const providerSettings = modelSettings.providers[provider];
		const nextLabel = label.trim();
		if (!providerSettings || !nextLabel) return;
		modelSettingsLoading = true;
		try {
			await saveProviderPayload(provider, modelProviderPayload(provider, providerSettings, nextLabel));
		} catch (error) {
			modelSettingsStatus = error instanceof Error ? error.message : String(error);
		} finally {
			modelSettingsLoading = false;
		}
	}

	async function saveModelProviderMemo(provider: Provider, memo: string): Promise<void> {
		if (!modelSettings || !isAdministrator()) return;
		const providerSettings = modelSettings.providers[provider];
		if (!providerSettings) return;
		modelSettingsLoading = true;
		try {
			await saveProviderPayload(provider, modelProviderPayload(provider, providerSettings, undefined, memo));
		} catch (error) {
			modelSettingsStatus = error instanceof Error ? error.message : String(error);
		} finally {
			modelSettingsLoading = false;
		}
	}

	async function saveModelProvider(provider: Provider, patch: Partial<ModelProviderSetting> = {}): Promise<void> {
		if (!modelSettings || !isAdministrator()) return;
		const current = modelSettings.providers[provider];
		if (!current) return;
		modelSettingsLoading = true;
		try {
			await saveProviderPayload(provider, modelProviderPayload(provider, { ...current, ...patch }));
		} catch (error) {
			modelSettingsStatus = error instanceof Error ? error.message : String(error);
		} finally {
			modelSettingsLoading = false;
		}
	}

	async function saveModelSettings(): Promise<void> {
		if (!modelSettings || !isAdministrator()) return;
		modelSettingsLoading = true;
		try {
			const providers = Object.fromEntries(Object.entries(modelSettings.providers).map(([id, provider]) => [id, modelProviderPayload(id, provider)]));
			const response = await deps.apiFetch('/api/settings/models', {
				method: 'PUT',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ providers })
			});
			if (!response.ok) throw new Error(`HTTP ${response.status}`);
			acceptModelResponse(await response.json(), t().settingsModelSaved);
			await deps.loadAvailableModels();
		} catch (error) {
			modelSettingsStatus = error instanceof Error ? error.message : String(error);
		} finally {
			modelSettingsLoading = false;
		}
	}

	return {
		get modelSettings() { return modelSettings; },
		get modelSettingsStatus() { return modelSettingsStatus; },
		get modelFetchResults() { return modelFetchResults; },
		get modelSettingsLoading() { return modelSettingsLoading; },
		get modelCatalog() { return modelCatalog; },
		updateModelProvider,
		addModelProvider,
		askDeleteModelProvider,
		fetchProviderModels,
		askClearModelApiKey,
		saveModelProviderName,
		saveModelProviderMemo,
		saveModelProvider,
		saveModelSettings,
		loadModelSettings
	};
}

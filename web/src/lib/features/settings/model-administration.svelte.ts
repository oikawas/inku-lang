import { t } from '$lib/i18n/index.svelte';
import { setModelLabelTable } from '$lib/modelMeta';
import { type ModelLabel, type ModelOption, type Provider, type ProviderGroup } from '$lib/models';
import type { ApiFetch } from '$lib/transport/api-fetch';
import type { SettingsActor } from './navigation-state.svelte';

export type ModelProviderSetting = {
	label?: string;
	kind?: string;
	default_base_url?: string;
	requires_api_key?: boolean;
	memo?: string;
	rate_limits?: { rpm: number; tpm: number; rpd: number };
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
	chatgptAvailable?: () => boolean;
	loadAvailableModels: () => void | Promise<void>;
	requestConfirmation: (confirmation: SettingsConfirmation) => void;
	describeApiError: (detail: unknown, status: number) => string;
};

export type ModelAdministration = {
	readonly modelSettings: ModelSettings | null;
	readonly modelSettingsStatus: string | null;
	readonly modelFetchResults: Record<string, ModelFetchResult>;
	readonly modelSettingsLoading: boolean;
	// The Sign in with ChatGPT registration's state, as the Server answered with the publication.
	readonly chatgptState: string | null;
	readonly modelCatalog: ProviderGroup[];
	updateModelProvider: (provider: Provider, patch: Partial<ModelProviderSetting>) => void;
	addModelProvider: (provider: Provider, patch: Partial<ModelProviderSetting>) => Promise<void>;
	chatgptDraft: (request: { draft?: ChatGPTDraft['draft'] | null; edit?: ChatGPTDraftEdit | null;
		assessment_drafts?: Record<string, ModelOption> }) => Promise<ChatGPTDraft>;
	askDeleteModelProvider: (provider: Provider) => void;
	fetchProviderModels: (provider: Provider) => Promise<void>;
	askClearModelApiKey: (provider: Provider) => void;
	saveModelProviderName: (provider: Provider, label: string) => Promise<boolean>;
	saveModelProviderMemo: (provider: Provider, memo: string) => Promise<boolean>;
	saveModelProvider: (provider: Provider, patch?: Partial<ModelProviderSetting>) => Promise<boolean>;
	saveModelSettings: () => Promise<void>;
	loadModelSettings: () => Promise<void>;
	resetForLoggedOut: () => void;
};

type ChatGPTPublication = {
	profile_id: string;
	generation: number;
	// The shared core gives every published model its purposes.
	models: (ModelOption & { purposes: ('llm' | 'vision')[] })[];
	enabled_models: Record<string, boolean>;
	model_labels?: ModelLabel[];
	assessment_keys?: (keyof ModelOption)[];
	// The shared core's descriptor of the sign-in service (Sign in with ChatGPT).
	service?: { id: string; label: string; labels: { ja: string; en: string }; abbreviation: string;
		usage_url: string; kind: string; requires_api_key: boolean };
	// The group the core builds from the descriptor with these models, and the registration's state
	// (Sign in with ChatGPT step 6, 2026-11-15).
	group: ProviderGroup;
	state: string;
};

export type ChatGPTDraftEdit =
	| { kind: 'toggle_model'; id: string; selected: boolean }
	| { kind: 'toggle_purpose'; id: string; purpose: 'llm' | 'vision' }
	| { kind: 'select_all'; ids: string[]; selected: boolean };
export type ChatGPTDraft = {
	draft: { selected: Record<string, boolean>; purposes: Record<string, ('llm' | 'vision')[]> };
	rows: { id: string; selected: boolean; can_toggle: boolean; purposes: ('llm' | 'vision')[]; locked_purposes: ('llm' | 'vision')[] }[];
	dirty: boolean;
	can_refresh: boolean;
	can_save: boolean;
	save: { profile_id: string; generation: number; published_models: string[]; model_purposes: Record<string, ('llm' | 'vision')[]> };
	assessments: Record<string, unknown>[];
};

export function createModelAdministration<TActor extends SettingsActor>(
	deps: ModelAdministrationDeps<TActor>
): ModelAdministration {
	let modelSettings = $state<ModelSettings | null>(null);
	let modelSettingsStatus = $state<string | null>(null);
	let modelFetchResults = $state<Record<string, ModelFetchResult>>({});
	let modelSettingsLoading = $state(false);
	let modelCatalog = $state<ProviderGroup[]>([]);
	let chatgptPublication = $state<ChatGPTPublication | null>(null);
	let assessmentKeys = $state<(keyof ModelOption)[]>([]);
	let boundOwner = $state<string | undefined>(undefined);
	let revision = 0;

	function personalModelsAllowed(): boolean {
		return !!deps.currentUser()?.id && deps.chatgptAvailable?.() === true;
	}

	function resetForLoggedOut(): void {
		revision++;
		boundOwner = undefined;
		chatgptPublication = null;
		assessmentKeys = [];
		modelSettings = null;
		modelSettingsStatus = null;
		modelFetchResults = {};
		modelSettingsLoading = false;
		modelCatalog = [];
	}

	function sameOwner(owner: string | undefined, version: number): boolean {
		return deps.currentUser() !== null && deps.currentUser()?.id === owner && revision === version;
	}

	function acceptChatGPT(data: ChatGPTPublication): void {
		setModelLabelTable(data.model_labels);
		if (data.assessment_keys) assessmentKeys = data.assessment_keys;
		const models = data.models;
		chatgptPublication = data;
		// The group is the Server's answer (the core's provider_groups with this plan's models);
		// it replaces a same-id group and leads the list.
		modelCatalog = [data.group, ...modelCatalog.filter((group) => group.id !== data.group.id)];
		modelSettings = { providers: { ...modelSettings?.providers, chatgpt: {
			base_url: '', api_key_set: false, api_key_hint: null, models,
			enabled_models: data.enabled_models
		} } };
	}

	// One edit of the publication draft, answered by the shared core through the Server:
	// the draft after it, each row's state, whether it changed, the save body and the
	// changed shared assessments (Sign in with ChatGPT step 2, 2026-11-14).
	async function chatgptDraft(request: { draft?: ChatGPTDraft['draft'] | null; edit?: ChatGPTDraftEdit | null;
		assessment_drafts?: Record<string, ModelOption> }): Promise<ChatGPTDraft> {
		if (!chatgptPublication) throw new Error('chatgpt_not_connected');
		const { service: _service, group: _group, state: _state, ...publication } = chatgptPublication;
		const response = await deps.apiFetch('/api/me/chatgpt/models/draft', {
			method: 'POST', cache: 'no-store', headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({ publication, draft: request.draft ?? null, edit: request.edit ?? null,
				administrator: isAdministrator(), assessment_drafts: request.assessment_drafts ?? {} })
		});
		const value = await response.json();
		if (!response.ok) throw new Error(typeof value?.detail?.code === 'string' ? value.detail.code : `HTTP ${response.status}`);
		return value as ChatGPTDraft;
	}

	async function personalResponse(response: Response): Promise<ChatGPTPublication> {
		const body = await response.json();
		if (!response.ok) throw new Error(t().chatgptStatus(body.detail?.code ?? 'chatgpt_transport_unavailable'));
		return body as ChatGPTPublication;
	}

	function isAdministrator(): boolean {
		return deps.currentUser()?.permission_groups?.includes('admins') === true;
	}

	function visibleProvider(provider: string): boolean {
		return provider === 'chatgpt' ? personalModelsAllowed() : isAdministrator();
	}

	// The Server response is authoritative for both catalog metadata and stored
	// provider settings; never retain a locally assembled approximation after a save.
	function acceptModelResponse(data: { catalog: ProviderGroup[]; settings: ModelSettings; model_labels?: ModelLabel[]; assessment_keys?: (keyof ModelOption)[] }, status: string): void {
		setModelLabelTable(data.model_labels);
		if (data.assessment_keys) assessmentKeys = data.assessment_keys;
		modelCatalog = data.catalog;
		modelSettings = data.settings;
		if (personalModelsAllowed() && chatgptPublication) acceptChatGPT(chatgptPublication);
		modelSettingsStatus = status;
	}

	async function loadModelSettings(): Promise<void> {
		if (!isAdministrator() && !personalModelsAllowed()) {
			modelSettings = null;
			modelSettingsStatus = t().settingsAdminOnlyMessage;
			return;
		}
		const owner = deps.currentUser()?.id;
		if (owner !== boundOwner) resetForLoggedOut();
		boundOwner = owner;
		const version = revision;
		modelSettingsLoading = true;
		modelSettings = null;
		modelCatalog = [];
		modelSettingsStatus = null;
		try {
			if (isAdministrator()) {
				const response = await deps.apiFetch('/api/settings/models', { cache: 'no-store' });
				if (!response.ok) throw new Error(`HTTP ${response.status}`);
				const data = await response.json();
				if (!sameOwner(owner, version)) return;
				acceptModelResponse(data, '');
			} else {
				modelCatalog = [];
				modelSettings = { providers: {} };
			}
			if (personalModelsAllowed()) {
				const response = await deps.apiFetch('/api/me/chatgpt/models/settings', { cache: 'no-store' });
				const data = await response.json();
				if (!sameOwner(owner, version) || !personalModelsAllowed()) return;
				if (response.ok) acceptChatGPT(data);
				else {
					chatgptPublication = null;
					modelCatalog = modelCatalog.filter((group) => group.id !== 'chatgpt');
					if (!isAdministrator()) throw new Error(t().chatgptStatus(data.detail?.code ?? 'chatgpt_transport_unavailable'));
				}
			}
			modelSettingsStatus = null;
		} catch (error) {
			if (sameOwner(owner, version)) {
				modelSettings = null;
				modelCatalog = [];
				modelSettingsStatus = error instanceof Error ? error.message : String(error);
			}
		} finally {
			if (sameOwner(owner, version)) modelSettingsLoading = false;
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
					rate_limits: patch.rate_limits,
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
		if (provider === 'chatgpt') {
			if (!personalModelsAllowed()) return;
			const owner = deps.currentUser()?.id, version = revision;
			modelSettingsLoading = true;
			modelFetchResults = { ...modelFetchResults, chatgpt: { type: 'success', message: t().chatgptStatus('chatgpt_models_loading') } };
			try {
				const data = await personalResponse(await deps.apiFetch('/api/me/chatgpt/models/refresh', { method: 'POST' }));
				if (!sameOwner(owner, version) || !personalModelsAllowed()) return;
				acceptChatGPT(data);
				modelFetchResults = { ...modelFetchResults, chatgpt: { type: 'success', message: data.models.length ? t().chatgptModelsLoaded(data.models.length) : t().chatgptModelsEmpty } };
				await deps.loadAvailableModels();
			} catch (error) {
				if (sameOwner(owner, version)) modelFetchResults = { ...modelFetchResults, chatgpt: { type: 'error', message: error instanceof Error ? error.message : String(error) } };
			} finally {
				if (sameOwner(owner, version)) modelSettingsLoading = false;
			}
			return;
		}
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
			rate_limits: provider.rate_limits,
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

	async function saveModelProviderName(provider: Provider, label: string): Promise<boolean> {
		if (!modelSettings || !isAdministrator()) return false;
		const providerSettings = modelSettings.providers[provider];
		const nextLabel = label.trim();
		if (!providerSettings || !nextLabel) return false;
		modelSettingsLoading = true;
		try {
			await saveProviderPayload(provider, modelProviderPayload(provider, providerSettings, nextLabel));
			return true;
		} catch (error) {
			modelSettingsStatus = error instanceof Error ? error.message : String(error);
			return false;
		} finally {
			modelSettingsLoading = false;
		}
	}

	async function saveModelProviderMemo(provider: Provider, memo: string): Promise<boolean> {
		if (!modelSettings || !isAdministrator()) return false;
		const providerSettings = modelSettings.providers[provider];
		if (!providerSettings) return false;
		modelSettingsLoading = true;
		try {
			await saveProviderPayload(provider, modelProviderPayload(provider, providerSettings, undefined, memo));
			return true;
		} catch (error) {
			modelSettingsStatus = error instanceof Error ? error.message : String(error);
			return false;
		} finally {
			modelSettingsLoading = false;
		}
	}

	async function saveModelProvider(provider: Provider, patch: Partial<ModelProviderSetting> = {}): Promise<boolean> {
		if (provider === 'chatgpt') {
			if (!personalModelsAllowed() || !chatgptPublication) return false;
			const owner = deps.currentUser()?.id, version = revision;
			const selected = patch.enabled_models ?? modelSettings?.providers.chatgpt?.enabled_models ?? {};
			const draftModels = patch.models ?? modelSettings?.providers.chatgpt?.models ?? chatgptPublication.models;
			modelSettingsLoading = true;
			try {
				// The save body and the changed shared assessments are the shared core's answer
				// (Sign in with ChatGPT step 2, 2026-11-14). The assessments are shared model
				// settings (the author, 2026-10-13): an administrator saves a changed model's
				// assessment there, before the person's publication, whose answer then carries it.
				const answer = await chatgptDraft({
					draft: {
						selected: Object.fromEntries(chatgptPublication.models.map((model) => [model.id, selected[model.id] === true])),
						purposes: Object.fromEntries(chatgptPublication.models.map((model) => [model.id,
							draftModels.find((draft) => draft.id === model.id)?.purposes ?? model.purposes]))
					},
					assessment_drafts: Object.fromEntries(draftModels.map((model) => [model.id, model]))
				});
				const assessments = answer.assessments;
				if (assessments.length) {
					const shared = await deps.apiFetch('/api/settings/models', {
						method: 'PUT', headers: { 'Content-Type': 'application/json' },
						// The shared assessments go in like any provider's models (the common format).
						body: JSON.stringify({ providers: { chatgpt: { models: assessments } } })
					});
					if (!shared.ok) throw new Error(`HTTP ${shared.status}`);
				}
				const data = await personalResponse(await deps.apiFetch('/api/me/chatgpt/models/settings', {
					method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(answer.save)
				}));
				if (!sameOwner(owner, version) || !personalModelsAllowed()) return false;
				acceptChatGPT(data);
				modelSettingsStatus = t().settingsModelSaved;
				await deps.loadAvailableModels();
				return true;
			} catch (error) {
				if (sameOwner(owner, version)) modelSettingsStatus = error instanceof Error ? error.message : String(error);
				return false;
			} finally {
				if (sameOwner(owner, version)) modelSettingsLoading = false;
			}
		}
		if (!modelSettings || !isAdministrator()) return false;
		const current = modelSettings.providers[provider];
		if (!current) return false;
		modelSettingsLoading = true;
		try {
			await saveProviderPayload(provider, modelProviderPayload(provider, { ...current, ...patch }));
			return true;
		} catch (error) {
			modelSettingsStatus = error instanceof Error ? error.message : String(error);
			return false;
		} finally {
			modelSettingsLoading = false;
		}
	}

	async function saveModelSettings(): Promise<void> {
		if (!modelSettings || !isAdministrator()) return;
		modelSettingsLoading = true;
		try {
			const providers = Object.fromEntries(Object.entries(modelSettings.providers).filter(([id]) => id !== 'chatgpt').map(([id, provider]) => [id, modelProviderPayload(id, provider)]));
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
		get modelSettings() {
			if (!deps.currentUser() || deps.currentUser()?.id !== boundOwner || !modelSettings) return null;
			return { providers: Object.fromEntries(Object.entries(modelSettings.providers).filter(([id]) => visibleProvider(id))) };
		},
		get modelSettingsStatus() { return deps.currentUser()?.id === boundOwner ? modelSettingsStatus : null; },
		get modelFetchResults() {
			return deps.currentUser()?.id === boundOwner ? Object.fromEntries(Object.entries(modelFetchResults).filter(([id]) => visibleProvider(id))) : {};
		},
		// The registration's state, as the Server answered with the publication.
		get chatgptState() { return deps.currentUser()?.id === boundOwner ? chatgptPublication?.state ?? null : null; },
		get modelSettingsLoading() { return deps.currentUser()?.id === boundOwner && modelSettingsLoading; },
		get modelCatalog() { return deps.currentUser()?.id === boundOwner ? modelCatalog.filter((provider) => visibleProvider(provider.id)) : []; },
		updateModelProvider,
		addModelProvider,
		chatgptDraft,
		askDeleteModelProvider,
		fetchProviderModels,
		askClearModelApiKey,
		saveModelProviderName,
		saveModelProviderMemo,
		saveModelProvider,
		saveModelSettings,
		loadModelSettings,
		resetForLoggedOut
	};
}

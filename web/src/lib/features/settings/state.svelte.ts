import type { ApiFetch } from '$lib/transport/api-fetch';
import type { SettingsDetailLevel } from '$lib/settingsDetail';
import type { Provider, ProviderGroup } from '$lib/models';
import {
	createSettingsNavigation,
	type SettingsActor,
	type SettingsMode,
	type SettingsNavigation,
	type SettingsTab
} from './navigation-state.svelte';
import {
	createServerAdministration,
	type ServerAdministration
} from './server-administration.svelte';
import {
	createModelAdministration,
	type ModelAdministration,
	type ModelProviderSetting,
	type SettingsConfirmation
} from './model-administration.svelte';
import {
	createUserAdministration,
	type SettingsUserAdministration
} from './user-administration.svelte';

export type { SettingsMode, SettingsTab } from './navigation-state.svelte';
export type {
	DbBackupEntry,
	PluginItem,
	SettingsStatus
} from './server-administration.svelte';
export type {
	ModelFetchResult,
	ModelProviderSetting,
	ModelSettings,
	SettingsConfirmation
} from './model-administration.svelte';
export type {
	CreateSettingsUserInput,
	SettingsUserAdministration,
	SettingsUserGroup,
	SettingsUserItem,
	UpdateSettingsUserInput
} from './user-administration.svelte';

type SettingsControllerDeps<TActor extends SettingsActor> = {
	apiFetch: ApiFetch;
	currentUser: () => TActor | null;
	setCurrentUser: (actor: TActor) => void;
	loadAvailableModels: () => void | Promise<void>;
	refreshCurrentUserSettings: () => boolean | Promise<boolean>;
	loadExportTemplates: () => void | Promise<void>;
	cancelModelSelection: () => void;
	requestConfirmation: (confirmation: SettingsConfirmation) => void;
	setRenderFanoutLimit: (limit: number) => void;
	describeApiError: (detail: unknown, status: number) => string;
};

export type SettingsController = SettingsNavigation & ServerAdministration & ModelAdministration & {
	readonly modelAdministration: ModelAdministration;
	readonly userAdministration: SettingsUserAdministration;
};

export function createSettingsController<TActor extends SettingsActor>(
	deps: SettingsControllerDeps<TActor>
): SettingsController {
	const serverAdministration = createServerAdministration({
		apiFetch: deps.apiFetch,
		currentUser: deps.currentUser,
		setRenderFanoutLimit: deps.setRenderFanoutLimit,
		describeApiError: deps.describeApiError
	});
	const modelAdministration = createModelAdministration({
		apiFetch: deps.apiFetch,
		currentUser: deps.currentUser,
		loadAvailableModels: deps.loadAvailableModels,
		requestConfirmation: deps.requestConfirmation,
		describeApiError: deps.describeApiError
	});
	const userAdministration = createUserAdministration({
		apiFetch: deps.apiFetch,
		currentUser: deps.currentUser,
		refreshCurrentUserSettings: deps.refreshCurrentUserSettings,
		describeApiError: deps.describeApiError
	});
	const navigation = createSettingsNavigation({
		apiFetch: deps.apiFetch,
		currentUser: deps.currentUser,
		setCurrentUser: deps.setCurrentUser,
		loadAvailableModels: deps.loadAvailableModels,
		cancelModelSelection: deps.cancelModelSelection,
		describeApiError: deps.describeApiError,
		loadTab(tab) {
			if (tab === 'models') void modelAdministration.loadModelSettings();
			if (tab === 'db' || tab === 'server_misc' || tab === 'logs') void serverAdministration.loadStatus();
			if (tab === 'users') void userAdministration.load();
			if (tab === 'export') void deps.loadExportTemplates();
		}
	});

	return {
		get opened() { return navigation.opened; },
		get mode() { return navigation.mode; },
		get tab() { return navigation.tab; },
		get detail() { return navigation.detail; },
		get status() { return serverAdministration.status; },
		get statusError() { return serverAdministration.statusError; },
		get statusLoading() { return serverAdministration.statusLoading; },
		get dbBackupStatus() { return serverAdministration.dbBackupStatus; },
		get outputSaveStatus() { return serverAdministration.outputSaveStatus; },
		get logRetentionStatus() { return serverAdministration.logRetentionStatus; },
		get renderLimitsStatus() { return serverAdministration.renderLimitsStatus; },
		get pluginActionStatus() { return serverAdministration.pluginActionStatus; },
		get renderConcurrencyStatus() { return serverAdministration.renderConcurrencyStatus; },
		get modelSettings() { return modelAdministration.modelSettings; },
		get modelSettingsStatus() { return modelAdministration.modelSettingsStatus; },
		get modelFetchResults() { return modelAdministration.modelFetchResults; },
		get modelSettingsLoading() { return modelAdministration.modelSettingsLoading; },
		get modelCatalog(): ProviderGroup[] { return modelAdministration.modelCatalog; },
		modelAdministration,
		userAdministration,
		restoreDetail: navigation.restoreDetail,
		setDetail: (detail: SettingsDetailLevel) => navigation.setDetail(detail),
		openSettings: navigation.openSettings,
		openModelSelection: navigation.openModelSelection,
		finishModelSelection: navigation.finishModelSelection,
		close: navigation.close,
		selectTab: navigation.selectTab,
		loadStatus: serverAdministration.loadStatus,
		resetForLoggedOut() {
			userAdministration.resetForLoggedOut();
			serverAdministration.resetForLoggedOut();
		},
		loadPluginContent: serverAdministration.loadPluginContent,
		savePlugin: serverAdministration.savePlugin,
		createPlugin: serverAdministration.createPlugin,
		deletePlugin: serverAdministration.deletePlugin,
		setPluginEnabled: serverAdministration.setPluginEnabled,
		updateDbBackupSettings: serverAdministration.updateDbBackupSettings,
		runDbBackupNow: serverAdministration.runDbBackupNow,
		updateOutputSaveSettings: serverAdministration.updateOutputSaveSettings,
		updateRenderConcurrencySettings: serverAdministration.updateRenderConcurrencySettings,
		updateLogRetentionSettings: serverAdministration.updateLogRetentionSettings,
		updateRenderLimits: serverAdministration.updateRenderLimits,
		updateModelProvider: (provider: Provider, patch: Partial<ModelProviderSetting>) => modelAdministration.updateModelProvider(provider, patch),
		addModelProvider: modelAdministration.addModelProvider,
		askDeleteModelProvider: modelAdministration.askDeleteModelProvider,
		fetchProviderModels: modelAdministration.fetchProviderModels,
		askClearModelApiKey: modelAdministration.askClearModelApiKey,
		saveModelProviderName: modelAdministration.saveModelProviderName,
		saveModelProviderMemo: modelAdministration.saveModelProviderMemo,
		saveModelProvider: modelAdministration.saveModelProvider,
		saveModelSettings: modelAdministration.saveModelSettings,
		loadModelSettings: modelAdministration.loadModelSettings
	};
}

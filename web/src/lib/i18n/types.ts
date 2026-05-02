export interface LangPack {
	code: string;
	label: string;

	// Header
	subtitle: string;
	settingsButton: string;
	themeLight: string;
	themeDark: string;

	// Login
	loginTitle: string;
	loginUsernamePlaceholder: string;
	loginPasswordPlaceholder: string;
	loginSubmit: string;
	loginPasswordShow: string;
	loginPasswordHide: string;

	// Model row
	stage1Label: string;
	stage2Label: string;
	providerLabel: string;
	modelLabel: string;
	showThinkingLabel: string;

	// Saijiki
	saijikiLabel: string;
	saijikiToggleBtn: string;
	saijikiTitle: string;
	saijikiHint: string;
	currentSetting: string;
	saveCurrentBtn: string;

	// Input
	modeSingle: string;
	modeDdlEdit: string;
	modeBatch: string;
	modeDemo: string;
	inputPlaceholder: string;
	ddlEditPlaceholder: string;
	batchPlaceholder: string;
	batchCount: (n: number) => string;
	batchHistoryLabel: string;
	batchHistoryPlaceholder: string;
	batchHistoryApply: string;
	batchSummary: (success: number, failed: number, total: number) => string;
	batchFailureTitle: string;
	batchFailureLine: (line: number) => string;
	batchActiveDdlLabel: string;
	batchActiveDdlPending: string;
	batchActiveLine: (line: number) => string;
	batchTokenLine: (input: number | null, output: number | null) => string;
	batchTokenTotal: (input: number, output: number) => string;
	demoSaveDb: string;
	demoSaveFiles: string;
	demoPromptModel: string;
	demoSeedPhrase: string;
	demoInterval: string;
	demoStart: string;
	demoStop: string;
	demoRunning: string;
	demoGeneratedPrompt: string;
	demoGeneratedDdl: string;
	demoSaveCurrent: string;
	demoSavedCurrent: string;
	demoWaiting: (seconds: number) => string;
	demoTotalStats: string;
	demoCurrentStats: string;
	demoStatsPending: string;
	demoRenderCount: (count: number) => string;

	// Submit / loading
	submitBtn: string;
	stopBtn: string;
	stageInterpreting: string;
	stageStructuring: (tokLabel: string) => string;
	batchProgress: (current: number, total: number) => string;

	// Results
	vocabInInputLabel: string;
	thinkingLabel: string;
	ddlLabel: string;
	ddlEditSectionLabel: string;
	ddlEditNote: string;

	// Output tabs
	tabCanvas: string;
	tabPrompts: string;
	tabScore: string;

	// Input
	inputSectionLabel: string;
	canvasAspectButton: string;
	canvasAspectTitle: string;
	modelSelectButton: string;
	colorCatalogButton: string;
	clearInputBtn: string;

	// DDL edit
	replayFromDdlButton: string;
	ddlPaintButton: string;
	ddlEditBtn: string;
	ddlDoneBtn: string;
	saijikiPreviewPlaceholder: string;

	// Canvas
	canvasPlaceholder: string;
	starOn: string;
	starOff: string;
	historyStarredOnly: string;

	// Prompts tab
	promptStage1Input: string;
	promptStage1System: string;
	promptStage2Input: string;
	promptStage2System: string;
	promptLoading: string;
	promptExpand: string;
	promptCollapse: string;
	promptCopy: string;
	promptCopied: string;

	// Download
	exportLabel: string;
	dlSvgBtn: string;
	dlPngLabel: string;
	pngStandard: string;
	pngHighRes: string;
	pngSquare: string;
	pngSquareHighRes: string;

	// Elapsed / tokens
	elapsedDetailed: (s1: number, s2: number, total: number) => string;
	statsInterp: string;
	statsStruct: string;
	statsTotal: string;
	tokenSummary: (
		s1in: number | null,
		s1out: number | null,
		s2in: number | null,
		s2out: number | null
	) => string;

	// History
	historyTitle: string;
	historyCollapse: string;
	historyExpand: string;
	historyLockedDuringDemo: string;
	historyNewerPage: (n: number) => string;
	historyOlderPage: (n: number) => string;
	historyClearBtn: string;
	navOlderBtn: string;
	navNewerBtn: string;
	historyRenderedAtLabel: string;

	// Settings / catalog
	settingsTitle: string;
	settingsTabDb: string;
	settingsTabPlugins: string;
	settingsTabUsers: string;
	settingsTabExport: string;
	settingsTabMisc: string;
	settingsCurrentDb: string;
	settingsDbFileSize: string;
	settingsDbBackupTitle: string;
	settingsDbBackupUnsupported: string;
	settingsDbBackupInterval: string;
	settingsDbBackupMaxGenerations: string;
	settingsDbBackupLastAuto: string;
	settingsDbBackupStoredCounts: (autoCount: number, manualCount: number) => string;
	settingsDbBackupRunNow: string;
	settingsDbBackupRunDone: string;
	settingsDbBackupSaveFailed: string;
	settingsLoading: string;
	settingsLoadFailed: string;
	settingsReload: string;
	settingsPluginsStatus: string;
	settingsPluginsEmpty: string;
	settingsSystemPlugins: string;
	settingsCanvasPluginTitle: string;
	settingsCanvasPluginDescription: string;
	settingsPluginEnabled: string;
	settingsPluginDisabled: string;
	settingsPluginAdminOnly: string;
	settingsUserPlugins: string;
	settingsUserPluginsAddTitle: string;
	settingsUserPluginsAddDescription: string;
	settingsUserPluginPathPlaceholder: string;
	settingsYes: string;
	settingsNo: string;
	settingsUnavailable: string;
	settingsUsersLabel: string;
	settingsDisplayLabel: string;
	settingsMascotLabel: string;
	settingsExportLabel: string;
	settingsExportTemplatesTitle: string;
	settingsExportTemplatesDescription: string;
	settingsExportTemplateName: string;
	settingsExportTemplateDescription: string;
	settingsExportTemplateHeight: string;
	settingsExportTemplateAdd: string;
	settingsExportTemplateDelete: string;
	settingsExportTemplateSaveFailed: string;
	settingsHistoryLabel: string;
	settingsShowBirds: string;
	settingsShowKiwi: string;
	settingsShowCrab: string;
	settingsPngAlpha: string;
	settingsSaveReplay: string;
	colorCatalogTitle: string;
	colorCatalogDetail: string;
	colorCatalogConfirm: string;
	userRoleAdmin: string;
	userRoleGroupLead: string;
	userRoleUser: string;
	settingsUserSessionLabel: string;
	userCountLabel: (n: number) => string;
	userRoleLabel: string;
	userRoleSelectLabel: string;
	userGroupSelectLabel: string;
	userGenerationCountLabel: string;
	profileGenerationCountLabel: string;
	loginRequiredMessage: string;
	settingsAdminOnlyMessage: string;
	userInfoLoadFailed: string;
	userValidationCreate: string;
	userValidationUpdate: string;
	userPasswordTooShort: string;
	bootstrapAdminNote: string;
	userNamePlaceholder: string;
	userEmailPlaceholder: string;
	userPasswordPlaceholder: string;
	userNewPasswordPlaceholder: string;
	groupNamePlaceholder: string;
	userAddTitle: string;
	userEditTitle: string;
	userAddButton: string;
	userClearSelection: string;
	userSaveChanges: string;
	userSelectPrompt: string;
	userManageUnavailable: string;
	userGroupLabel: string;
	userNoGroup: string;
	userDeleteBlockedMessage: string;
	profileButton: string;
	profileTitle: string;
	profileEmailLabel: string;
	profileCurrentPasswordLabel: string;
	profileNewPasswordLabel: string;
	profilePasswordHelp: string;
	profileCurrentPasswordRequired: string;
	profileSaveButton: string;
	profileSavedMessage: string;
	logoutButton: string;
	addButton: string;
	editButton: string;
	deleteButton: string;
	closeLabel: string;
	historyTooltipModel: string;
	historyTooltipSavedAt: string;
	historyTooltipSeconds: string;
	historyTooltipColorCatalog: string;
	historyTooltipTokens: string;
	historyCurrentBadge: string;
	historyManagerTitle: string;
	historyTrashButton: (n: number) => string;
	historyThumbsTab: string;
	historyListTab: string;
	historySelectAll: string;
	historyMoveToTrash: string;
	historyRestoreSelected: string;
	historyPermanentDelete: string;
	historySearchLabel: string;
	historyPrev: string;
	historyNext: string;
	historyLoading: string;
	historyRestore: string;
	historyImageHeader: string;
	historyCreatedAtHeader: string;
	historyModelHeader: string;
	historySecondsHeader: string;
	historyCatalogHeader: string;
	historyActionHeader: string;
	confirmCancel: string;
	confirmRun: string;
	confirmTrashMessage: (n: number) => string;
	confirmRestoreMessage: (n: number) => string;
	confirmPermanentDeleteMessage: (n: number) => string;

	// Saijiki vocabulary (localized words per category key)
	saijikiWords: Record<string, string[]>;
}

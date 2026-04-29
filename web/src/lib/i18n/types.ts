export interface LangPack {
	code: string;
	label: string;

	// Header
	subtitle: string;
	settingsButton: string;

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
	modeBatch: string;
	inputPlaceholder: string;
	batchPlaceholder: string;
	batchCount: (n: number) => string;
	batchSummary: (success: number, failed: number, total: number) => string;
	batchFailureTitle: string;
	batchFailureLine: (line: number) => string;

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

	// Output tabs
	tabCanvas: string;
	tabPrompts: string;
	tabScore: string;

	// Input
	inputSectionLabel: string;
	modelSelectButton: string;
	colorCatalogButton: string;
	clearInputBtn: string;

	// DDL edit
	replayFromDdlButton: string;
	ddlEditBtn: string;
	ddlDoneBtn: string;

	// Canvas
	canvasPlaceholder: string;

	// Prompts tab
	promptStage1Input: string;
	promptStage1System: string;
	promptStage2Input: string;
	promptStage2System: string;
	promptLoading: string;
	promptExpand: string;
	promptCollapse: string;

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
	settingsTabMisc: string;
	settingsCurrentDb: string;
	settingsLoading: string;
	settingsLoadFailed: string;
	settingsReload: string;
	settingsPluginsStatus: string;
	settingsPluginsEmpty: string;
	settingsYes: string;
	settingsNo: string;
	settingsUnavailable: string;
	settingsUsersLabel: string;
	settingsDisplayLabel: string;
	settingsExportLabel: string;
	settingsHistoryLabel: string;
	settingsShowBirds: string;
	settingsPngAlpha: string;
	settingsSaveReplay: string;
	colorCatalogTitle: string;
	colorCatalogDetail: string;
	userRoleAdmin: string;
	userRoleGroupLead: string;
	userRoleUser: string;
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

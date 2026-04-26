export interface LangPack {
	code: string;
	label: string;

	// Header
	subtitle: string;

	// Model row
	stage1Label: string;
	stage2Label: string;
	providerLabel: string;
	modelLabel: string;
	showThinkingLabel: string;

	// Saijiki / Snapshot
	saijikiLabel: string;
	saijikiToggleBtn: string;
	saijikiTitle: string;
	saijikiHint: string;
	currentSetting: string;
	noSnapshots: string;
	saveCurrentBtn: string;
	snapshotNamePlaceholder: string;

	// Input
	modeSingle: string;
	modeBatch: string;
	inputPlaceholder: string;
	batchPlaceholder: string;
	batchCount: (n: number) => string;

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

	// Canvas
	canvasPlaceholder: string;

	// Prompts tab
	promptStage1Input: string;
	promptStage1System: string;
	promptStage2Input: string;
	promptStage2System: string;
	promptLoading: string;

	// Download
	dlSvgBtn: string;
	dlPngLabel: string;

	// Elapsed / tokens
	elapsedDetailed: (s1: number, s2: number, total: number) => string;
	tokenSummary: (
		s1in: number | null,
		s1out: number | null,
		s2in: number | null,
		s2out: number | null
	) => string;

	// History
	historyTitle: string;
	historyNewerPage: string;
	historyOlderPage: string;
	historyClearBtn: string;
	navOlderBtn: string;
	navNewerBtn: string;
}

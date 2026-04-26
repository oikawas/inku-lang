import type { LangPack } from './types';

export const en: LangPack = {
	code: 'en',
	label: 'English',

	subtitle: 'write visual tanka',

	stage1Label: 'interpret',
	stage2Label: 'structure',
	providerLabel: 'provider:',
	modelLabel: 'model:',
	showThinkingLabel: 'show thinking',

	saijikiLabel: 'saijiki:',
	saijikiToggleBtn: 'saijiki',
	saijikiTitle: 'Saijiki',
	saijikiHint: 'Click a word to insert it into the description.',
	currentSetting: 'current settings',
	noSnapshots: 'no snapshots saved',
	saveCurrentBtn: 'save current',
	snapshotNamePlaceholder: 'snapshot name (e.g. saijiki-v1)',

	modeSingle: 'describe',
	modeBatch: 'batch',
	inputPlaceholder: 'A moon rises beyond the mountains',
	batchPlaceholder: 'A moon rises beyond the mountains\nMist spreads at night\nBlue crayon lines',
	batchCount: (n) => `${n} items`,

	submitBtn: 'perform',
	stopBtn: 'stop',
	stageInterpreting: 'interpreting…',
	stageStructuring: (tok) => `structuring…${tok}`,
	batchProgress: (cur, tot) => `performing ${cur} / ${tot}…`,

	vocabInInputLabel: 'vocabulary in input',
	thinkingLabel: 'thinking (qwen3 internal)',
	ddlLabel: 'interpretation (normalized DDL)',

	tabCanvas: 'performance',
	tabPrompts: 'prompts',
	tabScore: 'score',

	canvasPlaceholder: '(not yet performed)',

	promptStage1Input: 'Stage 1 user input',
	promptStage1System: 'Stage 1 system prompt',
	promptStage2Input: 'Stage 2 user input (normalized DDL)',
	promptStage2System: 'Stage 2 system prompt',
	promptLoading: 'loading…',

	dlSvgBtn: '↓ SVG',
	dlPngLabel: 'PNG:',

	elapsedDetailed: (s1, s2, total) =>
		`interp ${s1.toFixed(1)}s + struct ${s2.toFixed(1)}s = ${total.toFixed(1)}s`,
	tokenSummary: (s1in, s1out, s2in, s2out) => {
		const parts: string[] = [];
		if (s1in != null) parts.push(`interp ${s1in}→${s1out ?? '?'}`);
		if (s2in != null) parts.push(`struct ${s2in}→${s2out ?? '?'}`);
		return parts.length ? parts.join(' / ') + ' tok' : '';
	},

	historyTitle: 'history',
	historyNewerPage: '← new',
	historyOlderPage: 'old →',
	historyClearBtn: 'clear all',
	navOlderBtn: '◀',
	navNewerBtn: '▶',
};

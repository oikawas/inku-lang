import type { LangPack } from './types';

export const ja: LangPack = {
	code: 'ja',
	label: '日本語',

	subtitle: '視覚的な短歌を書く',

	stage1Label: '解釈',
	stage2Label: '構造化',
	providerLabel: '接続先：',
	modelLabel: 'モデル：',
	showThinkingLabel: '思考を表示',

	saijikiLabel: '歳時記:',
	saijikiToggleBtn: '歳時記',
	saijikiTitle: '歳時記',
	saijikiHint: '語彙をクリックすると記述欄に挿入されます。',
	currentSetting: '現在の設定',
	noSnapshots: '保存済みスナップショットはありません',
	saveCurrentBtn: '現在を保存',
	snapshotNamePlaceholder: 'スナップショット名 (例: 歳時記v1)',

	modeSingle: '記述',
	modeBatch: 'バッチ',
	inputPlaceholder: '山の向こうに月が昇る',
	batchPlaceholder: '山の向こうに月が昇る\n夜の霧が広がる\n青いクレヨンの線',
	batchCount: (n) => `${n} 件`,

	submitBtn: '演奏する',
	stopBtn: '停止',
	stageInterpreting: '解釈中…',
	stageStructuring: (tok) => `構造化中…${tok}`,
	batchProgress: (cur, tot) => `${cur} / ${tot} 番目を演奏中…`,

	vocabInInputLabel: '入力に含まれた語彙',
	thinkingLabel: '思考 (qwen3 内部)',
	ddlLabel: '解釈 (正規化DDL)',

	tabCanvas: '演奏',
	tabPrompts: 'プロンプト',
	tabScore: '楽譜',

	canvasPlaceholder: '（まだ演奏されていない）',

	promptStage1Input: 'Stage 1 ユーザー入力',
	promptStage1System: 'Stage 1 システムプロンプト',
	promptStage2Input: 'Stage 2 ユーザー入力 (正規化DDL)',
	promptStage2System: 'Stage 2 システムプロンプト',
	promptLoading: '読み込み中…',

	dlSvgBtn: '↓ SVG',
	dlPngLabel: 'PNG:',

	elapsedDetailed: (s1, s2, total) =>
		`解釈 ${s1.toFixed(1)}s + 構造化 ${s2.toFixed(1)}s = ${total.toFixed(1)}s`,
	tokenSummary: (s1in, s1out, s2in, s2out) => {
		const parts: string[] = [];
		if (s1in != null) parts.push(`解釈 ${s1in}→${s1out ?? '?'}`);
		if (s2in != null) parts.push(`構造化 ${s2in}→${s2out ?? '?'}`);
		return parts.length ? parts.join(' / ') + ' tok' : '';
	},

	historyTitle: '履歴',
	historyNewerPage: '← 新',
	historyOlderPage: '旧 →',
	historyClearBtn: '全て消す',
	navOlderBtn: '◀',
	navNewerBtn: '▶',
};

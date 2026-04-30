<script module lang="ts">
	declare const __BUILD_NUMBER__: string;
</script>

<script lang="ts">
	import { onMount } from 'svelte';
	import { annotate } from '$lib/highlight';
	import AuthPanel from '$lib/components/AuthPanel.svelte';
	import CanvasPanel from '$lib/components/CanvasPanel.svelte';
	import ConfirmDialog from '$lib/components/ConfirmDialog.svelte';
	import ColorCatalogModal from '$lib/components/ColorCatalogModal.svelte';
	import DdlEditor from '$lib/components/DdlEditor.svelte';
	import HistoryManager from '$lib/components/HistoryManager.svelte';
	import HistoryStrip from '$lib/components/HistoryStrip.svelte';
	import InputPanel from '$lib/components/InputPanel.svelte';
	import SaijikiDrawer from '$lib/components/SaijikiDrawer.svelte';
	import SettingsModal from '$lib/components/SettingsModal.svelte';
	import {
		DEFAULT_PROVIDER,
		DEFAULT_MODEL,
		modelsForProvider,
		providerOfModel,
		type Provider
	} from '$lib/models';
	import { t, setLang, getLang, PACK_LIST, initLang } from '$lib/i18n/index.svelte';
	import { COLOR_CATALOGS, getCatalogById, getRenderColorMap, type RenderColorMap } from '$lib/colors';

	const HISTORY_MANAGER_PAGE_SIZE = 100;
	const PROVIDER_STAGE1_KEY = 'inku-provider-stage1';
	const MODEL_STAGE1_KEY    = 'inku-model-stage1';
	const PROVIDER_STAGE2_KEY = 'inku-provider-stage2';
	const MODEL_STAGE2_KEY    = 'inku-model-stage2';
	const CATALOG_KEY         = 'inku-color-catalog';
	const SHOW_BIRDS_KEY      = 'inku-show-birds';
	const PNG_ALPHA_KEY       = 'inku-png-alpha-white';
	const SAVE_REPLAY_KEY     = 'inku-save-replay-history';
	const BATCH_FAILURE_REPORT_KEY = 'inku-batch-failure-report';
	const BATCH_FAILURE_REPORT_MAX_ITEMS = 100;
	const BATCH_FAILURE_REPORT_MAX_TEXT = 300;

	type Score = { instructions: unknown[] };

	type PaintResult = {
		svg: string;
		score: Score;
		history_id?: string | null;
		history_at?: number | null;
		elapsed_stage1_ms: number;
		elapsed_stage2_ms: number;
		elapsed_total_ms: number;
		tokens_in_stage1: number | null;
		tokens_out_stage1: number | null;
		tokens_in_stage2: number | null;
		tokens_out_stage2: number | null;
	};

	type Iteration = {
		id?: string;
		input: string;
		ddl: string | null;
		thinking?: string | null;
		score: Score;
		svg: string;
		at: number;
		elapsed_ms?: number;
		stage1_model?: string | null;
		stage2_model?: string | null;
		tokens_in?: number | null;
		tokens_out?: number | null;
		catalog_id?: string | null;
		trashed?: boolean;
	};
	type BatchFailure = {
		line: number;
		input: string;
		message: string;
	};
	type BatchFailureReport = {
		success: number;
		total: number;
		failures: BatchFailure[];
	};

	type PluginItem = {
		name: string;
		version: string;
		status: string;
	};
	type SettingsStatus = {
		database: {
			backend: string;
			driver: string;
			url: string;
			database: string | null;
			is_default: boolean;
			runtime_editable: boolean;
			note: string;
		};
		plugins: {
			enabled: boolean;
			loaded: PluginItem[];
			runtime_editable: boolean;
			note: string;
		};
	};

	type UserRole = 'admin' | 'group_lead' | 'user';
	type UserGroup = {
		id: string;
		name: string;
		at: number;
	};
	type UserItem = {
		id: string;
		username: string;
		email: string;
		role: UserRole;
		role_label: string;
		group_id: string | null;
		group_name: string | null;
		at: number;
	};
	// ── Input ───────────────────────────────────────────────
	const DEFAULT_INPUT = '山の向こうに月が昇る';
	let inputMode   = $state<'single' | 'batch'>('single');
	let input       = $state(DEFAULT_INPUT);
	let batchInput  = $state('');
	let stage1UserPrompt = $state('');
	let ddlTextareaEl = $state<HTMLTextAreaElement | null>(null);
	let ddlHighlightEl = $state<HTMLDivElement | null>(null);
	let ddlSelection = $state({ start: 0, end: 0 });
	let ddlFocused = $state(false);
	let copiedPrompt = $state<'stage1' | 'stage2' | null>(null);

	// ── Loading ─────────────────────────────────────────────
	let loading    = $state(false);
	let activeRunMode = $state<'single' | 'batch' | null>(null);
	let stageLabel = $state('');
	let batchCurrent = $state(0);
	let batchTotal   = $state(0);
	let batchSuccess = $state(0);
	let batchFailures = $state<BatchFailure[]>([]);
	let batchFailureReport = $state<BatchFailureReport | null>(null);
	let batchActiveLine = $state<number | null>(null);
	let batchActiveDdl = $state<string | null>(null);
	let error        = $state<string | null>(null);

	// ── Replay ──────────────────────────────────────────────
	let reloading   = $state(false);
	let reloadError = $state<string | null>(null);

	// ── Result ──────────────────────────────────────────────
	let ddl      = $state<string | null>(null);
	let thinking = $state<string | null>(null);
	let result   = $state<PaintResult | null>(null);

	// ── UI ──────────────────────────────────────────────────
	let windowWidth  = $state(1200);
	let saijikiOpen  = $state(false);
	let activeSaijikiPreview = $state<SaijikiPreview | null>(null);
	let settingsOpen = $state(false);
	let settingsMode = $state<'model' | 'settings'>('settings');
	let settingsTab  = $state<'connection' | 'db' | 'plugins' | 'users' | 'misc'>('connection');
	let pngMenuOpen  = $state(false);
	let userMenuOpen = $state(false);
	let catalogOpen  = $state(false);
	let catalogSelectionSnapshot = $state<string | null>(null);
	let statsOpen    = $state(false);
	let outputTab    = $state<'canvas' | 'prompts' | 'score'>('canvas');
	let zoom         = $state(1);
	let canvasFitZoom = $state(1);
	let panX         = $state(0);
	let panY         = $state(0);
	let canvasDragging = $state(false);
	let dragStartX   = 0;
	let dragStartY   = 0;
	let dragStartPanX = 0;
	let dragStartPanY = 0;
	let promptStage1Expanded = $state(false);
	let promptStage2Expanded = $state(false);
	type ModelSelectionSnapshot = {
		stage1Provider: Provider;
		stage1Model: string;
		stage2Provider: Provider;
		stage2Model: string;
	};
	let modelSelectionSnapshot = $state<ModelSelectionSnapshot | null>(null);
	let showBirds = $state(true);
	let pngAlphaWhite = $state(false);
	let saveReplayAsNewVersion = $state(true);
	let miscSettingsLoaded = $state(false);

	// DOM refs for outside-click handling
	let pngWrapEl      = $state<HTMLDivElement | null>(null);
	let userMenuWrapEl = $state<HTMLDivElement | null>(null);

	type SaijikiPreview = {
		categoryKey: string;
		word: string;
		canonicalWord: string;
		effect: string;
		example: string;
		svg: string;
	};

	function saijikiPreview(categoryKey: string, canonicalWord: string, word: string): SaijikiPreview {
		const base = {
			categoryKey,
			word,
			canonicalWord,
			effect: '',
			example: '',
			svg: '',
		};
		const lineSvg = (attrs = '', strokeWidth = 5, lineCap = 'round', stroke = '#2b2b2b') => `<svg viewBox="0 0 180 92" aria-hidden="true"><rect width="180" height="92" rx="6" fill="#fffdf8"/><path d="M22 56 C56 26 95 76 158 38" fill="none" stroke="${stroke}" stroke-width="${strokeWidth}" stroke-linecap="${lineCap}" ${attrs}/></svg>`;
		const shapeSvg = (shape: string) => `<svg viewBox="0 0 180 92" aria-hidden="true"><rect width="180" height="92" rx="6" fill="#fffdf8"/>${shape}</svg>`;
		const angleSvg = (rotation: number, line = false) => shapeSvg(line
			? `<g transform="rotate(${rotation} 90 46)"><path d="M42 46 H138" fill="none" stroke="#2b2b2b" stroke-width="6" stroke-linecap="round"/></g><circle cx="90" cy="46" r="2.5" fill="#c9c2b5"/>`
			: `<g transform="rotate(${rotation} 90 46)"><rect x="58" y="29" width="64" height="34" fill="none" stroke="#2b2b2b" stroke-width="5" rx="2"/></g><circle cx="90" cy="46" r="2.5" fill="#c9c2b5"/>`);
		const scatter = `<svg viewBox="0 0 180 92" aria-hidden="true"><rect width="180" height="92" rx="6" fill="#fffdf8"/><circle cx="42" cy="35" r="5" fill="#2b2b2b"/><circle cx="84" cy="58" r="4" fill="#2b2b2b"/><circle cx="122" cy="30" r="5" fill="#2b2b2b"/><circle cx="146" cy="65" r="3.5" fill="#2b2b2b"/><circle cx="62" cy="72" r="3.5" fill="#2b2b2b"/></svg>`;
		const previews: Record<string, Omit<SaijikiPreview, 'categoryKey' | 'word' | 'canonicalWord'>> = {
			円: { effect: '正円を描く。中心と半径で配置される。', example: '中央に黒い円を置く', svg: shapeSvg('<circle cx="90" cy="46" r="25" fill="none" stroke="#2b2b2b" stroke-width="5"/>') },
			楕円: { effect: '横または縦に伸びた円を描く。', example: '横長の楕円を置く', svg: shapeSvg('<ellipse cx="90" cy="46" rx="42" ry="22" fill="none" stroke="#2b2b2b" stroke-width="5"/>') },
			三角: { effect: '三つの頂点を持つ形を描く。', example: '上に三角を置く', svg: shapeSvg('<path d="M90 20 L132 70 L48 70 Z" fill="none" stroke="#2b2b2b" stroke-width="5" stroke-linejoin="round"/>') },
			四角: { effect: '矩形を描く。比率語で縦長・横長にもなる。', example: '中央に四角を置く', svg: shapeSvg('<rect x="58" y="24" width="64" height="44" fill="none" stroke="#2b2b2b" stroke-width="5" rx="2"/>') },
			線: { effect: '始点から終点へ線を引く。', example: '左から右へ線を引く', svg: lineSvg() },
			弧: { effect: '円周の一部を描く。半円や三日月の基礎になる。', example: '上弦の弧を引く', svg: shapeSvg('<path d="M44 58 Q90 18 136 58" fill="none" stroke="#2b2b2b" stroke-width="6" stroke-linecap="round"/>') },
			水平: { effect: '0度の向き。線なら横線として扱う。', example: '水平の線を引く', svg: angleSvg(0, true) },
			垂直: { effect: '90度の向き。線なら縦線として扱う。', example: '垂直の線を引く', svg: angleSvg(90, true) },
			斜め: { effect: '約45度の傾きを与える。', example: '斜めの四角を置く', svg: angleSvg(45) },
			右上がり: { effect: '左下から右上へ向かう傾き。', example: '右上がりの線', svg: angleSvg(-30, true) },
			右下がり: { effect: '左上から右下へ向かう傾き。', example: '右下がりの線', svg: angleSvg(30, true) },
			回転: { effect: '図形全体を中心まわりに回転させる。', example: '回転した横長の四角', svg: angleSvg(30) },
			髪: { effect: '非常に細い線。繊細な輪郭に向く。', example: '髪のように細い線', svg: lineSvg('', 1.5) },
			鉛筆: { effect: '細めで軽い線。素描のような質感。', example: '鉛筆の線を引く', svg: lineSvg('opacity="0.82"', 3) },
			ペン: { effect: '標準的な太さの明瞭な線。', example: 'ペンの線を引く', svg: lineSvg('', 4) },
			ロットリング: { effect: '均一で硬い製図ペン風の線。', example: 'ロットリングの円', svg: lineSvg('', 3, 'butt') },
			クレヨン: { effect: '太く柔らかい描き味。色面にも向く。', example: '青いクレヨンの線', svg: lineSvg('opacity="0.72"', 9) },
			チョーク: { effect: 'かすれを含む淡い線。', example: '白いチョークの線', svg: lineSvg('opacity="0.46"', 8) },
			細筆: { effect: '筆圧のある細い筆線。', example: '細筆で弧を引く', svg: lineSvg('', 4) },
			太筆: { effect: '太く存在感のある筆線。', example: '太筆で黒い線を引く', svg: lineSvg('', 11) },
			縄: { effect: '太く荒い線。結び目や束の印象を作る。', example: '縄のような線', svg: lineSvg('stroke-dasharray="10 5"', 10) },
			実線: { effect: '切れ目のない線。', example: '実線で引く', svg: lineSvg() },
			破線: { effect: '短い線分を間隔を空けて並べる。', example: '破線の弧', svg: lineSvg('stroke-dasharray="14 9"') },
			点線: { effect: '点の連なりとして描く。', example: '点線で囲む', svg: lineSvg('stroke-dasharray="1 12"') },
			一点鎖線: { effect: '長線と点を交互に並べる。', example: '一点鎖線を引く', svg: lineSvg('stroke-dasharray="18 7 2 7"') },
			白: { effect: '白系の色で描く。背景との対比に注意。', example: '白い円', svg: shapeSvg('<rect x="48" y="18" width="84" height="56" fill="#2b2b2b" opacity="0.16"/><circle cx="90" cy="46" r="24" fill="#ffffff" stroke="#c9c2b5" stroke-width="4"/>') },
			黒: { effect: '黒で描く。最も強い輪郭になる。', example: '黒い円', svg: shapeSvg('<circle cx="90" cy="46" r="25" fill="#2b2b2b"/>') },
			青: { effect: '青系の色で描く。', example: '青い線', svg: lineSvg('', 5, 'round', '#2c5fb8') },
			赤: { effect: '赤系の色で描く。', example: '赤い三角', svg: shapeSvg('<path d="M90 20 L132 70 L48 70 Z" fill="none" stroke="#c9362d" stroke-width="6" stroke-linejoin="round"/>') },
			緑: { effect: '緑系の色で描く。', example: '緑の点を散らす', svg: scatter.replaceAll('#2b2b2b', '#2f8a4b') },
			灰: { effect: '灰色で描く。弱い輪郭や背景に向く。', example: '灰色の四角', svg: shapeSvg('<rect x="58" y="24" width="64" height="44" fill="none" stroke="#777777" stroke-width="6" rx="2"/>') },
			細かく: { effect: '小さな揺らぎを加える。', example: '細かく揺れる線', svg: lineSvg() },
			大きく: { effect: '振幅の大きな揺らぎを加える。', example: '大きく波打つ線', svg: shapeSvg('<path d="M20 48 C42 8 64 84 88 48 S134 8 160 48" fill="none" stroke="#2b2b2b" stroke-width="5" stroke-linecap="round"/>') },
			ゆっくり: { effect: 'ゆったりした周期の動きとして解釈する。', example: 'ゆっくり波打つ線', svg: shapeSvg('<path d="M22 48 C62 20 112 76 158 48" fill="none" stroke="#2b2b2b" stroke-width="5" stroke-linecap="round"/>') },
			速く: { effect: '細かく速い振動として解釈する。', example: '速く震える線', svg: shapeSvg('<path d="M20 48 L32 40 L44 56 L56 40 L68 56 L80 40 L92 56 L104 40 L116 56 L128 40 L140 56 L158 48" fill="none" stroke="#2b2b2b" stroke-width="4" stroke-linecap="round"/>') },
			揺れる: { effect: '自然な揺れを線や配置に与える。', example: '揺れる線', svg: lineSvg() },
			波打つ: { effect: '波形のうねりを作る。', example: '波打つ青い線', svg: shapeSvg('<path d="M20 48 C42 22 66 74 88 48 S134 22 160 48" fill="none" stroke="#2c5fb8" stroke-width="5" stroke-linecap="round"/>') },
			震える: { effect: '細かい震えを作る。', example: '震える黒い線', svg: shapeSvg('<path d="M20 48 L30 45 L40 52 L50 44 L60 50 L70 43 L80 51 L90 45 L100 53 L110 44 L120 50 L130 43 L140 51 L160 48" fill="none" stroke="#2b2b2b" stroke-width="4" stroke-linecap="round"/>') },
			滲む: { effect: '輪郭をぼかし、墨が染みるようにする。', example: '滲む黒い円', svg: shapeSvg('<defs><filter id="pblur"><feGaussianBlur stdDeviation="3"/></filter></defs><circle cx="90" cy="46" r="24" fill="#2b2b2b" opacity="0.72" filter="url(#pblur)"/><circle cx="90" cy="46" r="20" fill="#2b2b2b" opacity="0.62"/>') },
			上: { effect: '画面の上側へ配置する。', example: '上に円を置く', svg: shapeSvg('<circle cx="90" cy="25" r="14" fill="#2b2b2b"/><path d="M28 70 H152" stroke="#d7d1c4" stroke-width="2"/>') },
			下: { effect: '画面の下側へ配置する。', example: '下に円を置く', svg: shapeSvg('<path d="M28 22 H152" stroke="#d7d1c4" stroke-width="2"/><circle cx="90" cy="67" r="14" fill="#2b2b2b"/>') },
			中央: { effect: '中央付近へ配置する。', example: '中央に円を置く', svg: shapeSvg('<circle cx="90" cy="46" r="16" fill="#2b2b2b"/>') },
			左端: { effect: '左端近くへ寄せる。', example: '左端に線を置く', svg: shapeSvg('<path d="M30 18 V74" stroke="#2b2b2b" stroke-width="7" stroke-linecap="round"/><path d="M90 16 V76" stroke="#d7d1c4" stroke-width="2"/>') },
			右端: { effect: '右端近くへ寄せる。', example: '右端に線を置く', svg: shapeSvg('<path d="M90 16 V76" stroke="#d7d1c4" stroke-width="2"/><path d="M150 18 V74" stroke="#2b2b2b" stroke-width="7" stroke-linecap="round"/>') },
			上端: { effect: '上の縁へ寄せる。', example: '上端に線を引く', svg: shapeSvg('<path d="M30 18 H150" stroke="#2b2b2b" stroke-width="7" stroke-linecap="round"/><path d="M28 46 H152" stroke="#d7d1c4" stroke-width="2"/>') },
			下端: { effect: '下の縁へ寄せる。', example: '下端に線を引く', svg: shapeSvg('<path d="M28 46 H152" stroke="#d7d1c4" stroke-width="2"/><path d="M30 74 H150" stroke="#2b2b2b" stroke-width="7" stroke-linecap="round"/>') },
			中心: { effect: '中心座標を基準に配置する。', example: '中心に円を置く', svg: shapeSvg('<path d="M90 14 V78 M32 46 H148" stroke="#d7d1c4" stroke-width="2"/><circle cx="90" cy="46" r="15" fill="#2b2b2b"/>') },
			隅: { effect: '四隅のいずれかへ配置する。', example: '隅に小さな円を置く', svg: shapeSvg('<circle cx="36" cy="25" r="11" fill="#2b2b2b"/><circle cx="144" cy="67" r="11" fill="#2b2b2b" opacity="0.28"/>') },
			置く: { effect: '指定した場所に一つ置く。', example: '中央に円を置く', svg: shapeSvg('<circle cx="90" cy="46" r="22" fill="#2b2b2b"/>') },
			並べる: { effect: '同じ要素を列として並べる。', example: '円を横に並べる', svg: shapeSvg('<circle cx="55" cy="46" r="12" fill="#2b2b2b"/><circle cx="90" cy="46" r="12" fill="#2b2b2b"/><circle cx="125" cy="46" r="12" fill="#2b2b2b"/>') },
			埋める: { effect: '面や領域を密に満たす。', example: '点で埋める', svg: shapeSvg('<circle cx="50" cy="28" r="5" fill="#2b2b2b"/><circle cx="80" cy="32" r="5" fill="#2b2b2b"/><circle cx="112" cy="29" r="5" fill="#2b2b2b"/><circle cx="62" cy="55" r="5" fill="#2b2b2b"/><circle cx="97" cy="58" r="5" fill="#2b2b2b"/><circle cx="132" cy="55" r="5" fill="#2b2b2b"/>') },
			散らす: { effect: '要素を不規則に散布する。', example: '黒い点を散らす', svg: scatter },
			引く: { effect: '線や弧を描く動作。', example: '線を引く', svg: lineSvg() },
			縦長: { effect: '縦方向に長い比率にする。', example: '縦長の楕円', svg: shapeSvg('<ellipse cx="90" cy="46" rx="20" ry="34" fill="none" stroke="#2b2b2b" stroke-width="5"/>') },
			横長: { effect: '横方向に長い比率にする。', example: '横長の楕円', svg: shapeSvg('<ellipse cx="90" cy="46" rx="42" ry="18" fill="none" stroke="#2b2b2b" stroke-width="5"/>') },
			全幅: { effect: '画面幅いっぱいに広げる。', example: '全幅の線', svg: shapeSvg('<path d="M14 46 H166" stroke="#2b2b2b" stroke-width="6" stroke-linecap="round"/>') },
			半幅: { effect: '画面の半分程度の幅にする。', example: '半幅の線', svg: shapeSvg('<path d="M45 46 H135" stroke="#2b2b2b" stroke-width="6" stroke-linecap="round"/><path d="M14 72 H166" stroke="#d7d1c4" stroke-width="2"/>') },
			半円: { effect: '円の半分を描く。', example: '半円を置く', svg: shapeSvg('<path d="M50 60 A40 40 0 0 1 130 60" fill="none" stroke="#2b2b2b" stroke-width="6" stroke-linecap="round"/>') },
			上弦: { effect: '上側に弦を持つ弧として扱う。', example: '上弦の月', svg: shapeSvg('<path d="M50 56 Q90 22 130 56" fill="none" stroke="#2b2b2b" stroke-width="6" stroke-linecap="round"/>') },
			下弦: { effect: '下側に弦を持つ弧として扱う。', example: '下弦の月', svg: shapeSvg('<path d="M50 36 Q90 70 130 36" fill="none" stroke="#2b2b2b" stroke-width="6" stroke-linecap="round"/>') },
			三日月: { effect: '細い月形を描く。', example: '三日月を置く', svg: shapeSvg('<path d="M106 18 C76 24 62 52 82 74 C52 63 50 27 82 14 C92 12 100 14 106 18 Z" fill="#2b2b2b"/>') },
		};
		return { ...base, ...(previews[canonicalWord] ?? { effect: '記述の解釈に影響する語彙です。', example: `${word}を使う`, svg: lineSvg() }) };
	}

	// ── Color catalog ────────────────────────────────────────
	let selectedCatalog = $state('default');
	const currentCatalog = $derived(getCatalogById(selectedCatalog) ?? COLOR_CATALOGS[0]);

	function activeColorMap(): RenderColorMap | null {
		if (selectedCatalog === 'default') return null;
		return getRenderColorMap(selectedCatalog);
	}

	// ── Settings tabs ────────────────────────────────────────
	let settingsStatus = $state<SettingsStatus | null>(null);
	let settingsStatusError = $state<string | null>(null);
	let settingsStatusLoading = $state(false);
	let users = $state<UserItem[]>([]);
	let groups = $state<UserGroup[]>([]);
	let newUserName = $state('');
	let newUserEmail = $state('');
	let newUserPassword = $state('');
	let newUserRole = $state<UserRole>('user');
	let newUserGroupId = $state('');
	let selectedUserId = $state<string | null>(null);
	let editUserName = $state('');
	let editUserEmail = $state('');
	let editUserPassword = $state('');
	let editUserRole = $state<UserRole>('user');
	let editUserGroupId = $state('');
	let newGroupName = $state('');
	let userSettingsStatus = $state<string | null>(null);
	let userSettingsLoading = $state(false);
	let userSettingsRequestId = 0;
	let authToken = $state<string | null>(null);
	let currentUser = $state<UserItem | null>(null);
	let loginUserName = $state('admin');
	let loginPassword = $state('');
	let loginPasswordVisible = $state(false);
	let loginStatus = $state<string | null>(null);

	function apiFetch(path: string, init: RequestInit = {}) {
		const headers = new Headers(init.headers);
		return fetch(path, { ...init, headers, credentials: 'same-origin' });
	}

	function openSettings(tab: typeof settingsTab = 'db') {
		settingsMode = 'settings';
		settingsTab = tab;
		settingsOpen = true;
		if (tab === 'db' || tab === 'plugins') void loadSettingsStatus();
		if (tab === 'users') void loadUserSettings();
	}

	function openModelSelection() {
		modelSelectionSnapshot = { stage1Provider, stage1Model, stage2Provider, stage2Model };
		settingsMode = 'model';
		settingsTab = 'connection';
		settingsOpen = true;
	}

	function persistModelSelection() {
		try {
			localStorage.setItem(PROVIDER_STAGE1_KEY, stage1Provider);
			localStorage.setItem(MODEL_STAGE1_KEY, stage1Model);
			localStorage.setItem(PROVIDER_STAGE2_KEY, stage2Provider);
			localStorage.setItem(MODEL_STAGE2_KEY, stage2Model);
		} catch {}
	}

	function confirmModelSelection() {
		modelSelectionSnapshot = null;
		persistModelSelection();
		settingsOpen = false;
	}

	function cancelModelSelection() {
		if (modelSelectionSnapshot) {
			stage1Provider = modelSelectionSnapshot.stage1Provider;
			stage1Model = modelSelectionSnapshot.stage1Model;
			stage2Provider = modelSelectionSnapshot.stage2Provider;
			stage2Model = modelSelectionSnapshot.stage2Model;
			persistModelSelection();
		}
		modelSelectionSnapshot = null;
		settingsOpen = false;
	}

	function closeSettingsModal() {
		if (settingsMode === 'model') cancelModelSelection();
		else settingsOpen = false;
	}

	function openCatalogModal() {
		catalogSelectionSnapshot = selectedCatalog;
		catalogOpen = true;
	}

	function persistSelectedCatalog() {
		try { localStorage.setItem(CATALOG_KEY, selectedCatalog); } catch {}
	}

	function confirmCatalogSelection() {
		catalogSelectionSnapshot = null;
		persistSelectedCatalog();
		catalogOpen = false;
	}

	function cancelCatalogSelection() {
		if (catalogSelectionSnapshot !== null) {
			selectedCatalog = catalogSelectionSnapshot;
			persistSelectedCatalog();
		}
		catalogSelectionSnapshot = null;
		catalogOpen = false;
	}

	function selectSettingsTab(tab: typeof settingsTab) {
		settingsTab = tab;
		if (tab === 'db' || tab === 'plugins') void loadSettingsStatus();
		if (tab === 'users') void loadUserSettings();
	}

	async function loadUserSettings() {
		const requestId = ++userSettingsRequestId;
		userSettingsLoading = true;
		try {
			const meResponse = await apiFetch('/api/auth/me', { cache: 'no-store' });
			if (!meResponse.ok) throw new Error(t().loginRequiredMessage);
			const actor = await meResponse.json() as UserItem;
			if (requestId !== userSettingsRequestId) return;
			currentUser = actor;
			authToken = 'cookie';
			if (!['admin', 'group_lead'].includes(actor.role)) {
				users = [];
				groups = [];
				userSettingsStatus = null;
				return;
			}
			const [groupsResponse, usersResponse] = await Promise.all([
				apiFetch('/api/user-groups', { cache: 'no-store' }),
				apiFetch('/api/users', { cache: 'no-store' }),
			]);
			if (!groupsResponse.ok || !usersResponse.ok) throw new Error(t().userInfoLoadFailed);
			const [nextGroups, nextUsers] = await Promise.all([
				groupsResponse.json() as Promise<UserGroup[]>,
				usersResponse.json() as Promise<UserItem[]>,
			]);
			if (requestId !== userSettingsRequestId) return;
			groups = nextGroups;
			users = nextUsers;
			if (!newUserGroupId && groups[0]) newUserGroupId = groups[0].id;
			if (selectedUserId) {
				const selected = users.find((user) => user.id === selectedUserId);
				if (selected) setEditUser(selected);
				else clearEditUser();
			}
			userSettingsStatus = null;
		} catch (e) {
			if (requestId !== userSettingsRequestId) return;
			userSettingsStatus = e instanceof Error ? e.message : String(e);
		} finally {
			if (requestId === userSettingsRequestId) userSettingsLoading = false;
		}
	}

	async function loadSettingsStatus() {
		if (!currentUser || currentUser.role !== 'admin') {
			settingsStatus = null;
			settingsStatusError = currentUser
				? t().settingsAdminOnlyMessage
				: t().loginRequiredMessage;
			return;
		}
		settingsStatusLoading = true;
		try {
			const r = await apiFetch('/api/settings/status');
			if (!r.ok) {
				const d = await r.json().catch(() => ({})) as { detail?: string };
				throw new Error(d.detail ?? `HTTP ${r.status}`);
			}
			settingsStatus = await r.json();
			settingsStatusError = null;
		} catch (e) {
			settingsStatus = null;
			settingsStatusError = e instanceof Error ? e.message : String(e);
		} finally {
			settingsStatusLoading = false;
		}
	}

	async function loadCurrentUser() {
		try {
			const r = await apiFetch('/api/auth/me');
			if (!r.ok) throw new Error('session expired');
			currentUser = await r.json();
			authToken = 'cookie';
			loginStatus = null;
			await Promise.all([loadUserSettings(), loadSettingsStatus()]);
			await Promise.all([fetchHistoryPage(0), fetchTrashPage()]);
			if (historyItems.length > 0) loadIteration(0);
		} catch {
			authToken = null;
			currentUser = null;
			loginStatus = t().loginRequiredMessage;
			settingsStatus = null;
			settingsStatusError = t().loginRequiredMessage;
			historyItems = [];
			historyTotal = 0;
			trashItems = [];
			trashTotal = 0;
		}
	}

	async function login() {
		loginStatus = null;
		try {
			const r = await fetch('/api/auth/login', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				credentials: 'same-origin',
				body: JSON.stringify({ username: loginUserName, password: loginPassword })
			});
			if (!r.ok) {
				const d = await r.json().catch(() => ({})) as { detail?: string };
				throw new Error(d.detail ?? `HTTP ${r.status}`);
			}
			const data = await r.json() as { user: UserItem };
			authToken = 'cookie';
			currentUser = data.user;
			loginStatus = null;
			historyItems = [];
			historyTotal = 0;
			trashItems = [];
			trashTotal = 0;
			managerHistoryItems = [];
			managerHistoryTotal = 0;
			managerTrashItems = [];
			managerTrashTotal = 0;
			loginPassword = '';
			await Promise.all([loadUserSettings(), loadSettingsStatus()]);
			await Promise.all([fetchHistoryPage(0), fetchTrashPage()]);
			if (historyItems.length > 0) loadIteration(0);
		} catch (e) {
			const message = e instanceof Error ? e.message : String(e);
			loginStatus = message;
			userSettingsStatus = message;
		}
	}

	async function logout() {
		if (currentUser || authToken) {
			try { await apiFetch('/api/auth/logout', { method: 'POST' }); } catch {}
		}
		userMenuOpen = false;
		authToken = null;
		currentUser = null;
		loginStatus = null;
		settingsStatus = null;
		settingsStatusError = t().loginRequiredMessage;
		users = [];
		groups = [];
		historyItems = [];
		historyTotal = 0;
		trashItems = [];
		trashTotal = 0;
		managerHistoryItems = [];
		managerHistoryTotal = 0;
		managerTrashItems = [];
		managerTrashTotal = 0;
	}

	async function addUser() {
		const name = newUserName.trim();
		const email = newUserEmail.trim();
		if (currentUser?.role === 'group_lead') {
			newUserRole = 'user';
			newUserGroupId = currentUser.group_id ?? '';
		}
		if (!name || !email || newUserPassword.length < 8) {
			userSettingsStatus = t().userValidationCreate;
			return;
		}
		try {
			const r = await apiFetch('/api/users', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ username: name, email, password: newUserPassword, role: newUserRole, group_id: newUserGroupId || null })
			});
			if (!r.ok) {
				const d = await r.json().catch(() => ({})) as { detail?: string };
				throw new Error(d.detail ?? `HTTP ${r.status}`);
			}
			newUserName = '';
			newUserEmail = '';
			newUserPassword = '';
			newUserRole = 'user';
			await loadUserSettings();
		} catch (e) {
			userSettingsStatus = e instanceof Error ? e.message : String(e);
		}
	}

	async function updateUser(user: UserItem, patch: Partial<UserItem> & { password?: string }) {
		try {
			const r = await apiFetch(`/api/users/${user.id}`, {
				method: 'PATCH',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify(patch)
			});
			if (!r.ok) {
				const d = await r.json().catch(() => ({})) as { detail?: string };
				throw new Error(d.detail ?? `HTTP ${r.status}`);
			}
			await loadUserSettings();
		} catch (e) {
			userSettingsStatus = e instanceof Error ? e.message : String(e);
			await loadUserSettings();
		}
	}

	function setEditUser(user: UserItem) {
		selectedUserId = user.id;
		editUserName = user.username;
		editUserEmail = user.email;
		editUserPassword = '';
		editUserRole = user.role;
		editUserGroupId = user.group_id ?? '';
	}

	function clearEditUser() {
		selectedUserId = null;
		editUserName = '';
		editUserEmail = '';
		editUserPassword = '';
		editUserRole = 'user';
		editUserGroupId = '';
	}

	async function saveUserEdit() {
		const user = users.find((item) => item.id === selectedUserId);
		if (!user) return;
		const username = editUserName.trim();
		const email = editUserEmail.trim();
		if (!username || !email) {
			userSettingsStatus = t().userValidationUpdate;
			return;
		}
		if (editUserPassword && editUserPassword.length < 8) {
			userSettingsStatus = t().userPasswordTooShort;
			return;
		}
		const patch: Partial<UserItem> & { password?: string } = {
			username,
			email,
			role: currentUser?.role === 'group_lead' ? 'user' : editUserRole,
			group_id: currentUser?.role === 'group_lead' ? currentUser.group_id : (editUserGroupId || null),
		};
		if (editUserPassword) patch.password = editUserPassword;
		await updateUser(user, patch);
	}

	async function removeUser(id: string) {
		try {
			const r = await apiFetch(`/api/users/${id}`, { method: 'DELETE' });
			if (!r.ok) {
				const d = await r.json().catch(() => ({})) as { detail?: string };
				throw new Error(d.detail ?? `HTTP ${r.status}`);
			}
			if (selectedUserId === id) clearEditUser();
			await loadUserSettings();
		} catch (e) {
			userSettingsStatus = e instanceof Error ? e.message : String(e);
		}
	}

	async function addGroup() {
		const name = newGroupName.trim();
		if (!name) return;
		try {
			const r = await apiFetch('/api/user-groups', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ name })
			});
			if (!r.ok) {
				const d = await r.json().catch(() => ({})) as { detail?: string };
				throw new Error(d.detail ?? `HTTP ${r.status}`);
			}
			newGroupName = '';
			await loadUserSettings();
		} catch (e) {
			userSettingsStatus = e instanceof Error ? e.message : String(e);
		}
	}

	async function removeGroup(group: UserGroup) {
		try {
			const r = await apiFetch(`/api/user-groups/${group.id}`, { method: 'DELETE' });
			if (!r.ok) {
				const d = await r.json().catch(() => ({})) as { detail?: string };
				throw new Error(d.detail ?? `HTTP ${r.status}`);
			}
			await loadUserSettings();
		} catch (e) {
			userSettingsStatus = e instanceof Error ? e.message : String(e);
		}
	}

	function persistMiscSettings() {
		try {
			localStorage.setItem(SHOW_BIRDS_KEY, showBirds ? '1' : '0');
			localStorage.setItem(PNG_ALPHA_KEY, pngAlphaWhite ? '1' : '0');
			localStorage.setItem(SAVE_REPLAY_KEY, saveReplayAsNewVersion ? '1' : '0');
		} catch {}
	}

	// ── 感情語 → DDL ヒント ──────────────────────────────────
	const EMOTION_DDL_MAP: Record<string, string> = {
		'美しい':  '線は細く(pencil)、揺らぎは小さく(fine)、動きはゆっくり(slow)',
		'美しく':  '線は細く(pencil)、揺らぎは小さく(fine)、動きはゆっくり(slow)',
		'激しい':  '線は太く(brush_thick)、揺らぎは大きく(broad)、動きは速く(high)',
		'激しく':  '線は太く(brush_thick)、揺らぎは大きく(broad)、動きは速く(high)',
		'静かな':  '揺らぎなし(none)、線は細く(hair)、密度を低く',
		'静かに':  '揺らぎなし(none)、線は細く(hair)、密度を低く',
		'素敵':    '線は細く(pen)、揺らぎは小さく(fine)、配置は整然と',
		'きれい':  '線は細く(pencil)、揺らぎは小さく(fine)、密度を低く',
		'やさしい':'揺らぎは波(wave)、振幅は小さく(fine)、線は細く(pencil)',
		'切ない':  '色は青(blue)か灰(gray)、線は細く(hair)、揺らぎはゆっくり(slow)',
		'哀しい':  '色は青(blue)、線は細く(hair)、要素数は少なく',
		'儚い':    '線は最細(hair)、破線か点線(dashed/dotted)、要素は散らす(scatter)',
		'神秘的':  '背景は黒(black)、円や弧を使う(circle/arc)、放射状(radial)',
		'幻想的':  '揺らぎはperlin、振幅は大きく(broad)、複数色(color_cycle)',
		'寂しい':  '要素数は少なく、間隔を広く、色は灰(gray)',
		'爽やか':  '色は青(blue)か白(white)背景、線は細く(pen)、揺らぎなし(none)',
	};

	function buildEmotionHint(text: string): string {
		const emotions = annotate(text).filter(p => p.kind === 'emotion').map(p => p.text);
		if (emotions.length === 0) return '';
		const hints = emotions.map(e => {
			const h = EMOTION_DDL_MAP[e];
			return h ? `「${e}」→ ${h}` : `「${e}」`;
		});
		return `\n\n[感情語をDDLに反映してください: ${hints.join('、')}]`;
	}

	// ── エクスポートファイル名 ────────────────────────────────
	function exportFilename(ext: string, size?: number): string {
		const now = new Date();
		const pad = (n: number) => String(n).padStart(2, '0');
		const date = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
		const time = `${pad(now.getHours())}-${pad(now.getMinutes())}`;
		const sizeStr = size != null ? `-${size}` : '';
		return `inku-${date}-${time}${sizeStr}.${ext}`;
	}

	// ── Models ──────────────────────────────────────────────
	let stage1Provider  = $state<Provider>(DEFAULT_PROVIDER);
	let stage1Model     = $state<string>(DEFAULT_MODEL);
	let stage2Provider  = $state<Provider>(DEFAULT_PROVIDER);
	let stage2Model     = $state<string>(DEFAULT_MODEL);
	let includeThinking = $state(false);

	// ── Timer ───────────────────────────────────────────────
	let elapsedStage1Ms = $state(0);
	let elapsedStage2Ms = $state(0);
	let elapsedTotalMs  = $state(0);
	let liveMs          = $state(0);
	let _timerStart     = 0;
	let _timerHandle: ReturnType<typeof setInterval> | null = null;

	// ── Tokens ──────────────────────────────────────────────
	let tokensInStage1  = $state<number | null>(null);
	let tokensOutStage1 = $state<number | null>(null);
	let tokensInStage2  = $state<number | null>(null);
	let tokensOutStage2 = $state<number | null>(null);

	// ── History ─────────────────────────────────────────────
	let historyItems = $state<Iteration[]>([]);
	let historyTotal = $state(0);
	let historyOffset = $state(0);
	let historyCursor = $state(-1);
	let displayedHistoryItem = $state<Iteration | null>(null);
	const visibleThumbCount = $derived(Math.max(1, Math.floor((windowWidth - 40) / 89)));
	const historyWindowSize = $derived(visibleThumbCount);
	const historyPage = $derived(Math.floor(historyOffset / historyWindowSize));
	const historyTotalPages = $derived(Math.max(1, Math.ceil(historyTotal / historyWindowSize)));
	let historyManagerOpen = $state(false);
	let historyManagerView = $state<'active' | 'trash'>('active');
	let historyManagerTab = $state<'thumbs' | 'list'>('thumbs');
	let historyManagerPage = $state(0);
	let historyManagerLoading = $state(false);
	let managerHistoryItems = $state<Iteration[]>([]);
	let managerHistoryTotal = $state(0);
	let managerTrashItems = $state<Iteration[]>([]);
	let managerTrashTotal = $state(0);
	let trashItems = $state<Iteration[]>([]);
	let trashTotal = $state(0);
	let historySearch = $state('');
	let selectedHistoryIds = $state<string[]>([]);
	let confirmAction = $state<{ message: string; run: () => void; destructive?: boolean } | null>(null);
	const managedHistoryItems = $derived(historyManagerView === 'trash' ? managerTrashItems : managerHistoryItems);
	const managedHistoryTotal = $derived(historyManagerView === 'trash' ? managerTrashTotal : managerHistoryTotal);
	const historyManagerTotalPages = $derived(Math.max(1, Math.ceil(managedHistoryTotal / HISTORY_MANAGER_PAGE_SIZE)));
	const historyManagerOffset = $derived(historyManagerPage * HISTORY_MANAGER_PAGE_SIZE);
	const historyManagerShownTo = $derived(Math.min(historyManagerOffset + managedHistoryItems.length, managedHistoryTotal));

	let promptsData = $state<{ stage1_system: string; stage2_system: string } | null>(null);

	// ── Batch derived ────────────────────────────────────────
	const batchLines    = $derived(batchInput.split('\n'));
	const lineNumbersText = $derived(batchLines.map((_, i) => String(i + 1)).join('\n'));
	const batchNonEmpty = $derived(batchLines.filter((l) => l.trim()).length);
	const batchRunning = $derived(activeRunMode === 'batch' && loading);
	const singleRunning = $derived(activeRunMode === 'single' && loading);
	const canSubmit     = $derived(
		inputMode === 'single' ? !!input.trim() : batchNonEmpty > 0
	);

	// ── Timer ───────────────────────────────────────────────
	function startTimer() {
		_timerStart = Date.now();
		liveMs = 0;
		_timerHandle = setInterval(() => { liveMs = Date.now() - _timerStart; }, 100);
	}
	function stopTimer() {
		if (_timerHandle !== null) { clearInterval(_timerHandle); _timerHandle = null; }
	}
	function compactBatchFailureReport(report: BatchFailureReport): BatchFailureReport {
		return {
			success: report.success,
			total: report.total,
			failures: report.failures.slice(0, BATCH_FAILURE_REPORT_MAX_ITEMS).map((failure) => ({
				line: failure.line,
				input: failure.input.slice(0, BATCH_FAILURE_REPORT_MAX_TEXT),
				message: failure.message.slice(0, BATCH_FAILURE_REPORT_MAX_TEXT),
			})),
		};
	}
	function setBatchFailureReport(report: BatchFailureReport | null) {
		const compactReport = report ? compactBatchFailureReport(report) : null;
		batchFailureReport = compactReport;
		try {
			if (compactReport) localStorage.setItem(BATCH_FAILURE_REPORT_KEY, JSON.stringify(compactReport));
			else localStorage.removeItem(BATCH_FAILURE_REPORT_KEY);
		} catch {
			try { localStorage.removeItem(BATCH_FAILURE_REPORT_KEY); } catch {}
		}
	}
	function loadBatchFailureReport(): BatchFailureReport | null {
		try {
			const raw = localStorage.getItem(BATCH_FAILURE_REPORT_KEY);
			if (!raw) return null;
			const report = JSON.parse(raw) as Partial<BatchFailureReport>;
			if (
				typeof report.success !== 'number' ||
				typeof report.total !== 'number' ||
				!Array.isArray(report.failures)
			) return null;
			const failures = report.failures
				.filter((failure): failure is BatchFailure =>
					typeof failure?.line === 'number' &&
					typeof failure.input === 'string' &&
					typeof failure.message === 'string'
				);
			if (failures.length === 0) return null;
			return compactBatchFailureReport({ success: report.success, total: report.total, failures });
		} catch {
			return null;
		}
	}

	// ── Core paint (2-stage) ─────────────────────────────────
	async function paintOne(text: string, historyInput = text): Promise<{ ddl: string; thinking: string | null } & PaintResult> {
		const lang = getLang();
		stageLabel = t().stageInterpreting;

		const augmented = text + buildEmotionHint(text);
		stage1UserPrompt = augmented;
		const r = await apiFetch('/api/paint', {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({
				text: augmented,
				original_text: text,
				stage1_model: stage1Model,
				stage2_model: stage2Model,
				include_thinking: includeThinking,
				lang,
				color_map: activeColorMap(),
				save_history: true,
				history_input: historyInput,
				catalog_id: selectedCatalog !== 'default' ? selectedCatalog : null
			})
		});
		if (!r.ok) {
			const d = await r.json().catch(() => ({})) as { detail?: string };
			throw new Error(d.detail ?? `HTTP ${r.status}`);
		}
		stageLabel = t().stageStructuring('');
		return await r.json() as { ddl: string; thinking: string | null } & PaintResult;
	}

	async function refreshHistoryAfterServerSave() {
		await fetchHistoryOffset(0);
		historyCursor = 0;
	}

	// ── Submit ──────────────────────────────────────────────
	async function submit() {
		if (!canSubmit || loading) return;
		const submittedMode = inputMode;
		loading = true; error = null;
		activeRunMode = submittedMode;
		ddl = null; thinking = null; ddlSelection = { start: 0, end: 0 };
		displayedHistoryItem = null;
		elapsedStage1Ms = 0; elapsedStage2Ms = 0; elapsedTotalMs = 0;
		tokensInStage1 = null; tokensOutStage1 = null; tokensInStage2 = null; tokensOutStage2 = null;
		batchCurrent = 0; batchActiveLine = null; batchActiveDdl = null;
		startTimer();

		try {
			if (submittedMode === 'single') {
				const r = await paintOne(input);
				ddl = r.ddl; ddlSelection = { start: r.ddl.length, end: r.ddl.length }; thinking = r.thinking; result = r; outputTab = 'canvas';
				fitCanvasZoom();
				elapsedStage1Ms = r.elapsed_stage1_ms; elapsedStage2Ms = r.elapsed_stage2_ms; elapsedTotalMs = r.elapsed_total_ms;
				tokensInStage1 = r.tokens_in_stage1; tokensOutStage1 = r.tokens_out_stage1;
				tokensInStage2 = r.tokens_in_stage2; tokensOutStage2 = r.tokens_out_stage2;
				await refreshHistoryAfterServerSave();
			} else {
				batchTotal = 0; batchSuccess = 0; batchFailures = []; setBatchFailureReport(null);
				const lines = batchLines
					.map((line, index) => ({ line: index + 1, input: line.trim() }))
					.filter((item) => item.input);
				batchTotal = lines.length; outputTab = 'canvas';
				for (let i = 0; i < lines.length; i++) {
					if (!loading) break;
					batchCurrent = i + 1;
					batchActiveLine = lines[i].line;
					try {
						const r = await paintOne(lines[i].input, `#${lines[i].line} ${lines[i].input}`);
						batchActiveDdl = r.ddl;
						thinking = r.thinking;
						if (displayedHistoryItem === null) {
							result = r;
							ddl = r.ddl;
							ddlSelection = { start: r.ddl.length, end: r.ddl.length };
							fitCanvasZoom();
						}
						await refreshHistoryAfterServerSave();
						batchSuccess += 1;
						if (batchFailures.length > 0) {
							setBatchFailureReport({ success: batchSuccess, total: batchTotal, failures: batchFailures });
						}
					} catch (e) {
						batchFailures = [
							...batchFailures,
							{
								line: lines[i].line,
								input: lines[i].input,
								message: e instanceof Error ? e.message : String(e),
							},
						];
						setBatchFailureReport({ success: batchSuccess, total: batchTotal, failures: batchFailures });
					}
				}
				elapsedTotalMs = Date.now() - _timerStart;
				if (batchFailures.length > 0) {
					setBatchFailureReport({
						success: batchSuccess,
						total: batchTotal,
						failures: batchFailures,
					});
				}
			}
		} catch (e) {
			error = e instanceof Error ? e.message : String(e); result = null;
		} finally {
			stopTimer(); loading = false; activeRunMode = null; stageLabel = ''; batchCurrent = 0; batchActiveLine = null; batchActiveDdl = null;
		}
	}

	function stopBatch() { loading = false; }

	// ── Replay (Stage 2 のみ) ────────────────────────────────
	async function replay() {
		if (!ddl || reloading) return;
		reloading = true; reloadError = null;
		displayedHistoryItem = null;
		const lang = getLang();
		const startedAt = Date.now();
		try {
			const r = await apiFetch('/api/compose', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ ddl, model: stage2Model, original_text: input, lang, color_map: activeColorMap() })
			});
			if (!r.ok) {
				const d = await r.json().catch(() => ({})) as { detail?: string };
				throw new Error(d.detail ?? `HTTP ${r.status}`);
			}
			const d = await r.json() as { score: Score; svg: string; tokens_in: number | null; tokens_out: number | null };
			const elapsedMs = Date.now() - startedAt;
			result = result
				? { ...result, score: d.score, svg: d.svg }
				: { score: d.score, svg: d.svg, elapsed_stage1_ms: 0, elapsed_stage2_ms: elapsedMs, elapsed_total_ms: elapsedMs, tokens_in_stage1: null, tokens_out_stage1: null, tokens_in_stage2: d.tokens_in, tokens_out_stage2: d.tokens_out };
			if (result) {
				result = { ...result, elapsed_stage2_ms: elapsedMs, elapsed_total_ms: elapsedMs, tokens_in_stage2: d.tokens_in, tokens_out_stage2: d.tokens_out };
			}
			if (saveReplayAsNewVersion) {
				await pushHistory({
					input,
					ddl,
					score: d.score,
					svg: d.svg,
					at: Date.now(),
					elapsed_ms: elapsedMs,
					stage1_model: stage1Model,
					stage2_model: stage2Model,
					tokens_in: d.tokens_in,
					tokens_out: d.tokens_out,
					catalog_id: selectedCatalog !== 'default' ? selectedCatalog : null
				});
			}
			outputTab = 'canvas';
			fitCanvasZoom();
		} catch (e) {
			reloadError = e instanceof Error ? e.message : String(e);
		} finally {
			reloading = false;
		}
	}

	// ── History ─────────────────────────────────────────────
	async function fetchHistoryOffset(offset: number): Promise<void> {
		if (!authToken) {
			historyItems = [];
			historyTotal = 0;
			historyOffset = 0;
			return;
		}
		const safeOffset = Math.max(0, offset);
		try {
			const r = await apiFetch(`/api/history?offset=${safeOffset}&limit=${historyWindowSize}`);
			if (!r.ok) return;
			const data = await r.json();
			if (data.items.length === 0 && data.total > 0 && safeOffset > 0) {
				const lastOffset = Math.floor((data.total - 1) / historyWindowSize) * historyWindowSize;
				await fetchHistoryOffset(lastOffset);
				return;
			}
			historyItems = data.items; historyTotal = data.total; historyOffset = safeOffset;
			if (historyCursor >= data.items.length) historyCursor = data.items.length > 0 ? 0 : -1;
			if (historyCursor < 0 && data.items.length > 0) historyCursor = 0;
		} catch { /* ignore */ }
	}

	async function fetchHistoryPage(page: number): Promise<void> {
		await fetchHistoryOffset(page * historyWindowSize);
	}

	async function gotoHistoryNewerPage(): Promise<void> {
		await fetchHistoryPage(historyPage - 1);
		loadIteration(0);
	}

	async function gotoHistoryOlderPage(): Promise<void> {
		await fetchHistoryPage(historyPage + 1);
		loadIteration(0);
	}

	async function fetchTrashPage(): Promise<void> {
		if (!authToken) {
			trashItems = [];
			trashTotal = 0;
			return;
		}
		try {
			const r = await apiFetch(`/api/history?offset=0&limit=100&trashed=true`);
			if (!r.ok) return;
			const data = await r.json();
			trashItems = data.items; trashTotal = data.total;
		} catch { /* ignore */ }
	}

	async function fetchHistoryManager(): Promise<void> {
		if (!authToken) return;
		historyManagerLoading = true;
		try {
			const trashed = historyManagerView === 'trash';
			const offset = historyManagerPage * HISTORY_MANAGER_PAGE_SIZE;
			const params = new URLSearchParams({
				offset: String(offset),
				limit: String(HISTORY_MANAGER_PAGE_SIZE),
				q: historySearch.trim(),
			});
			if (trashed) params.set('trashed', 'true');
			const r = await apiFetch(`/api/history?${params.toString()}`);
			if (!r.ok) return;
			const data = await r.json();
			if (trashed) {
				managerTrashItems = data.items;
				managerTrashTotal = data.total;
				if (!historySearch.trim()) {
					trashItems = data.items.slice(0, 100);
					trashTotal = data.total;
				}
			} else {
				managerHistoryItems = data.items;
				managerHistoryTotal = data.total;
			}
			if (data.items.length === 0 && data.total > 0 && historyManagerPage > 0) {
				historyManagerPage -= 1;
				await fetchHistoryManager();
			}
		} catch { /* ignore */ }
		finally {
			historyManagerLoading = false;
		}
	}

	async function pushHistory(it: Iteration): Promise<void> {
		if (!authToken) return;
		try {
				await apiFetch('/api/history', {
					method: 'POST',
					headers: { 'Content-Type': 'application/json' },
					body: JSON.stringify({ input: it.input, ddl: it.ddl, score: it.score, at: it.at, elapsed_ms: it.elapsed_ms ?? 0, stage1_model: it.stage1_model ?? null, stage2_model: it.stage2_model ?? null, tokens_in: it.tokens_in ?? null, tokens_out: it.tokens_out ?? null, catalog_id: it.catalog_id ?? null, color_map: activeColorMap() })
				});
		} catch { /* ignore */ }
		await fetchHistoryOffset(0);
		historyCursor = 0;
	}

	function clearInput() {
		if (inputMode === 'single') input = ''; else batchInput = '';
		ddl = null;
		thinking = null;
		result = null;
		stage1UserPrompt = '';
		error = null;
		reloadError = null;
		outputTab = 'canvas';
		elapsedStage1Ms = 0;
		elapsedStage2Ms = 0;
		elapsedTotalMs = 0;
		tokensInStage1 = null;
		tokensOutStage1 = null;
		tokensInStage2 = null;
		tokensOutStage2 = null;
		ddlFocused = false;
		ddlSelection = { start: 0, end: 0 };
		displayedHistoryItem = null;
		historyCursor = -1;
		resetZoom();
	}

	function toggleHistorySelection(id: string) {
		selectedHistoryIds = selectedHistoryIds.includes(id)
			? selectedHistoryIds.filter((x) => x !== id)
			: [...selectedHistoryIds, id];
	}

	function selectAllManagedHistory() {
		const ids = managedHistoryItems.map((it) => it.id).filter((id): id is string => !!id);
		selectedHistoryIds = selectedHistoryIds.length === ids.length ? [] : ids;
	}

	async function postHistoryIds(path: string, ids: string[]) {
		if (!authToken) return;
		await apiFetch(path, {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({ ids })
		});
		selectedHistoryIds = [];
		await Promise.all([fetchHistoryOffset(historyOffset), fetchTrashPage(), fetchHistoryManager()]);
		if (historyItems.length === 0 && historyOffset > 0) await fetchHistoryOffset(Math.max(0, historyOffset - historyWindowSize));
	}

	function askTrash(ids: string[]) {
		if (ids.length === 0) return;
		confirmAction = {
			message: t().confirmTrashMessage(ids.length),
			run: () => { void postHistoryIds('/api/history/trash', ids); }
		};
	}

	function askRestore(ids: string[]) {
		if (ids.length === 0) return;
		confirmAction = {
			message: t().confirmRestoreMessage(ids.length),
			run: () => { void postHistoryIds('/api/history/restore', ids); }
		};
	}

	function askPermanentDelete(ids: string[]) {
		if (ids.length === 0) return;
		confirmAction = {
			message: t().confirmPermanentDeleteMessage(ids.length),
			destructive: true,
			run: () => { void postHistoryIds('/api/history/permanent-delete', ids); }
		};
	}

	function loadIteration(idx: number) {
		if (idx < 0 || idx >= historyItems.length) return;
		historyCursor = idx;
		loadIterationItem(historyItems[idx]);
	}

	function loadIterationItem(it: Iteration) {
		inputMode = 'single';
		displayedHistoryItem = it;
		const itemDDL = it.ddl ?? '';
		input = it.input; ddl = itemDDL; ddlSelection = { start: itemDDL.length, end: itemDDL.length }; thinking = it.thinking ?? null;
		stage1UserPrompt = it.input ? it.input + buildEmotionHint(it.input) : '';
		result = { score: it.score, svg: it.svg, elapsed_stage1_ms: 0, elapsed_stage2_ms: 0, elapsed_total_ms: it.elapsed_ms ?? 0, tokens_in_stage1: null, tokens_out_stage1: null, tokens_in_stage2: null, tokens_out_stage2: null };
		error = null;
		outputTab = 'canvas';
		fitCanvasZoom();
	}

	const currentRenderedAt = $derived(
		historyCursor >= 0 && historyItems[historyCursor]
			? new Date(historyItems[historyCursor].at).toLocaleString(getLang() === 'ja' ? 'ja-JP' : 'en-US')
			: null
	);

	async function gotoPrev() {
		if (historyCursor < historyItems.length - 1) { loadIteration(historyCursor + 1); }
		else if (historyOffset + historyWindowSize < historyTotal) { await fetchHistoryOffset(historyOffset + historyWindowSize); loadIteration(0); }
	}
	async function gotoNext() {
		if (historyCursor > 0) { loadIteration(historyCursor - 1); }
		else if (historyOffset > 0) { await fetchHistoryOffset(Math.max(0, historyOffset - historyWindowSize)); loadIteration(historyItems.length - 1); }
	}

	const prevDisabled = $derived(historyCursor < 0 || historyOffset + historyCursor >= historyTotal - 1);
	const nextDisabled = $derived(historyCursor <= 0 && historyOffset <= 0);
	const navPos       = $derived(historyOffset + historyCursor + 1);

	// ── Saijiki ─────────────────────────────────────────────
	function insertWord(word: string) {
		if (ddl === null) return;
		const ta = ddlTextareaEl;
		if (!ta) {
			ddl = ddl + word;
			ddlSelection = { start: ddl.length, end: ddl.length };
			return;
		}
		const hasTextareaFocus = document.activeElement === ta;
		const currentDDL = ddl;
		const liveStart = ta.selectionStart ?? ddlSelection.start;
		const liveEnd = ta.selectionEnd ?? ddlSelection.end;
		const savedStart = ddlSelection.start;
		const savedEnd = ddlSelection.end;
		const start = Math.max(0, Math.min(currentDDL.length, hasTextareaFocus ? liveStart : savedStart));
		const end = Math.max(start, Math.min(currentDDL.length, hasTextareaFocus ? liveEnd : savedEnd));
		ddl = currentDDL.slice(0, start) + word + currentDDL.slice(end);
		ddlSelection = { start: start + word.length, end: start + word.length };
		requestAnimationFrame(() => {
			if (!ddlTextareaEl) return;
			ddlTextareaEl.focus();
			ddlTextareaEl.setSelectionRange(ddlSelection.start, ddlSelection.end);
		});
	}

	function rememberDDLSelection() {
		const ta = ddlTextareaEl;
		if (!ta || ddl === null) return;
		ddlSelection = {
			start: ta.selectionStart ?? ddl.length,
			end: ta.selectionEnd ?? ddl.length,
		};
	}

	function syncDDLHighlightScroll() {
		if (!ddlTextareaEl || !ddlHighlightEl) return;
		ddlHighlightEl.scrollTop = ddlTextareaEl.scrollTop;
		ddlHighlightEl.scrollLeft = ddlTextareaEl.scrollLeft;
	}

	function handleKeydown(e: KeyboardEvent) {
		if (e.key === 'Escape') {
			saijikiOpen = false;
			userMenuOpen = false;
			if (settingsOpen) closeSettingsModal();
			if (catalogOpen) cancelCatalogSelection();
			historyManagerOpen = false;
			confirmAction = null;
		}
		if (!shouldIgnoreCanvasShortcut(e)) handleCanvasKeydown(e);
	}

	function shouldIgnoreCanvasShortcut(e: KeyboardEvent) {
		if (!currentUser || settingsOpen || catalogOpen || historyManagerOpen || confirmAction) return true;
		const target = e.target;
		if (!(target instanceof HTMLElement)) return false;
		if (target.isContentEditable) return true;
		return !!target.closest('input, textarea, select, [contenteditable="true"]');
	}

	function handleDocClick(e: MouseEvent) {
		if (pngMenuOpen  && pngWrapEl     && !pngWrapEl.contains(e.target as Node))      pngMenuOpen  = false;
		if (userMenuOpen && userMenuWrapEl && !userMenuWrapEl.contains(e.target as Node)) userMenuOpen = false;
	}

	// ── Model selection ─────────────────────────────────────
	function setStage1Provider(v: Provider) {
		displayedHistoryItem = null;
		stage1Provider = v; stage1Model = modelsForProvider(v)[0]?.id ?? stage1Model;
	}
	function setStage1Model(v: string) {
		displayedHistoryItem = null;
		stage1Model = v;
	}
	function setStage2Provider(v: Provider) {
		displayedHistoryItem = null;
		stage2Provider = v; stage2Model = modelsForProvider(v)[0]?.id ?? stage2Model;
	}
	function setStage2Model(v: string) {
		displayedHistoryItem = null;
		stage2Model = v;
	}
	function setSelectedCatalog(id: string) {
		displayedHistoryItem = null;
		selectedCatalog = id;
	}

	// ── Download ────────────────────────────────────────────
	function escapeXml(s: string): string {
		return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
	}
	function triggerDownload(blob: Blob, filename: string) {
		const url = URL.createObjectURL(blob);
		const a = document.createElement('a'); a.href = url; a.download = filename; a.click();
		URL.revokeObjectURL(url);
	}
	function downloadSVG() {
		if (!result) return;
		const desc = `<desc>${escapeXml(input)}</desc>`;
		const svg  = result.svg.replace(/(<svg[^>]*>)/, `$1${desc}`);
		triggerDownload(new Blob([svg], { type: 'image/svg+xml' }), exportFilename('svg'));
	}

	async function downloadPNG(size: number) {
		if (!result) return;
		let svg = result.svg.replace(/(<svg)([^>]*)/, (_: string, tag: string, attrs: string) => {
			const a = attrs.replace(/\s+width="[^"]*"/g, '').replace(/\s+height="[^"]*"/g, '');
			return `${tag}${a} width="${size}" height="${size}"`;
		});
		const blob = new Blob([svg], { type: 'image/svg+xml' });
		const url  = URL.createObjectURL(blob);
		try {
			await new Promise<void>((resolve, reject) => {
				const canvas = document.createElement('canvas');
				canvas.width = size; canvas.height = size;
				const ctx = canvas.getContext('2d')!;
				if (!pngAlphaWhite) {
					ctx.fillStyle = '#ffffff'; ctx.fillRect(0, 0, size, size);
				}
				const img = new Image();
				img.onload = () => {
					ctx.drawImage(img, 0, 0, size, size);
					canvas.toBlob((b) => {
						if (!b) { reject(new Error('canvas error')); return; }
						triggerDownload(b, exportFilename('png', size)); resolve();
					}, 'image/png');
				};
				img.onerror = () => reject(new Error('svg load error'));
				img.src = url;
			});
		} finally { URL.revokeObjectURL(url); }
	}

	// ── Prompts ─────────────────────────────────────────────
	async function fetchPrompts(): Promise<void> {
		try { const r = await fetch(`/api/prompts?lang=${getLang()}`); if (r.ok) promptsData = await r.json(); } catch {}
	}

	async function copyPromptText(kind: 'stage1' | 'stage2', text: string | null | undefined): Promise<void> {
		const value = text ?? '';
		try {
			if (navigator.clipboard?.writeText) {
				await navigator.clipboard.writeText(value);
			} else {
				const textarea = document.createElement('textarea');
				textarea.value = value;
				textarea.setAttribute('readonly', 'true');
				textarea.style.position = 'fixed';
				textarea.style.left = '-9999px';
				document.body.appendChild(textarea);
				textarea.select();
				document.execCommand('copy');
				document.body.removeChild(textarea);
			}
			copiedPrompt = kind;
			window.setTimeout(() => {
				if (copiedPrompt === kind) copiedPrompt = null;
			}, 1200);
		} catch {
			copiedPrompt = null;
		}
	}

	function shortModel(m: string | null | undefined): string {
		if (!m) return '';
		if (m.includes('opus')) return 'opus';
		if (m.includes('haiku')) return 'haiku';
		if (m.includes('sonnet')) return 'sonnet';
		if (m.includes('qwen3')) return 'qwen3';
		if (m.includes('qwen')) return 'qwen';
		if (m.includes('gemma')) return 'gemma';
		return (m.split('/').pop() ?? m).slice(0, 8);
	}

	function statusModelName(m: string | null | undefined): string {
		if (!m) return '';
		const model = modelsForProvider(providerOfModel(m)).find((option) => option.id === m);
		return model?.label ?? m;
	}

	function catalogName(id: string | null | undefined): string {
		return getCatalogById(id ?? 'default')?.name ?? 'inku Default';
	}

	const statusStage1Model = $derived(displayedHistoryItem
		? (displayedHistoryItem.stage1_model ? statusModelName(displayedHistoryItem.stage1_model) : '-')
		: statusModelName(stage1Model));
	const statusStage2Model = $derived(displayedHistoryItem
		? (displayedHistoryItem.stage2_model ? statusModelName(displayedHistoryItem.stage2_model) : '-')
		: statusModelName(stage2Model));
	const statusCatalogName = $derived(displayedHistoryItem ? catalogName(displayedHistoryItem.catalog_id) : currentCatalog.name);

	function formatHistoryDate(at: number): string {
		return new Date(at).toLocaleString(getLang() === 'ja' ? 'ja-JP' : 'en-US');
	}

	function formatElapsed(ms: number | null | undefined): string {
		return ms ? `${(ms / 1000).toFixed(1)}s` : '-';
	}

	function historyModelSummary(it: Iteration): string {
		const s1 = it.stage1_model ? shortModel(it.stage1_model) : '-';
		const s2 = it.stage2_model ? shortModel(it.stage2_model) : '-';
		return `${s1} → ${s2}`;
	}

	function historyTokenSummary(it: Iteration): string {
		if (it.tokens_in == null && it.tokens_out == null) return '-';
		return `${it.tokens_in ?? '?'} → ${it.tokens_out ?? '?'} tok`;
	}

	function historyPreviewText(text: string): string {
		return text.length > 42 ? `${text.slice(0, 42)}...` : text;
	}

	function historyIndexLabel(index: number): number {
		return historyOffset + index + 1;
	}

	function openHistoryManager() {
		historyManagerOpen = true;
		historyManagerView = 'active';
		historyManagerTab = 'thumbs';
		historyManagerPage = 0;
		historySearch = '';
		selectedHistoryIds = [];
		managerHistoryItems = historyItems;
		managerHistoryTotal = historyTotal;
		managerTrashItems = [];
		managerTrashTotal = trashTotal;
		void fetchHistoryManager();
	}

	function setHistoryManagerView(view: 'active' | 'trash') {
		historyManagerView = view;
		historyManagerPage = 0;
		selectedHistoryIds = [];
		void fetchHistoryManager();
	}

	function setHistoryManagerPage(page: number) {
		const nextPage = Math.max(0, Math.min(page, historyManagerTotalPages - 1));
		if (nextPage === historyManagerPage) return;
		historyManagerPage = nextPage;
		selectedHistoryIds = [];
		void fetchHistoryManager();
	}

	$effect(() => {
		const q = historySearch.trim();
		if (!historyManagerOpen) return;
		historyManagerView;
		const handle = setTimeout(() => {
			historyManagerPage = 0;
			selectedHistoryIds = [];
			void fetchHistoryManager();
		}, q ? 250 : 0);
		return () => clearTimeout(handle);
	});

	const tokenSummary = $derived.by(() =>
		t().tokenSummary(tokensInStage1, tokensOutStage1, tokensInStage2, tokensOutStage2)
	);
	const scoreJsonLines = $derived(
		result ? JSON.stringify(result.score, null, 2).split('\n') : []
	);
	const scoreJsonHighlightedLines = $derived(scoreJsonLines.map(highlightJsonLine));
	const scoreJsonHighlighted = $derived(scoreJsonHighlightedLines.join('\n'));
	const ddlHighlighted = $derived(ddl !== null
		? highlightDDL(ddl, ddlFocused && ddlSelection.start === ddlSelection.end ? ddlSelection.start : null)
		: '');
	const batchActiveDdlHighlighted = $derived(batchActiveDdl !== null
		? highlightDDL(batchActiveDdl)
		: escapeHtml(t().batchActiveDdlPending));

	function escapeHtml(value: string) {
		return value
			.replaceAll('&', '&amp;')
			.replaceAll('<', '&lt;')
			.replaceAll('>', '&gt;');
	}

	function highlightJsonLine(line: string) {
		return escapeHtml(line).replace(
			/("(?:\\u[\da-fA-F]{4}|\\[^u]|[^\\"])*"(\s*:)?|\btrue\b|\bfalse\b|\bnull\b|-?\d+(?:\.\d*)?(?:[eE][+-]?\d+)?)/g,
			(match, _token, keySuffix) => {
				if (keySuffix) return `<span class="json-key">${match}</span>`;
				if (match.startsWith('"')) return `<span class="json-string">${match}</span>`;
				if (match === 'true' || match === 'false') return `<span class="json-bool">${match}</span>`;
				if (match === 'null') return `<span class="json-null">${match}</span>`;
				return `<span class="json-number">${match}</span>`;
			}
		);
	}

	function saijikiCategoryClass(category: string | undefined): string {
		switch (category) {
			case 'かたち': return 'shape';
			case 'てざわり': return 'touch';
			case 'つらなり': return 'line';
			case 'いろ': return 'color';
			case 'ゆらぎ': return 'motion';
			case 'ばしょ': return 'place';
			case 'うごき': return 'action';
			case 'かたむき': return 'angle';
			case 'わりあい': return 'ratio';
			default: return 'word';
		}
	}

	function ddlCaretMarkup(): string {
		return '<span class="ddl-custom-caret"></span>';
	}

	function renderDDLPart(text: string, kind: string, category: string | undefined, caretOffset: number | null): string {
		const before = caretOffset === null ? text : text.slice(0, caretOffset);
		const after = caretOffset === null ? '' : text.slice(caretOffset);
		const content = caretOffset === null ? escapeHtml(text) : `${escapeHtml(before)}${ddlCaretMarkup()}${escapeHtml(after)}`;
		if (kind === 'saijiki') {
			return `<span class="ddl-token ddl-token-${saijikiCategoryClass(category)}">${content}</span>`;
		}
		if (kind === 'emotion') {
			return `<span class="ddl-token-emotion">${content}</span>`;
		}
		return content;
	}

	function highlightDDL(text: string, caretIndex: number | null = null): string {
		const clampedCaret = caretIndex === null ? null : Math.max(0, Math.min(text.length, caretIndex));
		let offset = 0;
		const html = annotate(text).map((part) => {
			const nextOffset = offset + part.text.length;
			const localCaret = clampedCaret !== null
				&& clampedCaret >= offset
				&& (clampedCaret < nextOffset || (clampedCaret === text.length && clampedCaret === nextOffset))
				? clampedCaret - offset
				: null;
			const rendered = renderDDLPart(part.text, part.kind, part.category, localCaret);
			offset = nextOffset;
			return rendered;
		}).join('');
		if (clampedCaret === text.length && text.length === 0) return ddlCaretMarkup();
		return html;
	}

	function setZoom(nextZoom: number) {
		zoom = Math.max(0.25, Math.min(10, +nextZoom.toFixed(2)));
		if (zoom <= 1) {
			panX = 0;
			panY = 0;
		}
	}

	function resetZoom() {
		fitCanvasZoom();
	}

	function fitCanvasZoom() {
		zoom = 1;
		panX = 0;
		panY = 0;
		canvasDragging = false;
	}

	function updateCanvasFitZoom(nextZoom: number) {
		canvasFitZoom = Math.max(0.25, Math.min(10, +nextZoom.toFixed(2)));
	}

	function startCanvasDrag(event: PointerEvent) {
		if (outputTab !== 'canvas' || zoom <= 1 || event.button !== 0) return;
		canvasDragging = true;
		dragStartX = event.clientX;
		dragStartY = event.clientY;
		dragStartPanX = panX;
		dragStartPanY = panY;
		(event.currentTarget as HTMLElement).setPointerCapture(event.pointerId);
		event.preventDefault();
	}

	function moveCanvasDrag(event: PointerEvent) {
		if (!canvasDragging) return;
		panX = dragStartPanX + event.clientX - dragStartX;
		panY = dragStartPanY + event.clientY - dragStartY;
	}

	function endCanvasDrag(event: PointerEvent) {
		if (!canvasDragging) return;
		canvasDragging = false;
		const target = event.currentTarget as HTMLElement;
		if (target.hasPointerCapture(event.pointerId)) target.releasePointerCapture(event.pointerId);
	}

	function handleCanvasKeydown(event: KeyboardEvent) {
		if (outputTab !== 'canvas') return;
		if (event.key === '+' || event.key === '=' || event.code === 'Equal' || event.code === 'NumpadAdd') {
			setZoom(zoom + 0.25);
			event.preventDefault();
			return;
		}
		if (event.key === '-' || event.key === '_' || event.code === 'Minus' || event.code === 'NumpadSubtract') {
			setZoom(zoom - 0.25);
			event.preventDefault();
			return;
		}
		if (event.key === '0' || event.code === 'Digit0' || event.code === 'Numpad0') {
			resetZoom();
			event.preventDefault();
			return;
		}
		if (zoom <= 1) return;
		const step = event.shiftKey ? 120 : 40;
		if (event.key === 'ArrowLeft') panX += step;
		else if (event.key === 'ArrowRight') panX -= step;
		else if (event.key === 'ArrowUp') panY += step;
		else if (event.key === 'ArrowDown') panY -= step;
		else return;
		event.preventDefault();
	}

	// ── Stats string ─────────────────────────────────────────
	const statsLine = $derived.by(() => {
		if (!result) return '';
		const s1 = (result.elapsed_stage1_ms / 1000).toFixed(1);
		const s2 = (result.elapsed_stage2_ms / 1000).toFixed(1);
		const total = (result.elapsed_total_ms / 1000).toFixed(1);
		if (result.elapsed_stage1_ms > 0) return `${t().statsInterp} ${s1}s + ${t().statsStruct} ${s2}s = ${total}s`;
		return `${total}s`;
	});

	const historyNavSpan = $derived(historyWindowSize);
	let lastHistoryWindowSize = 0;

	$effect(() => {
		const size = historyWindowSize;
		if (lastHistoryWindowSize === 0) {
			lastHistoryWindowSize = size;
			return;
		}
		if (size === lastHistoryWindowSize) return;
		lastHistoryWindowSize = size;
		if (!authToken || historyTotal <= 0) return;
		void fetchHistoryOffset(historyOffset);
	});

	// ── Mount ───────────────────────────────────────────────
	onMount(() => {
		windowWidth = window.innerWidth;
		function onResize() { windowWidth = window.innerWidth; }
		window.addEventListener('resize', onResize);
		document.addEventListener('keydown', handleKeydown, true);

		initLang();
		try {
			const p1 = localStorage.getItem(PROVIDER_STAGE1_KEY) as Provider | null; if (p1) stage1Provider = p1;
			const m1 = localStorage.getItem(MODEL_STAGE1_KEY); if (m1) stage1Model = m1;
			const p2 = localStorage.getItem(PROVIDER_STAGE2_KEY) as Provider | null; if (p2) stage2Provider = p2;
			const m2 = localStorage.getItem(MODEL_STAGE2_KEY); if (m2) stage2Model = m2;
			const cat = localStorage.getItem(CATALOG_KEY); if (cat) selectedCatalog = cat;
			const birds = localStorage.getItem(SHOW_BIRDS_KEY); if (birds !== null) showBirds = birds !== '0';
			const alpha = localStorage.getItem(PNG_ALPHA_KEY); if (alpha !== null) pngAlphaWhite = alpha === '1';
			const replay = localStorage.getItem(SAVE_REPLAY_KEY); if (replay !== null) saveReplayAsNewVersion = replay !== '0';
			const savedBatchFailureReport = loadBatchFailureReport();
			setBatchFailureReport(savedBatchFailureReport);
			miscSettingsLoaded = true;
		} catch {}
		void (async () => {
			await Promise.all([loadCurrentUser(), fetchPrompts()]);
		})();

		return () => {
			window.removeEventListener('resize', onResize);
			document.removeEventListener('keydown', handleKeydown, true);
		};
	});

	$effect(() => { const _lang = getLang(); fetchPrompts(); });
	$effect(() => {
		showBirds; pngAlphaWhite; saveReplayAsNewVersion;
		if (miscSettingsLoaded) persistMiscSettings();
	});
</script>

<svelte:window onclick={handleDocClick} />

<!-- ══════════════════════════════════════════════════════════ -->
<!--  ROOT                                                       -->
<!-- ══════════════════════════════════════════════════════════ -->
{#if !currentUser}
	<AuthPanel
		bind:loginUserName
		bind:loginPassword
		bind:loginPasswordVisible
		{loginStatus}
		onLogin={login}
	/>
{:else}
<div class="root">

	<!-- ══ HEADER ══ -->
	<header class="header">
		<div class="logo-area">
			<div class="logo">inku</div>
			<div class="logo-sub">{t().subtitle}</div>
		</div>

		<div class="header-right">
			{#if currentUser}
				<div class="user-menu-wrap" bind:this={userMenuWrapEl}>
					<button
						class="user-badge"
						class:active={userMenuOpen}
						type="button"
						title={currentUser.email || currentUser.username}
						aria-haspopup="menu"
						aria-expanded={userMenuOpen}
						onclick={() => (userMenuOpen = !userMenuOpen)}
					>
						<span class="user-badge-name">{currentUser.username}</span>
					</button>
					{#if userMenuOpen}
						<div class="user-menu" role="menu">
							<button type="button" role="menuitem" onclick={logout}>{t().logoutButton}</button>
						</div>
					{/if}
				</div>
			{/if}

			<button
				class="settings-btn"
				class:active={settingsOpen}
				onclick={() => openSettings('db')}
			>⚙ {t().settingsButton}</button>

			<!-- Lang -->
			<div class="lang-switcher">
				{#each PACK_LIST as pack (pack.code)}
					<button class="lang-btn" class:active={getLang() === pack.code} onclick={() => setLang(pack.code)}>{pack.label}</button>
				{/each}
			</div>

			<!-- Build -->
			<span class="build-badge">Build {__BUILD_NUMBER__}</span>
		</div>
	</header>

	<!-- ══ BODY ══ -->
	<div class="body">
		<!-- ── LEFT PANEL ── -->
		<div class="left-panel">
			<div class="panel-scroll">
				<InputPanel
					bind:inputMode
					bind:input
					bind:batchInput
					{lineNumbersText}
					{batchNonEmpty}
					{batchRunning}
					{singleRunning}
					{batchActiveLine}
					{batchActiveDdlHighlighted}
					{batchTotal}
					{batchCurrent}
					{liveMs}
					{batchFailureReport}
					{canSubmit}
					{error}
					{stageLabel}
					{showBirds}
					onOpenModelSelection={openModelSelection}
					onOpenCatalogModal={openCatalogModal}
					onClearInput={clearInput}
					onSubmit={submit}
					onStop={stopBatch}
				/>

				<!-- thinking -->
				{#if thinking}
					<section class="panel-section">
						<details class="thinking-details">
							<summary>{t().thinkingLabel}</summary>
							<pre>{thinking}</pre>
						</details>
					</section>
				{/if}

				<!-- 解釈 (正規化DDL) -->
				{#if ddl !== null && inputMode === 'single'}
					<DdlEditor
						bind:ddl
						{ddlHighlighted}
						bind:ddlTextareaEl
						bind:ddlHighlightEl
						bind:ddlFocused
						{reloading}
						{reloadError}
						{loading}
						{showBirds}
						onToggleSaijiki={() => (saijikiOpen = !saijikiOpen)}
						onRememberSelection={rememberDDLSelection}
						onSyncHighlightScroll={syncDDLHighlightScroll}
						onReplay={replay}
					/>
				{/if}

				<!-- 統計 -->
				{#if result && elapsedTotalMs > 0}
					<section class="panel-section stats-section">
						<button class="stats-toggle" onclick={() => (statsOpen = !statsOpen)}>
							<span class="stats-arrow" class:open={statsOpen}>▶</span>
							{statsLine}
						</button>
						{#if statsOpen}
							<div class="stats-detail">
								{#if elapsedStage1Ms > 0}
									<div class="stats-grid">
										<span class="stats-key">{t().statsInterp}</span><span>{(elapsedStage1Ms / 1000).toFixed(1)}s{tokensInStage1 != null ? ` — ${tokensInStage1}→${tokensOutStage1}tok` : ''}</span>
										<span class="stats-key">{t().statsStruct}</span><span>{(elapsedStage2Ms / 1000).toFixed(1)}s{tokensInStage2 != null ? ` — ${tokensInStage2}→${tokensOutStage2}tok` : ''}</span>
										<span class="stats-key">{t().statsTotal}</span><span class="stats-total">{(elapsedTotalMs / 1000).toFixed(1)}s</span>
									</div>
								{:else}
									<span>{(elapsedTotalMs / 1000).toFixed(1)}s</span>
								{/if}
							</div>
						{/if}
					</section>
				{/if}

			</div><!-- /panel-scroll -->
		</div><!-- /left-panel -->

		<CanvasPanel
			bind:outputTab
			bind:promptStage1Expanded
			bind:promptStage2Expanded
			bind:pngMenuOpen
			bind:pngWrapEl
			{result}
			{currentRenderedAt}
			{nextDisabled}
			{prevDisabled}
			{historyTotal}
			{navPos}
			{zoom}
			actualZoom={canvasFitZoom * zoom}
			canPan={zoom > 1}
			{panX}
			{panY}
			{canvasDragging}
			{promptsData}
			stage1PromptText={stage1UserPrompt || (inputMode === 'single' ? input : batchInput)}
			{ddl}
			{copiedPrompt}
			{scoreJsonLines}
			{scoreJsonHighlighted}
			{statusStage1Model}
			{statusStage2Model}
			{statusCatalogName}
			onGotoNext={gotoNext}
			onGotoPrev={gotoPrev}
			onPointerDown={startCanvasDrag}
			onPointerMove={moveCanvasDrag}
			onPointerUp={endCanvasDrag}
			onSetZoom={setZoom}
			onResetZoom={resetZoom}
			onFitZoomChange={updateCanvasFitZoom}
			onCopyPromptText={copyPromptText}
			onDownloadSVG={downloadSVG}
			onDownloadPNG={downloadPNG}
		/>
	</div><!-- /body -->

	<HistoryStrip
		{historyItems}
		{historyTotal}
		{historyCursor}
		{historyPage}
		{historyTotalPages}
		{historyNavSpan}
		onOpenManager={openHistoryManager}
		onNewerPage={gotoHistoryNewerPage}
		onOlderPage={gotoHistoryOlderPage}
		onLoadIteration={loadIteration}
		{historyIndexLabel}
		{historyModelSummary}
		{formatHistoryDate}
		{formatElapsed}
		{catalogName}
		{shortModel}
	/>

</div><!-- /root -->

<SaijikiDrawer
	open={saijikiOpen}
	bind:activePreview={activeSaijikiPreview}
	onClose={() => (saijikiOpen = false)}
	onInsertWord={insertWord}
	previewForWord={saijikiPreview}
/>

<!-- ══ SETTINGS MODAL ══ -->
{#if settingsOpen}
	<SettingsModal
		{settingsMode}
		{settingsTab}
		{stage1Provider}
		{stage1Model}
		{stage2Provider}
		{stage2Model}
		bind:includeThinking
		{settingsStatus}
		{settingsStatusError}
		{settingsStatusLoading}
		{currentUser}
		{userSettingsStatus}
		{userSettingsLoading}
		bind:loginUserName
		bind:loginPassword
		{users}
		{groups}
		bind:newUserName
		bind:newUserEmail
		bind:newUserPassword
		bind:newUserRole
		bind:newUserGroupId
		{selectedUserId}
		bind:editUserName
		bind:editUserEmail
		bind:editUserPassword
		bind:editUserRole
		bind:editUserGroupId
		bind:newGroupName
		bind:showBirds
		bind:pngAlphaWhite
		bind:saveReplayAsNewVersion
		onClose={closeSettingsModal}
		onCloseSettings={() => (settingsOpen = false)}
		onSelectSettingsTab={selectSettingsTab}
		onSetStage1Provider={setStage1Provider}
		onSetStage1Model={setStage1Model}
		onSetStage2Provider={setStage2Provider}
		onSetStage2Model={setStage2Model}
		onLoadSettingsStatus={loadSettingsStatus}
		onLoadUserSettings={loadUserSettings}
		onLogin={login}
		onLogout={logout}
		onAddUser={addUser}
		onSetEditUser={setEditUser}
		onClearEditUser={clearEditUser}
		onSaveUserEdit={saveUserEdit}
		onRemoveUser={removeUser}
		onAddGroup={addGroup}
		onRemoveGroup={removeGroup}
		onCancelModelSelection={cancelModelSelection}
		onConfirmModelSelection={confirmModelSelection}
	/>
{/if}

<!-- ══ CATALOG MODAL ══ -->
{#if catalogOpen}
	<ColorCatalogModal
		{selectedCatalog}
		{currentCatalog}
		onSelectCatalog={setSelectedCatalog}
		onCancel={cancelCatalogSelection}
		onConfirm={confirmCatalogSelection}
	/>
{/if}

<!-- ══ HISTORY MANAGER MODAL ══ -->
{#if historyManagerOpen}
	<HistoryManager
		bind:historyManagerTab
		bind:historySearch
		{historyManagerView}
		{historyManagerPage}
		{historyManagerLoading}
		{historyManagerTotalPages}
		{historyManagerOffset}
		{historyManagerShownTo}
		{managedHistoryItems}
		{managedHistoryTotal}
		{managerTrashTotal}
		{trashTotal}
		{selectedHistoryIds}
		onClose={() => (historyManagerOpen = false)}
		onSetView={setHistoryManagerView}
		onSetPage={setHistoryManagerPage}
		onSelectAll={selectAllManagedHistory}
		onAskTrash={askTrash}
		onAskRestore={askRestore}
		onAskPermanentDelete={askPermanentDelete}
		onToggleSelection={toggleHistorySelection}
		onLoadItem={loadIterationItem}
		{historyModelSummary}
		{formatHistoryDate}
		{formatElapsed}
		{catalogName}
		{historyTokenSummary}
		{historyPreviewText}
		{shortModel}
	/>
{/if}

{#if confirmAction}
	<ConfirmDialog
		action={confirmAction}
		onCancel={() => (confirmAction = null)}
		onRun={() => { const run = confirmAction?.run; confirmAction = null; run?.(); }}
	/>
{/if}
{/if}

<style>
	/* ── CSS Variables ──────────────────────────────────────── */
	:global(:root) {
		--bg:           #f5f3ef;
		--bg2:          #eceae4;
		--bg3:          #e2dfd8;
		--fg:           #1a1917;
		--fg2:          #5a5751;
		--fg3:          #9a9690;
		--accent:       #2a4a72;
		--accent-light: #e8eef5;
		--border:       #d4d0c8;
		--border2:      #c4c0b8;
		--r:            4px;
		--r-lg:         8px;
	}

	:global(*, *::before, *::after) { box-sizing: border-box; margin: 0; padding: 0; }

	:global(html), :global(body) {
		height: 100%;
		font-family: -apple-system, 'Hiragino Kaku Gothic ProN', 'Yu Gothic', 'Meiryo', sans-serif;
		font-size: 13px;
		background: var(--bg);
		color: var(--fg);
	}

	:global(::-webkit-scrollbar) { width: 6px; height: 6px; }
	:global(::-webkit-scrollbar-track) { background: transparent; }
	:global(::-webkit-scrollbar-thumb) { background: var(--border2); border-radius: 3px; }

	/* ── Root layout ────────────────────────────────────────── */
	.root {
		display: flex;
		flex-direction: column;
		height: 100vh;
		overflow: hidden;
	}

	/* ── Header ─────────────────────────────────────────────── */
	.header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: 10px 20px;
		border-bottom: 1px solid var(--border);
		background: var(--bg);
		flex-shrink: 0;
		gap: 12px;
	}

	.logo { font-size: 22px; font-weight: 300; letter-spacing: 0.05em; line-height: 1.1; }
	.logo-sub { font-size: 11px; color: var(--fg3); margin-top: 2px; }

	.header-right {
		display: flex;
		align-items: center;
		gap: 8px;
		flex-shrink: 0;
	}

	.user-menu-wrap {
		position: relative;
		min-width: 0;
	}
	.user-badge {
		display: inline-flex;
		align-items: center;
		gap: 6px;
		max-width: 220px;
		padding: 0 2px;
		border-left: 1px solid var(--border);
		border-top: none;
		border-right: none;
		border-bottom: none;
		padding-left: 10px;
		background: transparent;
		color: var(--fg2);
		font-size: 11px;
		min-width: 0;
		cursor: pointer;
		font-family: inherit;
	}
	.user-badge:hover,
	.user-badge.active {
		color: var(--fg);
	}
	.user-badge-name {
		font-weight: 400;
		color: inherit;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.user-menu {
		position: absolute;
		top: calc(100% + 6px);
		right: 0;
		z-index: 30;
		min-width: 126px;
		padding: 4px;
		border: 1px solid var(--border);
		border-radius: var(--r);
		background: #fff;
		box-shadow: 0 8px 22px rgba(37, 34, 26, 0.14);
	}
	.user-menu button {
		width: 100%;
		padding: 7px 9px;
		border: none;
		border-radius: 4px;
		background: transparent;
		color: var(--fg2);
		font-size: 11px;
		text-align: left;
		cursor: pointer;
		font-family: inherit;
	}
	.user-menu button:hover {
		background: var(--bg2);
		color: var(--fg);
	}
	.settings-btn {
		display: flex; align-items: center; gap: 4px;
		padding: 5px 11px;
		border: 1px solid var(--border2);
		border-radius: var(--r);
		background: #fff;
		color: var(--fg2);
		font-size: 12px;
		cursor: pointer;
		font-family: inherit;
	}
	.settings-btn.active, .settings-btn:hover { background: var(--bg2); }

	.lang-switcher {
		display: flex;
		border: 1px solid var(--border2);
		border-radius: var(--r);
		overflow: hidden;
	}
	.lang-btn {
		padding: 4px 10px; border: none; border-right: 1px solid var(--border2);
		background: #fff; color: var(--fg2); font-size: 12px; cursor: pointer; font-family: inherit;
	}
	.lang-btn:last-child { border-right: none; }
	.lang-btn.active { background: var(--fg); color: #fff; }

	.build-badge { font-size: 11px; color: var(--fg3); font-variant-numeric: tabular-nums; }

	/* ── Body ───────────────────────────────────────────────── */
	.body {
		display: flex;
		flex: 1;
		overflow: hidden;
		position: relative;
	}

	/* ── Left panel ─────────────────────────────────────────── */
	.left-panel {
		width: 440px;
		flex-shrink: 0;
		display: flex;
		flex-direction: column;
		border-right: 1px solid var(--border);
		overflow: hidden;
	}

	.panel-scroll {
		flex: 1;
		overflow-y: auto;
		padding: 14px 16px;
		display: flex;
		flex-direction: column;
		gap: 14px;
	}

	.panel-section { display: flex; flex-direction: column; gap: 6px; }

	/* thinking */
	.thinking-details {
		font-size: 12px; background: #f3efe6;
		border-left: 3px solid #c9a08a; border-radius: 0 3px 3px 0; padding: 6px 10px;
	}
	.thinking-details summary { cursor: pointer; color: #8a6f5a; font-style: italic; }
	.thinking-details pre {
		white-space: pre-wrap; word-break: break-word; color: #6b5340;
		font-family: inherit; line-height: 1.6; margin-top: 6px;
		max-height: 180px; overflow-y: auto; font-size: 12px;
	}

	/* Stats */
	.stats-toggle {
		display: flex; align-items: center; gap: 5px;
		width: 100%; padding: 4px 2px;
		border: none; background: none;
		color: var(--fg3); font-size: 11px; cursor: pointer;
		text-align: left; font-family: inherit;
	}
	.stats-arrow {
		display: inline-block; font-size: 9px;
		transition: transform 0.15s;
	}
	.stats-arrow.open { transform: rotate(90deg); }
	.stats-detail {
		background: var(--bg2); border-radius: var(--r); border-left: 2px solid var(--border2);
		padding: 8px 12px; font-size: 11px; color: var(--fg2); line-height: 1.9;
	}
	.stats-grid { display: grid; grid-template-columns: auto 1fr; gap: 0 12px; }
	.stats-key { color: var(--fg3); }
	.stats-total { font-weight: 500; }

	/* ── Animations ─────────────────────────────────────────── */
	@keyframes inkupulse {
		0%, 100% { opacity: 1; transform: scale(1); }
		50%       { opacity: 0.4; transform: scale(0.7); }
	}
	@keyframes birdWalk {
		0% { transform: translate(-28px, 0) scaleX(1); }
		9% { transform: translate(-14px, -1px) scaleX(1); }
		18% { transform: translate(-14px, 0) scaleX(1); }
		28% { transform: translate(12px, -1px) scaleX(1); }
		36% { transform: translate(12px, 0) scaleX(1); }
		44% { transform: translate(5px, 0) scaleX(1); }
		48% { transform: translate(2px, 0) scaleX(1); }
		52% { transform: translate(0, 0) scaleX(-1); }
		62% { transform: translate(-18px, -1px) scaleX(-1); }
		72% { transform: translate(-18px, 0) scaleX(-1); }
		82% { transform: translate(10px, -1px) scaleX(-1); }
		90% { transform: translate(10px, 0) scaleX(-1); }
		96% { transform: translate(-6px, 0) scaleX(-1); }
		100% { transform: translate(-28px, 0) scaleX(1); }
	}
	@keyframes birdSideView {
		0%, 40%, 56%, 94%, 100% { opacity: 1; transform: scaleX(1); }
		46%, 50%, 98% { opacity: 0; transform: scaleX(0.72); }
	}
	@keyframes birdFrontView {
		0%, 42%, 56%, 96%, 100% { opacity: 0; transform: scaleX(0.86); }
		47%, 50%, 53%, 98% { opacity: 1; transform: scaleX(1); }
	}
	@keyframes birdThreeQuarterView {
		0%, 39%, 57%, 93%, 100% { opacity: 0; transform: rotate(0deg); }
		43%, 55%, 95%, 99% { opacity: 0.92; transform: rotate(3deg); }
	}
	@keyframes birdWing {
		0%, 18%, 38%, 55%, 72%, 100% { transform: rotate(0deg) scaleY(1); }
		22%, 24%, 26% { transform: rotate(-28deg) scaleY(0.75); }
		29% { transform: rotate(8deg) scaleY(1.08); }
		78%, 80% { transform: rotate(-18deg) scaleY(0.82); }
		82% { transform: rotate(6deg) scaleY(1.06); }
	}
	@keyframes birdPeck {
		0%, 42%, 58%, 100% { transform: rotate(0deg) translateY(0); }
		46%, 50%, 54% { transform: rotate(-16deg) translateY(5px); }
		48%, 52%, 56% { transform: rotate(5deg) translateY(0); }
	}
	@keyframes birdPreen {
		0%, 62%, 78%, 100% { transform: rotate(0deg); }
		66%, 70%, 74% { transform: rotate(9deg) translateX(1px); }
		68%, 72% { transform: rotate(-5deg) translateX(-1px); }
	}
	@keyframes birdHead {
		0%, 42%, 58%, 62%, 100% { transform: rotate(0deg); }
		46%, 50%, 54% { transform: rotate(-22deg) translate(-1px, 4px); }
		66%, 70%, 74% { transform: rotate(18deg) translate(5px, 2px); }
	}
	@keyframes birdStepA {
		0%, 100% { transform: rotate(0deg); }
		45% { transform: rotate(14deg) translateX(1px); }
	}
	@keyframes birdStepB {
		0%, 100% { transform: rotate(0deg); }
		45% { transform: rotate(-14deg) translateX(-1px); }
	}
</style>

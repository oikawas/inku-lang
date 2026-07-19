<script module lang="ts">
	declare const __BUILD_NUMBER__: string;
</script>

<script lang="ts">
	import { onMount, untrack } from 'svelte';
	import { annotate, interpretationFeedback } from '$lib/highlight';
	import { hydrateSaijiki } from '$lib/saijiki';
	import AppRail from '$lib/components/AppRail.svelte';
	import AuthPanel from '$lib/components/AuthPanel.svelte';
	import CanvasPanel from '$lib/components/CanvasPanel.svelte';
	import type { LineageGraph, LineageNode } from '$lib/components/LineagePanel.svelte';
	import ConfirmDialog from '$lib/components/ConfirmDialog.svelte';
	import ColorCatalogModal from '$lib/components/ColorCatalogModal.svelte';
	import DdlViewer from '$lib/components/DdlViewer.svelte';
	import DdlEditorDialog from '$lib/components/DdlEditorDialog.svelte';
	import HistoryManager from '$lib/components/HistoryManager.svelte';
	import HistoryStrip from '$lib/components/HistoryStrip.svelte';
	import InputPanel from '$lib/components/InputPanel.svelte';
	import ProfileModal from '$lib/components/ProfileModal.svelte';
	import SaijikiDrawer from '$lib/components/SaijikiDrawer.svelte';
	import SettingsModal from '$lib/components/SettingsModal.svelte';
	import Tooltip from '$lib/components/Tooltip.svelte';
	import {
		PROVIDER_GROUPS,
		DEFAULT_PROVIDER,
		DEFAULT_MODEL,
		modelsForProvider,
		providerOfModel,
		qualifiedModelId,
		type Provider,
		type ProviderGroup,
		type ModelOption
	} from '$lib/models';
	import { t, getLang, initLang } from '$lib/i18n/index.svelte';
	import { FALLBACK_CATALOG, catalogById, type ColorCatalog, type ColorCatalogsResponse } from '$lib/colors';
	import { DEFAULT_DEMO_SETTINGS, type DemoSettings } from '$lib/demo';
	import { DEFAULT_EXPORT_TEMPLATES, normalizeExportTemplates, type ExportTemplate } from '$lib/exportTemplates';
	import {
		CANVAS_ASPECT_PLUGIN_ID,
		DEFAULT_CANVAS_ASPECT_ID,
		getCanvasAspectOption,
		normalizeCanvasAspectId,
		type CanvasAspectId,
	} from '$lib/plugins/system/canvas-aspect';
	import {
		HistoryManagerState,
		type HistoryItem,
		type Score
	} from '$lib/historyManagerState.svelte';

	const PROVIDER_STAGE1_KEY = 'inku-provider-stage1';
	const MODEL_STAGE1_KEY    = 'inku-model-stage1';
	const PROVIDER_STAGE2_KEY = 'inku-provider-stage2';
	const MODEL_STAGE2_KEY    = 'inku-model-stage2';
	const DEFAULT_VISION_MODEL = 'meta/llama-3.2-90b-vision-instruct';
	const CATALOG_KEY         = 'inku-color-catalog';
	const SHOW_BIRDS_KEY      = 'inku-show-birds';
	const SHOW_KIWI_KEY       = 'inku-show-kiwi';
	const SHOW_CRAB_KEY       = 'inku-show-crab';
	const PNG_ALPHA_KEY       = 'inku-png-alpha-white';
	const SAVE_REPLAY_KEY     = 'inku-save-replay-history';
	const HISTORY_SELECTION_CANVAS_KEY = 'inku-history-selection-canvas';
	const HISTORY_SELECTION_CATALOG_KEY = 'inku-history-selection-catalog';
	const BATCH_FAILURE_REPORT_KEY = 'inku-batch-failure-report';
	const APP_VERSION = 'v1.95.0';
	const REPOSITORY_URL = 'https://github.com/oikawas/inku-lang';
	const BATCH_FAILURE_REPORT_MAX_ITEMS = 100;
	const BATCH_FAILURE_REPORT_MAX_TEXT = 300;
	const BATCH_PROMPT_HISTORY_LIMIT = 20;
	const BATCH_PROMPT_HISTORY_MAX_TEXT = 20000;
	const EXTERNAL_HISTORY_REFRESH_MS = 12000;
	const EXTERNAL_HISTORY_REFRESH_MIN_GAP_MS = 5000;
	type HistorySelectionBehavior = 'history' | 'current';
	type InstructionLang = 'auto' | 'ja' | 'en';

	type PaintResult = {
		svg: string;
		score: Score;
		stage1_model?: string | null;
		stage2_model?: string | null;
		render_build_number?: string | null;
		render_color_profile?: Record<string, string> | null;
		render_engine_id?: string | null;
		render_engine_version?: string | null;
		render_hash?: string | null;
		render_hash_short?: string | null;
		render_color_catalog_id?: string | null;
		render_color_catalog_name?: string | null;
		render_color_catalog_sub?: string | null;
		render_color_map?: Record<string, string> | null;
		render_canvas_aspect?: string | null;
		render_canvas_aspect_id?: string | null;
		render_canvas_aspect_ratio?: number | null;
		render_seed?: number | null;
		vary_seed?: number | null;
		interpretation_seed?: string | null;
		seed_text?: string | null;
		instruction_lang_requested?: string | null;
		instruction_lang_resolved?: string | null;
		ui_lang?: string | null;
		history_id?: string | null;
		history_at?: number | null;
		description_hash?: string | null;
		lineage_node_id?: string | null;
		lineage_parent_node_id?: string | null;
		derivation_kind?: DerivationKind | null;
		derivation_metadata?: Record<string, unknown>;
		elapsed_stage1_ms: number;
		elapsed_stage2_ms: number;
		elapsed_total_ms: number;
		tokens_in_stage1: number | null;
		tokens_out_stage1: number | null;
		tokens_in_stage2: number | null;
		tokens_out_stage2: number | null;
		user_generation_count?: number | null;
	};
	type DerivationKind = 'touch_variation' | 'layout_variation' | 'catalog_change' | 'reinterpretation' | 'model_variation' | 'language_variation' | 'ddl_edit' | 'description_edit' | 'replay' | 'canvas_aspect_change';
	type RefineKind = 'touch' | 'layout' | 'reading' | 'color';
	type SvgProfile = 'display' | 'editable' | 'compat';

	type Iteration = HistoryItem;
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

	type PluginEntry = {
		qualified_name: string;
		surface_ja: string[];
		surface_en: string[];
		note_ja: string;
		note_en: string;
	};
	type PluginItem = {
		name: string;
		namespace?: string;
		version: string;
		status: string;
		entries?: PluginEntry[];
		reasons?: string[];
	};
	type SettingsStatus = {
		database: {
			backend: string;
			driver: string;
			url: string;
			database: string | null;
			is_default: boolean;
			file_size_bytes: number | null;
			file_path: string | null;
			runtime_editable: boolean;
			note: string;
		};
		db_backup: {
			supported: boolean;
			interval_days: number;
			max_generations: number;
			last_auto_backup_at: number;
			backup_dir: string;
			auto_count: number;
			manual_count: number;
		};
		plugins: {
			enabled: boolean;
			loaded: PluginItem[];
			runtime_editable: boolean;
			note: string;
		};
		output_save: {
			enabled: boolean;
			output_dir: string;
			png_size: number;
			workers: number;
			queue_limit: number;
			submitted: number;
			completed: number;
			failed: number;
			skipped: number;
			note: string;
		};
		log_retention: {
			enabled: boolean;
			retention_days: number;
			rotate: 'daily' | 'weekly' | 'monthly';
			compress: boolean;
			log_dir: string;
			services: string[];
			systemd_dropins: Record<string, string>;
			logrotate_config: string;
			note: string;
		};
	};

	type UserRole = 'admin' | 'group_lead' | 'user';
	type SettingsTab = 'connection' | 'models' | 'db' | 'plugins' | 'users' | 'unread' | 'export' | 'misc' | 'server_misc' | 'logs';
	type UserModelSettings = {
		stage1_provider: Provider;
		stage1_model: string;
		stage2_provider: Provider;
		stage2_model: string;
		vision_provider: Provider;
		vision_model: string;
		okugaki_model?: string;
		model_inspection_selected_models?: string[];
		instruction_caption_visible?: boolean;
	};
	type ModelProviderSetting = {
		label?: string;
		kind?: string;
		default_base_url?: string;
		requires_api_key?: boolean;
		memo?: string;
		models?: ModelOption[];
		base_url: string;
		api_key_set: boolean;
		api_key_hint: string | null;
		api_key?: string;
		clear_api_key?: boolean;
		enabled_models?: Record<string, boolean>;
	};
	type ModelSettings = {
		providers: Record<string, ModelProviderSetting>;
	};
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
		ui_theme?: 'light' | 'dark';
		settings_tab?: SettingsTab;
		model_settings?: UserModelSettings;
		image_generation_count: number;
		at: number;
	};
	// ── Input ───────────────────────────────────────────────
	const DEFAULT_INPUT = '山の向こうに月が昇る';
	let inputMode   = $state<'single' | 'batch' | 'demo'>('single');
	let input       = $state(DEFAULT_INPUT);
	let touchSeedText = $state('');
	let batchInput  = $state('');
	const instructionLang: InstructionLang = 'auto';
	let stage1UserPrompt = $state('');
	let ddlTextareaEl = $state<HTMLTextAreaElement | null>(null);
	let ddlHighlightEl = $state<HTMLDivElement | null>(null);
	let ddlSelection = $state({ start: 0, end: 0 });
	let ddlFocused = $state(false);
	type CopyKind = 'stage1' | 'stage2' | 'score';
	let copiedPrompt = $state<CopyKind | null>(null);
	let statusHashCopied = $state(false);

	// ── Loading ─────────────────────────────────────────────
	let loading    = $state(false);
	let activeRunMode = $state<'single' | 'batch' | 'demo' | null>(null);
	let submitAbortController: AbortController | null = null;
	let submitStopRequested = false;
	let replayAbortController: AbortController | null = null;
	let replayStopRequested = false;
	let stageLabel = $state('');
	let batchCurrent = $state(0);
	let batchTotal   = $state(0);
	let batchSuccess = $state(0);
	let batchFailures = $state<BatchFailure[]>([]);
	let batchFailureReport = $state<BatchFailureReport | null>(null);
	let batchPromptHistory = $state<string[]>([]);
	let batchRandomColorCatalog = $state(false);
	let batchActiveLine = $state<number | null>(null);
	let batchActiveDdl = $state<string | null>(null);
	let batchActiveTokensIn = $state<number | null>(null);
	let batchActiveTokensOut = $state<number | null>(null);
	let batchTokensInTotal = $state(0);
	let batchTokensOutTotal = $state(0);
	let batchLatestResult = $state<PaintResult | null>(null);
	let batchLatestDdl = $state<string | null>(null);
	let batchLatestThinking = $state<string | null>(null);
	let batchLatestPrompt = $state('');
	let batchAutoFollowLatest = $state(false);
	let previousInputMode = $state<'single' | 'batch' | 'demo'>('single');
	let error        = $state<string | null>(null);
	let demoSettings = $state<DemoSettings>({ ...DEFAULT_DEMO_SETTINGS });
	let demoGeneratedPrompt = $state('');
	let demoGeneratedDdl = $state<string | null>(null);
	let demoError = $state<string | null>(null);
	let demoSaveStatus = $state<string | null>(null);
	let demoSavingCurrent = $state(false);
	let demoCurrentSaved = $state(false);
	let demoWaitingSeconds = $state<number | null>(null);
	let demoCurrentStartedAt: number | null = null;
	let demoCurrentLiveMs = $state<number | null>(null);
	let demoCurrentElapsedMs = $state<number | null>(null);
	let demoCurrentTokensIn = $state<number | null>(null);
	let demoCurrentTokensOut = $state<number | null>(null);
	let demoTotalElapsedMs = $state(0);
	let demoTotalTokensIn = $state(0);
	let demoTotalTokensOut = $state(0);
	let demoRenderCount = $state(0);
	let demoSettingsLoaded = $state(false);
	let demoRunId = 0;

	// ── Replay ──────────────────────────────────────────────
	let reloading   = $state(false);
	let reloadError = $state<string | null>(null);

	// ── Result ──────────────────────────────────────────────
	let ddl      = $state<string | null>(null);
	let ddlGeneratedBaseline = $state<string | null>(null);
	let ddlAutoRepairEnabled = $state(true);
	let thinking = $state<string | null>(null);
	let result   = $state<PaintResult | null>(null);
	let variationBusy = $state(false);
	type DdlDiffPart = { kind: "same" | "removed" | "added"; text: string };
	type TextDiffPart = { kind: "same" | "removed" | "added"; text: string };
	type ModelInspectionResult = {
		id: string;
		model: string;
		stage1Model?: string | null;
		label: string;
		input: string;
		ddl: string;
		svg: string;
		score: Score;
		stage2Model?: string | null;
		renderBuildNumber?: string | null;
		renderColorProfile?: Record<string, string> | null;
		renderEngineId?: string | null;
		renderEngineVersion?: string | null;
		renderColorCatalogId?: string | null;
		renderColorCatalogName?: string | null;
		renderColorCatalogSub?: string | null;
		renderColorMap?: Record<string, string> | null;
		renderCanvasAspect?: string | null;
		renderCanvasAspectId?: string | null;
		renderCanvasAspectRatio?: number | null;
		renderSeed?: number | null;
		varySeed?: number | null;
		tokensIn: number | null;
		tokensOut: number | null;
		tokensInStage2: number | null;
		tokensOutStage2: number | null;
		elapsedMs: number;
		lineageParentNodeId?: string | null;
		compareMode: ModelCompareMode;
		comparisonKind?: 'model' | 'language';
		stage1Lang?: 'ja' | 'en';
		stage2Lang?: 'ja' | 'en';
		savedHistoryId?: string | null;
		starred?: boolean;
		saving?: boolean;
	};
	type ModelInspectionChoice = { id: string; label: string; providerLabel: string };
	type VariationCandidate = { id: string; label: string; result: PaintResult & { ddl: string; thinking: string | null }; selected: boolean; saved?: boolean };
	let interpretationDiffParts = $state<DdlDiffPart[]>([]);
	let variationCandidates = $state<VariationCandidate[]>([]);
	let lineageIntermediateNotice = $state<string | null>(null);
	let lineageIntermediateNoticeTimer: number | null = null;
	let nearbyHistory = $state<Iteration[]>([]);
	let variationGridBusy = $state(false);
	let variationGridCanAbort = $state(false);
	let variationGridIncludesReading = $state(false);
	let variationGridTaskLabel = $state('');
	let variationGridAbortController: AbortController | null = null;
	let variationGridStatus = $state<string | null>(null);
	type ModelCompareMode = 'common' | 'stage1_fixed' | 'stage2_fixed';
	let modelCompareMode = $state<ModelCompareMode>('common');
	let modelCompareFixedModel = $state('');
	let modelInspectionBusy = $state(false);
	let modelInspectionStatus = $state<string | null>(null);
	let modelInspectionResults = $state<ModelInspectionResult[]>([]);
	let modelInspectionSelectedModels = $state<string[]>([]);
	let modelInspectionFailedModels = $state<Record<string, string>>({});
	let modelInspectionRunId = 0;
	let targetContextVersion = 0;
	let modelInspectionAbortController: AbortController | null = null;
	let languageCompareMode = $state<ModelCompareMode>('common');
	let languageCompareFixedLang = $state<'ja' | 'en'>('ja');
	let languageInspectionSelectedLangs = $state<Array<'ja' | 'en'>>([]);
	let languageInspectionBusy = $state(false);
	let languageInspectionStatus = $state<string | null>(null);
	let languageInspectionResults = $state<ModelInspectionResult[]>([]);
	let languageInspectionRunId = 0;
	let languageInspectionAbortController: AbortController | null = null;

	// ── UI ──────────────────────────────────────────────────
	let windowWidth  = $state(1200);
	let windowHeight = $state(800);
	let saijikiOpen  = $state(false);
	let activeSaijikiPreview = $state<SaijikiPreview | null>(null);
	let settingsOpen = $state(false);
	// DDL editor dialog (new / edit), shared by 記述タブ new-button and lineage card menu.
	let ddlDialogOpen = $state(false);
	let ddlDialogMode = $state<'new' | 'edit'>('new');
	let ddlDialogNode = $state<LineageNode | null>(null);
	let ddlDialogInitial = $state('');
	let ddlDialogDrawing = $state(false);
	let ddlDialogError = $state<string | null>(null);
	// DDL-authored (standalone) artworks carry the display_label marker 'DDL'.
	const DDL_ORIGIN_LABEL = 'DDL';
	let appInfoOpen = $state(false);
	let leftPanelCollapsed = $state(false);
	let settingsMode = $state<'model' | 'settings'>('settings');
	let settingsTab  = $state<SettingsTab>('connection');
	let pngMenuOpen  = $state(false);
	let userMenuOpen = $state(false);
	let darkMode     = $state(false);
	let catalogOpen  = $state(false);
	let canvasAspectMenuOpen = $state(false);
	let canvasAspectEnabled = $state(true);
	let canvasAspectId = $state<CanvasAspectId>(DEFAULT_CANVAS_ASPECT_ID);
	let pendingCanvasAspectDerivation = $state<{ parentNodeId: string; fromAspectId: CanvasAspectId; toAspectId: CanvasAspectId } | null>(null);
	let catalogSelectionSnapshot = $state<string | null>(null);
	let statsOpen    = $state(false);
	let instructionCaptionVisible = $state(true);
	let outputTab    = $state<'canvas' | 'refine' | 'lineage'>('canvas');
	let lineageGraph = $state<LineageGraph | null>(null);
	let lineageLoading = $state(false);
	let lineageError = $state<string | null>(null);
	let lineageLoadedFocus = $state<string | null>(null);
	let lineageRequestId = 0;
	let lineageDetached = $state(false);
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
		visionProvider: Provider;
		visionModel: string;
	};
	let modelSelectionSnapshot = $state<ModelSelectionSnapshot | null>(null);
	let modelSelectionAllowVision = $state(true);
	let showKiwi = $state(true);
	let showCrab = $state(true);
	let pngAlphaWhite = $state(false);
	let exportTemplates = $state<ExportTemplate[]>(DEFAULT_EXPORT_TEMPLATES.map((item) => ({ ...item })));
	let exportTemplateStatus = $state<string | null>(null);
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
		const touchSvg = (kind: string) => {
			const defs = '<defs><filter id="touch-soft"><feGaussianBlur stdDeviation="1.8"/></filter></defs>';
			const paths: Record<string, string> = {
				hair: '<path d="M22 54 C58 37 106 58 158 39" fill="none" stroke="#2b2b2b" stroke-width="1.2" stroke-linecap="round" opacity="0.72"/>',
				pencil: '<path d="M22 54 C58 37 106 58 158 39" fill="none" stroke="#2b2b2b" stroke-width="2.4" opacity="0.58"/><path d="M22 56 C62 39 108 59 158 41" fill="none" stroke="#2b2b2b" stroke-width="0.8" stroke-dasharray="1 6" opacity="0.42"/><g fill="#2b2b2b" opacity="0.22"><circle cx="49" cy="48" r="1"/><circle cx="82" cy="51" r="0.8"/><circle cx="121" cy="47" r="1.1"/></g>',
				pen: '<path d="M22 54 C58 37 106 58 158 39 L158 41 C106 60 58 39 22 55 Z" fill="#2b2b2b"/>',
				rotring: '<path d="M22 52 L158 40" fill="none" stroke="#2b2b2b" stroke-width="2.4" stroke-linecap="butt"/>',
				crayon: '<path d="M22 57 C58 35 108 62 158 38" fill="none" stroke="#2b2b2b" stroke-width="8" opacity="0.66" stroke-dasharray="12 2 3 2"/><path d="M22 52 C65 40 110 56 158 42" fill="none" stroke="#2b2b2b" stroke-width="2" opacity="0.35"/>',
				chalk: '<path d="M22 56 C58 35 105 61 158 39" fill="none" stroke="#2b2b2b" stroke-width="7" opacity="0.38" stroke-dasharray="8 4 2 5"/><g fill="#2b2b2b" opacity="0.22"><circle cx="39" cy="53" r="1.8"/><circle cx="70" cy="47" r="1.3"/><circle cx="111" cy="51" r="1.6"/><circle cx="145" cy="43" r="1.4"/></g>',
				brush_thin: '<path d="M22 55 C54 31 108 63 158 38 C126 53 67 48 22 55 Z" fill="#2b2b2b" opacity="0.9"/>',
				brush_thick: '<path d="M22 56 C47 25 105 68 158 37 C128 60 62 54 22 56 Z" fill="#2b2b2b" opacity="0.84"/><path d="M35 54 C72 42 112 58 151 41" fill="none" stroke="#fffdf8" stroke-width="1.2" opacity="0.45"/>',
				burin: '<path d="M22 55 C56 42 106 57 158 39 C119 55 67 51 22 55 Z" fill="#2b2b2b"/>',
				drypoint: `${defs}<path d="M22 55 C56 40 107 58 158 39 C118 54 67 52 22 55 Z" fill="#2b2b2b"/><path d="M23 59 C58 44 108 62 159 43" fill="none" stroke="#2b2b2b" stroke-width="5" opacity="0.28" filter="url(#touch-soft)"/>`,
			};
			return shapeSvg(paths[kind] ?? paths.pen);
		};
		if (categoryKey === "plugin-nature") {
			const natureSvg = shapeSvg("<path d=\"M32 48 C52 28 74 68 94 48 S132 28 150 48\" stroke=\"#b95845\" stroke-width=\"5\" fill=\"none\" stroke-linecap=\"round\"/><path d=\"M34 62 C58 50 78 76 102 62 S134 50 150 62\" stroke=\"#d39a7b\" stroke-width=\"3\" fill=\"none\" stroke-linecap=\"round\"/>");
			const naturePreviews: Record<string, Omit<SaijikiPreview, "categoryKey" | "word" | "canonicalWord">> = {
				"Nature.風": { effect: "左から右へのゆるやかな揺れを全体に通します。", example: "Nature.風を通す", svg: natureSvg },
				"Nature.うねり": { effect: "媒質を限定しない大きな波の揺れを全体に通します。", example: "Nature.うねりを通す", svg: natureSvg },
				"Nature.無風": { effect: "揺らぎと配置軌跡を抑え、静止に寄せます。", example: "Nature.無風", svg: natureSvg },
				"Nature.wind": { effect: "Adds a slow left-to-right wind-like sway.", example: "Nature.wind", svg: natureSvg },
				"Nature.undulation": { effect: "Adds a broad medium-free undulation.", example: "Nature.undulation", svg: natureSvg },
				"Nature.stillness": { effect: "Suppresses sway and placement paths.", example: "Nature.stillness", svg: natureSvg },
			};
			return { ...base, ...(naturePreviews[canonicalWord] ?? naturePreviews[word] ?? naturePreviews["Nature.うねり"]) };
		}
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
			雲形: {
				effect: word === 'cloudform' ? 'A closed irregular form whose contour is decided anew for each performance.' : '輪郭が演奏ごとに決まる、不規則さの文法を持つ閉じた形。',
				example: word === 'cloudform' ? 'Place a wide cloudform at center' : '中央に横長の雲形を置く',
				svg: shapeSvg('<path d="M45 52 C40 34 58 22 77 28 C90 15 111 22 113 36 C135 35 143 52 131 65 C116 76 96 66 82 72 C63 78 46 68 45 52 Z" fill="none" stroke="#2b2b2b" stroke-width="5" stroke-linejoin="round"/>')
			},
			水平: { effect: '0度の向き。線なら横線として扱う。', example: '水平の線を引く', svg: angleSvg(0, true) },
			垂直: { effect: '90度の向き。線なら縦線として扱う。', example: '垂直の線を引く', svg: angleSvg(90, true) },
			斜め: { effect: '約45度の傾きを与える。', example: '斜めの四角を置く', svg: angleSvg(45) },
			右上がり: { effect: '左下から右上へ向かう傾き。', example: '右上がりの線', svg: angleSvg(-30, true) },
			右下がり: { effect: '左上から右下へ向かう傾き。', example: '右下がりの線', svg: angleSvg(30, true) },
			回転: { effect: '図形全体を中心まわりに回転させる。', example: '回転した横長の四角', svg: angleSvg(30) },
			髪: { effect: '非常に細く、筆致の変化をほぼ抑えた線。', example: '髪のように細い線', svg: touchSvg('hair') },
			鉛筆: { effect: '幅と横揺れが連動し、細かな副線と紙目の粒を伴う。', example: '鉛筆の線を引く', svg: touchSvg('pencil') },
			ペン: { effect: '明瞭さを保ちながら、わずかな幅と軌道の変化を持つ。', example: 'ペンの線を引く', svg: touchSvg('pen') },
			ロットリング: { effect: '共有筆致を遮断した、均一で硬い製図線。', example: 'ロットリングの線', svg: touchSvg('rotring') },
			クレヨン: { effect: '太い主線に擦れた副線と粒を重ねる。', example: '青いクレヨンの線', svg: touchSvg('crayon') },
			チョーク: { effect: '幅の崩れ、途切れ、粉状の粒を含む淡い線。', example: '白いチョークの線', svg: touchSvg('chalk') },
			細筆: { effect: '入りと抜きが細く、筆圧で幅が大きく変わる。', example: '細筆で線を引く', svg: touchSvg('brush_thin') },
			太筆: { effect: '大きな幅変化と穂先の筋を持つ太い筆線。', example: '太筆で黒い線を引く', svg: touchSvg('brush_thick') },
			ビュラン: { effect: '入りと抜きが細く、中央に彫りの勢いが集まる硬い線。', example: 'ビュランで線を彫る', svg: touchSvg('burin') },
			ドライポイント: { effect: '緩い中膨らみと、片側だけの柔らかなburrを伴う線。', example: 'ドライポイントの線', svg: touchSvg('drypoint') },
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
			沿う: { effect: `直前の線を参照する関係。`, example: `前の線に沿って`, svg: shapeSvg(`<path d="M24 56 C58 28 104 70 156 34" fill="none" stroke="#2b2b2b" stroke-width="5" stroke-linecap="round"/><circle cx="62" cy="45" r="5" fill="#c9362d"/><circle cx="94" cy="51" r="5" fill="#c9362d"/><circle cx="126" cy="43" r="5" fill="#c9362d"/>`) },
			触れない: { effect: `直前の形に接触しない関係。`, example: `前の形に触れない`, svg: shapeSvg(`<circle cx="78" cy="46" r="22" fill="none" stroke="#2b2b2b" stroke-width="5"/><circle cx="124" cy="46" r="10" fill="none" stroke="#c9362d" stroke-width="5"/>`) },
			切る: { effect: `直前の線を横切る関係。`, example: `前の線を切る`, svg: shapeSvg(`<path d="M38 46 H142" stroke="#2b2b2b" stroke-width="6" stroke-linecap="round"/><path d="M92 20 L78 72" stroke="#c9362d" stroke-width="6" stroke-linecap="round"/>`) },
			間に: { effect: `直前の二つの要素の間に置く関係。`, example: `前の二つの間に`, svg: shapeSvg(`<circle cx="56" cy="46" r="14" fill="none" stroke="#2b2b2b" stroke-width="5"/><circle cx="124" cy="46" r="14" fill="none" stroke="#2b2b2b" stroke-width="5"/><circle cx="90" cy="46" r="8" fill="#c9362d"/>`) },
		};
		return { ...base, ...(previews[canonicalWord] ?? { effect: '記述の解釈に影響する語彙です。', example: `${word}を使う`, svg: lineSvg() }) };
	}

	// ── Color catalog ────────────────────────────────────────
	let selectedCatalog = $state('default');
	let colorCatalogs = $state<ColorCatalog[]>([FALLBACK_CATALOG]);
	let defaultCatalogId = $state('default');
	const currentCatalog = $derived(catalogById(colorCatalogs, selectedCatalog) ?? colorCatalogs[0] ?? FALLBACK_CATALOG);
	let historySelectionCanvas = $state<HistorySelectionBehavior>('current');
	let historySelectionCatalog = $state<HistorySelectionBehavior>('current');

	// ── Settings tabs ────────────────────────────────────────
	let settingsStatus = $state<SettingsStatus | null>(null);
	let settingsStatusError = $state<string | null>(null);
	let settingsStatusLoading = $state(false);
	let pluginEntries = $state<PluginEntry[]>([]);
	let modelSettings = $state<ModelSettings | null>(null);
	let modelSettingsStatus = $state<string | null>(null);
	let modelFetchResults = $state<Record<string, { type: 'success' | 'error'; message: string }>>({});
	let modelSettingsLoading = $state(false);
	let modelCatalog = $state<ProviderGroup[]>(PROVIDER_GROUPS);
	let availableModelCatalog = $state<ProviderGroup[]>(PROVIDER_GROUPS);
	let availableVisionModelCatalog = $state<ProviderGroup[]>([]);
	let availableModelsLoaded = $state(false);
	let dbBackupStatus = $state<string | null>(null);
	let outputSaveStatus = $state<string | null>(null);
	let logRetentionStatus = $state<string | null>(null);
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
	let editGroupId = $state<string | null>(null);
	let editGroupName = $state('');
	let userSettingsStatus = $state<string | null>(null);
	let userSettingsLoading = $state(false);
	let userSettingsRequestId = 0;
	let authToken = $state<string | null>(null);
	let currentUser = $state<UserItem | null>(null);
	let loginUserName = $state('admin');
	let loginPassword = $state('');
	let loginPasswordVisible = $state(false);
	let loginStatus = $state<string | null>(null);
	let profileOpen = $state(false);
	let profileEmail = $state('');
	let profileCurrentPassword = $state('');
	let profileNewPassword = $state('');
	let profileStatus = $state<string | null>(null);
	let profileSaving = $state(false);

	function apiFetch(path: string, init: RequestInit = {}) {
		const headers = new Headers(init.headers);
		return fetch(path, { ...init, headers, credentials: 'same-origin' });
	}

	let nearbyHistoryRequestId = 0;
	let nearbyHistoryLoadedId: string | null = null;

	async function loadNearbyHistory(historyId: string | null | undefined) {
		const normalizedHistoryId = historyId ?? null;
		if (normalizedHistoryId === nearbyHistoryLoadedId) return;
		nearbyHistoryLoadedId = normalizedHistoryId;
		const requestId = ++nearbyHistoryRequestId;
		nearbyHistory = [];
		if (!historyId) return;
		try {
			const response = await apiFetch(`/api/history/${historyId}/neighbors`, { cache: 'no-store' });
			if (!response.ok) throw new Error(`HTTP ${response.status}`);
			const items = await response.json();
			if (requestId === nearbyHistoryRequestId) {
				nearbyHistory = Array.isArray(items) ? items : [];
			}
		} catch {
			if (requestId === nearbyHistoryRequestId) nearbyHistory = [];
		}
	}

	function applyUserTheme(user: UserItem | null) {
		darkMode = user?.ui_theme === 'dark';
	}

	function modelsFor(provider: Provider) {
		return availableModelCatalog.find((group) => group.id === provider)?.models ?? modelsForProvider(provider);
	}

	function visionModelsFor(provider: Provider) {
		return availableVisionModelCatalog.find((group) => group.id === provider)?.models ?? [];
	}

	function reconcileDemoPromptModel() {
		if (!availableModelsLoaded || !demoSettingsLoaded) return;
		const configuredModels = availableModelCatalog.flatMap((group) => group.models);
		if (configuredModels.some((model) => model.id === demoSettings.prompt_model)) return;
		const fallbackModel = configuredModels[0]?.id;
		if (!fallbackModel) return;
		void saveDemoSettings({ ...demoSettings, prompt_model: fallbackModel });
	}

	function applyUserModelSettings(user: UserItem | null) {
		const settings = user?.model_settings;
		if (!settings) return;
		stage1Provider = settings.stage1_provider;
		stage1Model = settings.stage1_model;
		stage2Provider = settings.stage2_provider;
		stage2Model = settings.stage2_model;
		visionProvider = settings.vision_provider;
		visionModel = settings.vision_model;
		okugakiModel = settings.okugaki_model || qualifiedModelId(settings.vision_provider, settings.vision_model);
		instructionCaptionVisible = settings.instruction_caption_visible !== false;
		modelInspectionSelectedModels = Array.isArray(settings.model_inspection_selected_models)
			? settings.model_inspection_selected_models.filter((model): model is string => typeof model === 'string').slice(0, 4)
			: [];
	}

	async function persistInstructionCaptionVisible(visible: boolean) {
		instructionCaptionVisible = visible;
		if (!currentUser) return;
		try {
			const r = await apiFetch('/api/auth/me/settings', { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ model_settings: { instruction_caption_visible: visible } }) });
			if (!r.ok) throw new Error(`HTTP ${r.status}`);
			currentUser = await r.json() as UserItem;
		} catch (e) { console.warn('failed to save instruction caption setting', e); }
	}

	async function persistOkugakiModel(model: string): Promise<void> {
		const nextModel = model.trim();
		if (!nextModel || nextModel === okugakiModel) return;
		const previous = okugakiModel;
		okugakiModel = nextModel;
		if (!currentUser) return;
		try {
			const r = await apiFetch('/api/auth/me/settings', {
				method: 'PATCH',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ model_settings: { okugaki_model: nextModel } })
			});
			if (!r.ok) throw new Error(`HTTP ${r.status}`);
			currentUser = await r.json() as UserItem;
		} catch (e) {
			okugakiModel = previous;
			console.warn('failed to save okugaki model', e);
			throw e;
		}
	}

	async function persistVisionModel(provider: Provider, model: string): Promise<void> {
		if (!provider || !model) return;
		if (provider === visionProvider && model === visionModel) return;
		const prevProvider = visionProvider;
		const prevModel = visionModel;
		visionProvider = provider;
		visionModel = model;
		if (!currentUser) return;
		try {
			const r = await apiFetch('/api/auth/me/settings', {
				method: 'PATCH',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ model_settings: { vision_provider: provider, vision_model: model } })
			});
			if (!r.ok) throw new Error(`HTTP ${r.status}`);
			currentUser = await r.json() as UserItem;
		} catch (e) {
			visionProvider = prevProvider;
			visionModel = prevModel;
			console.warn('failed to save vision model', e);
			throw e;
		}
	}

	function isSettingsContentTab(tab: SettingsTab | undefined): tab is Exclude<SettingsTab, 'connection'> {
		return tab === 'models' || tab === 'db' || tab === 'plugins' || tab === 'users' || tab === 'unread' || tab === 'export' || tab === 'misc' || tab === 'server_misc' || tab === 'logs';
	}

	function canAccessSettingsTab(tab: SettingsTab) {
		if (tab === 'models' || tab === 'db' || tab === 'users' || tab === 'server_misc' || tab === 'logs') return currentUser?.role === 'admin';
		return tab !== 'connection';
	}

	function defaultSettingsTab() {
		return currentUser?.role === 'admin' ? 'models' : 'plugins';
	}

	function normalizeBatchPromptHistory(items: string[]): string[] {
		const normalized: string[] = [];
		const seen = new Set<string>();
		for (const item of items) {
			const prompt = item.trim().replace(/\r\n/g, '\n').replace(/\r/g, '\n');
			if (!prompt || seen.has(prompt) || prompt.length > BATCH_PROMPT_HISTORY_MAX_TEXT) continue;
			normalized.push(prompt);
			seen.add(prompt);
			if (normalized.length >= BATCH_PROMPT_HISTORY_LIMIT) break;
		}
		return normalized;
	}

	async function loadBatchPromptHistory() {
		if (!currentUser) {
			batchPromptHistory = [];
			return;
		}
		try {
			const r = await apiFetch('/api/auth/me/batch-prompt-history', { cache: 'no-store' });
			if (!r.ok) throw new Error(`HTTP ${r.status}`);
			const data = await r.json() as { items?: unknown };
			batchPromptHistory = Array.isArray(data.items)
				? normalizeBatchPromptHistory(data.items.filter((item): item is string => typeof item === 'string'))
				: [];
		} catch (e) {
			batchPromptHistory = [];
			console.warn('failed to load batch prompt history', e);
		}
	}

	function normalizeDemoSettings(settings: DemoSettings): DemoSettings {
		return {
			save_db: !!settings.save_db,
			save_files: !!settings.save_files,
			prompt_model: settings.prompt_model || DEFAULT_MODEL,
			seed_phrase: settings.seed_phrase.trim() || DEFAULT_DEMO_SETTINGS.seed_phrase,
			interval_seconds: Math.max(1, Math.min(3600, Math.round(settings.interval_seconds || 30))),
			random_color_catalog: !!settings.random_color_catalog,
		};
	}

	async function loadPluginStorage() {
		if (!currentUser) {
			canvasAspectId = DEFAULT_CANVAS_ASPECT_ID;
			return;
		}
		try {
			const r = await apiFetch('/api/auth/me/plugin-storage', { cache: 'no-store' });
			if (!r.ok) throw new Error(`HTTP ${r.status}`);
			const data = await r.json() as { storage?: Record<string, unknown> };
			const canvasValue = data.storage?.[CANVAS_ASPECT_PLUGIN_ID] as { selected?: unknown; enabled?: unknown } | undefined;
			canvasAspectEnabled = canvasValue?.enabled !== false;
			canvasAspectId = normalizeCanvasAspectId(canvasValue?.selected);
		} catch (e) {
			canvasAspectEnabled = true;
			canvasAspectId = DEFAULT_CANVAS_ASPECT_ID;
			console.warn('failed to load plugin storage', e);
		}
	}

	function canvasAspectPluginValue() {
		return { enabled: canvasAspectEnabled, selected: canvasAspectId };
	}

	function effectiveCanvasAspectId(): CanvasAspectId {
		return canvasAspectEnabled ? canvasAspectId : DEFAULT_CANVAS_ASPECT_ID;
	}

	async function saveCanvasAspectPluginValue() {
		if (!currentUser) return;
		try {
			const r = await apiFetch(`/api/auth/me/plugin-storage/${CANVAS_ASPECT_PLUGIN_ID}`, {
				method: 'PUT',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ value: canvasAspectPluginValue() })
			});
			if (!r.ok) throw new Error(`HTTP ${r.status}`);
		} catch (e) {
			console.warn('failed to save canvas aspect plugin storage', e);
		}
	}

	async function setCanvasAspectEnabled(value: boolean) {
		if (currentUser?.role !== 'admin') return;
		canvasAspectEnabled = value;
		canvasAspectMenuOpen = false;
		if (!value) {
			result = null;
			displayedHistoryItem = null;
			historyCursor = -1;
			outputTab = 'canvas';
			pngMenuOpen = false;
			fitCanvasZoom();
		}
		await saveCanvasAspectPluginValue();
	}

	async function selectCanvasAspect(id: CanvasAspectId) {
		if (currentUser?.role !== 'admin') return;
		const nextAspectId = normalizeCanvasAspectId(id);
		const currentAspectId = effectiveCanvasAspectId();
		canvasAspectMenuOpen = false;
		if (nextAspectId === currentAspectId) {
			await saveCanvasAspectPluginValue();
			return;
		}
		const existingPending = pendingCanvasAspectDerivation;
		const parentNodeId = existingPending?.parentNodeId ?? await ensureVisibleLineageParentId();
		pendingCanvasAspectDerivation = parentNodeId
			? { parentNodeId, fromAspectId: existingPending?.fromAspectId ?? currentAspectId, toAspectId: nextAspectId }
			: null;
		canvasAspectId = nextAspectId;
		result = null;
		displayedHistoryItem = null;
		historyCursor = -1;
		outputTab = 'canvas';
		pngMenuOpen = false;
		fitCanvasZoom();
		await saveCanvasAspectPluginValue();
	}

	async function loadDemoSettings() {
		if (!currentUser) {
			demoSettings = { ...DEFAULT_DEMO_SETTINGS };
			demoSettingsLoaded = false;
			return;
		}
		try {
			const r = await apiFetch('/api/auth/me/demo-settings', { cache: 'no-store' });
			if (!r.ok) throw new Error(`HTTP ${r.status}`);
			demoSettings = normalizeDemoSettings(await r.json() as DemoSettings);
			demoSettingsLoaded = true;
			reconcileDemoPromptModel();
		} catch (e) {
			demoSettings = { ...DEFAULT_DEMO_SETTINGS };
			demoSettingsLoaded = false;
			console.warn('failed to load demo settings', e);
		}
	}

	async function loadExportTemplates() {
		if (!currentUser) {
			exportTemplates = DEFAULT_EXPORT_TEMPLATES.map((item) => ({ ...item }));
			exportTemplateStatus = null;
			return;
		}
		try {
			const r = await apiFetch('/api/auth/me/export-templates', { cache: 'no-store' });
			if (!r.ok) throw new Error(`HTTP ${r.status}`);
			const data = await r.json() as { templates?: unknown };
			exportTemplates = normalizeExportTemplates(data.templates);
			exportTemplateStatus = null;
		} catch (e) {
			exportTemplates = DEFAULT_EXPORT_TEMPLATES.map((item) => ({ ...item }));
			exportTemplateStatus = t().settingsExportTemplateSaveFailed;
			console.warn('failed to load export templates', e);
		}
	}

	async function saveExportTemplates(nextTemplates: ExportTemplate[]) {
		const previous = exportTemplates;
		const next = normalizeExportTemplates(nextTemplates);
		exportTemplates = next;
		exportTemplateStatus = null;
		if (!currentUser) return;
		try {
			const r = await apiFetch('/api/auth/me/export-templates', {
				method: 'PUT',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ templates: next })
			});
			if (!r.ok) {
				const d = await r.json().catch(() => ({})) as { detail?: string };
				throw new Error(d.detail ?? `HTTP ${r.status}`);
			}
			const data = await r.json() as { templates?: unknown };
			exportTemplates = normalizeExportTemplates(data.templates);
		} catch (e) {
			exportTemplates = previous;
			exportTemplateStatus = t().settingsExportTemplateSaveFailed;
			console.warn('failed to save export templates', e);
		}
	}

	function addExportTemplate() {
		const id = `png-${Date.now().toString(36)}`;
		void saveExportTemplates([
			...exportTemplates,
			{ id, name: 'PNG 3000px', description: 'PNG / Y軸 3000px', y_px: 3000 }
		]);
	}

	function updateExportTemplate(id: string, patch: Partial<ExportTemplate>) {
		void saveExportTemplates(exportTemplates.map((template) => (
			template.id === id ? { ...template, ...patch } : template
		)));
	}

	function removeExportTemplate(id: string) {
		void saveExportTemplates(exportTemplates.filter((template) => template.id !== id));
	}

	async function saveDemoSettings(settings: DemoSettings) {
		const next = normalizeDemoSettings(settings);
		demoSettings = next;
		if (!currentUser || !demoSettingsLoaded) return;
		try {
			const r = await apiFetch('/api/auth/me/demo-settings', {
				method: 'PUT',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify(next)
			});
			if (!r.ok) throw new Error(`HTTP ${r.status}`);
			demoSettings = normalizeDemoSettings(await r.json() as DemoSettings);
		} catch (e) {
			console.warn('failed to save demo settings', e);
		}
	}

	async function rememberBatchPrompt(prompt: string) {
		if (!currentUser) return;
		const previous = batchPromptHistory;
		const next = normalizeBatchPromptHistory([prompt, ...batchPromptHistory]);
		if (next.length === previous.length && next.every((item, i) => item === previous[i])) return;
		batchPromptHistory = next;
		try {
			const r = await apiFetch('/api/auth/me/batch-prompt-history', {
				method: 'PUT',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ items: next })
			});
			if (!r.ok) {
				const d = await r.json().catch(() => ({})) as { detail?: string };
				throw new Error(d.detail ?? `HTTP ${r.status}`);
			}
			const data = await r.json() as { items?: unknown };
			if (Array.isArray(data.items)) {
				batchPromptHistory = normalizeBatchPromptHistory(
					data.items.filter((item): item is string => typeof item === 'string')
				);
			}
		} catch (e) {
			batchPromptHistory = previous;
			console.warn('failed to update batch prompt history', e);
		}
	}

	async function updateUiTheme(nextDarkMode: boolean) {
		if (!currentUser) return;
		const previousDarkMode = darkMode;
		const previousUser = currentUser;
		darkMode = nextDarkMode;
		try {
			const r = await apiFetch('/api/auth/me/settings', {
				method: 'PATCH',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ ui_theme: nextDarkMode ? 'dark' : 'light' })
			});
			if (!r.ok) {
				const d = await r.json().catch(() => ({})) as { detail?: string };
				throw new Error(d.detail ?? `HTTP ${r.status}`);
			}
			currentUser = await r.json() as UserItem;
			applyUserTheme(currentUser);
		} catch (e) {
			currentUser = previousUser;
			darkMode = previousDarkMode;
			console.warn('failed to update UI theme', e);
		}
	}

	async function updateUserSettingsTab(tab: typeof settingsTab) {
		if (!currentUser || !isSettingsContentTab(tab)) return;
		const previousUser = currentUser;
		try {
			const r = await apiFetch('/api/auth/me/settings', {
				method: 'PATCH',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ settings_tab: tab })
			});
			if (!r.ok) {
				const d = await r.json().catch(() => ({})) as { detail?: string };
				throw new Error(d.detail ?? `HTTP ${r.status}`);
			}
			currentUser = await r.json() as UserItem;
		} catch (e) {
			currentUser = previousUser;
			console.warn('failed to update settings tab', e);
		}
	}

	function openSettings(tab: typeof settingsTab | null = null) {
		settingsMode = 'settings';
		const candidate = tab ?? (isSettingsContentTab(currentUser?.settings_tab) ? currentUser.settings_tab : defaultSettingsTab());
		const nextTab = canAccessSettingsTab(candidate) ? candidate : defaultSettingsTab();
		settingsTab = nextTab;
		settingsOpen = true;
		if (nextTab === 'models') void loadModelSettings();
		if (nextTab === 'db' || nextTab === 'server_misc' || nextTab === 'logs') void loadSettingsStatus();
		if (nextTab === 'users') void loadUserSettings();
		if (nextTab === 'export') void loadExportTemplates();
	}

	function openModelSelection(allowVision = true) {
		modelSelectionAllowVision = allowVision;
		modelSelectionSnapshot = { stage1Provider, stage1Model, stage2Provider, stage2Model, visionProvider, visionModel };
		settingsMode = 'model';
		settingsTab = 'connection';
		settingsOpen = true;
		void loadAvailableModels();
	}

	async function persistModelSelection() {
		if (!currentUser) return;
		const previousUser = currentUser;
		const model_settings: UserModelSettings = {
			stage1_provider: stage1Provider,
			stage1_model: stage1Model,
			stage2_provider: stage2Provider,
			stage2_model: stage2Model,
			vision_provider: visionProvider,
			vision_model: visionModel,
			okugaki_model: okugakiModel,
			model_inspection_selected_models: modelInspectionSelectedModels,
			instruction_caption_visible: instructionCaptionVisible,
		};
		try {
			const r = await apiFetch('/api/auth/me/settings', {
				method: 'PATCH',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ model_settings })
			});
			if (!r.ok) {
				const d = await r.json().catch(() => ({})) as { detail?: string };
				throw new Error(d.detail ?? `HTTP ${r.status}`);
			}
			currentUser = await r.json() as UserItem;
			applyUserModelSettings(currentUser);
		} catch (e) {
			currentUser = previousUser;
			console.warn('failed to update model selection', e);
		}
	}

	async function confirmModelSelection() {
		modelSelectionSnapshot = null;
		await persistModelSelection();
		settingsOpen = false;
	}

	function cancelModelSelection() {
		if (modelSelectionSnapshot) {
			stage1Provider = modelSelectionSnapshot.stage1Provider;
			stage1Model = modelSelectionSnapshot.stage1Model;
			stage2Provider = modelSelectionSnapshot.stage2Provider;
			stage2Model = modelSelectionSnapshot.stage2Model;
			visionProvider = modelSelectionSnapshot.visionProvider;
			visionModel = modelSelectionSnapshot.visionModel;
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

	async function loadColorCatalogs() {
		try {
			const r = await apiFetch('/api/color-catalogs', { cache: 'no-store' });
			if (!r.ok) throw new Error(`HTTP ${r.status}`);
			const data = await r.json() as ColorCatalogsResponse;
			if (!Array.isArray(data.catalogs) || data.catalogs.length === 0) throw new Error('empty color catalog list');
			colorCatalogs = data.catalogs;
			defaultCatalogId = data.default_catalog_id || 'default';
			if (!catalogById(colorCatalogs, selectedCatalog)) selectedCatalog = defaultCatalogId;
		} catch (e) {
			console.warn('failed to load color catalogs', e);
		}
	}

	function selectSettingsTab(tab: typeof settingsTab) {
		if (!canAccessSettingsTab(tab)) return;
		settingsTab = tab;
		void updateUserSettingsTab(tab);
		if (tab === 'models') void loadModelSettings();
		if (tab === 'db' || tab === 'server_misc' || tab === 'logs') void loadSettingsStatus();
		if (tab === 'users') void loadUserSettings();
		if (tab === 'export') void loadExportTemplates();
	}

	async function loadModelSettings() {
		if (currentUser?.role !== 'admin') {
			modelSettings = null;
			modelSettingsStatus = t().settingsAdminOnlyMessage;
			return;
		}
		modelSettingsLoading = true;
		try {
			const r = await apiFetch('/api/settings/models', { cache: 'no-store' });
			if (!r.ok) throw new Error(`HTTP ${r.status}`);
			const data = await r.json() as { catalog: ProviderGroup[]; settings: ModelSettings };
			modelCatalog = data.catalog;
			modelSettings = data.settings;
			modelSettingsStatus = null;
		} catch (e) {
			modelSettingsStatus = e instanceof Error ? e.message : String(e);
		} finally {
			modelSettingsLoading = false;
		}
	}

	async function loadAvailableModels() {
		if (!currentUser) {
			availableModelsLoaded = false;
			return;
		}
		try {
			const r = await apiFetch('/api/models', { cache: 'no-store' });
			if (!r.ok) throw new Error(`HTTP ${r.status}`);
			const data = await r.json() as { catalog: ProviderGroup[]; llm_catalog?: ProviderGroup[]; vision_catalog?: ProviderGroup[]; settings: { model_settings?: UserModelSettings } };
			availableModelCatalog = data.llm_catalog ?? data.catalog;
			availableVisionModelCatalog = data.vision_catalog ?? data.catalog.filter((group) => group.models.some((model) => model.purposes?.includes('vision')));
			availableModelsLoaded = true;
			if (data.settings.model_settings) {
				applyUserModelSettings({ ...currentUser, model_settings: data.settings.model_settings });
			}
			if (!modelsFor(stage1Provider).some((model) => model.id === stage1Model)) {
				stage1Model = modelsFor(stage1Provider)[0]?.id ?? stage1Model;
			}
			if (!modelsFor(stage2Provider).some((model) => model.id === stage2Model)) {
				stage2Model = modelsFor(stage2Provider)[0]?.id ?? stage2Model;
			}
			if (!visionModelsFor(visionProvider).some((model) => model.id === visionModel)) {
				const fallbackGroup = availableVisionModelCatalog.find((group) => group.models.length > 0);
				visionProvider = fallbackGroup?.id ?? visionProvider;
				visionModel = fallbackGroup?.models[0]?.id ?? visionModel;
			}
			reconcileDemoPromptModel();
		} catch (e) {
			console.warn('failed to load model catalog', e);
		}
	}

	function updateModelProvider(provider: Provider, patch: Partial<ModelProviderSetting>) {
		if (!modelSettings) return;
		const current = modelSettings.providers[provider] ?? { base_url: '', api_key_set: false, api_key_hint: null };
		modelSettings = {
			...modelSettings,
			providers: {
				...modelSettings.providers,
				[provider]: { ...current, ...patch },
			},
		};
	}

	async function addModelProvider(provider: Provider, patch: Partial<ModelProviderSetting>) {
		if (!modelSettings || !provider || currentUser?.role !== 'admin') return;
		modelSettingsLoading = true;
		try {
			const r = await apiFetch('/api/settings/models', {
				method: 'PUT',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({
					providers: {
						[provider]: {
							label: patch.label ?? provider,
							kind: patch.kind,
							requires_api_key: patch.requires_api_key,
							memo: patch.memo,
							models: patch.models ?? [],
							base_url: patch.base_url ?? patch.default_base_url ?? '',
							api_key: patch.api_key || undefined,
							enabled_models: patch.enabled_models ?? {},
						},
					},
				}),
			});
			if (!r.ok) throw new Error(`HTTP ${r.status}`);
			const data = await r.json() as { catalog: ProviderGroup[]; settings: ModelSettings };
			modelCatalog = data.catalog;
			modelSettings = data.settings;
			modelSettingsStatus = t().settingsModelSaved;
			await loadAvailableModels();
		} catch (e) {
			modelSettingsStatus = e instanceof Error ? e.message : String(e);
			throw e;
		} finally {
			modelSettingsLoading = false;
		}
	}

	function askDeleteModelProvider(provider: Provider) {
		const providerLabel = modelCatalog.find((item) => item.id === provider)?.label ?? provider;
		confirmAction = {
			message: t().settingsModelDeleteServiceConfirm(providerLabel),
			destructive: true,
			run: () => { void deleteModelProvider(provider); },
		};
	}

	async function deleteModelProvider(provider: Provider) {
		if (currentUser?.role !== 'admin') return;
		modelSettingsLoading = true;
		try {
			const r = await apiFetch('/api/settings/models', {
				method: 'PUT',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ providers: { [provider]: { delete: true } } }),
			});
			if (!r.ok) throw new Error(`HTTP ${r.status}`);
			const data = await r.json() as { catalog: ProviderGroup[]; settings: ModelSettings };
			modelCatalog = data.catalog;
			modelSettings = data.settings;
			modelSettingsStatus = t().settingsModelSaved;
			await loadAvailableModels();
		} catch (e) {
			modelSettingsStatus = e instanceof Error ? e.message : String(e);
		} finally {
			modelSettingsLoading = false;
		}
	}

	async function fetchProviderModels(provider: Provider) {
		if (currentUser?.role !== 'admin') return;
		modelSettingsLoading = true;
		const nextResults = { ...modelFetchResults };
		delete nextResults[provider];
		modelFetchResults = nextResults;
		try {
			const r = await apiFetch(`/api/settings/models/${encodeURIComponent(provider)}/fetch-models`, {
				method: 'POST',
			});
			if (!r.ok) {
				const d = await r.json().catch(() => ({})) as { detail?: string };
				throw new Error(d.detail ?? `HTTP ${r.status}`);
			}
			const data = await r.json() as { catalog: ProviderGroup[]; settings: ModelSettings };
			modelCatalog = data.catalog;
			modelSettings = data.settings;
			modelSettingsStatus = t().settingsModelFetchModelsSaved;
			modelFetchResults = { ...modelFetchResults, [provider]: { type: 'success', message: t().settingsModelFetchModelsSaved } };
			await loadAvailableModels();
		} catch (e) {
			const message = e instanceof Error ? e.message : String(e);
			modelFetchResults = { ...modelFetchResults, [provider]: { type: 'error', message } };
			modelSettingsStatus = message;
		} finally {
			modelSettingsLoading = false;
		}
	}

	function askClearModelApiKey(provider: Provider) {
		const providerLabel = modelCatalog.find((item) => item.id === provider)?.label ?? provider;
		confirmAction = {
			message: t().settingsModelClearApiKeyConfirm(providerLabel),
			destructive: true,
			runLabel: t().settingsModelClearApiKey,
			run: () => { void clearModelApiKey(provider); },
		};
	}

	async function clearModelApiKey(provider: Provider) {
		if (currentUser?.role !== 'admin') return;
		modelSettingsLoading = true;
		try {
			const current = modelSettings?.providers[provider];
			const r = await apiFetch('/api/settings/models', {
				method: 'PUT',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({
					providers: {
						[provider]: {
							base_url: current?.base_url,
							clear_api_key: true,
							enabled_models: current?.enabled_models ?? {},
						},
					},
				}),
			});
			if (!r.ok) throw new Error(`HTTP ${r.status}`);
			const data = await r.json() as { catalog: ProviderGroup[]; settings: ModelSettings };
			modelCatalog = data.catalog;
			modelSettings = data.settings;
			modelSettingsStatus = t().settingsModelApiKeyCleared;
		} catch (e) {
			modelSettingsStatus = e instanceof Error ? e.message : String(e);
		} finally {
			modelSettingsLoading = false;
		}
	}

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
			enabled_models: provider.enabled_models ?? {},
		};
	}

	async function saveModelProviderName(provider: Provider, label: string) {
		if (!modelSettings || currentUser?.role !== 'admin') return;
		const providerSettings = modelSettings.providers[provider];
		if (!providerSettings) return;
		const nextLabel = label.trim();
		if (!nextLabel) return;
		modelSettingsLoading = true;
		try {
			const r = await apiFetch('/api/settings/models', {
				method: 'PUT',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({
					providers: {
						[provider]: modelProviderPayload(provider, providerSettings, nextLabel),
					},
				}),
			});
			if (!r.ok) throw new Error(`HTTP ${r.status}`);
			const data = await r.json() as { catalog: ProviderGroup[]; settings: ModelSettings };
			modelCatalog = data.catalog;
			modelSettings = data.settings;
			modelSettingsStatus = t().settingsModelSaved;
			await loadAvailableModels();
		} catch (e) {
			modelSettingsStatus = e instanceof Error ? e.message : String(e);
		} finally {
			modelSettingsLoading = false;
		}
	}

	async function saveModelProviderMemo(provider: Provider, memo: string) {
		if (!modelSettings || currentUser?.role !== 'admin') return;
		const providerSettings = modelSettings.providers[provider];
		if (!providerSettings) return;
		modelSettingsLoading = true;
		try {
			const r = await apiFetch('/api/settings/models', {
				method: 'PUT',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({
					providers: {
						[provider]: modelProviderPayload(provider, providerSettings, undefined, memo),
					},
				}),
			});
			if (!r.ok) throw new Error(`HTTP ${r.status}`);
			const data = await r.json() as { catalog: ProviderGroup[]; settings: ModelSettings };
			modelCatalog = data.catalog;
			modelSettings = data.settings;
			modelSettingsStatus = t().settingsModelSaved;
			await loadAvailableModels();
		} catch (e) {
			modelSettingsStatus = e instanceof Error ? e.message : String(e);
		} finally {
			modelSettingsLoading = false;
		}
	}

	async function saveModelProvider(provider: Provider, patch: Partial<ModelProviderSetting> = {}) {
		if (!modelSettings || currentUser?.role !== 'admin') return;
		const currentProviderSettings = modelSettings.providers[provider];
		const providerSettings = currentProviderSettings ? { ...currentProviderSettings, ...patch } : null;
		if (!providerSettings) return;
		modelSettingsLoading = true;
		try {
			const r = await apiFetch('/api/settings/models', {
				method: 'PUT',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({
					providers: {
						[provider]: modelProviderPayload(provider, providerSettings),
					},
				}),
			});
			if (!r.ok) throw new Error(`HTTP ${r.status}`);
			const data = await r.json() as { catalog: ProviderGroup[]; settings: ModelSettings };
			modelCatalog = data.catalog;
			modelSettings = data.settings;
			modelSettingsStatus = t().settingsModelSaved;
			await loadAvailableModels();
		} catch (e) {
			modelSettingsStatus = e instanceof Error ? e.message : String(e);
		} finally {
			modelSettingsLoading = false;
		}
	}

	async function saveModelSettings() {
		if (!modelSettings || currentUser?.role !== 'admin') return;
		modelSettingsLoading = true;
		try {
			const providers = Object.fromEntries(Object.entries(modelSettings.providers).map(([id, provider]) => {
				return [id, modelProviderPayload(id, provider)];
			}));
			const r = await apiFetch('/api/settings/models', {
				method: 'PUT',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({
					providers,
				}),
			});
			if (!r.ok) throw new Error(`HTTP ${r.status}`);
			const data = await r.json() as { catalog: ProviderGroup[]; settings: ModelSettings };
			modelCatalog = data.catalog;
			modelSettings = data.settings;
			modelSettingsStatus = t().settingsModelSaved;
			await loadAvailableModels();
		} catch (e) {
			modelSettingsStatus = e instanceof Error ? e.message : String(e);
		} finally {
			modelSettingsLoading = false;
		}
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
			applyUserTheme(actor);
			applyUserModelSettings(actor);
			authToken = 'cookie';
			if (actor.role !== 'admin') {
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

	async function loadPluginVocabulary() {
		try {
			const response = await apiFetch("/api/saijiki", { cache: "no-store" });
			if (!response.ok) throw new Error(`HTTP ${response.status}`);
			const data = await response.json() as {
				categories: { key: string; name_ja: string; name_en: string; words: string[] }[];
				plugins: PluginEntry[];
			};
			hydrateSaijiki(
				data.categories.map((c) => ({ key: c.key, label: c.name_ja, en: c.name_en, words: c.words }))
			);
			pluginEntries = data.plugins ?? [];
		} catch (error) {
			// keep the bundled saijiki snapshot; only plugin words are cleared
			pluginEntries = [];
			console.warn("failed to load saijiki vocabulary", error);
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
			dbBackupStatus = null;
			outputSaveStatus = null;
			logRetentionStatus = null;
		} catch (e) {
			settingsStatus = null;
			settingsStatusError = e instanceof Error ? e.message : String(e);
		} finally {
			settingsStatusLoading = false;
		}
	}

	// ── User plugin management (backend contract may not be deployed yet) ──
	let pluginActionStatus = $state<string | null>(null);

	function pluginErrorMessage(status: number, detail: unknown): string {
		if (status === 404 || status === 405 || status === 501) {
			return getLang() === 'ja'
				? 'このプラグイン管理機能はサーバー側が未実装です（バックエンド待ち）。'
				: 'This plugin management endpoint is not implemented on the server yet.';
		}
		if (Array.isArray(detail)) return (detail as string[]).join(' / ');
		if (typeof detail === 'string') return detail;
		return `HTTP ${status}`;
	}

	async function loadPluginContent(id: string): Promise<string | null> {
		pluginActionStatus = null;
		try {
			const r = await apiFetch(`/api/plugins/${encodeURIComponent(id)}/content`);
			if (!r.ok) {
				const d = await r.json().catch(() => ({})) as { detail?: unknown };
				pluginActionStatus = pluginErrorMessage(r.status, d.detail);
				return null;
			}
			const data = await r.json() as { content?: string };
			return data.content ?? '';
		} catch (e) {
			pluginActionStatus = e instanceof Error ? e.message : String(e);
			return null;
		}
	}

	// Returns null on success, or an array of validation reasons / messages on failure.
	async function savePlugin(id: string, content: string): Promise<string[] | null> {
		pluginActionStatus = null;
		try {
			const r = await apiFetch(`/api/plugins/${encodeURIComponent(id)}`, {
				method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ content }),
			});
			if (!r.ok) {
				const d = await r.json().catch(() => ({})) as { detail?: unknown };
				return Array.isArray(d.detail) ? d.detail as string[] : [pluginErrorMessage(r.status, d.detail)];
			}
			await loadSettingsStatus();
			return null;
		} catch (e) {
			return [e instanceof Error ? e.message : String(e)];
		}
	}

	async function createPlugin(content: string, filename: string): Promise<string[] | null> {
		pluginActionStatus = null;
		try {
			const r = await apiFetch('/api/plugins', {
				method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ content, filename }),
			});
			if (!r.ok) {
				const d = await r.json().catch(() => ({})) as { detail?: unknown };
				return Array.isArray(d.detail) ? d.detail as string[] : [pluginErrorMessage(r.status, d.detail)];
			}
			await loadSettingsStatus();
			return null;
		} catch (e) {
			return [e instanceof Error ? e.message : String(e)];
		}
	}

	async function deletePlugin(id: string): Promise<boolean> {
		pluginActionStatus = null;
		try {
			const r = await apiFetch(`/api/plugins/${encodeURIComponent(id)}`, { method: 'DELETE' });
			if (!r.ok) {
				const d = await r.json().catch(() => ({})) as { detail?: unknown };
				pluginActionStatus = pluginErrorMessage(r.status, d.detail);
				return false;
			}
			await loadSettingsStatus();
			return true;
		} catch (e) {
			pluginActionStatus = e instanceof Error ? e.message : String(e);
			return false;
		}
	}

	async function setPluginEnabled(id: string, enabled: boolean): Promise<boolean> {
		pluginActionStatus = null;
		try {
			const r = await apiFetch(`/api/plugins/${encodeURIComponent(id)}/enabled`, {
				method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ enabled }),
			});
			if (!r.ok) {
				const d = await r.json().catch(() => ({})) as { detail?: unknown };
				pluginActionStatus = pluginErrorMessage(r.status, d.detail);
				return false;
			}
			await loadSettingsStatus();
			return true;
		} catch (e) {
			pluginActionStatus = e instanceof Error ? e.message : String(e);
			return false;
		}
	}

	async function updateDbBackupSettings(intervalDays: number, maxGenerations: number) {
		dbBackupStatus = null;
		try {
			const r = await apiFetch('/api/settings/db-backup', {
				method: 'PUT',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ interval_days: intervalDays, max_generations: maxGenerations })
			});
			if (!r.ok) {
				const d = await r.json().catch(() => ({})) as { detail?: string };
				throw new Error(d.detail ?? `HTTP ${r.status}`);
			}
			const nextBackup = await r.json() as SettingsStatus['db_backup'];
			if (settingsStatus) settingsStatus = { ...settingsStatus, db_backup: nextBackup };
		} catch (e) {
			dbBackupStatus = t().settingsDbBackupSaveFailed;
			console.warn('failed to update DB backup settings', e);
		}
	}

	async function runDbBackupNow() {
		dbBackupStatus = null;
		try {
			const r = await apiFetch('/api/settings/db-backup/run', { method: 'POST' });
			if (!r.ok) {
				const d = await r.json().catch(() => ({})) as { detail?: string };
				throw new Error(d.detail ?? `HTTP ${r.status}`);
			}
			await loadSettingsStatus();
			dbBackupStatus = t().settingsDbBackupRunDone;
		} catch (e) {
			dbBackupStatus = e instanceof Error ? e.message : String(e);
		}
	}

	async function updateOutputSaveSettings(enabled: boolean, outputDir: string, pngSize: number) {
		outputSaveStatus = null;
		try {
			const r = await apiFetch('/api/settings/output-save', {
				method: 'PUT',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ enabled, output_dir: outputDir, png_size: pngSize })
			});
			if (!r.ok) {
				const d = await r.json().catch(() => ({})) as { detail?: string };
				throw new Error(d.detail ?? `HTTP ${r.status}`);
			}
			const nextOutputSave = await r.json() as SettingsStatus['output_save'];
			if (settingsStatus) settingsStatus = { ...settingsStatus, output_save: nextOutputSave };
			outputSaveStatus = t().settingsOutputSaveSaved;
		} catch (e) {
			outputSaveStatus = e instanceof Error ? e.message : String(e);
			console.warn('failed to update output save settings', e);
		}
	}

	async function updateLogRetentionSettings(enabled: boolean, retentionDays: number, rotate: string, compress: boolean) {
		logRetentionStatus = null;
		try {
			const r = await apiFetch('/api/settings/log-retention', {
				method: 'PUT',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ enabled, retention_days: retentionDays, rotate, compress })
			});
			if (!r.ok) {
				const d = await r.json().catch(() => ({})) as { detail?: string };
				throw new Error(d.detail ?? `HTTP ${r.status}`);
			}
			const nextLogRetention = await r.json() as SettingsStatus['log_retention'];
			if (settingsStatus) settingsStatus = { ...settingsStatus, log_retention: nextLogRetention };
			logRetentionStatus = t().settingsLogRetentionSaved;
		} catch (e) {
			logRetentionStatus = e instanceof Error ? e.message : String(e);
			console.warn('failed to update log retention settings', e);
		}
	}

	async function loadCurrentUser() {
		try {
			const r = await apiFetch('/api/auth/me');
			if (!r.ok) throw new Error('session expired');
			currentUser = await r.json() as UserItem;
			applyUserTheme(currentUser);
			applyUserModelSettings(currentUser);
			authToken = 'cookie';
			loginStatus = null;
			await Promise.all([loadAvailableModels(), loadUserSettings(), loadSettingsStatus(), loadBatchPromptHistory(), loadDemoSettings(), loadPluginStorage(), loadPluginVocabulary(), loadExportTemplates()]);
			await Promise.all([fetchHistoryPage(0), fetchTrashPage()]);
			if (historyItems.length > 0) loadIteration(0);
		} catch {
			authToken = null;
			currentUser = null;
			applyUserTheme(null);
			batchPromptHistory = [];
			demoSettings = { ...DEFAULT_DEMO_SETTINGS };
			demoSettingsLoaded = false;
			exportTemplates = DEFAULT_EXPORT_TEMPLATES.map((item) => ({ ...item }));
			exportTemplateStatus = null;
			canvasAspectEnabled = true;
			canvasAspectId = DEFAULT_CANVAS_ASPECT_ID;
			loginStatus = t().loginRequiredMessage;
			settingsStatus = null;
			settingsStatusError = t().loginRequiredMessage;
			historyItems = [];
			historyTotal = 0;
			trashItems = [];
			trashTotal = 0;
			historyManager.clear();
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
			applyUserTheme(data.user);
			applyUserModelSettings(data.user);
			loginStatus = null;
			historyItems = [];
			historyTotal = 0;
			trashItems = [];
			trashTotal = 0;
			historyManager.clear();
			loginPassword = '';
			await Promise.all([loadAvailableModels(), loadUserSettings(), loadSettingsStatus(), loadBatchPromptHistory(), loadDemoSettings(), loadPluginStorage(), loadPluginVocabulary(), loadExportTemplates()]);
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
		profileOpen = false;
		authToken = null;
		currentUser = null;
		applyUserTheme(null);
		batchPromptHistory = [];
		demoSettings = { ...DEFAULT_DEMO_SETTINGS };
		demoSettingsLoaded = false;
		exportTemplates = DEFAULT_EXPORT_TEMPLATES.map((item) => ({ ...item }));
		exportTemplateStatus = null;
		canvasAspectEnabled = true;
		canvasAspectId = DEFAULT_CANVAS_ASPECT_ID;
		loginStatus = null;
		settingsStatus = null;
		settingsStatusError = t().loginRequiredMessage;
		users = [];
		groups = [];
		historyItems = [];
		historyTotal = 0;
		trashItems = [];
		trashTotal = 0;
		historyManager.clear();
	}

	function openProfile() {
		if (!currentUser) return;
		profileEmail = currentUser.email;
		profileCurrentPassword = '';
		profileNewPassword = '';
		profileStatus = null;
		profileOpen = true;
		userMenuOpen = false;
	}

	function closeProfile() {
		if (profileSaving) return;
		profileOpen = false;
		profileCurrentPassword = '';
		profileNewPassword = '';
	}

	async function saveProfile() {
		if (!currentUser) return;
		const email = profileEmail.trim();
		if (!email) {
			profileStatus = t().userValidationUpdate;
			return;
		}
		if (profileNewPassword && profileNewPassword.length < 8) {
			profileStatus = t().userPasswordTooShort;
			return;
		}
		if (profileNewPassword && !profileCurrentPassword) {
			profileStatus = t().profileCurrentPasswordRequired;
			return;
		}
		profileSaving = true;
		profileStatus = null;
		try {
			const body: { email: string; password?: string; current_password?: string } = { email };
			if (profileNewPassword) {
				body.password = profileNewPassword;
				body.current_password = profileCurrentPassword;
			}
			const r = await apiFetch('/api/auth/me/profile', {
				method: 'PATCH',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify(body),
			});
			if (!r.ok) {
				const d = await r.json().catch(() => ({})) as { detail?: string };
				throw new Error(d.detail ?? `HTTP ${r.status}`);
			}
			currentUser = await r.json() as UserItem;
			applyUserTheme(currentUser);
			profileEmail = currentUser.email;
			profileCurrentPassword = '';
			profileNewPassword = '';
			profileStatus = t().profileSavedMessage;
			await loadUserSettings();
		} catch (e) {
			profileStatus = e instanceof Error ? e.message : String(e);
		} finally {
			profileSaving = false;
		}
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

	function setEditGroup(group: UserGroup) {
		editGroupId = group.id;
		editGroupName = group.name;
	}

	function clearEditGroup() {
		editGroupId = null;
		editGroupName = '';
	}

	async function saveGroupEdit() {
		const id = editGroupId;
		const name = editGroupName.trim();
		if (!id || !name) return;
		try {
			const r = await apiFetch(`/api/user-groups/${id}`, {
				method: 'PATCH',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ name })
			});
			if (!r.ok) {
				const d = await r.json().catch(() => ({})) as { detail?: string };
				throw new Error(d.detail ?? `HTTP ${r.status}`);
			}
			clearEditGroup();
			await loadUserSettings();
		} catch (e) {
			userSettingsStatus = e instanceof Error ? e.message : String(e);
		}
	}

	function persistMiscSettings() {
		try {
			localStorage.setItem(SHOW_KIWI_KEY, showKiwi ? '1' : '0');
			localStorage.setItem(SHOW_CRAB_KEY, showCrab ? '1' : '0');
			localStorage.setItem(PNG_ALPHA_KEY, pngAlphaWhite ? '1' : '0');
			localStorage.setItem(SAVE_REPLAY_KEY, saveReplayAsNewVersion ? '1' : '0');
			localStorage.setItem(HISTORY_SELECTION_CANVAS_KEY, historySelectionCanvas);
			localStorage.setItem(HISTORY_SELECTION_CATALOG_KEY, historySelectionCatalog);
		} catch {}
	}

	function normalizeHistorySelectionBehavior(value: string | null): HistorySelectionBehavior {
		return value === 'history' ? 'history' : 'current';
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
	let visionProvider  = $state<Provider>(DEFAULT_PROVIDER);
	let visionModel     = $state<string>(DEFAULT_VISION_MODEL);
	let okugakiModel    = $state<string>(qualifiedModelId(DEFAULT_PROVIDER, DEFAULT_VISION_MODEL));
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
	$effect(() => {
		const historyId = displayedHistoryItem?.id ?? result?.history_id ?? null;
		void loadNearbyHistory(historyId);
	});
	let historySelectionSyncRequest = 0;
	const visibleThumbCount = $derived(Math.max(1, Math.floor((windowWidth - 40) / 89)));
	const historyWindowSize = $derived(visibleThumbCount);
	const historyPage = $derived(Math.floor(historyOffset / historyWindowSize));
	const historyTotalPages = $derived(Math.max(1, Math.ceil(historyTotal / historyWindowSize)));
	let historyStarredOnly = $state(false);
	let trashItems = $state<Iteration[]>([]);
	let trashTotal = $state(0);
	let externalHistoryRefreshInFlight = false;
	let lastExternalHistoryRefreshAt = 0;
	const historyManager = new HistoryManagerState(apiFetch, (items, total) => {
		trashItems = items;
		trashTotal = total;
	});
	let confirmAction = $state<{ message: string; run: () => void; destructive?: boolean; runLabel?: string; secondaryLabel?: string; secondaryRun?: () => void; hideCancel?: boolean } | null>(null);

	let promptsData = $state<{ stage1_system: string; stage2_system: string } | null>(null);

	// ── Batch derived ────────────────────────────────────────
	const batchLines    = $derived(batchInput.split('\n'));
	const lineNumbersText = $derived(batchLines.map((_, i) => String(i + 1)).join('\n'));
	const batchNonEmpty = $derived(batchLines.filter((l) => l.trim()).length);
	const batchRunning = $derived(activeRunMode === 'batch' && loading);
	const singleRunning = $derived((activeRunMode === 'single' && loading) || reloading);
	const demoRunning = $derived(activeRunMode === 'demo' && loading);
	const demoCanSaveCurrent = $derived(!!result && !!demoGeneratedPrompt && !!demoGeneratedDdl && !demoCurrentSaved);
	const ddlEditedAfterGeneration = $derived(inputMode === 'single' && ddl !== null && ddlGeneratedBaseline !== null && ddl !== ddlGeneratedBaseline);
	const canSubmit     = $derived(
		inputMode === 'single' ? !!input.trim() : inputMode === 'batch' ? batchNonEmpty > 0 : false
	);
	const currentInstructionText = $derived.by(() => {
		if (displayedHistoryItem?.input) return displayedHistoryItem.input;
		if (inputMode === 'demo' || activeRunMode === 'demo') return demoGeneratedPrompt;
		if (inputMode === 'batch' || activeRunMode === 'batch') return batchLatestPrompt;
		return input;
	});

	// Standalone DDL-authored artworks have no instruction; gate instruction-only refine paths.
	const statusDdlOrigin = $derived((displayedHistoryItem?.display_label ?? null) === DDL_ORIGIN_LABEL);

	// ── Timer ───────────────────────────────────────────────
	function startTimer() {
		_timerStart = Date.now();
		liveMs = 0;
		_timerHandle = setInterval(() => {
			const now = Date.now();
			liveMs = now - _timerStart;
			if (demoCurrentStartedAt !== null) {
				demoCurrentLiveMs = now - demoCurrentStartedAt;
			}
		}, 100);
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
	type PaintOptions = {
		historyInput?: string;
		saveHistory?: boolean;
		saveArtifacts?: boolean;
		countGeneration?: boolean;
		catalogId?: string;
		randomColorCatalog?: boolean;
		canvasAspectId?: CanvasAspectId;
		renderSeed?: number;
		varySeed?: number;
		interpretationSeed?: string;
		seedText?: string;
		signal?: AbortSignal;
		sourceText?: string;
		displayLabel?: string;
		batchLineNumber?: number;
		batchRunId?: string;
		historyVisibility?: 'normal' | 'lineage_only';
		lineageParentNodeId?: string | null;
		derivationKind?: DerivationKind | null;
		derivationMetadata?: Record<string, unknown>;
	};

async function requestVisionRefineAdvice(historyId: string, model: string, instruction: string, direction: string, enabledKinds: string[], signal: AbortSignal) {
	const r = await apiFetch('/api/refine/vision-advice', {
		method: 'POST',
		signal,
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify({ history_id: historyId, model, instruction, direction, enabled_kinds: enabledKinds, language: getLang() })
	});
	if (!r.ok) {
		const data = await r.json().catch(() => ({})) as { detail?: string };
		throw new Error(data.detail ?? `HTTP ${r.status}`);
	}
	return await r.json() as { observation: string; next_direction: string; suggested_kind: string; model: string };
}

	async function paintOne(text: string, options: PaintOptions = {}): Promise<{ ddl: string; thinking: string | null } & PaintResult> {
		const uiLang = getLang();
		stageLabel = t().stageInterpreting;
		const historyInput = options.historyInput ?? text;
		const resolvedStage1Model = qualifiedModelId(stage1Provider, stage1Model);
		const resolvedStage2Model = qualifiedModelId(stage2Provider, stage2Model);

		const augmented = text + buildEmotionHint(text);
		stage1UserPrompt = augmented;
		const r = await apiFetch('/api/paint', {
			method: 'POST',
			signal: options.signal,
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({
				text: augmented,
				original_text: text,
				stage1_model: resolvedStage1Model,
				stage2_model: resolvedStage2Model,
				include_thinking: includeThinking,
				instruction_lang: instructionLang,
				ui_lang: uiLang,
				canvas_aspect: options.canvasAspectId ?? effectiveCanvasAspectId(),
				render_seed: options.renderSeed,
				vary_seed: options.varySeed,
				interpretation_seed: options.interpretationSeed,
				seed_text: options.seedText,
				auto_repair: ddlAutoRepairEnabled,
				save_history: options.saveHistory ?? true,
				save_artifacts: options.saveArtifacts ?? true,
				count_generation: options.countGeneration ?? true,
				history_input: historyInput,
				history_source_text: options.sourceText ?? text,
				history_display_label: options.displayLabel ?? null,
				batch_line_number: options.batchLineNumber ?? null,
				batch_run_id: options.batchRunId ?? null,
				history_visibility: options.historyVisibility ?? 'normal',
				lineage_parent_node_id: options.lineageParentNodeId ?? null,
				derivation_kind: options.derivationKind ?? null,
				derivation_metadata: options.derivationMetadata ?? {},
				catalog_id: options.catalogId ?? selectedCatalog,
				random_color_catalog: options.randomColorCatalog ?? false
			})
		});
		if (!r.ok) {
			const d = await r.json().catch(() => ({})) as { detail?: string };
			throw new Error(d.detail ?? `HTTP ${r.status}`);
		}
		stageLabel = t().stageStructuring('');
		const data = await r.json() as { ddl: string; thinking: string | null } & PaintResult;
		await loadNearbyHistory(data.history_id);
const unreadWords = interpretationFeedback(text, data.ddl)
	.filter((part) => part.tone === 'weak')
	.flatMap((part) => part.text.match(/[一-龯々ぁ-んァ-ヶー]{2,}|[A-Za-z][A-Za-z'-]+/g) ?? []);
if (unreadWords.length > 0) {
	void apiFetch('/api/feedback/unread-words', {
		method: 'POST', headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify({ words: unreadWords, context: text })
	}).catch(() => undefined);
}
		if ((options.saveHistory ?? true) && data.lineage_node_id) lineageDetached = false;
		if (currentUser && typeof data.user_generation_count === 'number') {
			currentUser = { ...currentUser, image_generation_count: data.user_generation_count };
		}
		return data;
	}

	type InterpretResult = {
		ddl: string;
		thinking: string | null;
		tokens_in: number | null;
		tokens_out: number | null;
	};

	async function interpretOne(text: string, signal?: AbortSignal, modelOverride?: string, langOverride?: InstructionLang): Promise<InterpretResult> {
		const uiLang = getLang();
		const augmented = text + buildEmotionHint(text);
		stage1UserPrompt = augmented;
		const resolvedStage1Model = modelOverride ?? qualifiedModelId(stage1Provider, stage1Model);
		const r = await apiFetch('/api/interpret', {
			method: 'POST',
			signal,
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({
				text: augmented,
				original_text: text,
				model: resolvedStage1Model,
				include_thinking: includeThinking,
				instruction_lang: langOverride ?? instructionLang,
				ui_lang: uiLang,
				expand_intermediate: true,
			})
		});
		if (!r.ok) {
			const d = await r.json().catch(() => ({})) as { detail?: string };
			throw new Error(d.detail ?? `HTTP ${r.status}`);
		}
		const data = await r.json() as {
			ddl: string;
			thinking: string | null;
			tokens_in?: number | null;
			tokens_out?: number | null;
		};
		return {
			ddl: data.ddl,
			thinking: data.thinking,
			tokens_in: data.tokens_in ?? null,
			tokens_out: data.tokens_out ?? null,
		};
	}

	async function composeOne(currentDdl: string, originalText: string, signal?: AbortSignal, modelOverride?: string, langOverride?: InstructionLang, renderOptions: { catalogId?: string; canvasAspectId?: CanvasAspectId } = {}): Promise<{
		score: Score;
		svg: string;
		stage2_model?: string | null;
		render_build_number?: string | null;
		render_color_profile?: Record<string, string> | null;
		render_engine_id?: string | null;
		render_engine_version?: string | null;
		render_hash?: string | null;
		render_hash_short?: string | null;
		render_color_catalog_id?: string | null;
		render_color_catalog_name?: string | null;
		render_color_catalog_sub?: string | null;
		render_color_map?: Record<string, string> | null;
		render_canvas_aspect?: string | null;
		render_canvas_aspect_id?: string | null;
		render_canvas_aspect_ratio?: number | null;
		render_seed?: number | null;
		vary_seed?: number | null;
		instruction_lang_requested?: string | null;
		instruction_lang_resolved?: string | null;
		ui_lang?: string | null;
		elapsed_ms: number;
		tokens_in: number | null;
		tokens_out: number | null;
	}> {
		const uiLang = getLang();
		const resolvedStage2Model = modelOverride ?? qualifiedModelId(stage2Provider, stage2Model);
		const r = await apiFetch('/api/compose', {
			method: 'POST',
			signal,
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({
				ddl: currentDdl,
				model: resolvedStage2Model,
				original_text: originalText,
				instruction_lang: langOverride ?? instructionLang,
				ui_lang: uiLang,
				catalog_id: renderOptions.catalogId ?? selectedCatalog,
				canvas_aspect: renderOptions.canvasAspectId ?? effectiveCanvasAspectId(),
				auto_repair: ddlAutoRepairEnabled,
			})
		});
		if (!r.ok) {
			const d = await r.json().catch(() => ({})) as { detail?: string };
			throw new Error(d.detail ?? `HTTP ${r.status}`);
		}
		const data = await r.json() as {
			score: Score;
			svg: string;
			stage2_model?: string | null;
			render_build_number?: string | null;
			render_color_profile?: Record<string, string> | null;
			render_engine_id?: string | null;
			render_engine_version?: string | null;
			render_hash?: string | null;
			render_hash_short?: string | null;
			render_color_catalog_id?: string | null;
			render_color_catalog_name?: string | null;
			render_color_catalog_sub?: string | null;
			render_color_map?: Record<string, string> | null;
			render_canvas_aspect?: string | null;
			render_canvas_aspect_id?: string | null;
			render_canvas_aspect_ratio?: number | null;
			render_seed?: number | null;
			vary_seed?: number | null;
			elapsed_ms: number;
			tokens_in: number | null;
			tokens_out: number | null;
		};
		return data;
	}

	async function refreshHistoryAfterServerSave() {
		await fetchHistoryOffset(0);
		historyCursor = 0;
	}

	function sleep(ms: number): Promise<void> {
		return new Promise((resolve) => setTimeout(resolve, ms));
	}

	function randomColorCatalogId(excludeId?: string): string {
		const ids = colorCatalogs.map((catalog) => catalog.id).filter((id): id is string => !!id);
		if (ids.length === 0) return selectedCatalog;
		const candidates = ids.length > 1 && excludeId ? ids.filter((id) => id !== excludeId) : ids;
		return candidates[Math.floor(Math.random() * candidates.length)] ?? selectedCatalog;
	}

	async function generateDemoInstruction(settings: DemoSettings): Promise<string> {
		const model = qualifiedModelId(providerOfModel(settings.prompt_model), settings.prompt_model);
		const r = await apiFetch('/api/demo/instruction', {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({
				seed_phrase: settings.seed_phrase,
				model,
				instruction_lang: instructionLang,
				ui_lang: getLang(),
			})
		});
		if (!r.ok) {
			const d = await r.json().catch(() => ({})) as { detail?: string };
			throw new Error(d.detail ?? `HTTP ${r.status}`);
		}
		const data = await r.json() as { instruction: string };
		return data.instruction;
	}

	async function runDemoLoop(runId: number) {
		while (demoRunId === runId && loading) {
			const startedAt = Date.now();
			demoCurrentStartedAt = startedAt;
			demoCurrentLiveMs = 0;
			demoCurrentElapsedMs = null;
			demoCurrentTokensIn = null;
			demoCurrentTokensOut = null;
			demoWaitingSeconds = null;
			try {
				const settings = normalizeDemoSettings(demoSettings);
				await saveDemoSettings(settings);
				demoGeneratedPrompt = await generateDemoInstruction(settings);
				if (demoRunId !== runId || !loading) break;
				const demoCatalogId = selectedCatalog;
				const r = await paintOne(demoGeneratedPrompt, {
					saveHistory: settings.save_db,
					saveArtifacts: settings.save_files,
					countGeneration: false,
					historyInput: `[demo] ${demoGeneratedPrompt}`,
					sourceText: demoGeneratedPrompt,
					displayLabel: '[demo]',
					catalogId: demoCatalogId,
					randomColorCatalog: settings.random_color_catalog,
				});
				if (demoRunId !== runId || !loading) break;
				demoGeneratedDdl = r.ddl;
				if (settings.random_color_catalog && r.render_color_catalog_id) selectedCatalog = r.render_color_catalog_id;
				demoCurrentSaved = !!r.history_id;
				demoSaveStatus = null;
				ddl = r.ddl; ddlGeneratedBaseline = r.ddl; ddlSelection = { start: r.ddl.length, end: r.ddl.length }; thinking = r.thinking; result = r; outputTab = 'canvas';
				fitCanvasZoom();
				elapsedStage1Ms = r.elapsed_stage1_ms; elapsedStage2Ms = r.elapsed_stage2_ms; elapsedTotalMs = r.elapsed_total_ms;
				tokensInStage1 = r.tokens_in_stage1; tokensOutStage1 = r.tokens_out_stage1;
				tokensInStage2 = r.tokens_in_stage2; tokensOutStage2 = r.tokens_out_stage2;
				const currentTokensIn = (r.tokens_in_stage1 ?? 0) + (r.tokens_in_stage2 ?? 0);
				const currentTokensOut = (r.tokens_out_stage1 ?? 0) + (r.tokens_out_stage2 ?? 0);
				demoCurrentElapsedMs = r.elapsed_total_ms;
				demoCurrentLiveMs = r.elapsed_total_ms;
				demoCurrentStartedAt = null;
				demoCurrentTokensIn = currentTokensIn;
				demoCurrentTokensOut = currentTokensOut;
				demoTotalElapsedMs += r.elapsed_total_ms;
				demoTotalTokensIn += currentTokensIn;
				demoTotalTokensOut += currentTokensOut;
				demoRenderCount += 1;
				if (settings.save_db) await refreshHistoryAfterServerSave();
				const remainingMs = Math.max(0, settings.interval_seconds * 1000 - (Date.now() - startedAt));
				for (let left = Math.ceil(remainingMs / 1000); left > 0 && demoRunId === runId && loading; left--) {
					demoWaitingSeconds = left;
					await sleep(Math.min(1000, remainingMs));
				}
			} catch (e) {
				demoCurrentStartedAt = null;
				demoError = e instanceof Error ? e.message : String(e);
				await sleep(1000);
			}
		}
		if (demoRunId === runId) {
			demoCurrentStartedAt = null;
			stopTimer();
			loading = false;
			activeRunMode = null;
			stageLabel = '';
			demoWaitingSeconds = null;
		}
	}

	async function startDemo() {
		if (loading || variationGridBusy) return;
		clearInput();
		demoError = null;
		demoSaveStatus = null;
		demoCurrentSaved = false;
		error = null;
		demoGeneratedDdl = null;
		demoCurrentStartedAt = null;
		demoCurrentLiveMs = null;
		demoCurrentElapsedMs = null;
		demoCurrentTokensIn = null;
		demoCurrentTokensOut = null;
		demoTotalElapsedMs = 0;
		demoTotalTokensIn = 0;
		demoTotalTokensOut = 0;
		demoRenderCount = 0;
		displayedHistoryItem = null;
		activeRunMode = 'demo';
		loading = true;
		demoRunId += 1;
		startTimer();
		await runDemoLoop(demoRunId);
	}

	function stopDemo() {
		demoRunId += 1;
		demoCurrentStartedAt = null;
		loading = false;
		activeRunMode = null;
		stageLabel = '';
		demoWaitingSeconds = null;
		stopTimer();
	}

	// ── Submit ──────────────────────────────────────────────
	function requestSubmit() {
		if (inputMode === 'single' && ddlEditedAfterGeneration && !loading && !reloading) {
			confirmAction = {
				message: t().confirmDdlOverwriteMessage,
				runLabel: t().confirmOk,
				hideCancel: false,
				run: () => { void submit(); },
				secondaryLabel: t().ddlPaintButton,
				secondaryRun: () => { void replay(); },
			};
			return;
		}
		void submit();
	}

	async function submit() {
		if (!canSubmit || loading || variationGridBusy) return;
		resetTargetScopedState();
		try {
			await ensureVisibleLineageParentId();
		} catch (cause) {
			error = cause instanceof Error ? cause.message : String(cause);
			return;
		}
		const submittedMode = inputMode;
		const abortController = new AbortController();
		submitAbortController = abortController;
		submitStopRequested = false;
		const canvasAspectDerivation = submittedMode === 'single' ? pendingCanvasAspectDerivation : null;
		const submitParentNodeId = canvasAspectDerivation?.parentNodeId ?? (lineageDetached ? null : (displayedHistoryItem?.lineage_node_id ?? result?.lineage_node_id ?? null));
		const submitSource = displayedHistoryItem?.source_text ?? displayedHistoryItem?.input ?? input;
		const submitDerivationKind: DerivationKind | null = canvasAspectDerivation
			? 'canvas_aspect_change'
			: submitParentNodeId ? (input.trim() === submitSource.trim() ? 'replay' : 'description_edit') : null;
		const submitDerivationMetadata = canvasAspectDerivation
			? { from_canvas_aspect: canvasAspectDerivation.fromAspectId, to_canvas_aspect: canvasAspectDerivation.toAspectId }
			: {};
		loading = true; error = null;
		activeRunMode = submittedMode;
		ddl = null; ddlGeneratedBaseline = null; thinking = null; ddlSelection = { start: 0, end: 0 };
		displayedHistoryItem = null;
		historyCursor = -1;
		elapsedStage1Ms = 0; elapsedStage2Ms = 0; elapsedTotalMs = 0;
		tokensInStage1 = null; tokensOutStage1 = null; tokensInStage2 = null; tokensOutStage2 = null;
		batchCurrent = 0; batchActiveLine = null; batchActiveDdl = null;
		batchActiveTokensIn = null; batchActiveTokensOut = null; batchTokensInTotal = 0; batchTokensOutTotal = 0;
		if (submittedMode === 'batch') {
			batchLatestResult = null;
			batchLatestDdl = null;
			batchLatestThinking = null;
			batchLatestPrompt = '';
			batchAutoFollowLatest = true;
		}
		startTimer();

		try {
			if (submittedMode === 'single') {
				stageLabel = t().stageDdlGenerating;
				const stage1StartedAt = Date.now();
				const interpreted = await interpretOne(input, abortController.signal);
				if (submitStopRequested) return;
				elapsedStage1Ms = Date.now() - stage1StartedAt;
				tokensInStage1 = interpreted.tokens_in;
				tokensOutStage1 = interpreted.tokens_out;
				ddl = interpreted.ddl;
				ddlGeneratedBaseline = interpreted.ddl;
				ddlSelection = { start: interpreted.ddl.length, end: interpreted.ddl.length };
				thinking = interpreted.thinking;
				stageLabel = t().stageImageGenerating;
				reloading = true;
				const composed = await composeOne(interpreted.ddl, input, abortController.signal);
				if (submitStopRequested) return;
				reloading = false;
				elapsedStage2Ms = composed.elapsed_ms;
				elapsedTotalMs = Date.now() - _timerStart;
				tokensInStage2 = composed.tokens_in;
				tokensOutStage2 = composed.tokens_out;
				const resolvedStage1Model = qualifiedModelId(stage1Provider, stage1Model);
				const resolvedStage2Model = composed.stage2_model ?? qualifiedModelId(stage2Provider, stage2Model);
				const r: PaintResult = {
					score: composed.score,
					svg: composed.svg,
					stage1_model: resolvedStage1Model,
					stage2_model: resolvedStage2Model,
					render_build_number: composed.render_build_number,
					render_color_profile: composed.render_color_profile,
					render_engine_id: composed.render_engine_id,
					render_engine_version: composed.render_engine_version,
					render_color_catalog_id: composed.render_color_catalog_id,
					render_color_catalog_name: composed.render_color_catalog_name,
					render_color_catalog_sub: composed.render_color_catalog_sub,
					render_color_map: composed.render_color_map,
					render_canvas_aspect: composed.render_canvas_aspect,
					render_canvas_aspect_id: composed.render_canvas_aspect_id,
					render_canvas_aspect_ratio: composed.render_canvas_aspect_ratio,
					render_seed: composed.render_seed,
					vary_seed: composed.vary_seed,
					instruction_lang_requested: composed.instruction_lang_requested,
					instruction_lang_resolved: composed.instruction_lang_resolved,
					ui_lang: composed.ui_lang,
					render_hash: composed.render_hash,
					render_hash_short: composed.render_hash_short,
					elapsed_stage1_ms: elapsedStage1Ms,
					elapsed_stage2_ms: elapsedStage2Ms,
					elapsed_total_ms: elapsedTotalMs,
					tokens_in_stage1: tokensInStage1,
					tokens_out_stage1: tokensOutStage1,
					tokens_in_stage2: tokensInStage2,
					tokens_out_stage2: tokensOutStage2,
				};
				result = r; outputTab = 'canvas';
				fitCanvasZoom();
				const savedHistory = await pushHistory({
					input,
					ddl: interpreted.ddl,
					score: composed.score,
					svg: composed.svg,
					at: Date.now(),
					elapsed_ms: elapsedTotalMs,
					stage1_model: resolvedStage1Model,
					stage2_model: resolvedStage2Model,
					tokens_in: (tokensInStage1 ?? 0) + (tokensInStage2 ?? 0) || null,
					tokens_out: (tokensOutStage1 ?? 0) + (tokensOutStage2 ?? 0) || null,
					catalog_id: selectedCatalog,
				}, { selectSaved: true, countGeneration: true, sourceText: input, lineageParentNodeId: submitParentNodeId, derivationKind: submitDerivationKind, derivationMetadata: submitDerivationMetadata });
				if (savedHistory && submitAbortController === abortController && !submitStopRequested) {
					if (canvasAspectDerivation) pendingCanvasAspectDerivation = null;
					lineageDetached = false;
					displayedHistoryItem = savedHistory;
					result = {
						...r,
						history_id: savedHistory.id,
						history_at: savedHistory.at,
						render_hash: savedHistory.render_hash,
						render_hash_short: savedHistory.render_hash_short,
						description_hash: savedHistory.description_hash,
						lineage_node_id: savedHistory.lineage_node_id,
					};
					await loadNearbyHistory(savedHistory.id);
				}
			} else {
				batchTotal = 0; batchSuccess = 0; batchFailures = []; setBatchFailureReport(null);
				batchActiveTokensIn = null; batchActiveTokensOut = null; batchTokensInTotal = 0; batchTokensOutTotal = 0;
				const batchCanvasAspectId = effectiveCanvasAspectId();
				const batchCatalogId = selectedCatalog;
				const batchRunId = typeof crypto?.randomUUID === 'function' ? crypto.randomUUID() : `${Date.now()}`;
				const lines = batchLines
					.map((line, index) => ({ line: index + 1, input: line.trim() }))
					.filter((item) => item.input);
				batchTotal = lines.length; outputTab = 'canvas';
				for (let i = 0; i < lines.length; i++) {
					if (submitStopRequested) break;
					batchCurrent = i + 1;
					batchActiveLine = lines[i].line;
					batchActiveTokensIn = null;
					batchActiveTokensOut = null;
					try {
						const r = await paintOne(lines[i].input, {
							historyInput: `#${lines[i].line} ${lines[i].input}`,
							sourceText: lines[i].input,
							displayLabel: `#${lines[i].line}`,
							batchLineNumber: lines[i].line,
							batchRunId,
							catalogId: batchRandomColorCatalog ? randomColorCatalogId() : batchCatalogId,
							canvasAspectId: batchCanvasAspectId,
							signal: abortController.signal,
						});
						if (submitStopRequested) break;
						batchActiveDdl = r.ddl;
						batchActiveTokensIn = (r.tokens_in_stage1 ?? 0) + (r.tokens_in_stage2 ?? 0) || null;
						batchActiveTokensOut = (r.tokens_out_stage1 ?? 0) + (r.tokens_out_stage2 ?? 0) || null;
						batchTokensInTotal += batchActiveTokensIn ?? 0;
						batchTokensOutTotal += batchActiveTokensOut ?? 0;
						thinking = r.thinking;
						batchLatestResult = r;
						batchLatestDdl = r.ddl;
						batchLatestThinking = r.thinking;
						batchLatestPrompt = `#${lines[i].line} ${lines[i].input}`;
						if (inputMode === 'batch' && batchAutoFollowLatest) {
							displayLatestBatchRender();
						}
						await refreshHistoryAfterServerSave();
						batchSuccess += 1;
						if (batchFailures.length > 0) {
							setBatchFailureReport({ success: batchSuccess, total: batchTotal, failures: batchFailures });
						}
					} catch (e) {
						if (submitStopRequested || abortController.signal.aborted) break;
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
			if (!(submitStopRequested || abortController.signal.aborted)) {
				error = e instanceof Error ? e.message : String(e); result = null;
			}
		} finally {
			if (submitAbortController === abortController) submitAbortController = null;
			submitStopRequested = false;
			stopTimer(); loading = false; reloading = false; activeRunMode = null; stageLabel = ''; batchCurrent = 0; batchActiveLine = null; batchActiveDdl = null; batchActiveTokensIn = null; batchActiveTokensOut = null;
		}
	}

	function stopBatch() {
		if (activeRunMode !== 'single' && activeRunMode !== 'batch') return;
		submitStopRequested = true;
		submitAbortController?.abort();
	}

	function stopReplay() {
		if (!reloading) return;
		replayStopRequested = true;
		replayAbortController?.abort();
	}

	function stopDdlRender() {
		if (replayAbortController) {
			stopReplay();
			return;
		}
		stopBatch();
	}

	// ── Replay (Stage 2 のみ) ────────────────────────────────
	async function replay() {
		if (!ddl || reloading) return;
		resetTargetScopedState();
		try {
			await ensureVisibleLineageParentId();
		} catch (cause) {
			reloadError = cause instanceof Error ? cause.message : String(cause);
			return;
		}
		const canvasAspectDerivation = pendingCanvasAspectDerivation;
		const replayParentNodeId = canvasAspectDerivation?.parentNodeId ?? (lineageDetached ? null : (displayedHistoryItem?.lineage_node_id ?? result?.lineage_node_id ?? null));
		const replayKind: DerivationKind | null = canvasAspectDerivation
			? 'canvas_aspect_change'
			: replayParentNodeId ? (ddlGeneratedBaseline !== null && ddl !== ddlGeneratedBaseline ? 'ddl_edit' : 'replay') : null;
		const replayDerivationMetadata = canvasAspectDerivation
			? { from_canvas_aspect: canvasAspectDerivation.fromAspectId, to_canvas_aspect: canvasAspectDerivation.toAspectId }
			: {};
		const abortController = new AbortController();
		replayAbortController = abortController;
		replayStopRequested = false;
		reloading = true; reloadError = null;
		displayedHistoryItem = null;
		historyCursor = -1;
		const uiLang = getLang();
		const replayInput = input;
		const startedAt = Date.now();
		elapsedStage1Ms = 0; elapsedStage2Ms = 0; elapsedTotalMs = 0;
		tokensInStage1 = null; tokensOutStage1 = null; tokensInStage2 = null; tokensOutStage2 = null;
		stageLabel = t().stageStructuring('');
		startTimer();
		try {
			const resolvedStage2Model = qualifiedModelId(stage2Provider, stage2Model);
			const r = await apiFetch('/api/compose', {
				method: 'POST',
				signal: abortController.signal,
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({
					ddl,
					model: resolvedStage2Model,
					original_text: replayInput,
					instruction_lang: instructionLang,
					ui_lang: uiLang,
					catalog_id: selectedCatalog,
					canvas_aspect: effectiveCanvasAspectId(),
					auto_repair: ddlAutoRepairEnabled
				})
			});
			if (!r.ok) {
				const d = await r.json().catch(() => ({})) as { detail?: string };
				throw new Error(d.detail ?? `HTTP ${r.status}`);
			}
			const d = await r.json() as {
				score: Score;
				svg: string;
				stage2_model?: string | null;
				render_build_number?: string | null;
				render_color_profile?: Record<string, string> | null;
				render_engine_id?: string | null;
				render_engine_version?: string | null;
				render_color_catalog_id?: string | null;
				render_color_catalog_name?: string | null;
				render_color_catalog_sub?: string | null;
				render_color_map?: Record<string, string> | null;
				render_canvas_aspect?: string | null;
				render_canvas_aspect_id?: string | null;
				render_canvas_aspect_ratio?: number | null;
				render_seed?: number | null;
				vary_seed?: number | null;
				instruction_lang_requested?: string | null;
				instruction_lang_resolved?: string | null;
				ui_lang?: string | null;
				render_hash?: string | null;
				render_hash_short?: string | null;
				tokens_in: number | null;
				tokens_out: number | null;
			};
			const elapsedMs = Date.now() - startedAt;
			const resolvedStage1Model = result?.stage1_model ?? qualifiedModelId(stage1Provider, stage1Model);
			const savedStage2Model = d.stage2_model ?? resolvedStage2Model;
			const replayMetadata = {
				render_build_number: d.render_build_number,
				render_color_profile: d.render_color_profile,
				render_engine_id: d.render_engine_id,
				render_engine_version: d.render_engine_version,
				render_color_catalog_id: d.render_color_catalog_id,
				render_color_catalog_name: d.render_color_catalog_name,
				render_color_catalog_sub: d.render_color_catalog_sub,
				render_color_map: d.render_color_map,
				render_canvas_aspect: d.render_canvas_aspect,
				render_canvas_aspect_id: d.render_canvas_aspect_id,
				render_canvas_aspect_ratio: d.render_canvas_aspect_ratio,
				render_seed: d.render_seed,
				vary_seed: d.vary_seed,
				instruction_lang_requested: d.instruction_lang_requested,
				instruction_lang_resolved: d.instruction_lang_resolved,
				ui_lang: d.ui_lang,
				render_hash: d.render_hash,
				render_hash_short: d.render_hash_short
			};
			result = result
				? { ...result, score: d.score, svg: d.svg, stage2_model: savedStage2Model, ...replayMetadata }
				: { score: d.score, svg: d.svg, stage1_model: resolvedStage1Model, stage2_model: savedStage2Model, ...replayMetadata, elapsed_stage1_ms: 0, elapsed_stage2_ms: elapsedMs, elapsed_total_ms: elapsedMs, tokens_in_stage1: null, tokens_out_stage1: null, tokens_in_stage2: d.tokens_in, tokens_out_stage2: d.tokens_out };
			if (result) {
				result = { ...result, elapsed_stage2_ms: elapsedMs, elapsed_total_ms: elapsedMs, tokens_in_stage2: d.tokens_in, tokens_out_stage2: d.tokens_out };
			}
			elapsedStage1Ms = 0; elapsedStage2Ms = elapsedMs; elapsedTotalMs = elapsedMs;
			tokensInStage1 = null; tokensOutStage1 = null; tokensInStage2 = d.tokens_in; tokensOutStage2 = d.tokens_out;
			if (saveReplayAsNewVersion) {
				const savedHistory = await pushHistory({
					input: replayInput,
					ddl,
					score: d.score,
					svg: d.svg,
					at: Date.now(),
					elapsed_ms: elapsedMs,
					stage1_model: resolvedStage1Model,
					stage2_model: savedStage2Model,
					tokens_in: d.tokens_in,
					tokens_out: d.tokens_out,
					catalog_id: selectedCatalog !== 'default' ? selectedCatalog : null
				}, { selectSaved: true, sourceText: replayInput, lineageParentNodeId: replayParentNodeId, derivationKind: replayKind, derivationMetadata: replayDerivationMetadata });
				if (savedHistory && result) {
					if (canvasAspectDerivation) pendingCanvasAspectDerivation = null;
					lineageDetached = false;
					displayedHistoryItem = savedHistory;
					result = {
						...result,
						history_id: savedHistory.id,
						history_at: savedHistory.at,
						render_hash: savedHistory.render_hash,
						render_hash_short: savedHistory.render_hash_short,
					};
				}
			}
			outputTab = 'canvas';
			fitCanvasZoom();
		} catch (e) {
			if (!replayStopRequested && !abortController.signal.aborted) {
				reloadError = e instanceof Error ? e.message : String(e);
			}
		} finally {
			if (replayAbortController === abortController) replayAbortController = null;
			replayStopRequested = false;
			stopTimer();
			stageLabel = '';
			reloading = false;
		}
	}

	// ── History ─────────────────────────────────────────────
	function estimatedHistoryManagerPageSize(): number {
		const modalWidth = Math.max(320, windowWidth * 0.8);
		const modalHeight = Math.max(280, windowHeight * 0.8);
		const gridWidth = Math.max(1, modalWidth - 20);
		const gridHeight = Math.max(1, modalHeight - 94);
		const gap = 8;
		const minCardWidth = 104;
		const columns = Math.max(1, Math.floor((gridWidth + gap) / (minCardWidth + gap)));
		const cardWidth = Math.max(minCardWidth, (gridWidth - gap * (columns - 1)) / columns);
		const imageWidth = Math.max(1, cardWidth - 12);
		const cardHeight = imageWidth * 58 / 82 + 75;
		const rows = Math.max(1, Math.floor((gridHeight + gap) / (cardHeight + gap)));
		return Math.max(historyWindowSize, Math.min(100, columns * rows));
	}

	function preloadHistoryManagerFirstPage() {
		if (!authToken || historyManager.open || historyStarredOnly || historyOffset !== 0) return;
		historyManager.preloadFirstPage(
			historyItems,
			historyTotal,
			trashTotal,
			estimatedHistoryManagerPageSize()
		);
	}

	async function fetchHistoryOffset(offset: number, options: { preserveSelection?: boolean; anchorId?: string } = {}): Promise<boolean> {
		if (!authToken) {
			historyItems = [];
			historyTotal = 0;
			historyOffset = 0;
			return false;
		}
		const safeOffset = Math.max(0, offset);
		const selectedHistoryId = options.anchorId ?? (options.preserveSelection
			? historyItems[historyCursor]?.id ?? displayedHistoryItem?.id ?? result?.history_id ?? null
			: null);
		try {
			const listLimit = options.anchorId
				? historyWindowSize
				: safeOffset === 0 && !historyStarredOnly
					? estimatedHistoryManagerPageSize()
					: historyWindowSize;
			const params = new URLSearchParams({
				offset: String(safeOffset),
				limit: String(listLimit),
			});
			if (historyStarredOnly) params.set('starred', 'true');
			if (options.anchorId) params.set('anchor_id', options.anchorId);
			const r = await apiFetch(`/api/history?${params.toString()}`);
			if (!r.ok) return false;
			const data = await r.json();
			const resolvedOffset = Number.isFinite(data.offset) ? Number(data.offset) : safeOffset;
			if (data.items.length === 0 && data.total > 0 && resolvedOffset > 0 && !options.anchorId) {
				const lastOffset = Math.floor((data.total - 1) / historyWindowSize) * historyWindowSize;
				return await fetchHistoryOffset(lastOffset);
			}
			const stripItems = resolvedOffset === 0 && !historyStarredOnly
				? data.items.slice(0, historyWindowSize)
				: data.items;
			historyItems = stripItems; historyTotal = data.total; historyOffset = resolvedOffset;
			if (selectedHistoryId) {
				const selectedIndex = stripItems.findIndex((item: Iteration) => item.id === selectedHistoryId);
				if (selectedIndex >= 0) historyCursor = selectedIndex;
				else if (options.anchorId || options.preserveSelection) historyCursor = -1;
				else if (historyCursor >= stripItems.length) historyCursor = stripItems.length > 0 ? 0 : -1;
			} else {
				if (historyCursor >= stripItems.length) historyCursor = stripItems.length > 0 ? 0 : -1;
				if (historyCursor < 0 && stripItems.length > 0) historyCursor = 0;
			}
			if (!historyManager.open) {
				if (resolvedOffset === 0 && !historyStarredOnly) {
					historyManager.primeFirstPage(data.items, data.total, trashTotal, listLimit);
				} else {
					preloadHistoryManagerFirstPage();
				}
			}
			return options.anchorId ? historyCursor >= 0 && historyItems[historyCursor]?.id === options.anchorId : true;
		} catch {
			return false;
		}
	}

	async function syncHistoryStripToItem(item: Pick<Iteration, 'id' | 'trashed' | 'history_visibility'>): Promise<void> {
		const requestId = ++historySelectionSyncRequest;
		if (!item.id || item.trashed || item.history_visibility === 'lineage_only') {
			historyCursor = -1;
			return;
		}
		const localIndex = historyItems.findIndex((candidate) => candidate.id === item.id);
		if (localIndex >= 0) {
			historyCursor = localIndex;
			return;
		}
		historyCursor = -1;
		let found = await fetchHistoryOffset(0, { anchorId: item.id });
		if (requestId !== historySelectionSyncRequest) {
			if (displayedHistoryItem) void syncHistoryStripToItem(displayedHistoryItem);
			return;
		}
		if (!found && historyStarredOnly) {
			historyStarredOnly = false;
			found = await fetchHistoryOffset(0, { anchorId: item.id });
		}
		if (requestId !== historySelectionSyncRequest) {
			if (displayedHistoryItem) void syncHistoryStripToItem(displayedHistoryItem);
			return;
		}
		if (!found) historyCursor = -1;
	}

	async function refreshHistoryForExternalSave(force = false): Promise<void> {
		if (!authToken || historyManager.open || historyStarredOnly || historyOffset !== 0 || loading) return;
		if (document.visibilityState !== 'visible') return;
		const now = Date.now();
		if (!force && now - lastExternalHistoryRefreshAt < EXTERNAL_HISTORY_REFRESH_MIN_GAP_MS) return;
		if (externalHistoryRefreshInFlight) return;
		externalHistoryRefreshInFlight = true;
		lastExternalHistoryRefreshAt = now;
		try {
			const activeHistoryId = displayedHistoryItem?.id ?? result?.history_id ?? historyItems[historyCursor]?.id ?? null;
			if (activeHistoryId) await fetchHistoryOffset(0, { anchorId: activeHistoryId });
			else await fetchHistoryOffset(0, { preserveSelection: true });
			if (historyManager.open && historyManager.view === 'active' && historyManager.page === 0 && !historyManager.search.trim() && !historyManager.starredOnly) {
				await historyManager.fetch({ view: 'active', page: 0, search: '', starredOnly: false, silent: true });
			}
		} finally {
			externalHistoryRefreshInFlight = false;
		}
	}

	async function fetchHistoryPage(page: number): Promise<void> {
		await fetchHistoryOffset(page * historyWindowSize);
	}

	async function gotoHistoryNewerPage(): Promise<void> {
		await fetchHistoryPage(historyPage - 1);
		loadIteration(0);
	}

	async function gotoHistoryLatestPage(): Promise<void> {
		await fetchHistoryPage(0);
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

	type HistoryStarTarget = { id?: string; starred?: boolean; note?: string | null };

	function updateHistoryStarState(item: HistoryStarTarget) {
		if (!item.id) return;
		const hasNote = Object.prototype.hasOwnProperty.call(item, "note");
		historyItems = historyItems.map((it) => it.id === item.id ? { ...it, starred: item.starred, note: hasNote ? item.note : it.note } : it);
		historyManager.applyStarState(item);
		trashItems = trashItems.map((it) => it.id === item.id ? { ...it, starred: item.starred, note: hasNote ? item.note : it.note } : it);
		if (displayedHistoryItem?.id === item.id) displayedHistoryItem = { ...displayedHistoryItem, starred: item.starred, note: hasNote ? item.note : displayedHistoryItem.note };
	}

	async function toggleHistoryStar(item: HistoryStarTarget | null | undefined, event?: Event): Promise<void> {
		event?.stopPropagation();
		if (!item?.id) return;
		const nextStarred = !item.starred;
		updateHistoryStarState({ ...item, starred: nextStarred });
		try {
			const r = await apiFetch(`/api/history/${item.id}/star`, {
				method: 'PATCH',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ starred: nextStarred })
			});
			if (!r.ok) throw new Error(`HTTP ${r.status}`);
			const updated = await r.json() as Iteration;
			updateHistoryStarState(updated);
			const refreshes: Promise<unknown>[] = [];
			if (historyStarredOnly) {
				if (!updated.starred) historyStarredOnly = false;
				refreshes.push(fetchHistoryOffset(0, { anchorId: updated.id }));
			}
			if (historyManager.starredOnly) refreshes.push(historyManager.fetch());
			if (refreshes.length > 0) await Promise.all(refreshes);
		} catch (e) {
			updateHistoryStarState(item);
			console.warn('failed to update history star', e);
		}
	}

	async function refreshCurrentUserOnly(): Promise<void> {
		try {
			const r = await apiFetch('/api/auth/me', { cache: 'no-store' });
			if (!r.ok) return;
			currentUser = await r.json() as UserItem;
			applyUserTheme(currentUser);
		} catch {
			/* ignore */
		}
	}

	async function pushHistory(it: Iteration, options: { selectSaved?: boolean; countGeneration?: boolean; sourceText?: string; displayLabel?: string; batchLineNumber?: number; batchRunId?: string; historyVisibility?: 'normal' | 'lineage_only'; lineageParentNodeId?: string | null; derivationKind?: DerivationKind | null; derivationMetadata?: Record<string, unknown> } = {}): Promise<Iteration | null> {
		if (!authToken) return null;
		let saved: Iteration | null = null;
		try {
			const r = await apiFetch('/api/history', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ input: it.input, ddl: it.ddl, score: it.score, svg: it.svg ?? "", at: it.at, elapsed_ms: it.elapsed_ms ?? 0, stage1_model: it.stage1_model ?? null, stage2_model: it.stage2_model ?? null, tokens_in: it.tokens_in ?? null, tokens_out: it.tokens_out ?? null, catalog_id: it.catalog_id ?? selectedCatalog, render_build_number: it.render_build_number ?? null, render_color_profile: it.render_color_profile ?? null, render_engine_id: it.render_engine_id ?? null, render_engine_version: it.render_engine_version ?? null, render_color_catalog_id: it.render_color_catalog_id ?? null, render_color_catalog_name: it.render_color_catalog_name ?? null, render_color_catalog_sub: it.render_color_catalog_sub ?? null, render_color_map: it.render_color_map ?? null, render_canvas_aspect: it.render_canvas_aspect ?? it.render_canvas_aspect_id ?? effectiveCanvasAspectId(), render_canvas_aspect_id: it.render_canvas_aspect_id ?? it.render_canvas_aspect ?? effectiveCanvasAspectId(), render_canvas_aspect_ratio: it.render_canvas_aspect_ratio ?? null, render_seed: it.render_seed == null ? null : Number(it.render_seed), vary_seed: it.vary_seed == null ? null : Number(it.vary_seed), interpretation_seed: it.interpretation_seed ?? null, save_artifacts: true, count_generation: options.countGeneration ?? false, canvas_aspect: it.render_canvas_aspect_id ?? it.render_canvas_aspect ?? effectiveCanvasAspectId(), instruction_lang_requested: it.instruction_lang_requested ?? instructionLang, instruction_lang_resolved: it.instruction_lang_resolved ?? null, ui_lang: it.ui_lang ?? getLang(), source_text: options.sourceText ?? it.source_text ?? it.input, display_label: options.displayLabel ?? it.display_label ?? null, batch_line_number: options.batchLineNumber ?? it.batch_line_number ?? null, batch_run_id: options.batchRunId ?? it.batch_run_id ?? null, history_visibility: options.historyVisibility ?? 'normal', lineage_parent_node_id: options.lineageParentNodeId ?? null, derivation_kind: options.derivationKind ?? null, derivation_metadata: options.derivationMetadata ?? {} })
			});
			if (r.ok) saved = await r.json() as Iteration;
		} catch { /* ignore */ }
		if (options.countGeneration) await refreshCurrentUserOnly();
		if (options.selectSaved && saved?.id && options.historyVisibility !== 'lineage_only') {
			await fetchHistoryOffset(0, { anchorId: saved.id });
		} else {
			const activeHistoryId = displayedHistoryItem?.id ?? result?.history_id ?? historyItems[historyCursor]?.id ?? null;
			if (activeHistoryId) await fetchHistoryOffset(0, { anchorId: activeHistoryId });
			else {
				await fetchHistoryOffset(historyOffset, { preserveSelection: true });
				historyCursor = -1;
			}
		}
		return saved;
	}

	async function saveCurrentDemoToHistory(): Promise<void> {
		if (!result || !demoGeneratedPrompt || !demoGeneratedDdl || demoSavingCurrent || demoCurrentSaved) return;
		demoSavingCurrent = true;
		demoSaveStatus = null;
		try {
			const r = await apiFetch('/api/history', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({
					input: `[demo] ${demoGeneratedPrompt}`,
					source_text: demoGeneratedPrompt,
					display_label: '[demo]',
					ddl: demoGeneratedDdl,
					score: result.score,
					at: Date.now(),
					elapsed_ms: result.elapsed_total_ms ?? 0,
					stage1_model: result.stage1_model ?? qualifiedModelId(stage1Provider, stage1Model),
					stage2_model: result.stage2_model ?? qualifiedModelId(stage2Provider, stage2Model),
					tokens_in: (result.tokens_in_stage1 ?? 0) + (result.tokens_in_stage2 ?? 0) || null,
					tokens_out: (result.tokens_out_stage1 ?? 0) + (result.tokens_out_stage2 ?? 0) || null,
					catalog_id: result.render_color_catalog_id ?? (selectedCatalog !== 'default' ? selectedCatalog : null),
					save_artifacts: demoSettings.save_files,
					canvas_aspect: effectiveCanvasAspectId(),
					instruction_lang_requested: result.instruction_lang_requested ?? instructionLang,
					instruction_lang_resolved: result.instruction_lang_resolved ?? null,
					ui_lang: result.ui_lang ?? getLang(),
				})
			});
			if (!r.ok) {
				const d = await r.json().catch(() => ({})) as { detail?: string };
				throw new Error(d.detail ?? `HTTP ${r.status}`);
			}
			const saved = await r.json() as Iteration;
			if (result) {
				result = { ...result, history_id: saved.id, history_at: saved.at, render_hash: saved.render_hash, render_hash_short: saved.render_hash_short };
			}
			demoCurrentSaved = true;
			demoSaveStatus = t().demoSavedCurrent;
			await fetchHistoryOffset(0);
			historyCursor = 0;
		} catch (e) {
			demoError = e instanceof Error ? e.message : String(e);
		} finally {
			demoSavingCurrent = false;
		}
	}

	function clearInput() {
		resetTargetScopedState();
		pendingCanvasAspectDerivation = null;
		if (inputMode === 'single') input = '';
		if (inputMode === 'batch') batchInput = '';
		if (inputMode === 'demo') {
			demoGeneratedPrompt = '';
			demoGeneratedDdl = null;
			demoError = null;
			demoSaveStatus = null;
			demoCurrentSaved = false;
		}
		ddl = inputMode === 'single' ? '' : null;
		ddlGeneratedBaseline = inputMode === 'single' ? '' : null;
		thinking = null;
		result = null;
		stage1UserPrompt = '';
		error = null;
		reloadError = null;
		batchFailures = [];
		setBatchFailureReport(null);
		batchActiveLine = null;
		batchActiveDdl = null;
		batchLatestPrompt = '';
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
		historyManager.toggleSelection(id);
	}

	function selectAllManagedHistory() {
		historyManager.toggleSelectAll();
	}

	async function postHistoryIds(path: string, ids: string[]) {
		if (!authToken) return;
		await apiFetch(path, {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({ ids })
		});
		if (displayedHistoryItem?.id && ids.includes(displayedHistoryItem.id)) {
			if (path === '/api/history/trash') {
				displayedHistoryItem = { ...displayedHistoryItem, trashed: true };
				historyCursor = -1;
			} else if (path === '/api/history/restore') {
				displayedHistoryItem = { ...displayedHistoryItem, trashed: false };
				void syncHistoryStripToItem(displayedHistoryItem);
			} else if (path === '/api/history/permanent-delete') {
				displayedHistoryItem = null;
				historyCursor = -1;
			}
		}
		historyManager.selectedIds = [];
		await Promise.all([fetchHistoryOffset(historyOffset), fetchTrashPage(), historyManager.fetch()]);
		if (lineageGraph?.focus_node_id) await fetchLineage(lineageGraph.focus_node_id, true);
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
		if (demoRunning) return;
		if (idx < 0 || idx >= historyItems.length) return;
		historyCursor = idx;
		loadIterationItem(historyItems[idx]);
	}

	function currentComparisonItem(): Iteration | null {
		if (displayedHistoryItem) return displayedHistoryItem;
		if (!result) return null;
		return {
			input,
			ddl,
			score: result.score,
			svg: result.svg,
			at: Date.now(),
			elapsed_ms: result.elapsed_total_ms,
			stage1_model: result.stage1_model ?? qualifiedModelId(stage1Provider, stage1Model),
			stage2_model: result.stage2_model ?? qualifiedModelId(stage2Provider, stage2Model),
		};
	}

	const activeComparisonItem = $derived(currentComparisonItem());

	function modelInspectionModelChoices(): ModelInspectionChoice[] {
		const seen = new Set<string>();
		const choices: ModelInspectionChoice[] = [];
		for (const group of availableModelCatalog) {
			for (const model of group.models) {
				const id = qualifiedModelId(group.id as Provider, model.id);
				if (seen.has(id)) continue;
				seen.add(id);
				choices.push({ id, label: model.label || model.id, providerLabel: group.label || String(group.id) });
			}
		}
		return choices;
	}

	const modelInspectionChoices = $derived(modelInspectionModelChoices());

	const modelInspectionTargetStage1Model = $derived(result?.stage1_model ?? qualifiedModelId(stage1Provider, stage1Model));
	const modelInspectionTargetStage2Model = $derived(result?.stage2_model ?? qualifiedModelId(stage2Provider, stage2Model));
	const modelInspectionTargetModel = $derived(modelInspectionTargetStage1Model);

	function setModelCompareMode(mode: ModelCompareMode) {
		if (modelInspectionBusy) return;
		modelCompareMode = mode;
		modelCompareFixedModel = mode === 'stage1_fixed' ? modelInspectionTargetStage1Model : mode === 'stage2_fixed' ? modelInspectionTargetStage2Model : '';
		modelInspectionSelectedModels = []; modelInspectionResults = []; modelInspectionFailedModels = {}; modelInspectionStatus = null;
	}

	function setModelCompareFixedModel(model: string) {
		if (modelInspectionBusy) return;
		modelCompareFixedModel = model; modelInspectionResults = []; modelInspectionFailedModels = {}; modelInspectionStatus = null;
	}

	function isModelInspectionChoiceBlocked(model: string) {
		if (modelCompareMode === 'common') return model === modelInspectionTargetStage1Model || model === modelInspectionTargetStage2Model;
		if (modelCompareMode === 'stage1_fixed') return modelCompareFixedModel === modelInspectionTargetStage1Model && model === modelInspectionTargetStage2Model;
		return model === modelInspectionTargetStage1Model && modelCompareFixedModel === modelInspectionTargetStage2Model;
	}

	async function persistModelInspectionSelection(models: string[]) {
		if (!currentUser) return;
		try {
			const r = await apiFetch('/api/auth/me/settings', {
				method: 'PATCH',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({
					model_settings: {
						model_inspection_selected_models: models.slice(0, 4),
					},
				}),
			});
			if (!r.ok) throw new Error(`HTTP ${r.status}`);
			currentUser = await r.json() as UserItem;
		} catch (e) {
			console.warn('failed to save model comparison selection', e);
		}
	}

	$effect(() => {
		const available = new Set(modelInspectionChoices.map((choice) => choice.id));
		const next = modelInspectionSelectedModels.filter((id) => available.has(id) && !isModelInspectionChoiceBlocked(id)).slice(0, 4);
		if (next.join("\n") !== modelInspectionSelectedModels.join("\n")) {
			modelInspectionSelectedModels = next;
			void persistModelInspectionSelection(next);
		}
	});

	function toggleModelInspectionModel(modelId: string) {
		if (modelInspectionBusy || isModelInspectionChoiceBlocked(modelId)) return;
		if (modelInspectionSelectedModels.includes(modelId)) {
			const next = modelInspectionSelectedModels.filter((id) => id !== modelId);
			modelInspectionSelectedModels = next;
			void persistModelInspectionSelection(next);
			return;
		}
		if (modelInspectionSelectedModels.length >= 4) {
			modelInspectionStatus = t().modelCompareMaxSelected;
			return;
		}
		const next = [...modelInspectionSelectedModels, modelId];
		modelInspectionSelectedModels = next;
		if (modelInspectionFailedModels[modelId]) {
			const { [modelId]: _failed, ...rest } = modelInspectionFailedModels;
			modelInspectionFailedModels = rest;
		}
		void persistModelInspectionSelection(next);
		modelInspectionStatus = null;
	}

	async function runModelInspection() {
		if (modelInspectionBusy || loading) return;
		const source = input.trim();
		if (!source) return;
		const contextVersion = targetContextVersion;
		const modelParentNodeId = await ensureVisibleLineageParentId();
		if (contextVersion !== targetContextVersion) return;
		const selectedModels = modelInspectionSelectedModels.slice(0, 4).filter((model) => !isModelInspectionChoiceBlocked(model));
		if (selectedModels.length === 0) { modelInspectionStatus = t().modelCompareSelectPrompt; return; }
		const jobs = selectedModels.map((model) => {
			const stage1 = modelCompareMode === "stage1_fixed" ? modelCompareFixedModel : model;
			const stage2 = modelCompareMode === "stage2_fixed" ? modelCompareFixedModel : model;
			return { model, stage1, stage2, id: modelCompareMode + ":" + stage1 + ":" + stage2 };
		});
		const rendered = new Set(modelInspectionResults.map((item) => item.id));
		const pending = jobs.filter((job) => !rendered.has(job.id));
		if (pending.length === 0) { modelInspectionStatus = t().modelCompareAllRendered; return; }

		const runId = ++modelInspectionRunId;
		const abortController = new AbortController();
		modelInspectionAbortController = abortController;
		modelInspectionBusy = true;
		modelInspectionStatus = null;
		const successful = [...modelInspectionResults];
		const failed: Record<string, string> = {};
		try {
			for (const job of pending) {
				if (abortController.signal.aborted || modelInspectionRunId !== runId) return;
				try {
					const started = Date.now();
					const interpreted = await interpretOne(source, abortController.signal, job.stage1);
					if (abortController.signal.aborted || modelInspectionRunId !== runId) return;
					const composed = await composeOne(interpreted.ddl, source, abortController.signal, job.stage2);
					if (abortController.signal.aborted || modelInspectionRunId !== runId) return;
					successful.push({
						id: job.id,
						model: job.model,
						stage1Model: job.stage1,
						label: statusModelName(job.stage1) + " / " + statusModelName(job.stage2),
						input: source,
						ddl: interpreted.ddl,
						svg: composed.svg,
						score: composed.score,
						stage2Model: composed.stage2_model ?? job.stage2,
						renderBuildNumber: composed.render_build_number ?? null,
						renderColorProfile: composed.render_color_profile ?? null,
						renderEngineId: composed.render_engine_id ?? null,
						renderEngineVersion: composed.render_engine_version ?? null,
						renderColorCatalogId: composed.render_color_catalog_id ?? null,
						renderColorCatalogName: composed.render_color_catalog_name ?? null,
						renderColorCatalogSub: composed.render_color_catalog_sub ?? null,
						renderColorMap: composed.render_color_map ?? null,
						renderCanvasAspect: composed.render_canvas_aspect ?? null,
						renderCanvasAspectId: composed.render_canvas_aspect_id ?? null,
						renderCanvasAspectRatio: composed.render_canvas_aspect_ratio ?? null,
						renderSeed: composed.render_seed ?? null,
						varySeed: composed.vary_seed ?? null,
						tokensIn: interpreted.tokens_in,
						tokensOut: interpreted.tokens_out,
						tokensInStage2: composed.tokens_in,
						tokensOutStage2: composed.tokens_out,
						elapsedMs: Date.now() - started,
						lineageParentNodeId: modelParentNodeId,
						compareMode: modelCompareMode,
						savedHistoryId: null,
						starred: false,
						saving: false,
					});
					modelInspectionResults = [...successful];
				} catch (cause) {
					if (abortController.signal.aborted || modelInspectionRunId !== runId) return;
					failed[job.model] = cause instanceof Error ? cause.message : String(cause);
					modelInspectionFailedModels = { ...modelInspectionFailedModels, [job.model]: failed[job.model] };
				}
			}
			if (Object.keys(failed).length > 0 && modelInspectionRunId === runId) {
				modelInspectionStatus = t().modelCompareFailedSummary(Object.keys(failed).length);
			}
		} finally {
			if (modelInspectionRunId === runId) {
				modelInspectionAbortController = null;
				modelInspectionBusy = false;
			}
		}
	}

	const languageInspectionTargetLang = $derived(
		(result?.instruction_lang_resolved === 'en' ? 'en' : result?.instruction_lang_resolved === 'ja' ? 'ja' : getLang()) as 'ja' | 'en'
	);

	function setLanguageCompareMode(mode: ModelCompareMode) {
		if (languageInspectionBusy) return;
		languageCompareMode = mode;
		languageCompareFixedLang = languageInspectionTargetLang;
		languageInspectionSelectedLangs = [];
		languageInspectionResults = [];
		languageInspectionStatus = null;
	}

	function setLanguageCompareFixedLang(lang: 'ja' | 'en') {
		if (languageInspectionBusy) return;
		languageCompareFixedLang = lang;
		languageInspectionResults = [];
		languageInspectionStatus = null;
	}

	function isLanguageInspectionChoiceBlocked(lang: 'ja' | 'en') {
		if (languageCompareMode === 'common') return lang === languageInspectionTargetLang;
		if (languageCompareMode === 'stage1_fixed') return languageCompareFixedLang === languageInspectionTargetLang && lang === languageInspectionTargetLang;
		return lang === languageInspectionTargetLang && languageCompareFixedLang === languageInspectionTargetLang;
	}

	function toggleLanguageInspectionLang(lang: 'ja' | 'en') {
		if (languageInspectionBusy || isLanguageInspectionChoiceBlocked(lang)) return;
		languageInspectionSelectedLangs = languageInspectionSelectedLangs.includes(lang)
			? languageInspectionSelectedLangs.filter((value) => value !== lang)
			: [...languageInspectionSelectedLangs, lang];
		languageInspectionStatus = null;
	}

	async function runLanguageInspection() {
		if (languageInspectionBusy || loading) return;
		const source = input.trim();
		if (!source) return;
		const selected = languageInspectionSelectedLangs.filter((lang) => !isLanguageInspectionChoiceBlocked(lang));
		if (selected.length === 0) {
			languageInspectionStatus = getLang() === 'ja' ? '比較する言語を1つ以上選択してください。' : 'Select at least one language to compare.';
			return;
		}
		const contextVersion = targetContextVersion;
		const parentNodeId = await ensureVisibleLineageParentId();
		if (contextVersion !== targetContextVersion) return;
		const jobs = selected.map((lang) => {
			const stage1Lang = languageCompareMode === 'stage1_fixed' ? languageCompareFixedLang : lang;
			const stage2Lang = languageCompareMode === 'stage2_fixed' ? languageCompareFixedLang : lang;
			return { lang, stage1Lang, stage2Lang, id: `${languageCompareMode}:${stage1Lang}:${stage2Lang}` };
		});
		const rendered = new Set(languageInspectionResults.map((item) => item.id));
		const pending = jobs.filter((job) => !rendered.has(job.id));
		if (pending.length === 0) {
			languageInspectionStatus = getLang() === 'ja' ? '選択済みの言語構成はすべて描画済みです。' : 'All selected language combinations are rendered.';
			return;
		}
		const runId = ++languageInspectionRunId;
		const abortController = new AbortController();
		languageInspectionAbortController = abortController;
		languageInspectionBusy = true;
		languageInspectionStatus = null;
		const successful = [...languageInspectionResults];
		try {
			for (const job of pending) {
				if (abortController.signal.aborted || languageInspectionRunId !== runId) return;
				try {
					const started = Date.now();
					const interpreted = await interpretOne(source, abortController.signal, undefined, job.stage1Lang);
					const composed = await composeOne(interpreted.ddl, source, abortController.signal, undefined, job.stage2Lang);
					if (abortController.signal.aborted || languageInspectionRunId !== runId) return;
					const langLabel = (lang: 'ja' | 'en') => lang === 'ja' ? (getLang() === 'ja' ? '日本語' : 'Japanese') : 'English';
					successful.push({
						id: job.id,
						model: qualifiedModelId(stage1Provider, stage1Model),
						stage1Model: qualifiedModelId(stage1Provider, stage1Model),
						stage2Model: composed.stage2_model ?? qualifiedModelId(stage2Provider, stage2Model),
						label: `${langLabel(job.stage1Lang)} / ${langLabel(job.stage2Lang)}`,
						input: source,
						ddl: interpreted.ddl,
						svg: composed.svg,
						score: composed.score,
						renderBuildNumber: composed.render_build_number ?? null,
						renderColorProfile: composed.render_color_profile ?? null,
						renderEngineId: composed.render_engine_id ?? null,
						renderEngineVersion: composed.render_engine_version ?? null,
						renderColorCatalogId: composed.render_color_catalog_id ?? null,
						renderColorCatalogName: composed.render_color_catalog_name ?? null,
						renderColorCatalogSub: composed.render_color_catalog_sub ?? null,
						renderColorMap: composed.render_color_map ?? null,
						renderCanvasAspect: composed.render_canvas_aspect ?? null,
						renderCanvasAspectId: composed.render_canvas_aspect_id ?? null,
						renderCanvasAspectRatio: composed.render_canvas_aspect_ratio ?? null,
						renderSeed: composed.render_seed ?? null,
						varySeed: composed.vary_seed ?? null,
						tokensIn: interpreted.tokens_in,
						tokensOut: interpreted.tokens_out,
						tokensInStage2: composed.tokens_in,
						tokensOutStage2: composed.tokens_out,
						elapsedMs: Date.now() - started,
						lineageParentNodeId: parentNodeId,
						compareMode: languageCompareMode,
						comparisonKind: 'language',
						stage1Lang: job.stage1Lang,
						stage2Lang: job.stage2Lang,
						savedHistoryId: null,
						starred: false,
						saving: false,
					});
					languageInspectionResults = [...successful];
				} catch (cause) {
					if (abortController.signal.aborted || languageInspectionRunId !== runId) return;
					languageInspectionStatus = cause instanceof Error ? cause.message : String(cause);
				}
			}
		} finally {
			if (languageInspectionRunId === runId) {
				languageInspectionAbortController = null;
				languageInspectionBusy = false;
			}
		}
	}


	function updateModelInspectionResult(id: string, patch: Partial<ModelInspectionResult>) {
		modelInspectionResults = modelInspectionResults.map((item) => item.id === id ? { ...item, ...patch } : item);
		languageInspectionResults = languageInspectionResults.map((item) => item.id === id ? { ...item, ...patch } : item);
	}

	async function saveModelInspectionResult(item: ModelInspectionResult, options: { star?: boolean } = {}) {
		if (item.saving) return;
		const contextVersion = targetContextVersion;
		if (item.savedHistoryId) {
			if (options.star) {
				await toggleHistoryStar({ id: item.savedHistoryId, starred: !!item.starred });
				if (contextVersion === targetContextVersion) updateModelInspectionResult(item.id, { starred: !item.starred });
			}
			return;
		}
		updateModelInspectionResult(item.id, { saving: true });
		if (item.comparisonKind === 'language') languageInspectionStatus = null;
		else modelInspectionStatus = null;
		try {
			const saved = await pushHistory({
				input: item.input,
				ddl: item.ddl,
				score: item.score,
				svg: item.svg,
				at: Date.now(),
				elapsed_ms: item.elapsedMs,
				stage1_model: item.stage1Model ?? item.model,
				stage2_model: item.stage2Model ?? null,
				tokens_in: (item.tokensIn ?? 0) + (item.tokensInStage2 ?? 0) || null,
				tokens_out: (item.tokensOut ?? 0) + (item.tokensOutStage2 ?? 0) || null,
				catalog_id: item.renderColorCatalogId ?? selectedCatalog,
				render_build_number: item.renderBuildNumber ?? null,
				render_color_profile: item.renderColorProfile ?? null,
				render_engine_id: item.renderEngineId ?? null,
				render_engine_version: item.renderEngineVersion ?? null,
				render_color_catalog_id: item.renderColorCatalogId ?? null,
				render_color_catalog_name: item.renderColorCatalogName ?? null,
				render_color_catalog_sub: item.renderColorCatalogSub ?? null,
				render_color_map: item.renderColorMap ?? null,
				render_canvas_aspect: item.renderCanvasAspect ?? item.renderCanvasAspectId ?? effectiveCanvasAspectId(),
				render_canvas_aspect_id: item.renderCanvasAspectId ?? item.renderCanvasAspect ?? effectiveCanvasAspectId(),
				render_canvas_aspect_ratio: item.renderCanvasAspectRatio ?? null,
				render_seed: item.renderSeed ?? null,
				vary_seed: item.varySeed ?? null,
				instruction_lang_requested: item.comparisonKind === 'language' ? item.stage2Lang : undefined,
				instruction_lang_resolved: item.comparisonKind === 'language' ? item.stage2Lang : undefined,
				ui_lang: getLang(),
			}, {
				countGeneration: true,
				sourceText: item.input,
				lineageParentNodeId: item.lineageParentNodeId ?? null,
				derivationKind: item.lineageParentNodeId ? (item.comparisonKind === 'language' ? 'language_variation' : 'model_variation') : null,
				derivationMetadata: item.comparisonKind === 'language'
					? { comparison_mode: item.compareMode, stage1_language: item.stage1Lang, stage2_language: item.stage2Lang }
					: { comparison_mode: item.compareMode, compared_model: item.model, stage1_model: item.stage1Model, stage2_model: item.stage2Model },
			});
			if (!saved?.id) throw new Error('failed to save comparison result');
			if (contextVersion !== targetContextVersion) return;
			updateModelInspectionResult(item.id, { savedHistoryId: saved.id, starred: !!saved.starred, saving: false });
			if (options.star) {
				await toggleHistoryStar({ id: saved.id, starred: !!saved.starred, note: saved.note });
				if (contextVersion === targetContextVersion) updateModelInspectionResult(item.id, { starred: !saved.starred });
			}
		} catch (e) {
			if (contextVersion === targetContextVersion) {
				updateModelInspectionResult(item.id, { saving: false });
				if (item.comparisonKind === 'language') languageInspectionStatus = e instanceof Error ? e.message : String(e);
				else modelInspectionStatus = e instanceof Error ? e.message : String(e);
			}
		}
	}

	async function replayHistoryItem(it: Iteration) {
		if (demoRunning || reloading) return;
		const contextVersion = targetContextVersion;
		if (it.render_seed == null) {
			reloadError = t().historyReplayMissingSeed;
			return;
		}
		reloading = true;
		reloadError = null;
		try {
			const catalogId = it.render_color_catalog_id ?? it.catalog_id ?? selectedCatalog;
			const canvasId = it.render_canvas_aspect_id ?? it.render_canvas_aspect ?? it.score?.canvas ?? effectiveCanvasAspectId();
			const r = await apiFetch('/api/render-svg', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({
					score: it.score,
					catalog_id: catalogId,
					canvas_aspect: canvasId,
					render_seed: Number(it.render_seed),
					seed_text: it.seed_text,
				})
			});
			if (!r.ok) throw new Error(await r.text());
			const svg = await r.text();
			if (contextVersion !== targetContextVersion) return;
			loadIterationItem({ ...it, svg });
			result = result ? { ...result, svg, render_hash: it.render_hash, render_hash_short: it.render_hash_short } : result;
			outputTab = 'canvas';
			fitCanvasZoom();
		} catch (e) {
			if (contextVersion === targetContextVersion) reloadError = e instanceof Error ? e.message : String(e);
		} finally {
			reloading = false;
		}
	}

async function fetchLineage(nodeId: string, force = false, descendantDepth = 3): Promise<void> {
	if (!nodeId || (!force && lineageLoadedFocus === nodeId)) return;
	const requestId = ++lineageRequestId;
	lineageLoading = true;
	lineageError = null;
	try {
		const url = "/api/lineage/" + encodeURIComponent(nodeId) + "?descendant_depth=" + descendantDepth + "&node_limit=200";
		const r = await apiFetch(url, { cache: "no-store" });
		if (!r.ok) throw new Error("HTTP " + r.status);
		const graph = await r.json() as LineageGraph;
		if (requestId !== lineageRequestId) return;
		lineageGraph = graph;
		lineageLoadedFocus = nodeId;
	} catch (cause) {
		if (requestId === lineageRequestId) lineageError = cause instanceof Error ? cause.message : String(cause);
	} finally {
		if (requestId === lineageRequestId) lineageLoading = false;
	}
}


async function loadLineageBranch(nodeId: string): Promise<void> {
	if (!lineageGraph) return;
	const focusNodeId = lineageGraph.focus_node_id;
	const requestId = ++lineageRequestId;
	lineageLoading = true;
	lineageError = null;
	try {
		const r = await apiFetch("/api/lineage/" + encodeURIComponent(nodeId) + "?descendant_depth=1&node_limit=200", { cache: "no-store" });
		if (!r.ok) throw new Error("HTTP " + r.status);
		const branch = await r.json() as LineageGraph;
		if (requestId !== lineageRequestId || lineageGraph?.focus_node_id !== focusNodeId) return;
		const nodes = new Map(lineageGraph.nodes.map((node) => [node.id, node]));
		const edges = new Map(lineageGraph.edges.map((edge) => [edge.id, edge]));
		for (const node of branch.nodes) nodes.set(node.id, node);
		for (const edge of branch.edges) edges.set(edge.id, edge);
		lineageGraph = { ...lineageGraph, nodes: [...nodes.values()], edges: [...edges.values()] };
	} catch (cause) {
		if (requestId === lineageRequestId) lineageError = cause instanceof Error ? cause.message : String(cause);
	} finally {
		if (requestId === lineageRequestId) lineageLoading = false;
	}
}


async function loadLineageOverview(): Promise<void> {
	const focusNodeId = lineageGraph?.focus_node_id ?? displayedHistoryItem?.lineage_node_id ?? result?.lineage_node_id ?? null;
	if (!focusNodeId || !lineageGraph) return;
	const childIds = new Set(lineageGraph.edges.map((edge) => edge.child_node_id));
	const rootNodeId = lineageGraph.nodes.find((node) => !childIds.has(node.id))?.id ?? focusNodeId;
	const requestId = ++lineageRequestId;
	lineageLoading = true;
	lineageError = null;
	try {
		const url = "/api/lineage/" + encodeURIComponent(rootNodeId) + "?descendant_depth=200&node_limit=200";
		const r = await apiFetch(url, { cache: "no-store" });
		if (!r.ok) throw new Error("HTTP " + r.status);
		const overview = await r.json() as LineageGraph;
		if (requestId !== lineageRequestId) return;
		lineageGraph = { ...overview, focus_node_id: focusNodeId };
		lineageLoadedFocus = focusNodeId;
	} catch (cause) {
		if (requestId === lineageRequestId) lineageError = cause instanceof Error ? cause.message : String(cause);
	} finally {
		if (requestId === lineageRequestId) lineageLoading = false;
	}
}


async function openLineageNode(node: LineageNode): Promise<void> {
	if (!node.history) return;
	loadIterationItem(node.history);
	outputTab = 'lineage';
	lineageDetached = false;
	await fetchLineage(node.id, true);
}

function lineageCatalogId(node: LineageNode): string {
	return node.history?.render_color_catalog_id ?? node.history?.catalog_id ?? selectedCatalog;
}

function lineageCanvasAspectId(node: LineageNode): CanvasAspectId {
	return normalizeCanvasAspectId(node.history?.render_canvas_aspect_id ?? node.history?.render_canvas_aspect ?? node.history?.score?.canvas ?? effectiveCanvasAspectId());
}

async function showNewLineageChild(historyId: string | null | undefined, nodeId: string | null | undefined): Promise<void> {
	if (!historyId || !nodeId) throw new Error(getLang() === 'ja' ? '描画結果を系譜へ保存できませんでした。' : 'The rendered result could not be saved to the lineage.');
	let found = await fetchHistoryOffset(0, { anchorId: historyId });
	if (!found && historyStarredOnly) {
		historyStarredOnly = false;
		found = await fetchHistoryOffset(0, { anchorId: historyId });
	}
	const saved = historyItems.find((item) => item.id === historyId);
	if (!saved) throw new Error(getLang() === 'ja' ? '保存した作品を読み込めませんでした。' : 'The saved artwork could not be loaded.');
	outputTab = 'lineage';
	loadIterationItem(saved);
	await fetchLineage(nodeId, true);
}

async function drawLineageDescriptionEdit(node: LineageNode, text: string): Promise<void> {
	const sourceText = text.trim();
	if (!sourceText || !node.history) return;
	const rendered = await paintOne(sourceText, {
		sourceText,
		historyInput: sourceText,
		catalogId: lineageCatalogId(node),
		canvasAspectId: lineageCanvasAspectId(node),
		lineageParentNodeId: node.id,
		derivationKind: 'description_edit',
		derivationMetadata: { edited_from_history_id: node.history.id ?? null },
	});
	await showNewLineageChild(rendered.history_id, rendered.lineage_node_id);
}

async function drawLineageDdlEdit(node: LineageNode, editedDdl: string): Promise<void> {
	const nextDdl = editedDdl.trim();
	if (!nextDdl || !node.history) return;
	const sourceText = node.history.source_text ?? node.history.input ?? '';
	const composed = await composeOne(nextDdl, sourceText, undefined, undefined, undefined, {
		catalogId: lineageCatalogId(node),
		canvasAspectId: lineageCanvasAspectId(node),
	});
	const resolvedEditStage1Model = node.history.stage1_model ?? qualifiedModelId(stage1Provider, stage1Model);
	const resolvedEditStage2Model = composed.stage2_model ?? qualifiedModelId(stage2Provider, stage2Model);
	const saved = await pushHistory({
		input: sourceText,
		source_text: sourceText,
		ddl: nextDdl,
		score: composed.score,
		svg: composed.svg,
		at: Date.now(),
		elapsed_ms: composed.elapsed_ms,
		stage1_model: resolvedEditStage1Model,
		stage2_model: resolvedEditStage2Model,
		tokens_in: composed.tokens_in,
		tokens_out: composed.tokens_out,
		catalog_id: lineageCatalogId(node),
		render_build_number: composed.render_build_number,
		render_color_profile: composed.render_color_profile,
		render_engine_id: composed.render_engine_id,
		render_engine_version: composed.render_engine_version,
		render_color_catalog_id: composed.render_color_catalog_id,
		render_color_catalog_name: composed.render_color_catalog_name,
		render_color_catalog_sub: composed.render_color_catalog_sub,
		render_color_map: composed.render_color_map,
		render_canvas_aspect: composed.render_canvas_aspect,
		render_canvas_aspect_id: composed.render_canvas_aspect_id,
		render_canvas_aspect_ratio: composed.render_canvas_aspect_ratio,
		render_seed: composed.render_seed,
		vary_seed: composed.vary_seed,
		instruction_lang_requested: composed.instruction_lang_requested,
		instruction_lang_resolved: composed.instruction_lang_resolved,
		ui_lang: composed.ui_lang,
		render_hash: composed.render_hash,
		render_hash_short: composed.render_hash_short,
	}, {
		selectSaved: true,
		countGeneration: true,
		sourceText,
		lineageParentNodeId: node.id,
		derivationKind: 'ddl_edit',
		derivationMetadata: { edited_from_history_id: node.history.id ?? null },
	});
	await showNewLineageChild(saved?.id, saved?.lineage_node_id);
}

// Draw a standalone artwork authored directly in DDL (no instruction, no parent).
async function drawNewDdl(rawDdl: string): Promise<void> {
	const nextDdl = rawDdl.trim();
	if (!nextDdl) return;
	const firstLine = (nextDdl.split('\n').find((line) => line.trim().length > 0) ?? nextDdl).trim().slice(0, 80);
	const composed = await composeOne(nextDdl, '', undefined, undefined, undefined, {
		catalogId: selectedCatalog,
		canvasAspectId: effectiveCanvasAspectId(),
	});
	const saved = await pushHistory({
		input: '',
		source_text: firstLine,
		ddl: nextDdl,
		score: composed.score,
		svg: composed.svg,
		at: Date.now(),
		elapsed_ms: composed.elapsed_ms,
		stage1_model: null,
		stage2_model: composed.stage2_model ?? qualifiedModelId(stage2Provider, stage2Model),
		tokens_in: composed.tokens_in,
		tokens_out: composed.tokens_out,
		catalog_id: selectedCatalog,
		render_build_number: composed.render_build_number,
		render_color_profile: composed.render_color_profile,
		render_engine_id: composed.render_engine_id,
		render_engine_version: composed.render_engine_version,
		render_color_catalog_id: composed.render_color_catalog_id,
		render_color_catalog_name: composed.render_color_catalog_name,
		render_color_catalog_sub: composed.render_color_catalog_sub,
		render_color_map: composed.render_color_map,
		render_canvas_aspect: composed.render_canvas_aspect,
		render_canvas_aspect_id: composed.render_canvas_aspect_id,
		render_canvas_aspect_ratio: composed.render_canvas_aspect_ratio,
		render_seed: composed.render_seed,
		vary_seed: composed.vary_seed,
		instruction_lang_requested: composed.instruction_lang_requested,
		instruction_lang_resolved: composed.instruction_lang_resolved,
		ui_lang: composed.ui_lang,
		render_hash: composed.render_hash,
		render_hash_short: composed.render_hash_short,
	}, {
		selectSaved: true,
		countGeneration: true,
		sourceText: firstLine,
		displayLabel: 'DDL',
	});
	await showNewLineageChild(saved?.id, saved?.lineage_node_id);
	outputTab = 'canvas';
}

function openNewDdlDialog(): void {
	ddlDialogMode = 'new';
	ddlDialogNode = null;
	ddlDialogInitial = '';
	ddlDialogError = null;
	ddlDialogOpen = true;
}

function openLineageDdlEditor(node: LineageNode): void {
	ddlDialogMode = 'edit';
	ddlDialogNode = node;
	ddlDialogInitial = node.history?.ddl ?? '';
	ddlDialogError = null;
	ddlDialogOpen = true;
}

function closeDdlDialog(): void {
	if (ddlDialogDrawing) return;
	ddlDialogOpen = false;
}

// Refresh the lineage tree when the comparison dialog closes so adopted
// results (saved as children) appear without reopening the tab.
function refreshLineageAfterRefine(): void {
	const focusId = lineageGraph?.focus_node_id ?? displayedHistoryItem?.lineage_node_id ?? result?.lineage_node_id ?? null;
	if (focusId) void fetchLineage(focusId, true);
}

async function handleDdlDialogDraw(nextDdl: string): Promise<void> {
	if (ddlDialogDrawing) return;
	ddlDialogDrawing = true;
	ddlDialogError = null;
	try {
		if (ddlDialogMode === 'edit' && ddlDialogNode) await drawLineageDdlEdit(ddlDialogNode, nextDdl);
		else await drawNewDdl(nextDdl);
		ddlDialogOpen = false;
	} catch (cause) {
		ddlDialogError = cause instanceof Error ? cause.message : String(cause);
	} finally {
		ddlDialogDrawing = false;
	}
}

async function promoteLineageNode(node: LineageNode): Promise<void> {
	const contextVersion = targetContextVersion;
	const r = await apiFetch(`/api/lineage/${encodeURIComponent(node.id)}/promote`, { method: 'POST' });
	if (!r.ok) return;
	const promoted = await r.json() as Iteration;
	if (contextVersion !== targetContextVersion) return;
	if (displayedHistoryItem?.id === promoted.id) {
		displayedHistoryItem = promoted;
		await Promise.all([fetchLineage(node.id, true), syncHistoryStripToItem(promoted)]);
	} else {
		const activeHistoryId = displayedHistoryItem?.id ?? result?.history_id ?? historyItems[historyCursor]?.id ?? null;
		await Promise.all([
			fetchLineage(node.id, true),
			activeHistoryId ? fetchHistoryOffset(0, { anchorId: activeHistoryId }) : fetchHistoryOffset(historyOffset, { preserveSelection: true }),
		]);
	}
}

async function saveLineageNote(node: LineageNode, note: string): Promise<void> {
	if (!node.history?.id) return;
	const contextVersion = targetContextVersion;
	const r = await apiFetch(`/api/history/${encodeURIComponent(node.history.id)}/star`, {
		method: 'PATCH',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify({ starred: !!node.history.starred, note: note.trim().slice(0, 240) })
	});
	if (!r.ok) throw new Error(`HTTP ${r.status}`);
	const updated = await r.json() as Iteration;
	if (contextVersion !== targetContextVersion) return;
	updateHistoryStarState(updated);
	await fetchLineage(node.id, true);
}

function detachLineage(): void {
	resetTargetScopedState();
	pendingCanvasAspectDerivation = null;
	lineageDetached = true;
	displayedHistoryItem = null;
	historyCursor = -1;
	lineageGraph = null;
	lineageLoadedFocus = null;
	outputTab = 'canvas';
}

$effect(() => {
	const nodeId = displayedHistoryItem?.lineage_node_id ?? result?.lineage_node_id ?? null;
	if (outputTab === 'lineage' && nodeId) void fetchLineage(nodeId);
});

	function resetTargetScopedState(options: { preserveVariationCandidates?: boolean } = {}): void {
		targetContextVersion += 1;
		if (!options.preserveVariationCandidates) {
			if (variationGridAbortController) variationGridAbortController.abort();
			variationGridAbortController = null;
			variationGridBusy = false;
			variationGridCanAbort = false;
			variationCandidates = [];
			variationGridIncludesReading = false;
			variationGridTaskLabel = '';
			variationGridStatus = null;
		}

		if (modelInspectionAbortController) modelInspectionAbortController.abort();
		modelInspectionAbortController = null;
		modelInspectionRunId += 1;
		modelInspectionBusy = false;
		modelInspectionResults = [];
		modelInspectionFailedModels = {};
		modelInspectionStatus = null;
		if (languageInspectionAbortController) languageInspectionAbortController.abort();
		languageInspectionAbortController = null;
		languageInspectionRunId += 1;
		languageInspectionBusy = false;
		languageInspectionResults = [];
		languageInspectionStatus = null;

		interpretationDiffParts = [];
		reloadError = null;
		if (lineageIntermediateNoticeTimer !== null) {
			window.clearTimeout(lineageIntermediateNoticeTimer);
			lineageIntermediateNoticeTimer = null;
		}
		lineageIntermediateNotice = null;

		lineageRequestId += 1;
		lineageLoading = false;
		lineageError = null;
		lineageGraph = null;
		lineageLoadedFocus = null;
	}

	function loadIterationItem(it: Iteration) {
		if (demoRunning) return;
		const preserveLineageTab = outputTab === 'lineage';
		resetTargetScopedState();
		pendingCanvasAspectDerivation = null;
		inputMode = 'single';
		displayedHistoryItem = it;
		void syncHistoryStripToItem(it);
		lineageDetached = false;
		if (historySelectionCatalog === 'history') {
			const catalogId = it.render_color_catalog_id ?? it.catalog_id;
			if (catalogId && catalogById(colorCatalogs, catalogId)) {
				selectedCatalog = catalogId;
				persistSelectedCatalog();
			}
		}
		if (historySelectionCanvas === 'history') {
			const canvasId = it.render_canvas_aspect_id ?? it.render_canvas_aspect ?? it.score?.canvas;
			if (canvasId) {
				canvasAspectId = normalizeCanvasAspectId(canvasId);
				void saveCanvasAspectPluginValue();
			}
		}
		const itemDDL = it.ddl ?? '';
		const sourceText = it.source_text ?? it.input;
		input = sourceText; ddl = itemDDL; ddlGeneratedBaseline = itemDDL; ddlSelection = { start: itemDDL.length, end: itemDDL.length }; thinking = it.thinking ?? null;
		stage1UserPrompt = sourceText ? sourceText + buildEmotionHint(sourceText) : '';
		result = {
			score: it.score,
			svg: it.svg,
			stage1_model: it.stage1_model,
			stage2_model: it.stage2_model,
			render_build_number: it.render_build_number,
			render_color_profile: it.render_color_profile,
			render_engine_id: it.render_engine_id,
			render_engine_version: it.render_engine_version,
			render_color_catalog_id: it.render_color_catalog_id,
			render_color_catalog_name: it.render_color_catalog_name,
			render_color_catalog_sub: it.render_color_catalog_sub,
			render_color_map: it.render_color_map,
			render_canvas_aspect: it.render_canvas_aspect,
			render_canvas_aspect_id: it.render_canvas_aspect_id,
			render_canvas_aspect_ratio: it.render_canvas_aspect_ratio,
			instruction_lang_requested: it.instruction_lang_requested,
			instruction_lang_resolved: it.instruction_lang_resolved,
			ui_lang: it.ui_lang,
			seed_text: it.seed_text ?? null,
			render_hash: it.render_hash,
			render_hash_short: it.render_hash_short,
			description_hash: it.description_hash,
			lineage_node_id: it.lineage_node_id,
			lineage_parent_node_id: it.lineage_parent_node_id,
			derivation_kind: it.derivation_kind as DerivationKind | null | undefined,
			derivation_metadata: it.derivation_metadata,
			render_seed: it.render_seed == null ? null : Number(it.render_seed),
			vary_seed: it.vary_seed == null ? null : Number(it.vary_seed),
			interpretation_seed: it.interpretation_seed ?? null,
			elapsed_stage1_ms: 0,
			elapsed_stage2_ms: 0,
			elapsed_total_ms: it.elapsed_ms ?? 0,
			tokens_in_stage1: null,
			tokens_out_stage1: null,
			tokens_in_stage2: null,
			tokens_out_stage2: null,
		};
		error = null;
		outputTab = preserveLineageTab ? 'lineage' : 'canvas';
		if (preserveLineageTab && it.lineage_node_id) void fetchLineage(it.lineage_node_id, true);
		fitCanvasZoom();
	}

	function openNearbyHistory(id: string): void {
		const item = nearbyHistory.find((candidate) => candidate.id === id);
		if (item) loadIterationItem(item);
	}

	const currentRenderedAt = $derived.by(() => {
		const at = displayedHistoryItem?.at ?? result?.history_at ?? null;
		return at == null ? null : new Date(at).toLocaleString(getLang() === 'ja' ? 'ja-JP' : 'en-US');
	});


	async function gotoPrev() {
		const preservedTab = outputTab;
		if (historyCursor < historyItems.length - 1) { loadIteration(historyCursor + 1); }
		else if (historyOffset + historyWindowSize < historyTotal) { await fetchHistoryOffset(historyOffset + historyWindowSize); loadIteration(0); }
		outputTab = preservedTab;
	}

	async function gotoNext() {
		const preservedTab = outputTab;
		if (historyCursor > 0) { loadIteration(historyCursor - 1); }
		else if (historyOffset > 0) { await fetchHistoryOffset(Math.max(0, historyOffset - historyWindowSize)); loadIteration(historyItems.length - 1); }
		outputTab = preservedTab;
	}

	async function gotoLatest() {
		if (historyTotal <= 0) return;
		await fetchHistoryOffset(0);
		loadIteration(0);
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
			if (profileOpen) closeProfile();
			if (settingsOpen) closeSettingsModal();
			if (catalogOpen) cancelCatalogSelection();
			historyManager.open = false;
			confirmAction = null;
		}
		if (!shouldIgnoreCanvasShortcut(e)) handleCanvasKeydown(e);
	}

	function shouldIgnoreCanvasShortcut(e: KeyboardEvent) {
		if (!currentUser || profileOpen || settingsOpen || catalogOpen || historyManager.open || confirmAction) return true;
		const target = e.target;
		if (!(target instanceof HTMLElement)) return false;
		if (target.isContentEditable) return true;
		return !!target.closest('input, textarea, select, [contenteditable="true"]');
	}

	function handleDocClick(e: MouseEvent) {
		if (pngMenuOpen  && pngWrapEl     && !pngWrapEl.contains(e.target as Node))      pngMenuOpen  = false;
		if (userMenuOpen && userMenuWrapEl && !userMenuWrapEl.contains(e.target as Node)) userMenuOpen = false;
		if (canvasAspectMenuOpen) canvasAspectMenuOpen = false;
	}

	// ── Model selection ─────────────────────────────────────
	function setStage1Provider(v: Provider) {
		displayedHistoryItem = null;
		historyCursor = -1;
		stage1Provider = v; stage1Model = modelsFor(v)[0]?.id ?? stage1Model;
	}
	function setStage1Model(v: string) {
		displayedHistoryItem = null;
		historyCursor = -1;
		stage1Model = v;
	}
	function setStage2Provider(v: Provider) {
		displayedHistoryItem = null;
		historyCursor = -1;
		stage2Provider = v; stage2Model = modelsFor(v)[0]?.id ?? stage2Model;
	}
	function setStage2Model(v: string) {
		displayedHistoryItem = null;
		historyCursor = -1;
		stage2Model = v;
	}
	function setVisionProvider(v: Provider) {
		visionProvider = v;
		visionModel = visionModelsFor(v)[0]?.id ?? visionModel;
	}
	function setVisionModel(v: string) {
		visionModel = v;
	}

	function createSafeIntegerSeed(excluded: Set<number> = new Set()): number {
		for (let attempt = 0; attempt < 32; attempt += 1) {
			let seed: number;
			if (typeof globalThis.crypto?.getRandomValues === 'function') {
				const words = new Uint32Array(2);
				globalThis.crypto.getRandomValues(words);
				seed = ((words[0] ?? 0) & 0x1fffff) * 0x100000000 + (words[1] ?? 0);
			} else {
				seed = Math.floor(Math.random() * (Number.MAX_SAFE_INTEGER + 1));
			}
			if (!excluded.has(seed)) return seed;
		}
		throw new Error('Could not allocate a unique seed');
	}

	function createInterpretationSeed(): string {
		if (typeof globalThis.crypto?.randomUUID === 'function') {
			return globalThis.crypto.randomUUID();
		}
		const bytes = new Uint8Array(16);
		if (typeof globalThis.crypto?.getRandomValues === 'function') {
			globalThis.crypto.getRandomValues(bytes);
		} else {
			for (let index = 0; index < bytes.length; index += 1) {
				bytes[index] = Math.floor(Math.random() * 256);
			}
		}
		bytes[6] = (bytes[6] & 0x0f) | 0x40;
		bytes[8] = (bytes[8] & 0x3f) | 0x80;
		const hex = Array.from(bytes, (value) => value.toString(16).padStart(2, '0')).join('');
		return [
			hex.slice(0, 8),
			hex.slice(8, 12),
			hex.slice(12, 16),
			hex.slice(16, 20),
			hex.slice(20),
		].join('-');
	}

	function buildDdlDiffParts(before: string | null, after: string | null): DdlDiffPart[] {
		const oldLines = (before ?? "").split(/\n+/).map((line) => line.trim()).filter(Boolean);
		const newLines = (after ?? "").split(/\n+/).map((line) => line.trim()).filter(Boolean);
		const parts: DdlDiffPart[] = [];
		for (const line of oldLines) {
			parts.push({ kind: newLines.includes(line) ? "same" : "removed", text: line });
		}
		for (const line of newLines) {
			if (!oldLines.includes(line)) parts.push({ kind: "added", text: line });
		}
		return parts;
	}

	const unsavedRefinementPreview = $derived(!!result && !result.lineage_node_id && !!result.lineage_parent_node_id && !!result.derivation_kind);

	function showLineageIntermediateNotice(): void {
		lineageIntermediateNotice = t().lineageIntermediateSavedNotice;
		if (lineageIntermediateNoticeTimer !== null) window.clearTimeout(lineageIntermediateNoticeTimer);
		lineageIntermediateNoticeTimer = window.setTimeout(() => {
			lineageIntermediateNotice = null;
			lineageIntermediateNoticeTimer = null;
		}, 5000);
	}

	function currentLineageParentId(): string | null {
		if (lineageDetached) return null;
		return displayedHistoryItem?.lineage_node_id ?? result?.lineage_node_id ?? null;
	}

async function ensureLineageParentId(): Promise<string | null> {
	const existing = currentLineageParentId();
	if (existing || !result || !ddl || !result.lineage_parent_node_id || !result.derivation_kind) return existing;
	const saved = await pushHistory({
		...result,
		input: input.trim(), ddl, score: result.score, svg: result.svg, at: Date.now(),
		elapsed_ms: result.elapsed_total_ms ?? 0,
		tokens_in: (result.tokens_in_stage1 ?? 0) + (result.tokens_in_stage2 ?? 0) || null,
		tokens_out: (result.tokens_out_stage1 ?? 0) + (result.tokens_out_stage2 ?? 0) || null,
	}, {
		sourceText: input.trim(), historyVisibility: 'lineage_only',
		lineageParentNodeId: result.lineage_parent_node_id,
		derivationKind: result.derivation_kind,
		derivationMetadata: result.derivation_metadata ?? {},
	});
	if (!saved?.lineage_node_id) return null;
	result = { ...result, history_id: saved.id, history_at: saved.at, lineage_node_id: saved.lineage_node_id, description_hash: saved.description_hash };
	return saved.lineage_node_id;
}

async function ensureVisibleLineageParentId(): Promise<string | null> {
	const materializingIntermediate = unsavedRefinementPreview;
	const nodeId = await ensureLineageParentId();
	if (materializingIntermediate && !nodeId) {
		error = t().lineageIntermediateSaveFailed;
		throw new Error(error);
	}
	if (materializingIntermediate) showLineageIntermediateNotice();
	return nodeId;
}

	function setSelectedCatalog(id: string) {
		displayedHistoryItem = null;
		historyCursor = -1;
		selectedCatalog = id;
	}

	async function varyPerformance() {
		if (!result || variationBusy) return;
		const parentNodeId = await ensureVisibleLineageParentId();
		variationBusy = true;
		reloading = true;
		reloadError = null;
		try {
			const usedSeeds = new Set<number>();
			if (Number.isFinite(result.render_seed ?? NaN)) usedSeeds.add(Number(result.render_seed));
			const nextSeed = createSafeIntegerSeed(usedSeeds);
			const r = await apiFetch('/api/render-svg', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({
					score: result.score,
					catalog_id: refinementCatalogId(),
					canvas_aspect: refinementCanvasAspectId(),
					render_seed: nextSeed,
				})
			});
			if (!r.ok) throw new Error(await r.text());
			const svg = await r.text();
			result = { ...result, svg, render_seed: nextSeed, render_hash: null, render_hash_short: null, history_id: null, history_at: null, lineage_node_id: null, lineage_parent_node_id: parentNodeId, derivation_kind: parentNodeId ? 'touch_variation' : null, derivation_metadata: { render_seed_from: result.render_seed ?? null, render_seed_to: nextSeed } };
			displayedHistoryItem = null;
			historyCursor = -1;
			outputTab = 'canvas';
			fitCanvasZoom();
		} catch (e) {
			reloadError = e instanceof Error ? e.message : String(e);
		} finally {
			reloading = false;
			variationBusy = false;
		}
	}

	async function varyComposition() {
		if (!result || variationBusy || loading) return;
		const source = input.trim();
		if (!source) return;
		const parentNodeId = await ensureVisibleLineageParentId();
		variationBusy = true;
		loading = true;
		error = null;
		try {
			const usedSeeds = new Set<number>();
			if (Number.isFinite(result.vary_seed ?? NaN)) usedSeeds.add(Number(result.vary_seed));
			const nextVarySeed = createSafeIntegerSeed(usedSeeds);
			const r = await paintOne(source, { varySeed: nextVarySeed, historyInput: source, sourceText: source, catalogId: refinementCatalogId(), canvasAspectId: refinementCanvasAspectId(), lineageParentNodeId: parentNodeId, derivationKind: parentNodeId ? 'layout_variation' : null, derivationMetadata: { vary_seed: nextVarySeed } });
			ddl = r.ddl;
			ddlGeneratedBaseline = r.ddl;
			thinking = r.thinking;
			result = r;
			displayedHistoryItem = null;
			elapsedStage1Ms = r.elapsed_stage1_ms;
			elapsedStage2Ms = r.elapsed_stage2_ms;
			elapsedTotalMs = r.elapsed_total_ms;
			tokensInStage1 = r.tokens_in_stage1;
			tokensOutStage1 = r.tokens_out_stage1;
			tokensInStage2 = r.tokens_in_stage2;
			tokensOutStage2 = r.tokens_out_stage2;
			outputTab = 'canvas';
			if (r.history_id) {
				await fetchHistoryOffset(0, { anchorId: r.history_id });
				displayedHistoryItem = historyItems.find((item) => item.id === r.history_id) ?? null;
			} else {
				historyCursor = -1;
			}
			fitCanvasZoom();
		} catch (e) {
			error = e instanceof Error ? e.message : String(e);
		} finally {
			loading = false;
			variationBusy = false;
			stopTimer();
		}
	}

	async function varyInterpretation() {
		if (!result || variationBusy || loading) return;
		const source = input.trim();
		if (!source) return;
		const parentNodeId = await ensureVisibleLineageParentId();
		variationBusy = true;
		loading = true;
		error = null;
		const previousDdl = ddl;
		try {
			const interpretationSeed = createInterpretationSeed();
			const r = await paintOne(source, { historyInput: source, sourceText: source, catalogId: refinementCatalogId(), canvasAspectId: refinementCanvasAspectId(), interpretationSeed, lineageParentNodeId: parentNodeId, derivationKind: parentNodeId ? 'reinterpretation' : null, derivationMetadata: { interpretation_seed: interpretationSeed } });
			interpretationDiffParts = buildDdlDiffParts(previousDdl, r.ddl);
			ddl = r.ddl;
			ddlGeneratedBaseline = r.ddl;
			thinking = r.thinking;
			result = r;
			displayedHistoryItem = null;
			elapsedStage1Ms = r.elapsed_stage1_ms;
			elapsedStage2Ms = r.elapsed_stage2_ms;
			elapsedTotalMs = r.elapsed_total_ms;
			tokensInStage1 = r.tokens_in_stage1;
			tokensOutStage1 = r.tokens_out_stage1;
			tokensInStage2 = r.tokens_in_stage2;
			tokensOutStage2 = r.tokens_out_stage2;
			outputTab = "canvas";
			if (r.history_id) {
				await fetchHistoryOffset(0, { anchorId: r.history_id });
				displayedHistoryItem = historyItems.find((item) => item.id === r.history_id) ?? null;
			} else {
				historyCursor = -1;
			}
			fitCanvasZoom();
		} catch (e) {
			error = e instanceof Error ? e.message : String(e);
		} finally {
			loading = false;
			variationBusy = false;
			stopTimer();
		}
	}

	function composeCandidateResult(source: string, baseDdl: string, data: PaintResult & { ddl: string; thinking?: string | null; elapsed_ms?: number; tokens_in?: number | null; tokens_out?: number | null }): PaintResult & { ddl: string; thinking: string | null } {
		return {
			...data,
			ddl: data.ddl,
			thinking: data.thinking ?? thinking,
			stage1_model: result?.stage1_model ?? qualifiedModelId(stage1Provider, stage1Model),
			stage2_model: data.stage2_model ?? qualifiedModelId(stage2Provider, stage2Model),
			elapsed_stage1_ms: 0,
			elapsed_stage2_ms: data.elapsed_ms ?? 0,
			elapsed_total_ms: data.elapsed_ms ?? 0,
			tokens_in_stage1: null,
			tokens_out_stage1: null,
			tokens_in_stage2: data.tokens_in ?? null,
			tokens_out_stage2: data.tokens_out ?? null,
			user_generation_count: null,
		};
	}

	function refinementCatalogId(): string {
		return result?.render_color_catalog_id ?? displayedHistoryItem?.catalog_id ?? defaultCatalogId;
	}

	function refinementCanvasAspectId(): CanvasAspectId {
		return normalizeCanvasAspectId(result?.render_canvas_aspect_id ?? result?.render_canvas_aspect ?? result?.score?.canvas ?? effectiveCanvasAspectId());
	}

	async function renderWordTouchCandidate(seedText: string, label: string, signal?: AbortSignal): Promise<VariationCandidate> {
		if (!result) throw new Error("missing result");
		const normalizedSeedText = seedText.trim();
		if (!normalizedSeedText) throw new Error(getLang() === 'ja' ? 'タッチを変える言葉を入力してください。' : 'Enter words to vary the touch.');
		const r = await apiFetch('/api/render-score', {
			method: 'POST',
			signal,
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({
				score: result.score,
				input: input.trim(),
				ddl: ddl ?? '',
				catalog_id: refinementCatalogId(),
				canvas_aspect: refinementCanvasAspectId(),
				vary_seed: result.vary_seed,
				interpretation_seed: result.interpretation_seed,
				seed_text: normalizedSeedText,
			}),
		});
		if (!r.ok) throw new Error(await r.text());
		const data = await r.json() as Partial<PaintResult> & Pick<PaintResult, 'svg' | 'score' | 'render_seed'>;
		return {
			id: `word-touch-${String(data.render_seed)}`,
			label,
			selected: false,
			result: {
				...result,
				...data,
				ddl: ddl ?? '',
				thinking,
				history_id: null,
				history_at: null,
				lineage_node_id: null,
				lineage_parent_node_id: currentLineageParentId(),
				derivation_kind: currentLineageParentId() ? 'touch_variation' : null,
				derivation_metadata: { render_seed_from: result.render_seed ?? null, render_seed_to: data.render_seed, seed_text: normalizedSeedText },
			},
		};
	}

	async function composeVariationCandidate(varySeed: number, label: string, signal?: AbortSignal): Promise<VariationCandidate> {
		const source = input.trim();
		const baseDdl = ddl ?? "";
		const r = await apiFetch("/api/compose", {
			method: "POST",
			signal,
			headers: { "Content-Type": "application/json" },
			body: JSON.stringify({
				ddl: baseDdl,
				original_text: source,
				model: qualifiedModelId(stage2Provider, stage2Model),
				instruction_lang: instructionLang,
				ui_lang: getLang(),
				catalog_id: refinementCatalogId(),
				canvas_aspect: refinementCanvasAspectId(),
				auto_repair: ddlAutoRepairEnabled,
				vary_seed: varySeed,
			})
		});
		if (!r.ok) throw new Error(await r.text());
		const data = await r.json();
		return { id: `comp-${varySeed}`, label, selected: false, result: { ...composeCandidateResult(source, baseDdl, data), lineage_parent_node_id: currentLineageParentId(), derivation_kind: currentLineageParentId() ? 'layout_variation' : null, derivation_metadata: { vary_seed: varySeed } } };
	}

	async function interpretationVariationCandidate(label: string, signal?: AbortSignal): Promise<VariationCandidate> {
		const source = input.trim();
		const interpretationSeed = createInterpretationSeed();
		const r = await paintOne(source, {
			historyInput: source,
			sourceText: source,
			saveHistory: false,
			saveArtifacts: false,
			countGeneration: false,
			catalogId: refinementCatalogId(),
			canvasAspectId: refinementCanvasAspectId(),
			interpretationSeed,
			signal,
		});
		return { id: "interp-" + interpretationSeed, label, selected: false, result: { ...r, lineage_parent_node_id: currentLineageParentId(), derivation_kind: currentLineageParentId() ? "reinterpretation" : null, derivation_metadata: { interpretation_seed: interpretationSeed } } };
	}

	function colorCatalogCandidateIds(count: 1 | 4): string[] {
		const currentId = refinementCatalogId();
		const candidates = colorCatalogs.map((catalog) => catalog.id).filter((id) => id && id !== currentId);
		for (let index = candidates.length - 1; index > 0; index -= 1) {
			const swapIndex = Math.floor(Math.random() * (index + 1));
			[candidates[index], candidates[swapIndex]] = [candidates[swapIndex], candidates[index]];
		}
		if (candidates.length === 0) throw new Error(t().refineNoAlternateCatalog);
		return Array.from({ length: count }, (_, index) => candidates[index % candidates.length]);
	}

	async function renderColorCatalogCandidate(catalogId: string, label: string, signal?: AbortSignal): Promise<VariationCandidate> {
		if (!result) throw new Error("missing result");
		const source = input.trim();
		const fromCatalogId = refinementCatalogId();
		const r = await apiFetch("/api/render-score", {
			method: "POST",
			signal,
			headers: { "Content-Type": "application/json" },
			body: JSON.stringify({
				score: result.score,
				input: source,
				ddl: ddl ?? "",
				catalog_id: catalogId,
				canvas_aspect: refinementCanvasAspectId(),
				render_seed: result.render_seed,
				vary_seed: result.vary_seed,
				interpretation_seed: result.interpretation_seed,
			}),
		});
		if (!r.ok) throw new Error(await r.text());
		const data = await r.json() as Partial<PaintResult> & Pick<PaintResult, "svg" | "score">;
		return {
			id: "catalog-" + catalogId + "-" + label,
			label,
			selected: false,
			result: {
				...result,
				...data,
				ddl: ddl ?? "",
				thinking,
				history_id: null,
				history_at: null,
				lineage_node_id: null,
				lineage_parent_node_id: currentLineageParentId(),
				derivation_kind: currentLineageParentId() ? "catalog_change" : null,
				derivation_metadata: { catalog_id_from: fromCatalogId, catalog_id_to: catalogId },
			},
		};
	}

	async function generateVariationCandidates(kind: RefineKind, count: 1 | 4, touchWords?: string) {
		if (!result || variationGridBusy || loading) return;
		const source = input.trim();
		if (!source || !ddl) return;
		const normalizedTouchWords = touchWords?.trim() ?? '';
		if (kind === 'touch' && !normalizedTouchWords) {
			variationGridStatus = getLang() === 'ja' ? 'タッチを変える言葉を入力してください。' : 'Enter words to vary the touch.';
			return;
		}
		if (kind === 'touch' && count === 4) {
			variationGridStatus = getLang() === 'ja' ? '同じ言葉は同じタッチ(Seed)になります。1案だけ生成可能です。' : 'The same words produce the same touch (Seed). Only one option can be generated.';
			return;
		}
		const contextVersion = targetContextVersion;
		await ensureVisibleLineageParentId();
		if (contextVersion !== targetContextVersion) return;
		const abortController = new AbortController();
		variationGridAbortController = abortController;
		variationGridBusy = true;
		variationGridCanAbort = false;
		variationGridIncludesReading = kind === "reading";
		variationGridTaskLabel = kind === "touch"
			? t().canvasVaryPerformance
			: kind === "layout"
				? t().canvasVaryComposition
				: kind === "reading"
					? t().canvasVaryInterpretation
					: t().canvasVaryColor;
		variationGridStatus = null;
		const abortTimer = window.setTimeout(() => {
			if (variationGridAbortController === abortController && variationGridBusy) variationGridCanAbort = true;
		}, 3000);
		try {
			const usedVarySeeds = new Set<number>();
			if (Number.isFinite(result.vary_seed ?? NaN)) usedVarySeeds.add(Number(result.vary_seed));
			for (const candidate of variationCandidates) {
				if (Number.isFinite(candidate.result.vary_seed ?? NaN)) usedVarySeeds.add(Number(candidate.result.vary_seed));
			}
			const catalogIds = kind === "color" ? colorCatalogCandidateIds(count) : [];
			const jobs = Array.from({ length: count }, (_, index) => {
				const sequence = index + 1;
				if (kind === "touch") {
					return renderWordTouchCandidate(normalizedTouchWords, t().canvasVaryPerformance, abortController.signal);
				}
				if (kind === "layout") {
					const varySeed = createSafeIntegerSeed(usedVarySeeds);
					usedVarySeeds.add(varySeed);
					return composeVariationCandidate(varySeed, t().canvasVaryComposition + " " + sequence, abortController.signal);
				}
				if (kind === "reading") {
					return interpretationVariationCandidate(t().canvasVaryInterpretation + " " + sequence, abortController.signal);
				}
				const catalogId = catalogIds[index];
				return renderColorCatalogCandidate(catalogId, t().canvasVaryColor + " " + sequence + " · " + catalogName(catalogId), abortController.signal);
			});
			variationCandidates = await Promise.all(jobs);
		} catch (e) {
			if (!(e instanceof DOMException && e.name === "AbortError")) variationGridStatus = e instanceof Error ? e.message : String(e);
		} finally {
			window.clearTimeout(abortTimer);
			if (variationGridAbortController === abortController) {
				variationGridAbortController = null;
				variationGridBusy = false;
				variationGridCanAbort = false;
			}
		}
	}

	function abortVariationCandidates() { variationGridAbortController?.abort(); }

	function toggleVariationCandidate(id: string) {
		variationCandidates = variationCandidates.map((candidate) => candidate.id === id ? { ...candidate, selected: !candidate.selected } : candidate);
	}

	function showVariationCandidate(candidate: VariationCandidate) {
		resetTargetScopedState({ preserveVariationCandidates: true });
		historyCursor = -1;
		ddl = candidate.result.ddl;
		ddlGeneratedBaseline = candidate.result.ddl;
		thinking = candidate.result.thinking;
		result = candidate.result;
		displayedHistoryItem = null;
		outputTab = "canvas";
		fitCanvasZoom();
	}

	async function saveSelectedVariationCandidates() {
		const contextVersion = targetContextVersion;
		const selected = variationCandidates.filter((candidate) => candidate.selected && !candidate.saved);
		if (selected.length === 0) {
			variationGridStatus = t().variationGridEmpty;
			return;
		}
		variationGridBusy = true;
		variationGridStatus = null;
		try {
			for (const candidate of selected) {
				const saved = await pushHistory({
					...candidate.result,
					input: input.trim(),
					ddl: candidate.result.ddl,
					score: candidate.result.score,
					svg: candidate.result.svg,
					at: Date.now(),
					elapsed_ms: candidate.result.elapsed_total_ms ?? 0,
					stage1_model: candidate.result.stage1_model ?? null,
					stage2_model: candidate.result.stage2_model ?? null,
					tokens_in: (candidate.result.tokens_in_stage1 ?? 0) + (candidate.result.tokens_in_stage2 ?? 0) || null,
					tokens_out: (candidate.result.tokens_out_stage1 ?? 0) + (candidate.result.tokens_out_stage2 ?? 0) || null,
					catalog_id: candidate.result.render_color_catalog_id ?? selectedCatalog,
				}, { countGeneration: true, sourceText: input.trim(), lineageParentNodeId: candidate.result.lineage_parent_node_id ?? null, derivationKind: candidate.result.derivation_kind ?? null, derivationMetadata: candidate.result.derivation_metadata ?? {} });
				if (contextVersion !== targetContextVersion) return;
				variationCandidates = variationCandidates.map((item) => item.id === candidate.id ? { ...item, saved: true, selected: false } : item);
				if (saved?.id && result === candidate.result) {
					result = { ...result, history_id: saved.id, history_at: saved.at, render_hash: saved.render_hash, render_hash_short: saved.render_hash_short, description_hash: saved.description_hash, lineage_node_id: saved.lineage_node_id };
					displayedHistoryItem = saved;
					void syncHistoryStripToItem(saved);
				}
			}
		} finally {
			if (contextVersion === targetContextVersion) variationGridBusy = false;
		}
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
	async function downloadSVG(profile: SvgProfile = 'display') {
		if (!result) return;
		let svg = result.svg;
		if (profile === 'display') {
			const desc = `<desc>${escapeXml(input)}</desc>`;
			svg = result.svg.replace(/(<svg[^>]*>)/, `$1${desc}`);
		} else if (displayedHistoryItem?.id) {
			const r = await apiFetch(`/api/history/${displayedHistoryItem.id}/svg?profile=${profile}`);
			if (!r.ok) throw new Error(await r.text());
			svg = await r.text();
		} else {
			const r = await apiFetch('/api/render-svg', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({
					score: result.score,
					catalog_id: refinementCatalogId(),
					canvas_aspect: refinementCanvasAspectId(),
					svg_profile: profile
				})
			});
			if (!r.ok) throw new Error(await r.text());
			svg = await r.text();
		}
		triggerDownload(new Blob([svg], { type: 'image/svg+xml' }), exportFilename(profile === 'display' ? 'svg' : `${profile}.svg`));
	}

	async function downloadPNG(size: number) {
		if (!result) return;
		const aspect = getCanvasAspectOption(effectiveCanvasAspectId());
		const pngHeight = Math.max(64, Math.round(size));
		const pngWidth = Math.max(64, Math.round(pngHeight * aspect.ratioW / aspect.ratioH));
		let svg = result.svg.replace(/(<svg)([^>]*)/, (_: string, tag: string, attrs: string) => {
			const a = attrs.replace(/\s+width="[^"]*"/g, '').replace(/\s+height="[^"]*"/g, '');
			return `${tag}${a} width="${pngWidth}" height="${pngHeight}"`;
		});
		const blob = new Blob([svg], { type: 'image/svg+xml' });
		const url  = URL.createObjectURL(blob);
		try {
			await new Promise<void>((resolve, reject) => {
				const canvas = document.createElement('canvas');
				canvas.width = pngWidth; canvas.height = pngHeight;
				const ctx = canvas.getContext('2d')!;
				if (!pngAlphaWhite) {
					ctx.fillStyle = '#ffffff'; ctx.fillRect(0, 0, pngWidth, pngHeight);
				}
				const img = new Image();
				img.onload = () => {
					ctx.drawImage(img, 0, 0, pngWidth, pngHeight);
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

	async function copyTextToClipboard(value: string): Promise<void> {
		if (navigator.clipboard?.writeText) {
			await navigator.clipboard.writeText(value);
			return;
		}
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

	async function copyPromptText(kind: CopyKind, text: string | null | undefined): Promise<void> {
		try {
			await copyTextToClipboard(text ?? '');
			copiedPrompt = kind;
			window.setTimeout(() => {
				if (copiedPrompt === kind) copiedPrompt = null;
			}, 1200);
		} catch {
			copiedPrompt = null;
		}
	}

	async function copyStatusHash(): Promise<void> {
		const value = statusHashFull;
		if (!value) return;
		try {
			await copyTextToClipboard(value);
			statusHashCopied = true;
			window.setTimeout(() => {
				statusHashCopied = false;
			}, 1200);
		} catch {
			statusHashCopied = false;
		}
	}

	function displayLatestBatchRender(): void {
		if (!batchLatestResult) return;
		result = batchLatestResult;
		ddl = batchLatestDdl;
		ddlGeneratedBaseline = batchLatestDdl;
		ddlSelection = { start: batchLatestDdl?.length ?? 0, end: batchLatestDdl?.length ?? 0 };
		thinking = batchLatestThinking;
		outputTab = 'canvas';
		fitCanvasZoom();
	}

	function resumeBatchLatestFollow(): void {
		resetTargetScopedState();
		batchAutoFollowLatest = true;
		displayedHistoryItem = null;
		historyCursor = -1;
		displayLatestBatchRender();
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
		const bareModel = m.includes(':') ? m.split(':').slice(1).join(':') : m;
		const model = modelsFor(providerOfModel(m)).find((option) => option.id === m || option.id === bareModel);
		return model?.label ?? m;
	}

	function catalogName(id: string | null | undefined): string {
		return catalogById(colorCatalogs, id ?? defaultCatalogId)?.name ?? 'inku Default';
	}

	function svgAspect(svg: string | null | undefined): { ratioW: number; ratioH: number } | null {
		if (!svg) return null;
		const viewBox = svg.match(/\bviewBox="[^"]*?([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)"/);
		if (viewBox) {
			const width = Number(viewBox[3]);
			const height = Number(viewBox[4]);
			if (width > 0 && height > 0) return { ratioW: width, ratioH: height };
		}
		const widthMatch = svg.match(/\bwidth="([\d.]+)"/);
		const heightMatch = svg.match(/\bheight="([\d.]+)"/);
		const width = widthMatch ? Number(widthMatch[1]) : 0;
		const height = heightMatch ? Number(heightMatch[1]) : 0;
		return width > 0 && height > 0 ? { ratioW: width, ratioH: height } : null;
	}

	const statusStage1Model = $derived(displayedHistoryItem
		? (displayedHistoryItem.stage1_model ? statusModelName(displayedHistoryItem.stage1_model) : '-')
		: (result?.stage1_model ? statusModelName(result.stage1_model) : '-'));
	const statusStage2Model = $derived(displayedHistoryItem
		? (displayedHistoryItem.stage2_model ? statusModelName(displayedHistoryItem.stage2_model) : '-')
		: (result?.stage2_model ? statusModelName(result.stage2_model) : '-'));
	const nextStage1Model = $derived(statusModelName(qualifiedModelId(stage1Provider, stage1Model)));
	const nextStage2Model = $derived(statusModelName(qualifiedModelId(stage2Provider, stage2Model)));
	const nextCatalogName = $derived(currentCatalog.name);
	const statusCatalogName = $derived(displayedHistoryItem
		? (displayedHistoryItem.render_color_catalog_name ?? catalogName(displayedHistoryItem.render_color_catalog_id ?? displayedHistoryItem.catalog_id))
		: (result?.render_color_catalog_name ?? (result?.render_color_catalog_id ? catalogName(result.render_color_catalog_id) : '-')));
	const currentCanvasAspect = $derived(getCanvasAspectOption(effectiveCanvasAspectId()));
	const nextCanvasName = $derived(currentCanvasAspect.label);
	const displayCanvasAspect = $derived(svgAspect(result?.svg) ?? currentCanvasAspect);
	const statusCanvasName = $derived.by(() => {
		const canvasId = displayedHistoryItem?.render_canvas_aspect_id ?? displayedHistoryItem?.render_canvas_aspect ?? displayedHistoryItem?.score?.canvas ?? result?.render_canvas_aspect_id ?? result?.render_canvas_aspect ?? result?.score?.canvas ?? null;
		return canvasId ? getCanvasAspectOption(canvasId).label : '-';
	});
	const statusHashFull = $derived(
		displayedHistoryItem?.render_hash
			?? result?.render_hash
			?? ''
	);
	const statusHashLabel = $derived((
		displayedHistoryItem?.render_hash_short
			?? displayedHistoryItem?.render_hash?.slice(-4)
			?? result?.render_hash_short
			?? result?.render_hash?.slice(-4)
			?? ''
	).toUpperCase());
	const statusHistoryItem = $derived.by(() => {
		if (displayedHistoryItem) return displayedHistoryItem;
		if (result?.history_id) {
			return historyItems.find((item) => item.id === result?.history_id) ?? {
				id: result.history_id,
				starred: false,
			};
		}
		if (inputMode === 'demo' || activeRunMode === 'demo') return null;
		return historyCursor >= 0 && historyItems[historyCursor] ? historyItems[historyCursor] : null;
	});
	const statusGeneration = $derived(((statusHistoryItem as { lineage_generation?: number | null } | null)?.lineage_generation) ?? null);

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

	function historyModelStage1Short(it: Iteration): string {
		return it.stage1_model ? shortModel(it.stage1_model) : '-';
	}

	function historyModelStage1Full(it: Iteration): string {
		return it.stage1_model ? statusModelName(it.stage1_model) : '-';
	}

	function historyModelStage2Full(it: Iteration): string {
		return it.stage2_model ? statusModelName(it.stage2_model) : '-';
	}

	function historyPreviewText(text: string): string {
		return text.length > 42 ? `${text.slice(0, 42)}...` : text;
	}

	function historyIndexLabel(index: number): number {
		return historyOffset + index + 1;
	}

	function openHistoryManager() {
		if (demoRunning) return;
		historyManager.openWith(historyItems, historyTotal, trashTotal);
	}

	function setHistoryStarredOnly(value: boolean) {
		historyStarredOnly = value;
		historyOffset = 0;
		historyCursor = -1;
		void fetchHistoryOffset(0);
	}

	$effect(() => {
		const q = historyManager.search.trim();
		if (!historyManager.open) return;
		historyManager.view;
		const handle = setTimeout(() => {
			untrack(() => { historyManager.searchChanged(q); });
		}, q ? 250 : 0);
		return () => clearTimeout(handle);
	});

	const tokenSummary = $derived.by(() =>
		t().tokenSummary(tokensInStage1, tokensOutStage1, tokensInStage2, tokensOutStage2)
	);
	function tokenPair(input: number | null, output: number | null): string {
		return `${input ?? '-'}→${output ?? '-'}tok`;
	}
	function totalTokenPair(
		firstIn: number | null,
		firstOut: number | null,
		secondIn: number | null,
		secondOut: number | null,
	): string {
		const hasInput = firstIn !== null || secondIn !== null;
		const hasOutput = firstOut !== null || secondOut !== null;
		const input = hasInput ? (firstIn ?? 0) + (secondIn ?? 0) : null;
		const output = hasOutput ? (firstOut ?? 0) + (secondOut ?? 0) : null;
		return tokenPair(input, output);
	}
	const scoreJsonPayload = $derived.by(() => {
		if (!result) return null;
		const payload: Record<string, unknown> = {};
		if (result.stage1_model !== undefined) payload.stage1_model = result.stage1_model;
		if (result.stage2_model !== undefined) payload.stage2_model = result.stage2_model;
		if (result.render_build_number !== undefined) payload.render_build_number = result.render_build_number;
		if (result.render_color_profile !== undefined) payload.render_color_profile = result.render_color_profile;
		if (result.render_engine_id !== undefined) payload.render_engine_id = result.render_engine_id;
		if (result.render_engine_version !== undefined) payload.render_engine_version = result.render_engine_version;
		if (result.render_canvas_aspect !== undefined) payload.render_canvas_aspect = result.render_canvas_aspect;
		if (result.render_canvas_aspect_id !== undefined) payload.render_canvas_aspect_id = result.render_canvas_aspect_id;
		if (result.render_canvas_aspect_ratio !== undefined) payload.render_canvas_aspect_ratio = result.render_canvas_aspect_ratio;
		if (result.instruction_lang_requested !== undefined) payload.instruction_lang_requested = result.instruction_lang_requested;
		if (result.instruction_lang_resolved !== undefined) payload.instruction_lang_resolved = result.instruction_lang_resolved;
		if (result.seed_text !== undefined) payload.seed_text = result.seed_text;
		const derivationMetadata = result.derivation_metadata ?? {};
		const resolvedLang = result.instruction_lang_resolved ?? null;
		payload.stage1_instruction_lang = typeof derivationMetadata.stage1_language === 'string' ? derivationMetadata.stage1_language : resolvedLang;
		payload.stage2_instruction_lang = typeof derivationMetadata.stage2_language === 'string' ? derivationMetadata.stage2_language : resolvedLang;
		if (result.ui_lang !== undefined) payload.ui_lang = result.ui_lang;
		if (result.render_hash !== undefined) payload.render_hash = result.render_hash;
		if (result.render_hash_short !== undefined) payload.render_hash_short = result.render_hash_short;
		if (result.render_color_catalog_id !== undefined) payload.render_color_catalog_id = result.render_color_catalog_id;
		if (result.render_color_catalog_name !== undefined) payload.render_color_catalog_name = result.render_color_catalog_name;
		if (result.render_color_catalog_sub !== undefined) payload.render_color_catalog_sub = result.render_color_catalog_sub;
		if (result.render_color_map !== undefined) payload.render_color_map = result.render_color_map;
		if (result.render_seed !== undefined) payload.render_seed = result.render_seed;
		if (result.vary_seed !== undefined) payload.vary_seed = result.vary_seed;
		if (result.interpretation_seed !== undefined) payload.interpretation_seed = result.interpretation_seed;
		if (result.description_hash !== undefined) payload.description_hash = result.description_hash;
		payload.elapsed_ms = displayedHistoryItem?.elapsed_ms ?? result.elapsed_total_ms;
		payload.tokens_in = displayedHistoryItem?.tokens_in ?? ((result.tokens_in_stage1 ?? 0) + (result.tokens_in_stage2 ?? 0) || null);
		payload.tokens_out = displayedHistoryItem?.tokens_out ?? ((result.tokens_out_stage1 ?? 0) + (result.tokens_out_stage2 ?? 0) || null);
		if (result.derivation_kind !== undefined) payload.derivation_kind = result.derivation_kind;
		if (result.derivation_metadata !== undefined) payload.derivation_metadata = result.derivation_metadata;
		payload.score = result.score;
		return payload;
	});
	const scoreJsonText = $derived(scoreJsonPayload ? JSON.stringify(scoreJsonPayload, null, 2) : '');
	const scoreJsonLines = $derived(scoreJsonText ? scoreJsonText.split('\n') : []);
	const scoreJsonHighlightedLines = $derived(scoreJsonLines.map(highlightJsonLine));
	const scoreJsonHighlighted = $derived(scoreJsonHighlightedLines.join('\n'));
	const scoreJsonSeparatorLine = $derived.by(() => {
		const index = scoreJsonLines.findIndex((line) => line.startsWith('  "score"'));
		return index >= 0 ? index : null;
	});
	const ddlHighlighted = $derived(ddl !== null
		? highlightDDL(ddl, ddlFocused && ddlSelection.start === ddlSelection.end ? ddlSelection.start : null)
		: '');
	const batchActiveDdlHighlighted = $derived(batchActiveDdl !== null
		? highlightDDL(batchActiveDdl)
		: escapeHtml(t().batchActiveDdlPending));
	const demoGeneratedDdlHighlighted = $derived(demoGeneratedDdl !== null
		? highlightDDL(demoGeneratedDdl)
		: '');

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
			case 'Nature': return 'plugin';
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
		windowHeight = window.innerHeight;
		function onResize() {
			windowWidth = window.innerWidth;
			windowHeight = window.innerHeight;
		}
		window.addEventListener('resize', onResize);
		document.addEventListener('keydown', handleKeydown, true);
		const externalHistoryRefreshTimer = window.setInterval(() => {
			void refreshHistoryForExternalSave();
		}, EXTERNAL_HISTORY_REFRESH_MS);
		function onHistoryVisibilityChange() {
			if (document.visibilityState === 'visible') void refreshHistoryForExternalSave(true);
		}
		function onHistoryWindowFocus() {
			void refreshHistoryForExternalSave(true);
		}
		document.addEventListener('visibilitychange', onHistoryVisibilityChange);
		window.addEventListener('focus', onHistoryWindowFocus);

		initLang();
		try {
			const p1 = localStorage.getItem(PROVIDER_STAGE1_KEY) as Provider | null; if (p1) stage1Provider = p1;
			const m1 = localStorage.getItem(MODEL_STAGE1_KEY); if (m1) stage1Model = m1;
			const p2 = localStorage.getItem(PROVIDER_STAGE2_KEY) as Provider | null; if (p2) stage2Provider = p2;
			const m2 = localStorage.getItem(MODEL_STAGE2_KEY); if (m2) stage2Model = m2;
			const cat = localStorage.getItem(CATALOG_KEY); if (cat) selectedCatalog = cat;
			const kiwi = localStorage.getItem(SHOW_KIWI_KEY);
			const birds = localStorage.getItem(SHOW_BIRDS_KEY);
			if (kiwi !== null) showKiwi = kiwi !== '0';
			else if (birds !== null) showKiwi = birds !== '0';
			const crab = localStorage.getItem(SHOW_CRAB_KEY); if (crab !== null) showCrab = crab !== '0';
			const alpha = localStorage.getItem(PNG_ALPHA_KEY); if (alpha !== null) pngAlphaWhite = alpha === '1';
			const replay = localStorage.getItem(SAVE_REPLAY_KEY); if (replay !== null) saveReplayAsNewVersion = replay !== '0';
			historySelectionCanvas = normalizeHistorySelectionBehavior(localStorage.getItem(HISTORY_SELECTION_CANVAS_KEY));
			historySelectionCatalog = normalizeHistorySelectionBehavior(localStorage.getItem(HISTORY_SELECTION_CATALOG_KEY));
			const savedBatchFailureReport = loadBatchFailureReport();
			setBatchFailureReport(savedBatchFailureReport);
			miscSettingsLoaded = true;
		} catch {}
		void (async () => {
			await Promise.all([loadColorCatalogs(), loadCurrentUser(), fetchPrompts()]);
		})();

		return () => {
			window.removeEventListener('resize', onResize);
			document.removeEventListener('keydown', handleKeydown, true);
			window.clearInterval(externalHistoryRefreshTimer);
			document.removeEventListener('visibilitychange', onHistoryVisibilityChange);
			window.removeEventListener('focus', onHistoryWindowFocus);
		};
	});

	$effect(() => { const _lang = getLang(); fetchPrompts(); });
	$effect(() => {
		showKiwi; showCrab; pngAlphaWhite; saveReplayAsNewVersion; historySelectionCanvas; historySelectionCatalog;
		if (miscSettingsLoaded) persistMiscSettings();
	});
	$effect(() => {
		if (typeof document === 'undefined') return;
		document.documentElement.dataset.theme = darkMode ? 'dark' : 'light';
	});
	$effect(() => {
		const mode = inputMode;
		const wasMode = previousInputMode;
		if (mode === wasMode) return;
		previousInputMode = mode;
		if (mode === 'batch' && (activeRunMode === 'batch' || batchLatestResult)) {
			untrack(resumeBatchLatestFollow);
		} else if (wasMode === 'batch') {
			batchAutoFollowLatest = false;
		}
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
	<AppRail
		{currentUser}
		bind:userMenuOpen
		bind:userMenuWrapEl
		{settingsOpen}
		{darkMode}
		buildNumber={__BUILD_NUMBER__}
		onToggleUserMenu={() => (userMenuOpen = !userMenuOpen)}
		onOpenProfile={openProfile}
		onLogout={logout}
		onOpenSettings={() => openSettings()}
		onToggleTheme={() => void updateUiTheme(!darkMode)}
		onOpenAppInfo={() => (appInfoOpen = true)}
	/>

	<!-- ══ BODY ══ -->
	<div class="main-shell">
		<div class="body">
			<!-- ── LEFT PANEL ── -->
			{#if !leftPanelCollapsed}
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
						singleDdlReady={ddl !== null}
						{batchActiveLine}
						{batchActiveDdlHighlighted}
						{batchTotal}
						{batchCurrent}
						{batchActiveTokensIn}
						{batchActiveTokensOut}
						{batchTokensInTotal}
						{batchTokensOutTotal}
						{liveMs}
						{batchFailureReport}
						{batchPromptHistory}
						bind:batchRandomColorCatalog
						bind:demoSettings
						demoModelProviderGroups={availableModelCatalog}
						{demoRunning}
						{demoWaitingSeconds}
						{demoCurrentLiveMs}
						{demoCurrentElapsedMs}
						{demoCurrentTokensIn}
						{demoCurrentTokensOut}
						{demoTotalElapsedMs}
						{demoTotalTokensIn}
						{demoTotalTokensOut}
						{demoRenderCount}
						{demoGeneratedPrompt}
						{demoGeneratedDdlHighlighted}
						{demoCanSaveCurrent}
						{demoSavingCurrent}
						{demoSaveStatus}
						{demoError}
						lockNonDemo={demoRunning}
						{canSubmit}
						generationDisabled={variationGridBusy}
						{error}
						{stageLabel}
						{showKiwi}
						{showCrab}
						{canvasAspectEnabled}
						{canvasAspectId}
						{canvasAspectMenuOpen}
						stage1ModelLabel={availableModelCatalog.find((group) => group.id === stage1Provider)?.models.find((model) => model.id === stage1Model)?.label ?? stage1Model}
						stage2ModelLabel={availableModelCatalog.find((group) => group.id === stage2Provider)?.models.find((model) => model.id === stage2Model)?.label ?? stage2Model}
						{nextStage1Model}
						{nextStage2Model}
						{nextCatalogName}
						{nextCanvasName}
						onToggleCanvasAspectMenu={() => (canvasAspectMenuOpen = !canvasAspectMenuOpen)}
						onSelectCanvasAspect={selectCanvasAspect}
						onOpenModelSelection={() => openModelSelection(false)}
						onOpenLlmModelSelection={() => openModelSelection(false)}
						onOpenCatalogModal={openCatalogModal}
						onClearInput={clearInput}
						onRememberBatchPrompt={rememberBatchPrompt}
						onDemoSettingsChange={saveDemoSettings}
						onSaveCurrentDemo={saveCurrentDemoToHistory}
						onStartDemo={startDemo}
						onStopDemo={stopDemo}
						onSubmit={requestSubmit}
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

					<!-- DDL ツール -->
					{#if inputMode === 'single'}
						<section class="panel-section ddl-tools-section">
							<button class="ddl-new-btn" type="button" onclick={openNewDdlDialog}>{t().ddlNewButton}</button>
						</section>
					{/if}

					<!-- 解釈 (正規化DDL・閲覧専用) -->
					{#if ddl !== null && inputMode === 'single'}
						<section class="panel-section">
							<DdlViewer {ddl} label={t().ddlLabel} saijikiLabel={t().saijikiToggleBtn} onToggleSaijiki={() => (saijikiOpen = !saijikiOpen)} />
						</section>
					{/if}

					{#if interpretationDiffParts.length > 0 && inputMode === "single"}
						<section class="panel-section interpretation-diff">
							{#each interpretationDiffParts as part}
								<div class:removed={part.kind === "removed"} class:added={part.kind === "added"} class:same={part.kind === "same"}>{part.kind === "removed" ? "−" : part.kind === "added" ? "+" : " "} {part.text}</div>
							{/each}
						</section>
					{/if}

					<!-- 統計 -->
					{#if result && elapsedTotalMs > 0}
						<section class="panel-section stats-section">
							<button class="stats-toggle" onclick={() => (statsOpen = !statsOpen)}>
								<span class="stats-arrow" class:open={statsOpen}>▶</span>
								<span>{t().resultLogLabel}</span>
							</button>
							{#if statsOpen}
								<div class="stats-detail">
									<div class="stats-grid">
										{#if elapsedStage1Ms > 0}
											<div class="stats-row">
												<span class="stats-key">{t().statsInterp}</span>
												<span class="stats-value">
													<span><span class="stats-metric-label">{t().statsElapsed}</span>{(elapsedStage1Ms / 1000).toFixed(1)}s</span>
													<span><span class="stats-metric-label">{t().statsTokens}</span>{tokenPair(tokensInStage1, tokensOutStage1)}</span>
												</span>
											</div>
										{/if}
										<div class="stats-row">
											<span class="stats-key">{t().statsStruct}</span>
											<span class="stats-value">
												<span><span class="stats-metric-label">{t().statsElapsed}</span>{(elapsedStage2Ms / 1000).toFixed(1)}s</span>
												<span><span class="stats-metric-label">{t().statsTokens}</span>{tokenPair(tokensInStage2, tokensOutStage2)}</span>
											</span>
										</div>
										<div class="stats-row stats-total">
											<span class="stats-key">{t().statsTotal}</span>
											<span class="stats-value">
												<span><span class="stats-metric-label">{t().statsElapsed}</span>{(elapsedTotalMs / 1000).toFixed(1)}s</span>
												<span><span class="stats-metric-label">{t().statsTokens}</span>{totalTokenPair(tokensInStage1, tokensOutStage1, tokensInStage2, tokensOutStage2)}</span>
											</span>
										</div>
									</div>
								</div>
							{/if}
						</section>
					{/if}

				</div><!-- /panel-scroll -->
			</div><!-- /left-panel -->
			{/if}

			<button
				class="left-rail-toggle"
				onclick={() => (leftPanelCollapsed = !leftPanelCollapsed)}
				title={leftPanelCollapsed ? (getLang() === 'ja' ? '記述エリアを開く' : 'Open input area') : (getLang() === 'ja' ? '記述エリアを畳む' : 'Collapse input area')}
				aria-label={leftPanelCollapsed ? (getLang() === 'ja' ? '記述エリアを開く' : 'Open input area') : (getLang() === 'ja' ? '記述エリアを畳む' : 'Collapse input area')}
				aria-expanded={!leftPanelCollapsed}
			>{leftPanelCollapsed ? '›' : '‹'}</button>

			<CanvasPanel
				bind:outputTab
				bind:promptStage1Expanded
				bind:promptStage2Expanded
				bind:pngMenuOpen
				bind:pngWrapEl
				{result}
				{nearbyHistory}
				onOpenNearbyHistory={openNearbyHistory}
				{unsavedRefinementPreview}
				{lineageIntermediateNotice}
				allowEmptyOutputTabs={inputMode === 'demo' || activeRunMode === 'demo'}
				{currentRenderedAt}
				{nextDisabled}
				{prevDisabled}
				{historyTotal}
				{navPos}
				canvasAspectWidth={displayCanvasAspect.ratioW}
				canvasAspectHeight={displayCanvasAspect.ratioH}
				{zoom}
				actualZoom={canvasFitZoom * zoom}
				canPan={zoom > 1}
				{panX}
				{panY}
				{canvasDragging}
				{promptsData}
				stage1PromptText={stage1UserPrompt || (inputMode === 'single' ? input : inputMode === 'batch' ? batchInput : demoGeneratedPrompt)}
				instructionText={currentInstructionText}
				{ddl}
				{copiedPrompt}
				{scoreJsonText}
				{scoreJsonLines}
				{scoreJsonHighlighted}
				{scoreJsonSeparatorLine}
				{statusStage1Model}
				{statusStage2Model}
				visionModel={qualifiedModelId(visionProvider, visionModel)}
				{okugakiModel}
				visionProviderGroups={availableVisionModelCatalog}
				{statusCatalogName}
				{statusCanvasName}
				{statusGeneration}
				{statusHistoryItem}
				{statusHashLabel}
				{statusHashCopied}
				onGotoNext={gotoNext}
				onGotoPrev={gotoPrev}
				onGotoLatest={gotoLatest}
				onPointerDown={startCanvasDrag}
				onPointerMove={moveCanvasDrag}
				onPointerUp={endCanvasDrag}
				onSetZoom={setZoom}
				onResetZoom={resetZoom}
				onFitZoomChange={updateCanvasFitZoom}
				onCopyPromptText={copyPromptText}
				onCopyStatusHash={copyStatusHash}
				onToggleStar={toggleHistoryStar}
				onDownloadSVG={downloadSVG}
				onDownloadPNG={downloadPNG}
				onVaryPerformance={varyPerformance}
				onVaryComposition={varyComposition}
				onVaryInterpretation={varyInterpretation}
				bind:instructionCaptionVisible
				onInstructionCaptionVisibleChange={persistInstructionCaptionVisible}
				{variationBusy}
				{variationCandidates}
				{variationGridBusy}
				{variationGridCanAbort}
				{variationGridIncludesReading}
				{variationGridTaskLabel}
				{variationGridStatus}
				bind:touchSeedText
				onGenerateVariationCandidates={generateVariationCandidates}
				onAbortVariationCandidates={abortVariationCandidates}
				onSaveSelectedVariationCandidates={saveSelectedVariationCandidates}
				onShowVariationCandidate={showVariationCandidate}
				onToggleVariationCandidate={toggleVariationCandidate}
				{activeComparisonItem}
				modelInspectionTargetModel={modelInspectionTargetModel}
				modelInspectionTargetStage1Model={modelInspectionTargetStage1Model}
				modelInspectionTargetStage2Model={modelInspectionTargetStage2Model}
				{modelCompareMode}
				{modelCompareFixedModel}
				{modelInspectionChoices}
				{modelInspectionSelectedModels}
				{modelInspectionFailedModels}
				{modelInspectionBusy}
				{modelInspectionStatus}
				{modelInspectionResults}
				onToggleModelInspectionModel={toggleModelInspectionModel}
				onSetModelCompareMode={setModelCompareMode}
				onSetModelCompareFixedModel={setModelCompareFixedModel}
				isModelInspectionChoiceBlocked={isModelInspectionChoiceBlocked}
				onRunModelInspection={runModelInspection}
				onAdoptModelInspectionResult={(item) => saveModelInspectionResult(item)}
				onToggleModelInspectionStar={(item) => saveModelInspectionResult(item, { star: true })}
				{languageInspectionTargetLang}
				{languageCompareMode}
				{languageCompareFixedLang}
				{languageInspectionSelectedLangs}
				{languageInspectionBusy}
				{languageInspectionStatus}
				{languageInspectionResults}
				onSetLanguageCompareMode={setLanguageCompareMode}
				onSetLanguageCompareFixedLang={setLanguageCompareFixedLang}
				onToggleLanguageInspectionLang={toggleLanguageInspectionLang}
				{isLanguageInspectionChoiceBlocked}
				onRunLanguageInspection={runLanguageInspection}
				onAdoptLanguageInspectionResult={(item) => saveModelInspectionResult(item)}
				onToggleLanguageInspectionStar={(item) => saveModelInspectionResult(item, { star: true })}
				{lineageGraph}
				{lineageLoading}
				{lineageError}
				isJapanese={getLang() === 'ja'}
				onOpenLineageNode={openLineageNode}
				onDrawLineageDescription={drawLineageDescriptionEdit}
				onDrawLineageDdl={drawLineageDdlEdit}
				onOpenLineageDdlEditor={openLineageDdlEditor}
				onCloseRefinement={refreshLineageAfterRefine}
				statusDdlOrigin={statusDdlOrigin}
				onSaveOkugakiModel={persistOkugakiModel}
				onSaveVisionModel={persistVisionModel}
				onPromoteLineageNode={promoteLineageNode}
				onSaveLineageNote={saveLineageNote}
				onAskTrashLineage={askTrash}
				onDetachLineage={detachLineage}
				onLoadLineageOverview={loadLineageOverview}
				onLoadLineageBranch={loadLineageBranch}
				onPaintOne={paintOne}
				onVisionAdvice={requestVisionRefineAdvice}
				pngTemplates={exportTemplates}
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
			onLatestPage={gotoHistoryLatestPage}
			onLoadIteration={loadIteration}
			onToggleStar={toggleHistoryStar}
			interactionLocked={demoRunning}
			{historyStarredOnly}
			onSetStarredOnly={setHistoryStarredOnly}
			{historyIndexLabel}
			{historyModelStage1Short}
			{historyModelStage1Full}
			{historyModelStage2Full}
			{formatHistoryDate}
			{catalogName}
			isJapanese={getLang() === 'ja'}
		/>
	</div><!-- /main-shell -->

</div><!-- /root -->

<SaijikiDrawer
	open={saijikiOpen}
	{pluginEntries}
	bind:activePreview={activeSaijikiPreview}
	onClose={() => (saijikiOpen = false)}
	onInsertWord={insertWord}
	previewForWord={saijikiPreview}
/>

<DdlEditorDialog
	open={ddlDialogOpen}
	isJapanese={getLang() === 'ja'}
	title={ddlDialogMode === 'new' ? t().ddlNewDialogTitle : (getLang() === 'ja' ? 'DDLを編集' : 'Edit DDL')}
	subtitle={ddlDialogMode === 'new' ? t().ddlNewDialogSubtitle : t().ddlEditDialogSubtitle}
	initialDdl={ddlDialogInitial}
	drawing={ddlDialogDrawing}
	error={ddlDialogError}
	previewForWord={saijikiPreview}
	onDraw={handleDdlDialogDraw}
	onClose={closeDdlDialog}
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
		{visionProvider}
		{visionModel}
		providerGroups={settingsMode === 'model' ? availableModelCatalog : modelCatalog}
		visionProviderGroups={availableVisionModelCatalog}
		allowVisionSelection={modelSelectionAllowVision}
		bind:includeThinking
		{settingsStatus}
		{settingsStatusError}
		{settingsStatusLoading}
		bind:modelSettings
		{modelSettingsStatus}
		{modelFetchResults}
		{modelSettingsLoading}
		{dbBackupStatus}
		{outputSaveStatus}
		{logRetentionStatus}
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
		bind:editGroupName
		{editGroupId}
		bind:showKiwi
		bind:showCrab
		bind:autoRepairEnabled={ddlAutoRepairEnabled}
		bind:pngAlphaWhite
		{exportTemplates}
		{exportTemplateStatus}
		bind:saveReplayAsNewVersion
		bind:historySelectionCanvas
		bind:historySelectionCatalog
		{canvasAspectEnabled}
		onSetCanvasAspectEnabled={setCanvasAspectEnabled}
		onClose={closeSettingsModal}
		onCloseSettings={() => (settingsOpen = false)}
		onSelectSettingsTab={selectSettingsTab}
		onSetStage1Provider={setStage1Provider}
		onSetStage1Model={setStage1Model}
		onSetStage2Provider={setStage2Provider}
		onSetStage2Model={setStage2Model}
		onSetVisionProvider={setVisionProvider}
		onSetVisionModel={setVisionModel}
		onUpdateModelProvider={updateModelProvider}
		onAddModelProvider={addModelProvider}
		onAskDeleteModelProvider={askDeleteModelProvider}
		onAskClearModelApiKey={askClearModelApiKey}
		onFetchModelList={fetchProviderModels}
		onSaveModelProviderName={saveModelProviderName}
		onSaveModelProviderMemo={saveModelProviderMemo}
		onSaveModelProvider={saveModelProvider}
		onSaveModelSettings={saveModelSettings}
		onLoadModelSettings={loadModelSettings}
		onLoadSettingsStatus={loadSettingsStatus}
		{pluginActionStatus}
		onLoadPluginContent={loadPluginContent}
		onSavePlugin={savePlugin}
		onCreatePlugin={createPlugin}
		onDeletePlugin={deletePlugin}
		onSetPluginEnabled={setPluginEnabled}
		onUpdateDbBackupSettings={updateDbBackupSettings}
		onRunDbBackupNow={runDbBackupNow}
		onUpdateOutputSaveSettings={updateOutputSaveSettings}
		onUpdateLogRetentionSettings={updateLogRetentionSettings}
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
		onSetEditGroup={setEditGroup}
		onClearEditGroup={clearEditGroup}
		onSaveGroupEdit={saveGroupEdit}
		onCancelModelSelection={cancelModelSelection}
		onConfirmModelSelection={confirmModelSelection}
		onAddExportTemplate={addExportTemplate}
		onUpdateExportTemplate={updateExportTemplate}
		onRemoveExportTemplate={removeExportTemplate}
	/>
{/if}

{#if appInfoOpen}
	<div class="modal-backdrop app-info-backdrop" onclick={() => (appInfoOpen = false)} aria-hidden="true"></div>
	<div class="app-info-modal" role="dialog" aria-modal="true" aria-labelledby="app-info-title">
		<div class="app-info-head">
			<div id="app-info-title" class="app-info-title">{t().appInfoTitle}</div>
			<button class="app-info-close" onclick={() => (appInfoOpen = false)} aria-label={t().appInfoClose}>×</button>
		</div>
		<div class="app-info-body">
			<section>
				<h2>{t().appInfoConceptTitle}</h2>
				<p>{t().appInfoConceptBody}</p>
			</section>
			<section>
				<h2>{t().appInfoCreatorTitle}</h2>
				<div class="app-info-creator">{t().appInfoCreatorName}</div>
				<p>{t().appInfoCreatorBody}</p>
			</section>
			<dl class="app-info-meta">
				<div>
					<dt>{t().appInfoVersionLabel}</dt>
					<dd>{APP_VERSION}</dd>
				</div>
				<div>
					<dt>{t().appInfoBuildLabel}</dt>
					<dd>{__BUILD_NUMBER__}</dd>
				</div>
				<div>
					<dt>{t().appInfoRepositoryLabel}</dt>
					<dd><a href={REPOSITORY_URL} target="_blank" rel="noreferrer">{REPOSITORY_URL}</a></dd>
				</div>
			</dl>
		</div>
	</div>
{/if}

{#if profileOpen && currentUser}
		<ProfileModal
			username={currentUser.username}
			email={currentUser.email}
			generationCount={currentUser.image_generation_count}
			status={profileStatus}
		saving={profileSaving}
		bind:profileEmail
		bind:profileCurrentPassword
		bind:profileNewPassword
		onClose={closeProfile}
		onSave={saveProfile}
	/>
{/if}

<!-- ══ CATALOG MODAL ══ -->
{#if catalogOpen}
	<ColorCatalogModal
		catalogs={colorCatalogs}
		{selectedCatalog}
		{currentCatalog}
		onSelectCatalog={setSelectedCatalog}
		onCancel={cancelCatalogSelection}
		onConfirm={confirmCatalogSelection}
	/>
{/if}

<!-- ══ HISTORY MANAGER MODAL ══ -->
{#if historyManager.open}
	<HistoryManager
		bind:historyManagerTab={historyManager.tab}
		bind:historySearch={historyManager.search}
		historyManagerView={historyManager.view}
		historyManagerPage={historyManager.page}
		historyManagerLoading={historyManager.loading}
		historyManagerTotalPages={historyManager.totalPages}
		historyManagerOffset={historyManager.offset}
		historyManagerShownTo={historyManager.shownTo}
		managedHistoryItems={historyManager.items}
		managedHistoryTotal={historyManager.total}
		managerTrashTotal={historyManager.trashTotal}
		{trashTotal}
		selectedHistoryIds={historyManager.selectedIds}
		historyManagerStarredOnly={historyManager.starredOnly}
		onClose={() => (historyManager.open = false)}
		onSetView={historyManager.setView}
		onSetPage={historyManager.setPage}
		onSetLatestPage={() => historyManager.setPage(0)}
		onSetFirstPage={() => historyManager.setPage(historyManager.totalPages - 1)}
		onSetPageSize={historyManager.setPageSize}
		onSetStarredOnly={historyManager.setStarredOnly}
		onSelectAll={selectAllManagedHistory}
		onAskTrash={askTrash}
		onAskRestore={askRestore}
		onAskPermanentDelete={askPermanentDelete}
		onToggleSelection={toggleHistorySelection}
		onLoadItem={loadIterationItem}
		onReplayItem={replayHistoryItem}
		onToggleStar={toggleHistoryStar}
		{historyModelSummary}
		{formatHistoryDate}
		{formatElapsed}
		{catalogName}
		{historyPreviewText}
		{shortModel}
		{apiFetch}
		currentHistoryId={displayedHistoryItem?.id ?? result?.history_id ?? null}
		currentLineageRootId={displayedHistoryItem?.lineage_root_node_id ?? null}
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
		--panel:        #ffffff;
		--panel2:       #faf9f6;
		--canvas-paper: #fffdf8;
		--tooltip-bg:   rgba(26,25,23,0.92);
		--floating-control-bg: rgba(255,255,255,0.9);
		--floating-control-hover: #fff;
		--floating-control-disabled-bg: rgba(255,255,255,0.72);
		--floating-control-fg: #1a1917;
		--floating-control-muted: #6d6860;
		--action-bg:    #1a1917;
		--action-hover: #33302b;
		--action-fg:    #fff;
		--action-disabled-bg: #807a70;
		--action-disabled-fg: #f7f3eb;
		--accent:       #2a4a72;
		--accent-light: #e8eef5;
		--border:       #d4d0c8;
		--border2:      #c4c0b8;
		--r:            4px;
		--r-lg:         8px;
	}

	:global(html[data-theme='dark']) {
		color-scheme: dark;
		--bg:           #171716;
		--bg2:          #20201f;
		--bg3:          #2b2926;
		--fg:           #eee9df;
		--fg2:          #c8c0b3;
		--fg3:          #90877a;
		--panel:        #242321;
		--panel2:       #1d1c1b;
		--canvas-paper: #f5f1e9;
		--tooltip-bg:   rgba(12,12,11,0.94);
		--floating-control-bg: rgba(45,43,39,0.96);
		--floating-control-hover: #38342f;
		--floating-control-disabled-bg: rgba(58,54,49,0.92);
		--floating-control-fg: #eee9df;
		--floating-control-muted: #b8afa1;
		--action-bg:    #6f92bd;
		--action-hover: #83a5ce;
		--action-fg:    #11151a;
		--action-disabled-bg: #4c5258;
		--action-disabled-fg: #d2d7dc;
		--accent:       #9ab7dc;
		--accent-light: #253246;
		--border:       #38342f;
		--border2:      #514b43;
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
		flex-direction: row;
		height: 100vh;
		overflow: hidden;
	}

	/* ── Body ───────────────────────────────────────────────── */
	.main-shell {
		flex: 1;
		min-width: 0;
		display: flex;
		flex-direction: column;
		overflow: hidden;
	}

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
		overflow: hidden;
	}

	.left-rail-toggle {
		flex: 0 0 auto;
		align-self: stretch;
		width: 18px;
		padding: 0;
		border: none;
		border-right: 1px solid var(--border);
		background: var(--bg2);
		color: var(--fg3);
		font-family: inherit;
		font-size: 13px;
		line-height: 1;
		cursor: pointer;
		display: flex;
		align-items: center;
		justify-content: center;
	}
	.left-rail-toggle:hover { background: var(--panel); color: var(--fg); }

	@media (max-width: 1180px) {
		.left-panel { width: min(400px, 42vw); }
		.panel-scroll { padding-inline: 12px; }
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
	.ddl-tools-section { flex-direction: row; }
	.ddl-new-btn { align-self: flex-start; padding: 7px 14px; border: 1px solid var(--border2); border-radius: var(--r); background: var(--panel); color: var(--fg); font: inherit; font-size: 13px; cursor: pointer; }
	.ddl-new-btn:hover { background: var(--bg2); }

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
		padding: 8px 10px; font-size: 11px; color: var(--fg2); line-height: 1.5;
		overflow: hidden;
	}
	.stats-grid {
		display: grid;
		gap: 5px;
	}
	.stats-row {
		display: grid;
		grid-template-columns: minmax(108px, 0.75fr) minmax(0, 1.25fr);
		gap: 8px;
		align-items: start;
		min-width: 0;
	}
	.stats-key { color: var(--fg3); min-width: 0; overflow-wrap: anywhere; }
	.stats-value {
		display: grid;
		grid-template-columns: minmax(86px, 1fr) minmax(100px, 1.1fr);
		gap: 6px 10px;
		min-width: 0;
		font-variant-numeric: tabular-nums;
	}
	.stats-value > span {
		min-width: 0;
		white-space: nowrap;
	}
	.stats-metric-label {
		display: inline-block;
		min-width: 3.9em;
		margin-right: 5px;
		color: var(--fg3);
		font-variant-numeric: normal;
	}
	.stats-total { font-weight: 500; }
	@media (max-width: 520px) {
		.stats-row { grid-template-columns: minmax(0, 1fr); }
		.stats-value { grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); }
	}

	/* App info */
	.app-info-backdrop {
		position: fixed;
		inset: 0;
		z-index: 700;
		background: rgba(0,0,0,0.25);
		backdrop-filter: blur(2px);
	}
	.app-info-modal {
		position: fixed;
		top: 50%;
		left: 50%;
		z-index: 701;
		width: min(520px, calc(100vw - 32px));
		max-height: min(720px, calc(100vh - 32px));
		transform: translate(-50%, -50%);
		display: flex;
		flex-direction: column;
		background: var(--panel2);
		border: 1px solid var(--border);
		border-radius: var(--r-lg);
		box-shadow: 0 18px 56px rgba(0,0,0,0.24);
		overflow: hidden;
	}
	.app-info-head {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 12px;
		padding: 14px 16px;
		border-bottom: 1px solid var(--border);
	}
	.app-info-title {
		font-size: 18px;
		font-weight: 300;
		letter-spacing: 0;
	}
	.app-info-close {
		width: 26px;
		height: 26px;
		border: 0;
		background: transparent;
		color: var(--fg3);
		font-size: 18px;
		line-height: 1;
		cursor: pointer;
		font-family: inherit;
	}
	.app-info-body {
		display: flex;
		flex-direction: column;
		gap: 18px;
		overflow-y: auto;
		padding: 18px 18px 20px;
		color: var(--fg2);
		font-size: 13px;
		line-height: 1.8;
	}
	.app-info-body h2 {
		margin: 0 0 6px;
		color: var(--fg);
		font-size: 12px;
		font-weight: 500;
		letter-spacing: 0.04em;
	}
	.app-info-body p {
		margin: 0;
		white-space: pre-line;
	}
	.app-info-creator {
		margin-bottom: 4px;
		color: var(--fg);
		font-size: 14px;
		font-weight: 500;
	}
	.app-info-meta {
		display: grid;
		grid-template-columns: auto minmax(0, 1fr);
		gap: 6px 14px;
		margin: 0;
		padding-top: 2px;
		font-size: 12px;
		line-height: 1.6;
	}
	.app-info-meta div {
		display: contents;
	}
	.app-info-meta dt {
		color: var(--fg3);
	}
	.app-info-meta dd {
		min-width: 0;
		margin: 0;
		color: var(--fg);
		word-break: break-word;
	}
	.app-info-meta a {
		color: var(--accent);
		text-decoration: none;
	}
	.app-info-meta a:hover {
		text-decoration: underline;
	}

	.interpretation-diff {
		gap: 2px;
		padding: 8px 10px;
		border: 1px solid var(--border);
		background: color-mix(in srgb, var(--bg2) 68%, transparent);
		font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
		font-size: 11px;
		line-height: 1.55;
	}
	.interpretation-diff div {
		white-space: pre-wrap;
		color: var(--fg3);
	}
	.interpretation-diff .removed { color: color-mix(in srgb, #a2342a 78%, var(--fg3)); }
	.interpretation-diff .added { color: color-mix(in srgb, #2f6b3a 78%, var(--fg3)); }

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

<script module lang="ts">
	declare const __APP_VERSION__: string;
	declare const __BUILD_NUMBER__: string;
	declare const __BUILD_DATE__: string;
</script>

<script lang="ts">
	import { onMount, untrack } from 'svelte';
	import { pipelineDescription } from '$lib/description-labels';
	import {
		canAccessSettingsTab as canAccessSettingsTabFor,
		defaultSettingsTab as defaultSettingsTabFor,
		holdsPermissionGroup,
		type PermissionGroup
	} from '$lib/permissionGroups';
	import {
		normalizeSettingsDetail,
		settingsTabShownAtDetail,
		type SettingsDetailLevel
	} from '$lib/settingsDetail';
	import { highlightDDL, interpretationFeedback } from '$lib/highlight';
	import { pluginWarningsToShow } from '$lib/plugin-names';
	import { hydrateSaijiki, hydrateSaijikiEn } from '$lib/saijiki';
	import { SURFACE_PREVIEWS, shapeSvg, type PreviewEntry } from '$lib/saijiki-surface';
	import AppRail from '$lib/components/AppRail.svelte';
	import AuthPanel from '$lib/components/AuthPanel.svelte';
	import CanvasPanel from '$lib/components/CanvasPanel.svelte';
	import type { LineageGraph, LineageNode } from '$lib/components/LineagePanel.svelte';
	import ConfirmDialog from '$lib/components/ConfirmDialog.svelte';
	import { DEFAULT_SKETCH_MODE, normalizeSketchGrain, normalizeSketchState, sketchGrainOf, sketchModeLabel, sketchModeOf, sketchStateNote, type SketchMode, type SketchState } from '$lib/sketch';
	import { submitDerivationKind as submitDerivationKindOf } from '$lib/derivation';
	import DdlViewer from '$lib/components/DdlViewer.svelte';
	import HistoryStrip from '$lib/components/HistoryStrip.svelte';
	import InputPanel from '$lib/components/InputPanel.svelte';
	import RunStatus from '$lib/components/RunStatus.svelte';
	import Tooltip from '$lib/components/Tooltip.svelte';
	import { normalizeUiCustom, normalizeUiMode, resolveUiVisibility, UI_VISIBILITY_KEYS, type UiCustomVisibility, type UiMode, type UiVisibilityKey } from '$lib/uiMode';
	import {
		PROVIDER_GROUPS,
		DEFAULT_PROVIDER,
		DEFAULT_MODEL,
		modelsForProvider,
		modelDisplayName,
		providerLabel,
		providerOfModel,
		qualifiedModelId,
		registerModelCatalog,
		resolveModelRefForDisplay,
		splitModelRef,
		type Provider,
		type ProviderGroup,
		type ModelOption
	} from '$lib/models';
	import { t, getLang, initLang } from '$lib/i18n/index.svelte';
	import { initMascot } from '$lib/mascot.svelte';
	import { FALLBACK_CATALOG, catalogById, catalogNameplate, type ColorCatalog, type ColorCatalogsResponse } from '$lib/colors';
	import { DEFAULT_DEMO_SETTINGS, type DemoSettings } from '$lib/demo';
	import { createElapsed } from '$lib/elapsed.svelte';
	import { DEFAULT_EXPORT_TEMPLATES, normalizeExportTemplates, type ExportTemplate } from '$lib/exportTemplates';
	// Persisted settings: one feature, one file.  Adding a setting must not send
	// every branch back into this file -- see lib/features/*/settings.svelte.ts.
	import { bindColorCatalogPersist, colorCatalogSettings } from '$lib/features/color-catalog/settings.svelte';
	import { bindDescribePanelPersist, describePanelSettings } from '$lib/features/describe-panel/settings.svelte';
	import { bindColorCatalogFallback } from '$lib/features/color-catalog/render';
	import { AUTO_CATALOG_ID, colorCatalogOverride } from '$lib/features/color-catalog/render';
	import { renderSettingsPayload, type RenderOverrides } from '$lib/features/render-payload';
	import { loadPersistedSettings } from '$lib/features/persisted-settings';
	import { applyUserSettings, collectUserSettings } from '$lib/features/user-settings';
	import { batchSettings } from '$lib/features/batch/settings.svelte';
	import { downloadFolderSettings } from '$lib/features/export/download-folder.svelte';
	import { dropFailedLine, planRetryRound } from '$lib/features/batch/retry';
	import {
		batchStoppedPartWay,
		conditionsOfWork,
		latestBatchWork,
		linesToResume,
		numberedBatchLines,
		type NumberedLine
	} from '$lib/features/batch/resume';
	import { wildSettings } from '$lib/features/wild/settings.svelte';
	import { wildOverride } from '$lib/features/wild/render';
	import { exportSettings } from '$lib/features/export/settings.svelte';
	import { downloadCard } from '$lib/cardExport';
	import { createExportActions } from '$lib/features/export/download';
	import { createModelInspection } from '$lib/features/model-inspection/state.svelte';
	import { resultLogSettings } from '$lib/features/result-log/settings.svelte';
	import {
		batchFailureReportStore,
		type BatchFailure
	} from '$lib/features/batch/failure-report.svelte';
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
	import { historyListLimit } from '$lib/historyListLimit';
	import { historyRefreshBlockedBy, historyStripIsCurrent, type HistoryState } from '$lib/historyRefreshDecision';
	import {
		alignHistoryOffset,
		historyNavDisabled,
		historyNavTarget,
		historyPageTarget,
		resolveStripSelection,
		type HistoryNavTarget
	} from '$lib/historyNavigation';
	import { hashDigest } from '$lib/hashIdentity';
	import { setThumbnailHidpi } from '$lib/thumbnailSource';

	const PROVIDER_STAGE1_KEY = 'inku-provider-stage1';
	const MODEL_STAGE1_KEY    = 'inku-model-stage1';
	const PROVIDER_STAGE2_KEY = 'inku-provider-stage2';
	const MODEL_STAGE2_KEY    = 'inku-model-stage2';
	// Which of the settings dialog's tabs are on show. Kept in the browser, not
	// on the member: it is a preference about this screen, and saving it would
	// need a field the server does not have.
	const SETTINGS_DETAIL_KEY = 'inku-settings-detail';
	const DEFAULT_VISION_MODEL = 'meta/llama-3.2-90b-vision-instruct';
	// Injected by vite.config from web/APP_VERSION, the single source shared with
	// the server (/api/info) and the CLI. Never write the version here again.
	const APP_VERSION = __APP_VERSION__;
	const REPOSITORY_URL = 'https://github.com/oikawas/inku-lang';
	// vite.config が BUILD_NUMBER の mtime を焼き込む。読めなければ null。
	const buildDateLabel = $derived.by(() => {
		const stamp = new Date(__BUILD_DATE__);
		if (Number.isNaN(stamp.getTime())) return null;
		return stamp.toLocaleString(getLang() === 'ja' ? 'ja-JP' : 'en-US', { dateStyle: 'medium', timeStyle: 'short' });
	});
	// Matches _BATCH_PROMPT_HISTORY_LIMIT in server/src/inku_server/db.py: the
	// server cuts the list on both the read and the write, so the shorter of the
	// two numbers is what the picker ever shows.
	const BATCH_PROMPT_HISTORY_LIMIT = 50;
	const BATCH_PROMPT_HISTORY_MAX_TEXT = 20000;
	const EXTERNAL_HISTORY_REFRESH_MS = 12000;
	const EXTERNAL_HISTORY_REFRESH_MIN_GAP_MS = 5000;
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
		ddl_version?: string | null;
		ddl_engine_version?: string | null;
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
		render_wild?: boolean | null;
		composition_seed?: number | null;
		interpretation_seed?: string | null;
		seed_text?: string | null;
		sketch_text?: string | null;
		sketch_grain?: string | null;
		sketch_fallback_used?: boolean;
		sketch_state?: string | null;
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
		source_ddl?: string | null;
		// What the expansion layer removed and why. It reaches the record on
		// every path; until now nothing showed it to the person who wrote the
		// sentence that went missing.
		plugin_warnings?: string[] | null;
		focus?: string | null;
		variation_amplitude?: string | null;
		variation_seed?: number | null;
		variation_moved_axes?: Array<{ axis: string; from: string; to: string }>;
		interpret_fallback_used?: boolean;
		interpret_fallback_reasons?: string[];
		tokens_in_stage1: number | null;
		tokens_out_stage1: number | null;
		tokens_in_stage2: number | null;
		tokens_out_stage2: number | null;
		user_generation_count?: number | null;
	};
	type DerivationKind = 'touch_change' | 'layout_change' | 'catalog_change' | 'reinterpretation' | 'model_comparison' | 'language_comparison' | 'ddl_edit' | 'description_edit' | 'replay' | 'canvas_aspect_change' | 'variation' | 'sketch_grain_change';
	type RefineKind = 'touch' | 'layout' | 'reading' | 'color' | 'variation';
	type VariationAmplitude = 'small' | 'medium' | 'large';

	type Iteration = HistoryItem;
	type ReplaySource = 'history-manager' | 'canvas' | 'refine' | 'lineage';
	type ReplayComparison = {
		source: ReplaySource;
		originalSvg: string;
		replayedSvg: string;
		recordedVersion: string | null;
		currentVersion: string | null;
		versionMessage: string | null;
		provisionalSeed: number | null;
	};

	type PluginEntry = {
		qualified_name: string;
		surface_ja: string[];
		surface_en: string[];
		note_ja: string;
		note_en: string;
		// Carried by GET /api/saijiki so the DDL editor can tell a wrong
		// qualified name from a name that does not exist at all.
		fires_on_ja?: string[];
		fires_on_en?: string[];
		// Where the drawing baked from this word's own expansion is served,
		// shared by both languages the way the built-in previews share theirs.
		// "" when the document ships none at that scale.
		preview_url?: string;
		preview_url_2x?: string;
	};
	type PluginItem = {
		name: string;
		namespace?: string;
		version: string;
		status: string;
		entries?: PluginEntry[];
		reasons?: string[];
	};
	type DbBackupEntry = {
		kind: 'auto' | 'manual';
		name: string;
		at: number;
		size_bytes: number;
		generation: number | null;
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
			backup_hour: number;
			backup_minute: number;
			last_auto_backup_at: number;
			next_auto_backup_at: number;
			backup_dir: string;
			auto_count: number;
			manual_count: number;
			backups: DbBackupEntry[];
			backups_total_count: number;
			backups_total_size_bytes: number;
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
		render_concurrency: {
			server_limit: number;
			client_limit: number;
			min_limit: number;
			max_limit: number;
			note: string;
		};
		render_limits: {
			limits: Record<string, number>;
			defaults: Record<string, number>;
			groups: Record<string, string[]>;
			absolute_max: number;
			note: string;
		};
		log_retention: {
			enabled: boolean;
			retention_days: number;
			rotate: 'daily' | 'weekly' | 'monthly';
			compress: boolean;
			log_dir: string;
			files: string[];
			note: string;
		};
	};

	type SettingsTab = 'connection' | 'models' | 'db' | 'plugins' | 'users' | 'unread' | 'export' | 'misc' | 'server_misc' | 'logs' | 'limits';
	type UserModelSettings = {
		stage1_provider: Provider;
		stage1_model: string;
		stage2_provider: Provider;
		stage2_model: string;
		vision_provider: Provider;
		vision_model: string;
		okugaki_provider?: Provider;
		okugaki_model?: string;
		instruction_caption_visible?: boolean;
		color_catalog_id?: string;
		sketch_open?: boolean;
		ddl_expanded_open?: boolean;
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
		permission_groups: PermissionGroup[];
		permission_group_labels: string[];
		group_id: string | null;
		group_name: string | null;
		ui_theme?: 'light' | 'dark';
		ui_mode?: UiMode;
		ui_custom?: UiCustomVisibility;
		tooltips_enabled?: boolean;
		download_folder_enabled?: boolean;
		download_folder_name?: string | null;
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
	// 0 while the batch is on its original pass, n while it is on retry round n.
	let batchRetryRound = $state(0);
	let batchSuccess = $state(0);
	let batchFailures = $state<BatchFailure[]>([]);
	let batchPromptHistory = $state<string[]>([]);
	// Set when the newest batch work says its run stopped before the end of the
	// prompt it came from -- what the resume button offers to finish. Null the
	// rest of the time, which is what withholds the button.
	let batchResume = $state<{ prompt: string; lines: NumberedLine[]; runId: string | null; work: Iteration } | null>(null);
	let batchActiveLine = $state<number | null>(null);
	let batchActiveDdl = $state<string | null>(null);
	// Which line the observer block is showing. Not batchActiveLine: that one is
	// taken when a line starts, while the instructions, the tokens and the prose
	// only exist once it comes back. Naming the block with the line being painted
	// put the previous line's work under the next line's number.
	let batchObservedLine = $state<number | null>(null);
	// 写生 (Stage 0.5) for the batch, kept apart from the single-mode prose: that
	// one is an editable draft bound to one description, and a batch must not
	// overwrite what the author is editing there. Written when a line returns,
	// the same moment batchActiveDdl is, so the two always describe one work.
	let batchSketchText = $state<string | null>(null);
	let batchSketchGrain = $state<unknown>(null);
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
	let demoTimedOut = $state(false);
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
	let replayComparison = $state<ReplayComparison | null>(null);

	// ── Result ──────────────────────────────────────────────
	let ddl      = $state<string | null>(null);
	// v1.98: ddl は入力側 (Stage 1 出力 / ユーザーが書いた DDL)、expandedDdl は展開後
	// (Stage 1.5 出力 = Stage 2 入力)。旧データは入力側を持たないため null になる。
	let expandedDdl = $state<string | null>(null);
	let ddlGeneratedBaseline = $state<string | null>(null);
	let ddlAutoRepairEnabled = $state(true);
	let thinking = $state<string | null>(null);
	let result   = $state<PaintResult | null>(null);
	// One read point for every draw path: whatever sets `result` shows them.
	const pluginWarningsShown = $derived(pluginWarningsToShow(result));
	// 写生 (Stage 0.5). Chosen per draw, so it is plain state -- not persisted the
	// way a user setting like the color catalog is (contract section 0.3.1).
	let sketchMode = $state<SketchMode>(DEFAULT_SKETCH_MODE);
	// The prose the layer wrote for the run on screen, and the author's edit of
	// it. Editing and painting again sends the edited prose instead of calling
	// the layer, so what the author reads is what Stage 1 reads.
	let sketchText = $state<string | null>(null);
	// Which description the prose was written for. Prose written for one text is
	// not prose for another, and the description can be edited after a run.
	let sketchSource = $state<string | null>(null);
	let sketchDraft = $state('');
	let sketchEditing = $state(false);
	// What the record says the layer did for the work on screen. `null` is a work
	// whose record is absent -- drawn before the column existed -- and the note
	// tells that apart from 'off', which is a choice the author made.
	let sketchState = $state<SketchState | null>(null);

	/** The prose to send for this description, or null to let the layer write it.
	 *  Used by the paths that re-run one stage over a description already on
	 *  screen (model and language comparison): holding the prose fixed is what
	 *  makes those a comparison of models rather than of two different texts. */
	function sketchTextFor(text: string): string | null {
		return sketchText && sketchSource !== null && sketchSource.trim() === text.trim()
			? sketchText
			: null;
	}

	/** What every request that begins at Stage 2 sends. Those paths never run
	 *  0.5 -- they carry the prose the work already has, so the four consumers
	 *  below Stage 1 read what a paint would have given them. */
	function sketchPayloadFor(text: string): Record<string, string> {
		const prose = sketchTextFor(text);
		if (!prose) return {};
		const grain = sketchGrainOf(sketchMode);
		return { sketch_text: prose, ...(grain ? { sketch_grain: grain } : {}) };
	}

	/** Show the prose a run or a saved work was painted from, and select the
	 *  grain it used so a redraw starts from the same place. A work with no
	 *  prose (painted with the layer off, or made before it existed) turns the
	 *  control off rather than silently painting it at the default grain.
	 *
	 *  The control still lands on 'off' for every work with no prose -- what the
	 *  author is going to draw next is a separate question from what the work on
	 *  screen was drawn through. The state is what keeps the two apart: it is
	 *  carried whole, so the note can say "drawn without the layer" and "drawn
	 *  before the layer was recorded" as the different things they are. */
	function adoptSketch(
		text: string | null,
		grain: unknown,
		source: string | null = null,
		state: unknown = null
	): void {
		sketchText = text;
		sketchSource = source;
		sketchDraft = text ?? '';
		sketchEditing = false;
		sketchMode = text ? sketchModeOf(normalizeSketchGrain(grain) ?? 'fine') : 'off';
		sketchState = normalizeSketchState(state);
	}
	let variationBusy = $state(false);
	type DdlDiffPart = { kind: "same" | "removed" | "added"; text: string };
	type TextDiffPart = { kind: "same" | "removed" | "added"; text: string };
	type VariationCandidate = { id: string; label: string; result: PaintResult & { ddl: string; thinking: string | null }; selected: boolean; saved?: boolean };
	/** Where one candidate of a fan-out is: queued for a lane, drawing, or done. */
	type VariationSlotState = 'waiting' | 'running' | 'done';
	let interpretationDiffParts = $state<DdlDiffPart[]>([]);
	let variationCandidates = $state<VariationCandidate[]>([]);
	let lineageIntermediateNotice = $state<string | null>(null);
	let lineageIntermediateNoticeTimer: number | null = null;
	let historyStarredFilterNotice = $state<string | null>(null);
	let historyStarredFilterNoticeTimer: number | null = null;
	let nearbyHistory = $state<Iteration[]>([]);
	let variationGridBusy = $state(false);
	let variationGridCanAbort = $state(false);
	let variationGridIncludesReading = $state(false);
	let variationGridTaskLabel = $state('');
	// Candidates run concurrently, so progress is "how many have finished",
	// not "which one is being processed".
	let variationGridDone = $state(0);
	let variationGridTotal = $state(0);
	// One entry per candidate, so the panel can show the fan-out as the several
	// jobs it is rather than as a single counter that moves once at the end.
	let variationGridSlots = $state<VariationSlotState[]>([]);
	let variationGridSlotLabels = $state<string[]>([]);
	let variationGridAbortController: AbortController | null = null;
	let variationGridStatus = $state<string | null>(null);
	let targetContextVersion = 0;

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
	let ddlDialogWildOverride = $state<boolean | null>(null);
	// DDL-authored (standalone) artworks carry the display_label marker 'DDL'.
	const DDL_ORIGIN_LABEL = 'DDL';
	let appInfoOpen = $state(false);
	let leftPanelCollapsed = $state(false);
	let settingsMode = $state<'model' | 'settings'>('settings');
	let settingsTab  = $state<SettingsTab>('connection');
	let settingsDetail = $state<SettingsDetailLevel>('standard');
	let pngMenuOpen  = $state(false);
	let userMenuOpen = $state(false);
	let darkMode     = $state(true);
	let catalogOpen  = $state(false);
	let canvasAspectMenuOpen = $state(false);
	let canvasAspectEnabled = $state(true);
	let canvasAspectId = $state<CanvasAspectId>(DEFAULT_CANVAS_ASPECT_ID);
	let pendingCanvasAspectDerivation = $state<{ parentNodeId: string; fromAspectId: CanvasAspectId; toAspectId: CanvasAspectId } | null>(null);
	let catalogSelectionSnapshot = $state<string | null>(null);
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
	let renderConcurrencyStatus = $state<string | null>(null);
	let renderFanoutLimit = $state(4);
	let developerMode = $state(false);
	// This server belongs to one person and signs them in by itself. The doors
	// that lead nowhere when there is nobody else to be -- signing out, above
	// all -- are dropped; the way back to a multi-user server (changing the
	// password) is deliberately kept.
	let singleUserMode = $state(false);
	// The work whose guest list is open, if any. Sharing is offered only when
	// there is somebody to share with: a single-user server is one person's own,
	// so the button is withheld there rather than opening onto an empty list.
	let shareTarget = $state<HistoryItem | null>(null);
	let currentRenderEngineVersion = $state<string | null>(null);
	let currentDdlVersion = $state<string | null>(null);
	let currentDdlEngineVersion = $state<string | null>(null);
	let exportTemplates = $state<ExportTemplate[]>(DEFAULT_EXPORT_TEMPLATES.map((item) => ({ ...item })));
	let exportTemplateStatus = $state<string | null>(null);

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
		/** Raster artwork, served by its own route. Set for plugin words;
		    built-in words carry their drawing in `svg` instead. */
		image?: string;
		image2x?: string;
	};

	// Entries are keyed by the Japanese surface. The caller pairs the two
	// display lists by position to derive the canonical word, an invariant the
	// saijiki table holds and server tests lock (test_saijiki_api.py).
	function saijikiPreview(categoryKey: string, canonicalWord: string, word: string): SaijikiPreview {
		const isJa = getLang() === 'ja';
		const base = {
			categoryKey,
			word,
			canonicalWord,
			effect: '',
			example: '',
			svg: '',
		};
		const localized = (entry: PreviewEntry) => ({
			effect: isJa ? entry.effect : entry.effectEn,
			example: isJa ? entry.example : entry.exampleEn,
			svg: entry.svg,
		});
		const lineSvg = (attrs = '', strokeWidth = 5, lineCap = 'round', stroke = '#2b2b2b') => `<svg viewBox="0 0 180 92" aria-hidden="true"><rect width="180" height="92" rx="6" fill="#fffdf8"/><path d="M22 56 C56 26 95 76 158 38" fill="none" stroke="${stroke}" stroke-width="${strokeWidth}" stroke-linecap="${lineCap}" ${attrs}/></svg>`;
		const touchSvg = (kind: string) => {
			const defs = '<defs><filter id="touch-soft"><feGaussianBlur stdDeviation="1.8"/></filter></defs>';
			const paths: Record<string, string> = {
				silverpoint: '<path d="M22 54 C58 37 106 58 158 39" fill="none" stroke="#2b2b2b" stroke-width="1.2" stroke-linecap="round" opacity="0.72"/>',
				pencil: '<path d="M22 54 C58 37 106 58 158 39" fill="none" stroke="#2b2b2b" stroke-width="2.4" opacity="0.58"/><path d="M22 56 C62 39 108 59 158 41" fill="none" stroke="#2b2b2b" stroke-width="0.8" stroke-dasharray="1 6" opacity="0.42"/><g fill="#2b2b2b" opacity="0.22"><circle cx="49" cy="48" r="1"/><circle cx="82" cy="51" r="0.8"/><circle cx="121" cy="47" r="1.1"/></g>',
				pen: '<path d="M22 54 C58 37 106 58 158 39 L158 41 C106 60 58 39 22 55 Z" fill="#2b2b2b"/>',
				rotring: '<path d="M22 52 L158 40" fill="none" stroke="#2b2b2b" stroke-width="2.4" stroke-linecap="butt"/>',
				crayon: '<path d="M22 57 C58 35 108 62 158 38" fill="none" stroke="#2b2b2b" stroke-width="8" opacity="0.66" stroke-dasharray="12 2 3 2"/><path d="M22 52 C65 40 110 56 158 42" fill="none" stroke="#2b2b2b" stroke-width="2" opacity="0.35"/>',
				chalk: '<path d="M22 56 C58 35 105 61 158 39" fill="none" stroke="#2b2b2b" stroke-width="7" opacity="0.38" stroke-dasharray="8 4 2 5"/><g fill="#2b2b2b" opacity="0.22"><circle cx="39" cy="53" r="1.8"/><circle cx="70" cy="47" r="1.3"/><circle cx="111" cy="51" r="1.6"/><circle cx="145" cy="43" r="1.4"/></g>',
				brush_thin: '<path d="M22 55 C54 31 108 63 158 38 C126 53 67 48 22 55 Z" fill="#2b2b2b" opacity="0.9"/>',
				brush_thick: '<path d="M22 56 C47 25 105 68 158 37 C128 60 62 54 22 56 Z" fill="#2b2b2b" opacity="0.84"/><path d="M35 54 C72 42 112 58 151 41" fill="none" stroke="#fffdf8" stroke-width="1.2" opacity="0.45"/>',
				burin: '<path d="M22 55 C56 42 106 57 158 39 C119 55 67 51 22 55 Z" fill="#2b2b2b"/>',
				drypoint: `${defs}<path d="M22 55 C56 40 107 58 158 39 C118 54 67 52 22 55 Z" fill="#2b2b2b"/><path d="M23 59 C58 44 108 62 159 43" fill="none" stroke="#2b2b2b" stroke-width="5" opacity="0.28" filter="url(#touch-soft)"/>`,
				computer: '<path d="M22 52 H34 V46 H46 V40 H58 V46 H70 V52 H82 V58 H94 V64 H106 V58 H118 V52 H130 V46 H142 V40 H158" fill="none" stroke="#2b2b2b" stroke-width="2.4" stroke-linejoin="round"/><path d="M22 36 H158 M22 68 H158" fill="none" stroke="#2b2b2b" stroke-width="0.9" stroke-dasharray="22 9" stroke-linecap="round" opacity="0.576"/>',
			};
			return shapeSvg(paths[kind] ?? paths.pen);
		};
		if (categoryKey === "plugin-nature") {
			const natureSvg = shapeSvg("<path d=\"M32 48 C52 28 74 68 94 48 S132 28 150 48\" stroke=\"#b95845\" stroke-width=\"5\" fill=\"none\" stroke-linecap=\"round\"/><path d=\"M34 62 C58 50 78 76 102 62 S134 50 150 62\" stroke=\"#d39a7b\" stroke-width=\"3\" fill=\"none\" stroke-linecap=\"round\"/>");
			const naturePreviews: Record<string, PreviewEntry> = {
				"Nature.風": { effect: "左から右へのゆるやかな揺れを全体に通します。", example: "Nature.風を通す", effectEn: "Runs a slow left-to-right sway through the whole drawing.", exampleEn: "Nature.wind", svg: natureSvg },
				"Nature.うねり": { effect: "媒質を限定しない大きな波の揺れを全体に通します。", example: "Nature.うねりを通す", effectEn: "Runs a broad medium-free undulation through the whole drawing.", exampleEn: "Nature.undulation", svg: natureSvg },
				"Nature.無風": { effect: "揺らぎと配置軌跡を抑え、静止に寄せます。", example: "Nature.無風", effectEn: "Suppresses sway and placement paths, settling toward stillness.", exampleEn: "Nature.stillness", svg: natureSvg },
			};
			naturePreviews["Nature.wind"] = naturePreviews["Nature.風"];
			naturePreviews["Nature.undulation"] = naturePreviews["Nature.うねり"];
			naturePreviews["Nature.stillness"] = naturePreviews["Nature.無風"];
			return { ...base, ...localized(naturePreviews[canonicalWord] ?? naturePreviews[word] ?? naturePreviews["Nature.うねり"]) };
		}
		const angleSvg = (rotation: number, line = false) => shapeSvg(line
			? `<g transform="rotate(${rotation} 90 46)"><path d="M42 46 H138" fill="none" stroke="#2b2b2b" stroke-width="6" stroke-linecap="round"/></g><circle cx="90" cy="46" r="2.5" fill="#c9c2b5"/>`
			: `<g transform="rotate(${rotation} 90 46)"><rect x="58" y="29" width="64" height="34" fill="none" stroke="#2b2b2b" stroke-width="5" rx="2"/></g><circle cx="90" cy="46" r="2.5" fill="#c9c2b5"/>`);
		const scatter = `<svg viewBox="0 0 180 92" aria-hidden="true"><rect width="180" height="92" rx="6" fill="#fffdf8"/><circle cx="42" cy="35" r="5" fill="#2b2b2b"/><circle cx="84" cy="58" r="4" fill="#2b2b2b"/><circle cx="122" cy="30" r="5" fill="#2b2b2b"/><circle cx="146" cy="65" r="3.5" fill="#2b2b2b"/><circle cx="62" cy="72" r="3.5" fill="#2b2b2b"/></svg>`;
		const previews: Record<string, PreviewEntry> = {
			円: { effect: '正円を描く。中心と半径で配置される。', example: '中央に黒い円を置く', effectEn: 'Draws a true circle, placed by its center and radius.', exampleEn: 'Place a black circle at center', svg: shapeSvg('<circle cx="90" cy="46" r="25" fill="none" stroke="#2b2b2b" stroke-width="5"/>') },
			楕円: { effect: '横または縦に伸びた円を描く。', example: '横長の楕円を置く', effectEn: 'Draws a circle stretched along one axis.', exampleEn: 'Place a wide ellipse', svg: shapeSvg('<ellipse cx="90" cy="46" rx="42" ry="22" fill="none" stroke="#2b2b2b" stroke-width="5"/>') },
			三角: { effect: '三つの頂点を持つ形を描く。', example: '上に三角を置く', effectEn: 'Draws a form with three vertices.', exampleEn: 'Place a triangle at the top', svg: shapeSvg('<path d="M90 20 L132 70 L48 70 Z" fill="none" stroke="#2b2b2b" stroke-width="5" stroke-linejoin="round"/>') },
			四角: { effect: '矩形を描く。比率語で縦長・横長にもなる。', example: '中央に四角を置く', effectEn: 'Draws a rectangle. Proportion words make it tall or wide.', exampleEn: 'Place a square at center', svg: shapeSvg('<rect x="58" y="24" width="64" height="44" fill="none" stroke="#2b2b2b" stroke-width="5" rx="2"/>') },
			線: { effect: '始点から終点へ線を引く。', example: '左から右へ線を引く', effectEn: 'Draws a line from a start point to an end point.', exampleEn: 'Draw a line from left to right', svg: lineSvg() },
			弧: { effect: '円周の一部を描く。半円や三日月の基礎になる。', example: '上弦の弧を引く', effectEn: 'Draws part of a circumference. The basis for semicircles and crescents.', exampleEn: 'Draw a waxing arc', svg: shapeSvg('<path d="M44 58 Q90 18 136 58" fill="none" stroke="#2b2b2b" stroke-width="6" stroke-linecap="round"/>') },
			雲形: { effect: '輪郭が演奏ごとに決まる、不規則さの文法を持つ閉じた形。', example: '中央に横長の雲形を置く', effectEn: 'A closed irregular form whose contour is decided anew for each performance.', exampleEn: 'Place a wide cloudform at center', svg: shapeSvg('<path d="M45 52 C40 34 58 22 77 28 C90 15 111 22 113 36 C135 35 143 52 131 65 C116 76 96 66 82 72 C63 78 46 68 45 52 Z" fill="none" stroke="#2b2b2b" stroke-width="5" stroke-linejoin="round"/>') },
			水平: { effect: '0度の向き。線なら横線として扱う。', example: '水平の線を引く', effectEn: 'A 0-degree orientation. A line is read as horizontal.', exampleEn: 'Draw a horizontal line', svg: angleSvg(0, true) },
			垂直: { effect: '90度の向き。線なら縦線として扱う。', example: '垂直の線を引く', effectEn: 'A 90-degree orientation. A line is read as vertical.', exampleEn: 'Draw a vertical line', svg: angleSvg(90, true) },
			斜め: { effect: '約45度の傾きを与える。', example: '斜めの四角を置く', effectEn: 'Applies a tilt of about 45 degrees.', exampleEn: 'Place a diagonal square', svg: angleSvg(45) },
			右上がり: { effect: '左下から右上へ向かう傾き。', example: '右上がりの線', effectEn: 'A tilt running from lower left to upper right.', exampleEn: 'A rising line', svg: angleSvg(-30, true) },
			右下がり: { effect: '左上から右下へ向かう傾き。', example: '右下がりの線', effectEn: 'A tilt running from upper left to lower right.', exampleEn: 'A falling line', svg: angleSvg(30, true) },
			回転: { effect: '図形全体を中心まわりに回転させる。', example: '回転した横長の四角', effectEn: 'Rotates the whole form around its center.', exampleEn: 'A rotated wide square', svg: angleSvg(30) },
			銀筆: { effect: '非常に細く、筆致の変化をほぼ抑えた線。', example: '銀筆で細い線を引く', effectEn: 'A very thin line with almost no variation in touch.', exampleEn: 'Draw a thin line with a silverpoint', svg: touchSvg('silverpoint') },
			鉛筆: { effect: '幅と横揺れが連動し、細かな副線と紙目の粒を伴う。', example: '鉛筆の線を引く', effectEn: 'Width and lateral sway move together, with fine secondary strokes and paper grain.', exampleEn: 'Draw a pencil line', svg: touchSvg('pencil') },
			ペン: { effect: '明瞭さを保ちながら、わずかな幅と軌道の変化を持つ。', example: 'ペンの線を引く', effectEn: 'Stays clear while varying slightly in width and path.', exampleEn: 'Draw a pen line', svg: touchSvg('pen') },
			ロットリング: { effect: '共有筆致を遮断した、均一で硬い製図線。', example: 'ロットリングの線', effectEn: 'A uniform, hard drafting line that blocks the shared touch.', exampleEn: 'A rotring line', svg: touchSvg('rotring') },
			クレヨン: { effect: '太い主線に擦れた副線と粒を重ねる。', example: '青いクレヨンの線', effectEn: 'Lays scuffed secondary strokes and grain over a thick main stroke.', exampleEn: 'A blue crayon line', svg: touchSvg('crayon') },
			チョーク: { effect: '幅の崩れ、途切れ、粉状の粒を含む淡い線。', example: '白いチョークの線', effectEn: 'A pale line with broken width, gaps, and powdery grain.', exampleEn: 'A white chalk line', svg: touchSvg('chalk') },
			細筆: { effect: '入りと抜きが細く、筆圧で幅が大きく変わる。', example: '細筆で線を引く', effectEn: 'Thin at entry and release, with width changing widely under pressure.', exampleEn: 'Draw a line with a fine brush', svg: touchSvg('brush_thin') },
			太筆: { effect: '大きな幅変化と穂先の筋を持つ太い筆線。', example: '太筆で黒い線を引く', effectEn: 'A thick brush stroke with wide width changes and streaks from the tip.', exampleEn: 'Draw a black line with a thick brush', svg: touchSvg('brush_thick') },
			ビュラン: { effect: '入りと抜きが細く、中央に彫りの勢いが集まる硬い線。', example: 'ビュランで線を彫る', effectEn: 'A hard line, thin at both ends, with the cutting force gathered at the center.', exampleEn: 'Cut a line with a burin', svg: touchSvg('burin') },
			ドライポイント: { effect: '緩い中膨らみと、片側だけの柔らかなburrを伴う線。', example: 'ドライポイントの線', effectEn: 'A line with a slight mid-swell and a soft burr on one side only.', exampleEn: 'A drypoint line', svg: touchSvg('drypoint') },
			コンピュータ: { effect: '幅と軌道を格子と段に落とし、同じ周期と破線を誤差なく反復する。', example: 'コンピュータの線', effectEn: 'Snaps width and path to a grid and steps, repeating the same cycle and dashes without error.', exampleEn: 'A computer line', svg: touchSvg('computer') },
			実線: { effect: '切れ目のない線。', example: '実線で引く', effectEn: 'An unbroken line.', exampleEn: 'Draw with a solid line', svg: lineSvg() },
			破線: { effect: '短い線分を間隔を空けて並べる。', example: '破線の弧', effectEn: 'Places short segments with gaps between them.', exampleEn: 'A dashed arc', svg: lineSvg('stroke-dasharray="14 9"') },
			点線: { effect: '点の連なりとして描く。', example: '点線で囲む', effectEn: 'Draws as a run of dots.', exampleEn: 'Enclose with a dotted line', svg: lineSvg('stroke-dasharray="1 12"') },
			一点鎖線: { effect: '長線と点を交互に並べる。', example: '一点鎖線を引く', effectEn: 'Alternates long dashes with dots.', exampleEn: 'Draw a dash-dot line', svg: lineSvg('stroke-dasharray="18 7 2 7"') },
			// おもて: eleven words, one contour, eleven interiors (saijiki-surface.ts).
			...SURFACE_PREVIEWS,
			白: { effect: '白系の色で描く。背景との対比に注意。', example: '白い円', effectEn: 'Draws in a white tone. Mind the contrast against the ground.', exampleEn: 'A white circle', svg: shapeSvg('<rect x="48" y="18" width="84" height="56" fill="#2b2b2b" opacity="0.16"/><circle cx="90" cy="46" r="24" fill="#ffffff" stroke="#c9c2b5" stroke-width="4"/>') },
			黒: { effect: '黒で描く。最も強い輪郭になる。', example: '黒い円', effectEn: 'Draws in black, giving the strongest contour.', exampleEn: 'A black circle', svg: shapeSvg('<circle cx="90" cy="46" r="25" fill="#2b2b2b"/>') },
			青: { effect: '青系の色で描く。', example: '青い線', effectEn: 'Draws in a blue tone.', exampleEn: 'A blue line', svg: lineSvg('', 5, 'round', '#2c5fb8') },
			赤: { effect: '赤系の色で描く。', example: '赤い三角', effectEn: 'Draws in a red tone.', exampleEn: 'A red triangle', svg: shapeSvg('<path d="M90 20 L132 70 L48 70 Z" fill="none" stroke="#c9362d" stroke-width="6" stroke-linejoin="round"/>') },
			緑: { effect: '緑系の色で描く。', example: '緑の点を散らす', effectEn: 'Draws in a green tone.', exampleEn: 'Scatter green dots', svg: scatter.replaceAll('#2b2b2b', '#2f8a4b') },
			灰: { effect: '灰色で描く。弱い輪郭や背景に向く。', example: '灰色の四角', effectEn: 'Draws in gray. Suits weak contours and grounds.', exampleEn: 'A gray square', svg: shapeSvg('<rect x="58" y="24" width="64" height="44" fill="none" stroke="#777777" stroke-width="6" rx="2"/>') },
			細かく: { effect: '小さな揺らぎを加える。', example: '細かく揺れる線', effectEn: 'Adds a small-amplitude fluctuation.', exampleEn: 'A finely swaying line', svg: lineSvg() },
			大きく: { effect: '振幅の大きな揺らぎを加える。', example: '大きく波打つ線', effectEn: 'Adds a large-amplitude fluctuation.', exampleEn: 'A largely undulating line', svg: shapeSvg('<path d="M20 48 C42 8 64 84 88 48 S134 8 160 48" fill="none" stroke="#2b2b2b" stroke-width="5" stroke-linecap="round"/>') },
			ゆっくり: { effect: 'ゆったりした周期の動きとして解釈する。', example: 'ゆっくり波打つ線', effectEn: 'Read as motion with a long period.', exampleEn: 'A slowly undulating line', svg: shapeSvg('<path d="M22 48 C62 20 112 76 158 48" fill="none" stroke="#2b2b2b" stroke-width="5" stroke-linecap="round"/>') },
			速く: { effect: '細かく速い振動として解釈する。', example: '速く震える線', effectEn: 'Read as a fine, fast vibration.', exampleEn: 'A quickly trembling line', svg: shapeSvg('<path d="M20 48 L32 40 L44 56 L56 40 L68 56 L80 40 L92 56 L104 40 L116 56 L128 40 L140 56 L158 48" fill="none" stroke="#2b2b2b" stroke-width="4" stroke-linecap="round"/>') },
			揺れる: { effect: '自然な揺れを線や配置に与える。', example: '揺れる線', effectEn: 'Gives lines and placement a natural sway.', exampleEn: 'A swaying line', svg: lineSvg() },
			波打つ: { effect: '波形のうねりを作る。', example: '波打つ青い線', effectEn: 'Makes a wave-shaped undulation.', exampleEn: 'An undulating blue line', svg: shapeSvg('<path d="M20 48 C42 22 66 74 88 48 S134 22 160 48" fill="none" stroke="#2c5fb8" stroke-width="5" stroke-linecap="round"/>') },
			震える: { effect: '細かい震えを作る。', example: '震える黒い線', effectEn: 'Makes a fine tremble.', exampleEn: 'A trembling black line', svg: shapeSvg('<path d="M20 48 L30 45 L40 52 L50 44 L60 50 L70 43 L80 51 L90 45 L100 53 L110 44 L120 50 L130 43 L140 51 L160 48" fill="none" stroke="#2b2b2b" stroke-width="4" stroke-linecap="round"/>') },
			滲む: { effect: '輪郭をぼかし、墨が染みるようにする。', example: '滲む黒い円', effectEn: 'Softens the contour so the ink bleeds.', exampleEn: 'A blurring black circle', svg: shapeSvg('<defs><filter id="pblur"><feGaussianBlur stdDeviation="3"/></filter></defs><circle cx="90" cy="46" r="24" fill="#2b2b2b" opacity="0.72" filter="url(#pblur)"/><circle cx="90" cy="46" r="20" fill="#2b2b2b" opacity="0.62"/>') },
			上: { effect: '画面の上側へ配置する。', example: '上に円を置く', effectEn: 'Places toward the upper side of the frame.', exampleEn: 'Place a circle at the top', svg: shapeSvg('<circle cx="90" cy="25" r="14" fill="#2b2b2b"/><path d="M28 70 H152" stroke="#d7d1c4" stroke-width="2"/>') },
			下: { effect: '画面の下側へ配置する。', example: '下に円を置く', effectEn: 'Places toward the lower side of the frame.', exampleEn: 'Place a circle at the bottom', svg: shapeSvg('<path d="M28 22 H152" stroke="#d7d1c4" stroke-width="2"/><circle cx="90" cy="67" r="14" fill="#2b2b2b"/>') },
			中央: { effect: '中央付近へ配置する。', example: '中央に円を置く', effectEn: 'Places near the middle of the frame.', exampleEn: 'Place a circle at center', svg: shapeSvg('<circle cx="90" cy="46" r="16" fill="#2b2b2b"/>') },
			左端: { effect: '左端近くへ寄せる。', example: '左端に線を置く', effectEn: 'Pulls close to the left edge.', exampleEn: 'Place a line at the left edge', svg: shapeSvg('<path d="M30 18 V74" stroke="#2b2b2b" stroke-width="7" stroke-linecap="round"/><path d="M90 16 V76" stroke="#d7d1c4" stroke-width="2"/>') },
			右端: { effect: '右端近くへ寄せる。', example: '右端に線を置く', effectEn: 'Pulls close to the right edge.', exampleEn: 'Place a line at the right edge', svg: shapeSvg('<path d="M90 16 V76" stroke="#d7d1c4" stroke-width="2"/><path d="M150 18 V74" stroke="#2b2b2b" stroke-width="7" stroke-linecap="round"/>') },
			上端: { effect: '上の縁へ寄せる。', example: '上端に線を引く', effectEn: 'Pulls to the upper margin.', exampleEn: 'Draw a line at the top edge', svg: shapeSvg('<path d="M30 18 H150" stroke="#2b2b2b" stroke-width="7" stroke-linecap="round"/><path d="M28 46 H152" stroke="#d7d1c4" stroke-width="2"/>') },
			下端: { effect: '下の縁へ寄せる。', example: '下端に線を引く', effectEn: 'Pulls to the lower margin.', exampleEn: 'Draw a line at the bottom edge', svg: shapeSvg('<path d="M28 46 H152" stroke="#d7d1c4" stroke-width="2"/><path d="M30 74 H150" stroke="#2b2b2b" stroke-width="7" stroke-linecap="round"/>') },
			中心: { effect: '中心座標を基準に配置する。', example: '中心に円を置く', effectEn: 'Places against the center coordinate.', exampleEn: 'Place a circle at the middle', svg: shapeSvg('<path d="M90 14 V78 M32 46 H148" stroke="#d7d1c4" stroke-width="2"/><circle cx="90" cy="46" r="15" fill="#2b2b2b"/>') },
			隅: { effect: '四隅のいずれかへ配置する。', example: '隅に小さな円を置く', effectEn: 'Places at one of the four corners.', exampleEn: 'Place a small circle in a corner', svg: shapeSvg('<circle cx="36" cy="25" r="11" fill="#2b2b2b"/><circle cx="144" cy="67" r="11" fill="#2b2b2b" opacity="0.28"/>') },
			置く: { effect: '指定した場所に一つ置く。', example: '中央に円を置く', effectEn: 'Places one element at the given location.', exampleEn: 'Place a circle at center', svg: shapeSvg('<circle cx="90" cy="46" r="22" fill="#2b2b2b"/>') },
			並べる: { effect: '同じ要素を列として並べる。', example: '円を横に並べる', effectEn: 'Lines the same element up as a row.', exampleEn: 'Line circles up horizontally', svg: shapeSvg('<circle cx="55" cy="46" r="12" fill="#2b2b2b"/><circle cx="90" cy="46" r="12" fill="#2b2b2b"/><circle cx="125" cy="46" r="12" fill="#2b2b2b"/>') },
			埋める: { effect: '面や領域を密に満たす。', example: '点で埋める', effectEn: 'Fills a face or region densely.', exampleEn: 'Fill with dots', svg: shapeSvg('<circle cx="50" cy="28" r="5" fill="#2b2b2b"/><circle cx="80" cy="32" r="5" fill="#2b2b2b"/><circle cx="112" cy="29" r="5" fill="#2b2b2b"/><circle cx="62" cy="55" r="5" fill="#2b2b2b"/><circle cx="97" cy="58" r="5" fill="#2b2b2b"/><circle cx="132" cy="55" r="5" fill="#2b2b2b"/>') },
			散らす: { effect: '要素を不規則に散布する。', example: '黒い点を散らす', effectEn: 'Scatters elements irregularly.', exampleEn: 'Scatter black dots', svg: scatter },
			引く: { effect: '線や弧を描く動作。', example: '線を引く', effectEn: 'The act of drawing a line or an arc.', exampleEn: 'Draw a line', svg: lineSvg() },
			敷き詰める: { effect: '要素を隙間なく反復して領域を覆う。', example: '四角で敷き詰める', effectEn: 'Repeats an element without gaps to cover the region.', exampleEn: 'Tile with squares', svg: shapeSvg('<g fill="none" stroke="#2b2b2b" stroke-width="3"><rect x="24" y="20" width="32" height="30"/><rect x="60" y="20" width="32" height="30"/><rect x="96" y="20" width="32" height="30"/><rect x="132" y="20" width="32" height="30"/><rect x="24" y="54" width="32" height="30"/><rect x="60" y="54" width="32" height="30"/><rect x="96" y="54" width="32" height="30"/><rect x="132" y="54" width="32" height="30"/></g>') },
			縦長: { effect: '縦方向に長い比率にする。', example: '縦長の楕円', effectEn: 'Makes the proportion long in the vertical direction.', exampleEn: 'A tall ellipse', svg: shapeSvg('<ellipse cx="90" cy="46" rx="20" ry="34" fill="none" stroke="#2b2b2b" stroke-width="5"/>') },
			横長: { effect: '横方向に長い比率にする。', example: '横長の楕円', effectEn: 'Makes the proportion long in the horizontal direction.', exampleEn: 'A wide ellipse', svg: shapeSvg('<ellipse cx="90" cy="46" rx="42" ry="18" fill="none" stroke="#2b2b2b" stroke-width="5"/>') },
			全幅: { effect: '画面幅いっぱいに広げる。', example: '全幅の線', effectEn: 'Spreads across the full width of the frame.', exampleEn: 'A full-width line', svg: shapeSvg('<path d="M14 46 H166" stroke="#2b2b2b" stroke-width="6" stroke-linecap="round"/>') },
			半幅: { effect: '画面の半分程度の幅にする。', example: '半幅の線', effectEn: 'Sets the width to about half the frame.', exampleEn: 'A half-width line', svg: shapeSvg('<path d="M45 46 H135" stroke="#2b2b2b" stroke-width="6" stroke-linecap="round"/><path d="M14 72 H166" stroke="#d7d1c4" stroke-width="2"/>') },
			半円: { effect: '円の半分を描く。', example: '半円を置く', effectEn: 'Draws half of a circle.', exampleEn: 'Place a semicircle', svg: shapeSvg('<path d="M50 60 A40 40 0 0 1 130 60" fill="none" stroke="#2b2b2b" stroke-width="6" stroke-linecap="round"/>') },
			上弦: { effect: '上側に弦を持つ弧として扱う。', example: '上弦の月', effectEn: 'Read as an arc with its chord on the upper side.', exampleEn: 'A waxing moon', svg: shapeSvg('<path d="M50 56 Q90 22 130 56" fill="none" stroke="#2b2b2b" stroke-width="6" stroke-linecap="round"/>') },
			下弦: { effect: '下側に弦を持つ弧として扱う。', example: '下弦の月', effectEn: 'Read as an arc with its chord on the lower side.', exampleEn: 'A waning moon', svg: shapeSvg('<path d="M50 36 Q90 70 130 36" fill="none" stroke="#2b2b2b" stroke-width="6" stroke-linecap="round"/>') },
			三日月: { effect: '細い月形を描く。', example: '三日月を置く', effectEn: 'Draws a thin moon form.', exampleEn: 'Place a crescent', svg: shapeSvg('<path d="M106 18 C76 24 62 52 82 74 C52 63 50 27 82 14 C92 12 100 14 106 18 Z" fill="#2b2b2b"/>') },
			沿う: { effect: `直前の線を参照する関係。`, example: `前の線に沿って`, effectEn: `A relation that refers to the preceding line.`, exampleEn: `along the previous line`, svg: shapeSvg(`<path d="M24 56 C58 28 104 70 156 34" fill="none" stroke="#2b2b2b" stroke-width="5" stroke-linecap="round"/><circle cx="62" cy="45" r="5" fill="#c9362d"/><circle cx="94" cy="51" r="5" fill="#c9362d"/><circle cx="126" cy="43" r="5" fill="#c9362d"/>`) },
			触れない: { effect: `直前の形に接触しない関係。`, example: `前の形に触れない`, effectEn: `A relation that makes no contact with the preceding shape.`, exampleEn: `not touching the previous shape`, svg: shapeSvg(`<circle cx="78" cy="46" r="22" fill="none" stroke="#2b2b2b" stroke-width="5"/><circle cx="124" cy="46" r="10" fill="none" stroke="#c9362d" stroke-width="5"/>`) },
			触れる: { effect: `直前の形に接触する関係。`, example: `前の線に触れる`, effectEn: `A relation that makes contact with the preceding shape.`, exampleEn: `touching the previous line`, svg: shapeSvg(`<circle cx="78" cy="46" r="22" fill="none" stroke="#2b2b2b" stroke-width="5"/><circle cx="124" cy="46" r="24" fill="none" stroke="#c9362d" stroke-width="5"/>`) },
			切る: { effect: `直前の線を横切る関係。`, example: `前の線を切る`, effectEn: `A relation that crosses the preceding line.`, exampleEn: `cutting the previous line`, svg: shapeSvg(`<path d="M38 46 H142" stroke="#2b2b2b" stroke-width="6" stroke-linecap="round"/><path d="M92 20 L78 72" stroke="#c9362d" stroke-width="6" stroke-linecap="round"/>`) },
			間に: { effect: `直前の二つの要素の間に置く関係。`, example: `前の二つの間に`, effectEn: `A relation that places between the two preceding elements.`, exampleEn: `between the previous two`, svg: shapeSvg(`<circle cx="56" cy="46" r="14" fill="none" stroke="#2b2b2b" stroke-width="5"/><circle cx="124" cy="46" r="14" fill="none" stroke="#2b2b2b" stroke-width="5"/><circle cx="90" cy="46" r="8" fill="#c9362d"/>`) },
		};
		const entry = previews[canonicalWord] ?? previews[word];
		if (entry) return { ...base, ...localized(entry) };
		return {
			...base,
			effect: isJa ? '記述の解釈に影響する語彙です。' : 'A vocabulary word that shapes how the description is read.',
			example: isJa ? `${word}を使う` : `Use "${word}"`,
			svg: lineSvg(),
		};
	}

	// Shown when a plugin document declares no artwork, or declares one the
	// server refused. The built-in table has the same shape of fallback: an
	// unknown word gets a generic mark rather than an empty frame.
	const PLUGIN_FALLBACK_SVG =
		'<svg viewBox="0 0 180 92" aria-hidden="true"><rect width="180" height="92" rx="6" fill="#fffdf8"/><path d="M32 48 C52 28 74 68 94 48 S132 28 150 48" stroke="#2a4a72" stroke-width="5" fill="none" stroke-linecap="round"/><path d="M34 62 C58 50 78 76 102 62 S134 50 150 62" stroke="#7d9cc4" stroke-width="3" fill="none" stroke-linecap="round"/></svg>';

	/**
	 * A plugin word's preview, in the same four parts a built-in word shows.
	 *
	 * The document supplies three of them already: the qualified name is the
	 * title, the note is the effect, and the first firing phrase is the example
	 * -- it is what a description would actually say to reach the word, which is
	 * what the built-in examples are too. The fourth is the drawing baked from
	 * the word's own expansion.
	 */
	function pluginPreview(entry: {
		qualified_name: string;
		note_ja: string;
		note_en: string;
		fires_on_ja?: string[];
		fires_on_en?: string[];
		preview_url?: string;
		preview_url_2x?: string;
	}): SaijikiPreview {
		const isJa = getLang() === 'ja';
		const firesOn = (isJa ? entry.fires_on_ja : entry.fires_on_en) ?? [];
		return {
			categoryKey: 'plugin',
			word: entry.qualified_name,
			canonicalWord: entry.qualified_name,
			effect: (isJa ? entry.note_ja : entry.note_en) || '',
			example: firesOn[0] ?? '',
			// The fallback is the drawing, not an empty frame; it is only read
			// when the word ships no artwork, since `image` wins where it is set.
			svg: PLUGIN_FALLBACK_SVG,
			image: entry.preview_url || undefined,
			image2x: entry.preview_url_2x || undefined,
		};
	}

	// ── Color catalog ────────────────────────────────────────
	// Refine dialogs: null = inherit from the parent artwork (field omitted).
	let refineWildOverride = $state<boolean | null>(null);
	function setRefineWild(value: boolean | null) { refineWildOverride = value; }
	let colorCatalogs = $state<ColorCatalog[]>([FALLBACK_CATALOG]);
	let defaultCatalogId = $state('default');
	// Old catalog id -> the id it answers to today, served by /api/color-catalogs.
	let renamedCatalogIds = $state<Record<string, string>>({});
	const currentCatalog = $derived(catalogById(colorCatalogs, colorCatalogSettings.effectiveId) ?? colorCatalogs[0] ?? FALLBACK_CATALOG);

	// ── Settings tabs ────────────────────────────────────────
	let settingsStatus = $state<SettingsStatus | null>(null);
	let settingsStatusError = $state<string | null>(null);
	let settingsStatusLoading = $state(false);
	let pluginEntries = $state<PluginEntry[]>([]);
	let modelSettings = $state<ModelSettings | null>(null);
	let modelSettingsStatus = $state<string | null>(null);
	let modelFetchResults = $state<Record<string, { type: 'success' | 'error'; message: string }>>({});
	let modelSettingsLoading = $state(false);
	let modelCatalog = $state<ProviderGroup[]>(PROVIDER_GROUPS.filter((group) => group.id !== 'nvidia'));
	let availableModelCatalog = $state<ProviderGroup[]>(PROVIDER_GROUPS.filter((group) => group.id !== 'nvidia'));
	let availableVisionModelCatalog = $state<ProviderGroup[]>([]);
	let availableModelsLoaded = $state(false);
	// Teach models.ts which providers this server serves, so that a reference
	// qualified with an operator-added provider is recognised as qualified.
	$effect(() => {
		registerModelCatalog(modelCatalog);
		registerModelCatalog(availableModelCatalog);
		registerModelCatalog(availableVisionModelCatalog);
	});
	let dbBackupStatus = $state<string | null>(null);
	let outputSaveStatus = $state<string | null>(null);
	let logRetentionStatus = $state<string | null>(null);
	let renderLimitsStatus = $state<string | null>(null);
	let users = $state<UserItem[]>([]);
	let groups = $state<UserGroup[]>([]);
	let newUserName = $state('');
	let newUserEmail = $state('');
	let newUserPassword = $state('');
	let newUserPermissionGroups = $state<PermissionGroup[]>(['users']);
	let newUserGroupId = $state('');
	let selectedUserId = $state<string | null>(null);
	let editUserName = $state('');
	let editUserEmail = $state('');
	let editUserPassword = $state('');
	let editUserPermissionGroups = $state<PermissionGroup[]>(['users']);
	let editUserGroupId = $state('');
	let newGroupName = $state('');
	let editGroupId = $state<string | null>(null);
	let editGroupName = $state('');
	let userSettingsStatus = $state<string | null>(null);
	let userSettingsLoading = $state(false);
	let userSettingsRequestId = 0;
	let authToken = $state<string | null>(null);
	let currentUser = $state<UserItem | null>(null);
	// What the signed-in member may do, derived once. Every gate below asks these
	// rather than reading the membership list itself: the per-work sharing rules
	// land on the same questions, and a condition spelled out in twenty places is
	// twenty places to keep in step.
	const isAdmin = $derived(holdsPermissionGroup(currentUser, 'admins'));
	// Leaders administer members; an admin outranks the distinction, so the
	// leader-only branches are the ones that must exclude them.
	const isLeaderOnly = $derived(!isAdmin && holdsPermissionGroup(currentUser, 'leaders'));
	const tooltipsEnabled = $derived(currentUser?.tooltips_enabled !== false);
	let uiModeSaving = $state(false);
	let uiModeSaveError = $state(false);
	const uiMode = $derived(normalizeUiMode(currentUser?.ui_mode));
	const uiCustom = $derived(normalizeUiCustom(currentUser?.ui_custom));
	const uiVisibility = $derived(resolveUiVisibility(uiMode, uiCustom));
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

	type ProviderFailure = {
		code: 'model_gone' | 'provider_auth' | 'provider_rate_limit' | 'provider_error';
		stage: string;
		provider_status: number;
		message: string;
	};

	/**
	 * v1.98: サーバーが返す失敗詳細を人が読める 1 行にする。
	 * プロバイダ由来の失敗（提供終了・認証・レート制限）は種別の説明を頭に置き、
	 * 原因を追えるようにプロバイダの原文メッセージを必ず併記する。
	 */
	function describeApiError(detail: unknown, status: number): string {
		if (detail === 'render capacity is full') return t().errorRenderBusy;
		if (detail === 'description is only labels') return t().errorDescriptionOnlyLabels;
		if (typeof detail === 'string' && detail) return detail;
		if (detail && typeof detail === 'object' && 'code' in detail) {
			const failure = detail as ProviderFailure;
			const stage = failure.stage === 'interpret' ? t().runStatusStage1 : t().runStatusStage2;
			const headline =
				failure.code === 'model_gone'
					? t().errorModelGone(stage)
					: failure.code === 'provider_auth'
						? t().errorProviderAuth(stage)
						: failure.code === 'provider_rate_limit'
							? t().errorProviderRateLimit(stage)
							: t().errorProviderOther(stage, failure.provider_status);
			return `${headline}\n${failure.message}`;
		}
		return `HTTP ${status}`;
	}

	// The server holds a fixed number of render slots and refuses immediately
	// (no queueing) when they are all taken, so a fan-out such as the 4-candidate
	// grid can lose requests to a 503 that a short wait would have avoided.
	// Retry that one condition here; every other status is passed through.
	const RENDER_CAPACITY_RETRIES = 3;

	function delay(ms: number, signal?: AbortSignal | null): Promise<void> {
		return new Promise((resolve, reject) => {
			if (signal?.aborted) { reject(new DOMException('Aborted', 'AbortError')); return; }
			const timer = window.setTimeout(() => { signal?.removeEventListener('abort', onAbort); resolve(); }, ms);
			function onAbort() { window.clearTimeout(timer); reject(new DOMException('Aborted', 'AbortError')); }
			signal?.addEventListener('abort', onAbort, { once: true });
		});
	}

	/** Failed response -> Error carrying the localized message, never the raw body. */
	async function apiError(r: Response): Promise<Error> {
		const d = await r.json().catch(() => ({})) as { detail?: unknown };
		return new Error(describeApiError(d.detail, r.status));
	}

	/**
	 * The drawing of a listed work, fetched only if the listing did not carry it.
	 *
	 * The listing asks for thumbnails instead of pictures, so an item that came
	 * from it holds an empty `svg`. Anything that needs the drawing itself --
	 * putting it on the canvas, comparing it with a replay, building a contact
	 * sheet, saving it again -- asks for that one work rather than making the
	 * listing carry every work's picture for the sake of the one that is used.
	 *
	 * The answer is kept on the item, so looking at the same work twice asks
	 * once. Failure leaves the empty string the item already had: the caller
	 * behaves as it did before any of this, which is the point of not removing
	 * the field.
	 */
	async function ensureIterationSvg(it: { id?: string; svg?: string }): Promise<string> {
		if (it.svg) return it.svg;
		if (!it.id) return '';
		try {
			const r = await apiFetch(`/api/history/${encodeURIComponent(it.id)}/svg`, { cache: 'no-store' });
			if (!r.ok) return '';
			const svg = await r.text();
			it.svg = svg;
			return svg;
		} catch {
			return '';
		}
	}

	async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
		const headers = new Headers(init.headers);
		for (let attempt = 0; ; attempt += 1) {
			const response = await fetch(path, { ...init, headers, credentials: 'same-origin' });
			if (response.status !== 503 || attempt >= RENDER_CAPACITY_RETRIES) return response;
			const body = await response.clone().text().catch(() => '');
			if (!body.includes('render capacity is full')) return response;
			// Slots free in well under the Retry-After of 1s the server suggests,
			// so back off in shorter steps but never longer than it asked for.
			const retryAfterMs = Number(response.headers.get('Retry-After')) * 1000;
			const backoffMs = 200 * 2 ** attempt;
			await delay(Number.isFinite(retryAfterMs) && retryAfterMs > 0 ? Math.min(retryAfterMs, backoffMs) : backoffMs, init.signal);
		}
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

	// The server holds the intent and the folder's name; the handle itself lives
	// in this browser's IndexedDB, so the two are applied together on sign-in.
	function applyDownloadFolderSettings(user: UserItem | null) {
		downloadFolderSettings.applyUser(user);
		void downloadFolderSettings.refresh();
	}

	async function updateDownloadFolder(update: { enabled?: boolean; name?: string | null }) {
		if (!currentUser) return;
		const previousUser = currentUser;
		const body: Record<string, unknown> = {};
		if (update.enabled !== undefined) body.download_folder_enabled = update.enabled;
		if (update.name !== undefined) body.download_folder_name = update.name ?? '';
		currentUser = {
			...currentUser,
			...(update.enabled !== undefined ? { download_folder_enabled: update.enabled } : {}),
			...(update.name !== undefined ? { download_folder_name: update.name } : {}),
		};
		downloadFolderSettings.applyUser(currentUser);
		try {
			const r = await apiFetch('/api/auth/me/settings', {
				method: 'PATCH',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify(body)
			});
			if (!r.ok) {
				const d = await r.json().catch(() => ({})) as { detail?: unknown };
				throw new Error(describeApiError(d.detail, r.status));
			}
			currentUser = await r.json() as UserItem;
			downloadFolderSettings.applyUser(currentUser);
		} catch (e) {
			currentUser = previousUser;
			downloadFolderSettings.applyUser(previousUser);
			console.warn('failed to update the download folder setting', e);
		}
	}

	async function chooseDownloadFolder() {
		const name = await downloadFolderSettings.choose();
		if (name === null) return;
		await updateDownloadFolder({ enabled: true, name });
	}

	async function clearDownloadFolder() {
		await downloadFolderSettings.clear();
		await updateDownloadFolder({ enabled: false, name: null });
	}

	function applyUserTheme(user: UserItem | null) {
		// No stored preference (signed out, or a row without one) follows the
		// release default rather than falling back to light.
		darkMode = (user?.ui_theme ?? 'dark') === 'dark';
	}

	function modelsFor(provider: Provider) {
		const group = availableModelCatalog.find((item) => item.id === provider);
		if (group) return group.models;
		return availableModelsLoaded ? [] : modelsForProvider(provider);
	}

	function visionModelsFor(provider: Provider) {
		return availableVisionModelCatalog.find((group) => group.id === provider)?.models ?? [];
	}

	function reconcileDemoPromptModel() {
		if (!availableModelsLoaded || !demoSettingsLoaded) return;
		const configured = availableModelCatalog.some(
			(group) => group.id === demoSettings.prompt_provider && group.models.some((model) => model.id === demoSettings.prompt_model)
		);
		if (configured) return;
		const fallbackGroup = availableModelCatalog.find((group) => group.models.length > 0);
		const fallbackModel = fallbackGroup?.models[0]?.id;
		if (!fallbackGroup || !fallbackModel) return;
		void saveDemoSettings({ ...demoSettings, prompt_provider: fallbackGroup.id, prompt_model: fallbackModel });
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
		okugakiModel = settings.okugaki_model
			? qualifiedModelId(settings.okugaki_provider ?? settings.vision_provider, settings.okugaki_model)
			: qualifiedModelId(settings.vision_provider, settings.vision_model);
		instructionCaptionVisible = settings.instruction_caption_visible !== false;
		applyUserSettings(settings);
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

	async function persistOkugakiModel(provider: Provider, model: string): Promise<void> {
		const nextModel = qualifiedModelId(provider, model.trim());
		if (!nextModel || nextModel === okugakiModel) return;
		const previous = okugakiModel;
		okugakiModel = nextModel;
		if (!currentUser) return;
		try {
			const r = await apiFetch('/api/auth/me/settings', {
				method: 'PATCH',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ model_settings: { okugaki_provider: provider, okugaki_model: model.trim() } })
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

	// Two gates, both of which have to open: the permission group says whether
	// this member may see the tab at all, the detail level says whether they
	// asked to. The tab bar in SettingsModal asks the second one the same way.
	function canAccessSettingsTab(tab: SettingsTab) {
		return canAccessSettingsTabFor(tab, currentUser) && settingsTabShownAtDetail(tab, settingsDetail);
	}

	function defaultSettingsTab(): SettingsTab {
		const preferred = defaultSettingsTabFor(currentUser);
		// `plugins` -- what a member outside the administrators group would land
		// on -- is one of the tabs the standard mode hides. `export` is the
		// fallback because no gate can hide it: it is neither administrator-only
		// nor detailed-only, and T-50 executes that claim.
		return canAccessSettingsTab(preferred) ? preferred : 'export';
	}

	function setSettingsDetail(detail: SettingsDetailLevel) {
		settingsDetail = detail;
		try { localStorage.setItem(SETTINGS_DETAIL_KEY, detail); } catch { /* private browsing */ }
		// Narrowing the dialog can hide the tab that is open. Route the move
		// through selectSettingsTab so the new tab loads what it needs, the way
		// it would if the member had pressed it.
		if (settingsOpen && !canAccessSettingsTab(settingsTab)) selectSettingsTab(defaultSettingsTab());
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

	// ── Resuming a batch that stopped part-way ──────────────
	// A page of works without their drawings is a few hundred kilobytes, so the
	// two questions are asked at different depths. Whether to offer the button
	// needs only the newest work carrying a batch number, and is asked every time
	// the batch tab is shown; which lines are missing needs the whole run, and is
	// asked once, after the button is pressed.
	const BATCH_RESUME_PROBE_LIMIT = 20;
	const BATCH_RESUME_SCAN_PAGE = 100;
	const BATCH_RESUME_SCAN_MAX = 500;

	async function fetchWorksPage(offset: number, limit: number): Promise<Iteration[]> {
		const params = new URLSearchParams({
			offset: String(offset),
			limit: String(limit),
			include_svg: 'false',
		});
		const r = await apiFetch(`/api/history?${params.toString()}`, { cache: 'no-store' });
		if (!r.ok) throw new Error(`HTTP ${r.status}`);
		const data = await r.json() as { items?: Iteration[] };
		return Array.isArray(data.items) ? data.items : [];
	}

	/** Whether the newest stored batch has lines the last run never reached. */
	async function refreshBatchResume() {
		const prompt = batchPromptHistory[0] ?? '';
		if (!currentUser || !prompt) { batchResume = null; return; }
		const lines = numberedBatchLines(prompt, (text) => !!pipelineDescription(text).trim());
		if (lines.length === 0) { batchResume = null; return; }
		try {
			const work = latestBatchWork(await fetchWorksPage(0, BATCH_RESUME_PROBE_LIMIT));
			batchResume = work && batchStoppedPartWay(lines, work)
				? { prompt, lines, runId: work.batch_run_id ?? null, work }
				: null;
		} catch (e) {
			batchResume = null;
			console.warn('failed to check whether the last batch reached its end', e);
		}
	}

	/** Every work of one batch run, paged back until the run has been walked past. */
	async function collectBatchRunWorks(runId: string | null, need: number): Promise<Iteration[]> {
		const collected: Iteration[] = [];
		for (let offset = 0; offset < BATCH_RESUME_SCAN_MAX; offset += BATCH_RESUME_SCAN_PAGE) {
			const page = await fetchWorksPage(offset, BATCH_RESUME_SCAN_PAGE);
			if (page.length === 0) break;
			const mine = page.filter((item) =>
				typeof item.batch_line_number === 'number'
				&& (runId === null || (item.batch_run_id ?? null) === runId));
			collected.push(...mine);
			// The run's works sit together, so a page without one means the listing
			// has walked past it -- but only once one has been seen. Works made
			// after the run sit above it, and a page of those is not the end.
			if (mine.length === 0 && collected.length > 0) break;
			if (collected.length >= need) break;
			if (page.length < BATCH_RESUME_SCAN_PAGE) break;
		}
		return collected;
	}

	/** Put back the conditions the last work of the stopped run was drawn under. */
	function applyBatchRunConditions(work: Iteration) {
		const conditions = conditionsOfWork(work);
		if (conditions.stage1Model) {
			const ref = splitModelRef(conditions.stage1Model, availableModelCatalog);
			if (ref.provider) stage1Provider = ref.provider;
			stage1Model = ref.model;
		}
		if (conditions.stage2Model) {
			const ref = splitModelRef(conditions.stage2Model, availableModelCatalog);
			if (ref.provider) stage2Provider = ref.provider;
			stage2Model = ref.model;
		}
		// `auto` reads each description anew, so a run made under it must resume
		// under it -- the resolved id is what the last line happened to get, not
		// what was asked for. A work older than the column records no mode, and
		// then the resolved id is the best that was ever stored.
		if (conditions.catalogMode === 'auto') colorCatalogSettings.selected = AUTO_CATALOG_ID;
		else if (conditions.catalogId) colorCatalogSettings.selected = conditions.catalogId;
		// Not conditional: a work with no prose was drawn with the layer off, and
		// leaving the switch where it is would resume under other conditions.
		sketchMode = sketchModeOf(conditions.sketchGrain);
		if (conditions.wild !== null) wildSettings.set(conditions.wild);
		if (conditions.canvasAspectId) canvasAspectId = normalizeCanvasAspectId(conditions.canvasAspectId);
	}

	async function resumeInterruptedBatch() {
		const resume = batchResume;
		if (!resume || loading || variationGridBusy) return;
		let works: Iteration[];
		try {
			works = await collectBatchRunWorks(resume.runId, resume.lines.length);
		} catch (e) {
			error = e instanceof Error ? e.message : String(e);
			return;
		}
		const remaining = linesToResume(resume.lines, works, resume.runId);
		// Nothing missing after all: the listing knows more than the probe did.
		if (remaining.length === 0) { batchResume = null; return; }
		applyBatchRunConditions(resume.work);
		// The box is refilled with the whole batch, not with what is left of it:
		// the resumed lines keep the numbers the prompt gave them, and the numbers
		// are what the works are named by.
		batchInput = resume.prompt;
		batchResume = null;
		await submit({ resumeLines: remaining });
	}

	function normalizeDemoSettings(settings: DemoSettings): DemoSettings {
		// Values stored before prompt_provider existed carry the provider inside
		// prompt_model; the server splits them, and so does this.
		const prompt = splitModelRef(settings.prompt_model || DEFAULT_MODEL);
		return {
			save_db: !!settings.save_db,
			save_files: !!settings.save_files,
			prompt_provider: prompt.provider ?? settings.prompt_provider ?? DEFAULT_PROVIDER,
			prompt_model: prompt.model,
			seed_phrase: settings.seed_phrase.trim() || DEFAULT_DEMO_SETTINGS.seed_phrase,
			interval_seconds: Math.max(1, Math.min(3600, Math.round(settings.interval_seconds || 30))),
			timeout_seconds: Math.max(60, Math.min(86400, Math.round(settings.timeout_seconds || 3600))),
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
		if (!isAdmin) return;
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
		if (!isAdmin) return;
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
				const d = await r.json().catch(() => ({})) as { detail?: unknown };
				throw new Error(describeApiError(d.detail, r.status));
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
				const d = await r.json().catch(() => ({})) as { detail?: unknown };
				throw new Error(describeApiError(d.detail, r.status));
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
				const d = await r.json().catch(() => ({})) as { detail?: unknown };
				throw new Error(describeApiError(d.detail, r.status));
			}
			currentUser = await r.json() as UserItem;
			applyUserTheme(currentUser);
			applyDownloadFolderSettings(currentUser);
		} catch (e) {
			currentUser = previousUser;
			darkMode = previousDarkMode;
			console.warn('failed to update UI theme', e);
		}
	}

	async function updateUiMode(nextMode: UiMode, nextCustom: UiCustomVisibility = uiCustom) {
		if (!currentUser || uiModeSaving) return;
		const previousUser = currentUser;
		const normalizedCustom = nextMode === 'simple' ? {} : normalizeUiCustom(nextCustom);
		uiModeSaving = true;
		uiModeSaveError = false;
		currentUser = { ...currentUser, ui_mode: nextMode, ui_custom: normalizedCustom };
		const nextVisibility = resolveUiVisibility(nextMode, normalizedCustom);
		if (!nextVisibility.input_modes) inputMode = 'single';
		if (!nextVisibility.work_tools) outputTab = 'canvas';
		try {
			const r = await apiFetch('/api/auth/me/settings', {
				method: 'PATCH',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ ui_mode: nextMode, ui_custom: normalizedCustom })
			});
			if (!r.ok) {
				const d = await r.json().catch(() => ({})) as { detail?: unknown };
				throw new Error(describeApiError(d.detail, r.status));
			}
			const updatedUser = await r.json() as UserItem;
			const savedCustom = normalizeUiCustom(updatedUser.ui_custom);
			const customMatches = UI_VISIBILITY_KEYS.every((key) => savedCustom[key] === normalizedCustom[key]);
			if (updatedUser.ui_mode !== nextMode || !customMatches) {
				throw new Error('UI mode settings were not persisted by the server');
			}
			currentUser = updatedUser;
		} catch (e) {
			currentUser = previousUser;
			uiModeSaveError = true;
			console.warn('failed to update UI mode', e);
		} finally {
			uiModeSaving = false;
		}
	}

	async function updateTooltipsEnabled(enabled: boolean) {
		if (!currentUser) return;
		const previousUser = currentUser;
		currentUser = { ...currentUser, tooltips_enabled: enabled };
		try {
			const r = await apiFetch('/api/auth/me/settings', {
				method: 'PATCH',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ tooltips_enabled: enabled })
			});
			if (!r.ok) {
				const d = await r.json().catch(() => ({})) as { detail?: unknown };
				throw new Error(describeApiError(d.detail, r.status));
			}
			const updatedUser = await r.json() as UserItem;
			if (updatedUser.tooltips_enabled !== enabled) {
				throw new Error('Tooltip settings were not persisted by the server');
			}
			currentUser = updatedUser;
		} catch (e) {
			currentUser = previousUser;
			console.warn('failed to update tooltip settings', e);
		}
	}

	function updateUiCustomItem(key: UiVisibilityKey, visible: boolean) {
		void updateUiMode('custom', { ...uiCustom, [key]: visible });
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
				const d = await r.json().catch(() => ({})) as { detail?: unknown };
				throw new Error(describeApiError(d.detail, r.status));
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
		// What the page owns; the features add their own fields to the save.
		const pageModelSettings: UserModelSettings = {
			stage1_provider: stage1Provider,
			stage1_model: stage1Model,
			stage2_provider: stage2Provider,
			stage2_model: stage2Model,
			vision_provider: visionProvider,
			vision_model: visionModel,
			okugaki_provider: splitModelRef(okugakiModel).provider ?? visionProvider,
			okugaki_model: splitModelRef(okugakiModel).model,
			instruction_caption_visible: instructionCaptionVisible,
		};
		const model_settings = { ...pageModelSettings, ...collectUserSettings() };
		try {
			const r = await apiFetch('/api/auth/me/settings', {
				method: 'PATCH',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ model_settings })
			});
			if (!r.ok) {
				const d = await r.json().catch(() => ({})) as { detail?: unknown };
				throw new Error(describeApiError(d.detail, r.status));
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
		catalogSelectionSnapshot = colorCatalogSettings.selected;
		catalogOpen = true;
	}

	function persistSelectedCatalog() {
		colorCatalogSettings.save();
	}

	// The selection rides in the user's model_settings: a drawing needs a session,
	// so a browser-wide value would only ever be the wrong user's.
	async function persistColorCatalogSelection(selected: string) {
		if (!currentUser) return;
		try {
			const r = await apiFetch('/api/auth/me/settings', { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ model_settings: { color_catalog_id: selected } }) });
			if (!r.ok) throw new Error(`HTTP ${r.status}`);
			currentUser = await r.json() as UserItem;
		} catch (e) { console.warn('failed to save color catalog selection', e); }
	}
	bindColorCatalogPersist((selected) => { void persistColorCatalogSelection(selected); });

	// The folds ride in the user's model_settings for the same reason the
	// catalogue does: neither section has anything to show without a session.
	// A failed save leaves the fold as the user just set it -- it is a view
	// state, and refolding it under them would be worse than forgetting it.
	async function persistDescribePanelFolds(fields: Record<string, boolean>) {
		if (!currentUser) return;
		try {
			const r = await apiFetch('/api/auth/me/settings', { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ model_settings: fields }) });
			if (!r.ok) throw new Error(`HTTP ${r.status}`);
			currentUser = await r.json() as UserItem;
		} catch (e) { console.warn('failed to save describe panel folds', e); }
	}
	bindDescribePanelPersist((fields) => { void persistDescribePanelFolds(fields); });
	// Where `auto` lands when the server cannot read a description.
	bindColorCatalogFallback(() => defaultCatalogId);

	function confirmCatalogSelection() {
		catalogSelectionSnapshot = null;
		persistSelectedCatalog();
		catalogOpen = false;
	}

	function cancelCatalogSelection() {
		if (catalogSelectionSnapshot !== null) {
			colorCatalogSettings.selected = catalogSelectionSnapshot;
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
			renamedCatalogIds = data.renamed_catalog_ids ?? {};
			if (!colorCatalogSettings.isAuto && !catalogById(colorCatalogs, colorCatalogSettings.selected)) colorCatalogSettings.selected = defaultCatalogId;
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
		if (!isAdmin) {
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
				const fallbackGroup = availableModelCatalog.find((group) => group.models.length > 0);
				stage1Provider = fallbackGroup?.id ?? stage1Provider;
				stage1Model = fallbackGroup?.models[0]?.id ?? stage1Model;
			}
			if (!modelsFor(stage2Provider).some((model) => model.id === stage2Model)) {
				const fallbackGroup = availableModelCatalog.find((group) => group.models.length > 0);
				stage2Provider = fallbackGroup?.id ?? stage2Provider;
				stage2Model = fallbackGroup?.models[0]?.id ?? stage2Model;
			}
			if (!visionModelsFor(visionProvider).some((model) => model.id === visionModel)) {
				const fallbackGroup = availableVisionModelCatalog.find((group) => group.models.length > 0);
				visionProvider = fallbackGroup?.id ?? visionProvider;
				visionModel = fallbackGroup?.models[0]?.id ?? visionModel;
			}
			const okugakiModelAvailable = availableVisionModelCatalog.some((group) =>
				group.models.some((model) => qualifiedModelId(group.id, model.id) === okugakiModel)
			);
			if (!okugakiModelAvailable) {
				okugakiModel = qualifiedModelId(visionProvider, visionModel);
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
		if (!modelSettings || !provider || !isAdmin) return;
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
		if (!isAdmin) return;
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
		if (!isAdmin) return;
		modelSettingsLoading = true;
		const nextResults = { ...modelFetchResults };
		delete nextResults[provider];
		modelFetchResults = nextResults;
		try {
			const r = await apiFetch(`/api/settings/models/${encodeURIComponent(provider)}/fetch-models`, {
				method: 'POST',
			});
			if (!r.ok) {
				const d = await r.json().catch(() => ({})) as { detail?: unknown };
				throw new Error(describeApiError(d.detail, r.status));
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
		if (!isAdmin) return;
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
		if (!modelSettings || !isAdmin) return;
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
		if (!modelSettings || !isAdmin) return;
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
		if (!modelSettings || !isAdmin) return;
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
		if (!modelSettings || !isAdmin) return;
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
			applyDownloadFolderSettings(actor);
			applyUserModelSettings(actor);
			authToken = 'cookie';
			if (!holdsPermissionGroup(actor, 'admins')) {
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
		type SaijikiPayload = {
			categories: { key: string; name_ja: string; name_en: string; words: string[] }[];
			plugins: PluginEntry[];
		};
		const fetchSaijiki = async (lang: 'ja' | 'en'): Promise<SaijikiPayload> => {
			const response = await apiFetch(`/api/saijiki?lang=${lang}`, { cache: "no-store" });
			if (!response.ok) throw new Error(`HTTP ${response.status}`);
			return await response.json() as SaijikiPayload;
		};
		try {
			// Both languages: highlighting matches the DDL's own language, which
			// follows instruction_lang and need not agree with the UI language.
			const [ja, en] = await Promise.all([fetchSaijiki('ja'), fetchSaijiki('en')]);
			hydrateSaijiki(
				ja.categories.map((c) => ({ key: c.key, label: c.name_ja, en: c.name_en, words: c.words }))
			);
			hydrateSaijikiEn(
				en.categories.map((c) => ({ key: c.key, label: c.name_ja, en: c.name_en, words: c.words }))
			);
			pluginEntries = ja.plugins ?? [];
		} catch (error) {
			// keep the bundled saijiki snapshot; only plugin words are cleared
			pluginEntries = [];
			console.warn("failed to load saijiki vocabulary", error);
		}
	}

	async function loadSettingsStatus() {
		if (!currentUser || !isAdmin) {
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
				const d = await r.json().catch(() => ({})) as { detail?: unknown };
				throw new Error(describeApiError(d.detail, r.status));
			}
			settingsStatus = await r.json();
			settingsStatusError = null;
			dbBackupStatus = null;
			outputSaveStatus = null;
			logRetentionStatus = null;
			renderLimitsStatus = null;
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

	async function updateDbBackupSettings(
		intervalDays: number,
		maxGenerations: number,
		backupHour: number,
		backupMinute: number
	) {
		dbBackupStatus = null;
		try {
			const r = await apiFetch('/api/settings/db-backup', {
				method: 'PUT',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({
					interval_days: intervalDays,
					max_generations: maxGenerations,
					backup_hour: backupHour,
					backup_minute: backupMinute
				})
			});
			if (!r.ok) {
				const d = await r.json().catch(() => ({})) as { detail?: unknown };
				throw new Error(describeApiError(d.detail, r.status));
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
				const d = await r.json().catch(() => ({})) as { detail?: unknown };
				throw new Error(describeApiError(d.detail, r.status));
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
				const d = await r.json().catch(() => ({})) as { detail?: unknown };
				throw new Error(describeApiError(d.detail, r.status));
			}
			const nextOutputSave = await r.json() as SettingsStatus['output_save'];
			if (settingsStatus) settingsStatus = { ...settingsStatus, output_save: nextOutputSave };
			outputSaveStatus = t().settingsOutputSaveSaved;
		} catch (e) {
			outputSaveStatus = e instanceof Error ? e.message : String(e);
			console.warn('failed to update output save settings', e);
		}
	}

	async function updateRenderConcurrencySettings(serverLimit: number, clientLimit: number) {
		renderConcurrencyStatus = null;
		try {
			const r = await apiFetch('/api/settings/render-concurrency', {
				method: 'PUT',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ server_limit: serverLimit, client_limit: clientLimit })
			});
			if (!r.ok) throw await apiError(r);
			const next = await r.json() as SettingsStatus['render_concurrency'];
			if (settingsStatus) settingsStatus = { ...settingsStatus, render_concurrency: next };
			// Apply to this tab at once; other tabs pick it up on their next load.
			renderFanoutLimit = next.client_limit;
			renderConcurrencyStatus = t().settingsRenderConcurrencySaved;
		} catch (e) {
			renderConcurrencyStatus = e instanceof Error ? e.message : String(e);
			console.warn('failed to update render concurrency settings', e);
		}
	}

	async function loadPublicAppInfo() {
		currentRenderEngineVersion = null;
		currentDdlVersion = null;
		currentDdlEngineVersion = null;
		try {
			const r = await fetch('/api/info', {
				cache: 'no-store',
				credentials: 'same-origin'
			});
			if (!r.ok) throw new Error(`HTTP ${r.status}`);
			const data = await r.json() as { developer_mode?: boolean; single_user_mode?: boolean; thumbnail_hidpi?: boolean; render_engine_version?: string; ddl_version?: string; ddl_engine_version?: string };
			developerMode = data.developer_mode === true;
			singleUserMode = data.single_user_mode === true;
			setThumbnailHidpi(data.thumbnail_hidpi === true);
			currentRenderEngineVersion = typeof data.render_engine_version === 'string'
				? data.render_engine_version
				: null;
			// The three layer versions the app info panel shows. They come from the
			// same call the render engine version does, so one answer carries all.
			currentDdlVersion = typeof data.ddl_version === 'string' ? data.ddl_version : null;
			currentDdlEngineVersion = typeof data.ddl_engine_version === 'string' ? data.ddl_engine_version : null;
		} catch (error) {
			console.warn('failed to load public app info', error);
		}
	}

	// Server-owned client limit. Any authenticated user may read it; only admins
	// may change it, so a failure keeps the built-in default rather than blocking.
	async function loadClientConfig() {
		try {
			const r = await apiFetch('/api/client-config', { cache: 'no-store' });
			if (!r.ok) throw new Error(`HTTP ${r.status}`);
			const data = await r.json() as { render_fanout_limit?: number };
			if (Number.isFinite(data.render_fanout_limit)) renderFanoutLimit = Number(data.render_fanout_limit);
		} catch (error) {
			console.warn('failed to load client config', error);
		}
	}

	// A null patch means "restore the defaults". Only the changed field is sent;
	// the server merges it over the stored set, rounds the result, and returns
	// what took effect -- so the panel is refreshed from the RESPONSE, never
	// from what was typed.
	async function updateRenderLimits(patch: Record<string, number> | null) {
		renderLimitsStatus = null;
		try {
			const r = await apiFetch('/api/settings/limits', {
				method: 'PUT',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify(patch === null ? { reset_to_defaults: true } : patch)
			});
			if (!r.ok) {
				const d = await r.json().catch(() => ({})) as { detail?: unknown };
				throw new Error(describeApiError(d.detail, r.status));
			}
			const nextLimits = await r.json() as SettingsStatus['render_limits'];
			if (settingsStatus) settingsStatus = { ...settingsStatus, render_limits: nextLimits };
			renderLimitsStatus = t().settingsRenderLimitsSaved;
		} catch (e) {
			renderLimitsStatus = e instanceof Error ? e.message : String(e);
			console.warn('failed to update render limits', e);
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
				const d = await r.json().catch(() => ({})) as { detail?: unknown };
				throw new Error(describeApiError(d.detail, r.status));
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
			applyDownloadFolderSettings(currentUser);
			applyUserModelSettings(currentUser);
			authToken = 'cookie';
			loginStatus = null;
			await Promise.all([loadAvailableModels(), loadUserSettings(), loadSettingsStatus(), loadBatchPromptHistory(), loadDemoSettings(), loadPluginStorage(), loadPluginVocabulary(), loadExportTemplates(), loadClientConfig()]);
			await Promise.all([fetchHistoryOffset(0), fetchTrashPage()]);
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
			loginStatus = null;
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
				const d = await r.json().catch(() => ({})) as { detail?: unknown };
				throw new Error(describeApiError(d.detail, r.status));
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
			// loadColorCatalogs and fetchPrompts ride here because I-086 put both
			// endpoints behind the guard. The startup fetch runs before anyone has
			// logged in and now gets a 401, so without reading them again the
			// catalog would stay on FALLBACK_CATALOG and the Prompt tab would stay
			// empty until the page was reloaded.
			await Promise.all([loadAvailableModels(), loadUserSettings(), loadSettingsStatus(), loadBatchPromptHistory(), loadDemoSettings(), loadPluginStorage(), loadPluginVocabulary(), loadExportTemplates(), loadClientConfig(), loadColorCatalogs(), fetchPrompts()]);
			await Promise.all([fetchHistoryOffset(0), fetchTrashPage()]);
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
		uiModeSaveError = false;
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
				const d = await r.json().catch(() => ({})) as { detail?: unknown };
				throw new Error(describeApiError(d.detail, r.status));
			}
			currentUser = await r.json() as UserItem;
			applyUserTheme(currentUser);
			applyDownloadFolderSettings(currentUser);
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
		if (isLeaderOnly) {
			newUserPermissionGroups = ['users'];
			newUserGroupId = currentUser?.group_id ?? '';
		}
		if (!name || !email || newUserPassword.length < 8) {
			userSettingsStatus = t().userValidationCreate;
			return;
		}
		try {
			const r = await apiFetch('/api/users', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ username: name, email, password: newUserPassword, permission_groups: newUserPermissionGroups, group_id: newUserGroupId || null })
			});
			if (!r.ok) {
				const d = await r.json().catch(() => ({})) as { detail?: unknown };
				throw new Error(describeApiError(d.detail, r.status));
			}
			newUserName = '';
			newUserEmail = '';
			newUserPassword = '';
			newUserPermissionGroups = ['users'];
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
				const d = await r.json().catch(() => ({})) as { detail?: unknown };
				throw new Error(describeApiError(d.detail, r.status));
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
		editUserPermissionGroups = [...user.permission_groups];
		editUserGroupId = user.group_id ?? '';
	}

	function clearEditUser() {
		selectedUserId = null;
		editUserName = '';
		editUserEmail = '';
		editUserPassword = '';
		editUserPermissionGroups = ['users'];
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
			permission_groups: isLeaderOnly ? ['users'] : editUserPermissionGroups,
			group_id: isLeaderOnly ? (currentUser?.group_id ?? null) : (editUserGroupId || null),
		};
		if (editUserPassword) patch.password = editUserPassword;
		await updateUser(user, patch);
	}

	async function removeUser(id: string) {
		try {
			const r = await apiFetch(`/api/users/${id}`, { method: 'DELETE' });
			if (!r.ok) {
				const d = await r.json().catch(() => ({})) as { detail?: unknown };
				throw new Error(describeApiError(d.detail, r.status));
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
				const d = await r.json().catch(() => ({})) as { detail?: unknown };
				throw new Error(describeApiError(d.detail, r.status));
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
				const d = await r.json().catch(() => ({})) as { detail?: unknown };
				throw new Error(describeApiError(d.detail, r.status));
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
				const d = await r.json().catch(() => ({})) as { detail?: unknown };
				throw new Error(describeApiError(d.detail, r.status));
			}
			clearEditGroup();
			await loadUserSettings();
		} catch (e) {
			userSettingsStatus = e instanceof Error ? e.message : String(e);
		}
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
	// Which listing request is the current one. Every other async route on this
	// page already carries one of these; the strip's did not, so an answer that
	// came back late overwrote a newer one without anything noticing.
	let historyFetchRequest = 0;
	let trashFetchRequest = 0;
	// How many listing requests are out. The nav buttons read it: pressing while
	// one is on its way asks for the same offset again, because the offset has
	// not moved yet, and both presses then land on the same work.
	let historyFetchInFlight = $state(0);
	const visibleThumbCount = $derived(Math.max(1, Math.floor((windowWidth - 40) / 89)));
	const historyWindowSize = $derived(visibleThumbCount);
	const historyPage = $derived(Math.floor(historyOffset / historyWindowSize));
	const historyTotalPages = $derived(Math.max(1, Math.ceil(historyTotal / historyWindowSize)));
	let historyStarredOnly = $state(false);
	// The strip's own 推敲のみ filter. Separate from the manager's: the two
	// boxes are filtered independently, the same way starred already is.
	let historyForRevisionOnly = $state(false);
	// Whether the strip is showing a filtered listing rather than the whole one.
	// Three places ask this to decide whether the page in hand is the plain
	// newest-first listing: what to seed the manager with, what the strip may
	// slice, and whether a freshness check may compare its first item with the
	// newest work. Read through one name so a fourth filter cannot be added to
	// some of them and forgotten in the rest.
	const historyStripFiltered = $derived(historyStarredOnly || historyForRevisionOnly);
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
	// Counted the way the server reads them: a line that is only its numbering
	// and a bracketed note has nothing to draw, and would come back a 400.
	const batchNonEmpty = $derived(batchLines.filter((l) => pipelineDescription(l).trim()).length);
	const batchRunning = $derived(activeRunMode === 'batch' && loading);
	// The line being painted, shown in place of the input box while the run holds
	// that box read-only anyway. The whole line is kept, numbering and all.
	const batchRunningLineText = $derived(
		batchActiveLine === null ? '' : (batchLines[batchActiveLine - 1] ?? '').trim()
	);
	const batchSketchGrainLabel = $derived(
		sketchModeLabel(sketchModeOf(batchSketchGrain), getLang() === 'ja')
	);
	const singleRunning = $derived((activeRunMode === 'single' && loading) || reloading);
	const demoRunning = $derived(activeRunMode === 'demo' && loading);
	const demoCanSaveCurrent = $derived(!!result && !!demoGeneratedPrompt && !!demoGeneratedDdl && !demoCurrentSaved);
	const ddlEditedAfterGeneration = $derived(inputMode === 'single' && ddl !== null && ddlGeneratedBaseline !== null && ddl !== ddlGeneratedBaseline);
	// The gate reads what the drawing reads.  The meter already cut the text
	// (InputPanel), so a description greyed out end to end must not be sendable:
	// the same rule, moved to the door instead of a second rule written here.
	const canSubmit     = $derived(
		inputMode === 'single' ? !!pipelineDescription(input).trim() : inputMode === 'batch' ? batchNonEmpty > 0 : false
	);
	const currentInstructionText = $derived.by(() => {
		if (displayedHistoryItem?.input) return displayedHistoryItem.input;
		if (inputMode === 'demo' || activeRunMode === 'demo') return demoGeneratedPrompt;
		if (inputMode === 'batch' || activeRunMode === 'batch') return batchLatestPrompt;
		return input;
	});

	// v1.98: Stage 1 が失敗してフォールバック DDL で描かれたかどうか。
	const interpretFallbackReason = $derived(
		displayedHistoryItem
			? (displayedHistoryItem.interpret_fallback ?? null)
			: (result?.interpret_fallback_used ? (result?.interpret_fallback_reasons?.[0] ?? 'stage1_fallback') : null)
	);

	// Standalone DDL-authored artworks have no instruction; gate instruction-only refine paths.
	const statusDdlOrigin = $derived((displayedHistoryItem?.display_label ?? null) === DDL_ORIGIN_LABEL);

	// ── Running-indicator state ─────────────────────────────
	// Tokens confirmed by the stage1 event of the paint currently in flight.
	// Cleared when that paint finishes; completed runs are folded into the
	// per-flow totals below.
	let activeRunTokensIn = $state<number | null>(null);
	let activeRunTokensOut = $state<number | null>(null);

	// Model names shown by every running indicator, provider first.
	const stage1ModelLabel = $derived(
		modelDisplayName(qualifiedModelId(stage1Provider, stage1Model), availableModelCatalog, stage1Provider)
	);
	const stage2ModelLabel = $derived(
		modelDisplayName(qualifiedModelId(stage2Provider, stage2Model), availableModelCatalog, stage2Provider)
	);

	// Flows that issue several paints per run keep their own running totals.
	let variationTokensIn = $state<number | null>(null);
	let variationTokensOut = $state<number | null>(null);

	const variationElapsed = createElapsed();
	function addTokens(total: number | null, delta: number | null | undefined): number | null {
		if (delta === null || delta === undefined) return total;
		return (total ?? 0) + delta;
	}

	function paintTokensIn(r: PaintResult): number | null {
		return addTokens(r.tokens_in_stage1 ?? null, r.tokens_in_stage2);
	}

	function paintTokensOut(r: PaintResult): number | null {
		return addTokens(r.tokens_out_stage1 ?? null, r.tokens_out_stage2);
	}

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

	// ── Core paint (2-stage) ─────────────────────────────────
	type PaintOptions = {
		historyInput?: string;
		saveHistory?: boolean;
		saveArtifacts?: boolean;
		countGeneration?: boolean;
		canvasAspectId?: CanvasAspectId;
		renderSeed?: number;
		/** Per-feature overrides for the render request; built by the features. */
		renderOverrides?: RenderOverrides;
		compositionSeed?: number;
		// 変奏 (v2.0): 両方そろって初めてサーバーが展開層をずらす。
		variationAmplitude?: string;
		variationSeed?: number;
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
		// 写生 (Stage 0.5). `sketchMode` says whether the layer runs and at which
		// grain; `sketchText` hands the server prose it already has, so a redraw
		// of a saved work replays instead of asking a non-deterministic layer again.
		sketchMode?: SketchMode;
		sketchText?: string | null;
		// Called when interpretation finishes, before rendering starts.
		onStage1?: (event: PaintStage1Event) => void;
	};

async function requestVisionRefineAdvice(historyId: string, model: string, instruction: string, direction: string, enabledKinds: string[], signal: AbortSignal) {
	const r = await apiFetch('/api/refine/vision-advice', {
		method: 'POST',
		signal,
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify({ history_id: historyId, model, instruction, direction, enabled_kinds: enabledKinds, language: getLang() })
	});
	if (!r.ok) {
		const data = await r.json().catch(() => ({})) as { detail?: unknown };
		throw new Error(describeApiError(data.detail, r.status));
	}
	return await r.json() as { observation: string; next_direction: string; suggested_kind: string; model: string };
}

	type PaintStage1Event = {
		event: 'stage1';
		ddl: string;
		thinking: string | null;
		stage1_model: string;
		stage2_model: string;
		tokens_in: number | null;
		tokens_out: number | null;
		elapsed_ms: number;
		interpret_fallback_used: boolean;
	};

	/**
	 * Consume the NDJSON stream of /api/paint/stream.
	 *
	 * The stage1 event arrives as soon as interpretation finishes, so the
	 * running indicator can show the real stage and the Stage 1 token counts
	 * instead of guessing. The done event carries the same payload the
	 * non-streaming /api/paint returns.
	 */
	async function readPaintStream(
		response: Response,
		onStage1: (event: PaintStage1Event) => void
	): Promise<{ ddl: string; thinking: string | null } & PaintResult> {
		const reader = response.body?.getReader();
		if (!reader) throw new Error('paint stream is not readable');
		const decoder = new TextDecoder();
		let buffer = '';
		let done: ({ ddl: string; thinking: string | null } & PaintResult) | null = null;

		for (;;) {
			const chunk = await reader.read();
			if (chunk.value) buffer += decoder.decode(chunk.value, { stream: true });
			let newline = buffer.indexOf('\n');
			while (newline >= 0) {
				const line = buffer.slice(0, newline).trim();
				buffer = buffer.slice(newline + 1);
				newline = buffer.indexOf('\n');
				if (!line) continue;
				const event = JSON.parse(line) as { event: string } & Record<string, unknown>;
				if (event.event === 'stage1') {
					onStage1(event as unknown as PaintStage1Event);
				} else if (event.event === 'error') {
					throw new Error(describeApiError(event.detail, Number(event.status ?? 500)));
				} else if (event.event === 'done') {
					done = event as unknown as { ddl: string; thinking: string | null } & PaintResult;
				}
			}
			if (chunk.done) break;
		}
		if (!done) throw new Error('paint stream ended before completion');
		return done;
	}

	async function paintOne(text: string, options: PaintOptions = {}): Promise<{ ddl: string; thinking: string | null } & PaintResult> {
		const uiLang = getLang();
		stageLabel = t().stageInterpreting;
		activeRunTokensIn = null;
		activeRunTokensOut = null;
		const historyInput = options.historyInput ?? text;
		const resolvedStage1Model = qualifiedModelId(stage1Provider, stage1Model);
		const resolvedStage2Model = qualifiedModelId(stage2Provider, stage2Model);

		stage1UserPrompt = text;
		const resolvedSketchMode = options.sketchMode ?? sketchMode;
		const resolvedSketchGrain = sketchGrainOf(resolvedSketchMode);
		const r = await apiFetch('/api/paint/stream', {
			method: 'POST',
			signal: options.signal,
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({
				description: text,
				sketch: resolvedSketchMode !== 'off',
				...(resolvedSketchGrain ? { sketch_grain: resolvedSketchGrain } : {}),
				...(options.sketchText ? { sketch_text: options.sketchText } : {}),
				stage1_model: resolvedStage1Model,
				stage2_model: resolvedStage2Model,
				include_thinking: includeThinking,
				instruction_lang: instructionLang,
				ui_lang: uiLang,
				canvas_aspect: options.canvasAspectId ?? effectiveCanvasAspectId(),
				render_seed: options.renderSeed,
				composition_seed: options.compositionSeed,
				variation_amplitude: options.variationAmplitude ?? null,
				variation_seed: options.variationSeed ?? null,
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
				...renderSettingsPayload('paint', options.renderOverrides)
			})
		});
		if (!r.ok) {
			const d = await r.json().catch(() => ({})) as { detail?: unknown };
			throw new Error(describeApiError(d.detail, r.status));
		}
		const data = await readPaintStream(r, (stage1) => {
			stageLabel = t().stageStructuring('');
			activeRunTokensIn = stage1.tokens_in;
			activeRunTokensOut = stage1.tokens_out;
			options.onStage1?.(stage1);
		});
		activeRunTokensIn = null;
		activeRunTokensOut = null;
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
		stage1UserPrompt = text;
		const resolvedStage1Model = modelOverride ?? qualifiedModelId(stage1Provider, stage1Model);
		const r = await apiFetch('/api/interpret', {
			method: 'POST',
			signal,
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({
				description: text,
				...(sketchTextFor(text) ? { sketch_text: sketchTextFor(text) } : {}),
				model: resolvedStage1Model,
				include_thinking: includeThinking,
				instruction_lang: langOverride ?? instructionLang,
				ui_lang: uiLang,
				expand_intermediate: true,
			})
		});
		if (!r.ok) {
			const d = await r.json().catch(() => ({})) as { detail?: unknown };
			throw new Error(describeApiError(d.detail, r.status));
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

	async function composeOne(currentDdl: string, originalText: string, signal?: AbortSignal, modelOverride?: string, langOverride?: InstructionLang, renderOptions: { canvasAspectId?: CanvasAspectId; lineageParentNodeId?: string | null; renderOverrides?: RenderOverrides } = {}): Promise<{
		score: Score;
		svg: string;
		// Stage 2 に渡った展開後 DDL (v1.98)
		ddl?: string | null;
		source_ddl?: string | null;
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
		render_wild?: boolean | null;
		composition_seed?: number | null;
		instruction_lang_requested?: string | null;
		instruction_lang_resolved?: string | null;
		ui_lang?: string | null;
		elapsed_ms: number;
		tokens_in: number | null;
		tokens_out: number | null;
		sketch_text?: string | null;
		sketch_grain?: string | null;
		sketch_state?: string | null;
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
				description: originalText,
				...sketchPayloadFor(originalText),
				instruction_lang: langOverride ?? instructionLang,
				ui_lang: uiLang,
				canvas_aspect: renderOptions.canvasAspectId ?? effectiveCanvasAspectId(),
				auto_repair: ddlAutoRepairEnabled,
				...renderSettingsPayload('compose', renderOptions.renderOverrides),
				...(renderOptions.lineageParentNodeId ? { lineage_parent_node_id: renderOptions.lineageParentNodeId } : {}),
			})
		});
		if (!r.ok) {
			const d = await r.json().catch(() => ({})) as { detail?: unknown };
			throw new Error(describeApiError(d.detail, r.status));
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
			render_wild?: boolean | null;
			composition_seed?: number | null;
			elapsed_ms: number;
			tokens_in: number | null;
			tokens_out: number | null;
		};
		return data;
	}

	// The strip badge marks what the canvas is showing, not what was saved last.
	// A batch can be stepped off the latest render — clicking a thumbnail or
	// leaving the バッチ tab stops the follow — and from then on the badge has to
	// stay on the artwork on screen instead of chasing every new line. It clears
	// when that artwork is not in the newest window, rather than pointing at a
	// neighbour.
	// While the reader has paged back through the strip, a finished batch line or
	// demo render must not drag them to the newest page. Only the count moves;
	// the window itself is refetched when the run ends (refreshHistoryAfterRun).
	// The same guard already protects the strip from externally saved works.
	async function refreshHistoryAfterServerSave() {
		if (historyOffset !== 0) {
			if (!historyStarredOnly && !historyForRevisionOnly) historyTotal += 1;
			return;
		}
		const activeHistoryId = displayedHistoryItem?.id ?? result?.history_id ?? null;
		await fetchHistoryOffset(0);
		if (!activeHistoryId) {
			historyCursor = 0;
			return;
		}
		historyCursor = historyItems.findIndex((item) => item.id === activeHistoryId);
	}

	// Catch the paged-away strip up once the run is over, staying on the page the
	// reader chose. Page 0 needs nothing: it was refreshed after every save.
	async function refreshHistoryAfterRun() {
		if (!authToken || historyOffset === 0) return;
		await fetchHistoryOffset(historyOffset, { preserveSelection: true });
	}

	function sleep(ms: number): Promise<void> {
		return new Promise((resolve) => setTimeout(resolve, ms));
	}

	async function generateDemoInstruction(settings: DemoSettings): Promise<string> {
		const model = qualifiedModelId(settings.prompt_provider, settings.prompt_model);
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
			const d = await r.json().catch(() => ({})) as { detail?: unknown };
			throw new Error(describeApiError(d.detail, r.status));
		}
		const data = await r.json() as { instruction: string };
		return data.instruction;
	}

	async function runDemoLoop(runId: number, timeoutAt: number) {
		while (demoRunId === runId && loading && Date.now() < timeoutAt) {
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
				// The demo draws with whatever the catalog modal has selected, including
				// "from the description": it used to carry a mode of its own.
				const demoCatalogId = colorCatalogSettings.selected;
				const r = await paintOne(demoGeneratedPrompt, {
					saveHistory: settings.save_db,
					saveArtifacts: settings.save_files,
					countGeneration: false,
					historyInput: `[demo] ${demoGeneratedPrompt}`,
					sourceText: demoGeneratedPrompt,
					displayLabel: '[demo]',
					renderOverrides: {
						...colorCatalogOverride(demoCatalogId),
						...wildOverride(false)
					},
				});
				if (demoRunId !== runId || !loading) break;
				demoGeneratedDdl = r.ddl;
				demoCurrentSaved = !!r.history_id;
				demoSaveStatus = null;
				const demoSourceDdl = r.source_ddl ?? r.ddl;
				ddl = demoSourceDdl; expandedDdl = r.ddl; ddlGeneratedBaseline = demoSourceDdl; thinking = r.thinking; result = r; outputTab = 'canvas';
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
				if (Date.now() >= timeoutAt) break;
				const intervalRemainingMs = settings.interval_seconds * 1000 - (Date.now() - startedAt);
				const timeoutRemainingMs = timeoutAt - Date.now();
				const remainingMs = Math.max(0, Math.min(intervalRemainingMs, timeoutRemainingMs));
				const waitingForNextRender = intervalRemainingMs <= timeoutRemainingMs;
				for (let left = Math.ceil(remainingMs / 1000); left > 0 && demoRunId === runId && loading; left--) {
					demoWaitingSeconds = waitingForNextRender ? left : null;
					await sleep(Math.min(1000, remainingMs));
				}
			} catch (e) {
				demoCurrentStartedAt = null;
				demoError = e instanceof Error ? e.message : String(e);
				const retryDelayMs = Math.min(1000, Math.max(0, timeoutAt - Date.now()));
				if (retryDelayMs > 0) await sleep(retryDelayMs);
			}
		}
		if (demoRunId === runId) {
			await refreshHistoryAfterRun();
			demoTimedOut = Date.now() >= timeoutAt;
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
		demoTimedOut = false;
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
		const timeoutAt = Date.now() + normalizeDemoSettings(demoSettings).timeout_seconds * 1000;
		await runDemoLoop(demoRunId, timeoutAt);
	}

	function stopDemo() {
		demoRunId += 1;
		void refreshHistoryAfterRun();
		demoTimedOut = false;
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

	/**
	 * `resumeLines` finishes a batch that stopped part-way: the lines it names are
	 * painted in place of the whole box, each keeping the number the prompt gave
	 * it. Everything else about the run is unchanged.
	 */
	async function submit(options: { resumeLines?: NumberedLine[] } = {}) {
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
		const submitTextChanged = input.trim() !== submitSource.trim();
		// 写生 (Stage 0.5). The grain edge fires only when the grain differs from
		// the parent's, exactly as description_edit fires only when the text does;
		// one edge, one cause, so a changed description stays a description edit.
		const submitParentGrain = normalizeSketchGrain(displayedHistoryItem?.sketch_grain);
		const submitGrain = sketchGrainOf(sketchMode);
		const submitGrainChanged = submitGrain !== submitParentGrain;
		const submitDerivationKind: DerivationKind | null = submitDerivationKindOf({
			hasParent: submitParentNodeId !== null,
			canvasAspectChanged: canvasAspectDerivation !== null,
			textChanged: submitTextChanged,
			grainChanged: submitGrainChanged
		});
		// A redraw at the same grain replays the prose it was painted from; the
		// layer is not deterministic, so calling it again would not be a replay.
		// An edited prose wins over the stored one, and a changed grain has to be
		// written anew.
		const sketchEdited = sketchDraft.trim() !== '' && sketchDraft.trim() !== (sketchText ?? '').trim();
		const submitSketchText = sketchEdited
			? sketchDraft.trim()
			: (!submitTextChanged && !submitGrainChanged ? sketchText : null);
		const submitDerivationMetadata = canvasAspectDerivation
			? { from_canvas_aspect: canvasAspectDerivation.fromAspectId, to_canvas_aspect: canvasAspectDerivation.toAspectId }
			: {};
		loading = true; error = null;
		activeRunMode = submittedMode;
		ddl = null; expandedDdl = null; ddlGeneratedBaseline = null; thinking = null;
		displayedHistoryItem = null;
		historyCursor = -1;
		elapsedStage1Ms = 0; elapsedStage2Ms = 0; elapsedTotalMs = 0;
		tokensInStage1 = null; tokensOutStage1 = null; tokensInStage2 = null; tokensOutStage2 = null;
		batchCurrent = 0; batchRetryRound = 0; batchActiveLine = null; batchActiveDdl = null; batchObservedLine = null;
		batchSketchText = null; batchSketchGrain = null;
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
				const r = await paintOne(input, {
					sourceText: input,
					canvasAspectId: effectiveCanvasAspectId(),
					lineageParentNodeId: submitParentNodeId,
					sketchText: submitSketchText,
					derivationKind: submitDerivationKind,
					derivationMetadata: submitDerivationMetadata,
					signal: abortController.signal,
					onStage1: (stage1) => {
						elapsedStage1Ms = stage1.elapsed_ms;
						tokensInStage1 = stage1.tokens_in;
						tokensOutStage1 = stage1.tokens_out;
						ddl = stage1.ddl;
						expandedDdl = null;
						ddlGeneratedBaseline = stage1.ddl;
						thinking = stage1.thinking;
						stageLabel = t().stageImageGenerating;
						reloading = true;
					}
				});
				if (submitStopRequested) return;
				reloading = false;
				elapsedStage1Ms = r.elapsed_stage1_ms;
				elapsedStage2Ms = r.elapsed_stage2_ms;
				elapsedTotalMs = r.elapsed_total_ms;
				tokensInStage1 = r.tokens_in_stage1;
				tokensOutStage1 = r.tokens_out_stage1;
				tokensInStage2 = r.tokens_in_stage2;
				tokensOutStage2 = r.tokens_out_stage2;
				ddl = r.source_ddl ?? r.ddl;
				expandedDdl = r.ddl;
				ddlGeneratedBaseline = ddl;
				thinking = r.thinking;
				result = r; outputTab = 'canvas';
				adoptSketch(r.sketch_text ?? null, r.sketch_grain, input, r.sketch_state);
				fitCanvasZoom();
				if (r.history_id && submitAbortController === abortController && !submitStopRequested) {
					if (canvasAspectDerivation) pendingCanvasAspectDerivation = null;
					lineageDetached = false;
					await fetchHistoryOffset(0, { anchorId: r.history_id });
					displayedHistoryItem = historyItems.find((item) => item.id === r.history_id) ?? null;
				}
			} else {
				batchTotal = 0; batchSuccess = 0; batchFailures = []; batchFailureReportStore.set(null);
				batchActiveTokensIn = null; batchActiveTokensOut = null; batchTokensInTotal = 0; batchTokensOutTotal = 0;
				const batchCanvasAspectId = effectiveCanvasAspectId();
				const batchCatalogId = colorCatalogSettings.selected;
				const batchRunId = typeof crypto?.randomUUID === 'function' ? crypto.randomUUID() : `${Date.now()}`;
				// The whole line is sent -- the server keeps the author's numbering
				// for the record and cuts it for the pipeline -- but a line with
				// nothing left after the cut is not a line to paint.
				const lines = batchLines
					.map((line, index) => ({ line: index + 1, input: line.trim() }))
					.filter((item) => pipelineDescription(item.input).trim());
				// Resuming paints the lines the stopped run never reached, each keeping
				// the number the prompt gave it; an ordinary run paints the whole box.
				const paintLines = options.resumeLines ?? lines;
				// The report's `total` is how many lines the batch had. batchTotal drives
				// the progress readouts and is re-pointed at each retry round, so the
				// report keeps its own copy.
				const batchLineTotal = paintLines.length;
				batchTotal = batchLineTotal; outputTab = 'canvas';
				let batchInterrupted = false;

				/** true = painted, string = the failure message, null = the run was interrupted. */
				const paintBatchLine = async (item: { line: number; input: string }): Promise<true | string | null> => {
					batchActiveLine = item.line;
					try {
						const r = await paintOne(item.input, {
							historyInput: `#${item.line} ${item.input}`,
							sourceText: item.input,
							displayLabel: `#${item.line}`,
							batchLineNumber: item.line,
							batchRunId,
							canvasAspectId: batchCanvasAspectId,
							renderOverrides: colorCatalogOverride(batchCatalogId),
							signal: abortController.signal,
						});
						if (submitStopRequested) return null;
						// The observer's four quantities are written together, so the
						// block always describes one work.
						batchObservedLine = item.line;
						batchActiveDdl = r.ddl;
						batchSketchText = r.sketch_text ?? null;
						batchSketchGrain = r.sketch_grain ?? null;
						batchActiveTokensIn = (r.tokens_in_stage1 ?? 0) + (r.tokens_in_stage2 ?? 0) || null;
						batchActiveTokensOut = (r.tokens_out_stage1 ?? 0) + (r.tokens_out_stage2 ?? 0) || null;
						batchTokensInTotal += batchActiveTokensIn ?? 0;
						batchTokensOutTotal += batchActiveTokensOut ?? 0;
						thinking = r.thinking;
						batchLatestResult = r;
						batchLatestDdl = r.ddl;
						batchLatestThinking = r.thinking;
						batchLatestPrompt = `#${item.line} ${item.input}`;
						if (inputMode === 'batch' && batchAutoFollowLatest) {
							displayLatestBatchRender();
						}
						await refreshHistoryAfterServerSave();
						batchSuccess += 1;
						return true;
					} catch (e) {
						if (submitStopRequested || abortController.signal.aborted) return null;
						return e instanceof Error ? e.message : String(e);
					}
				};

				const publishFailureReport = () => {
					batchFailureReportStore.set(
						batchFailures.length > 0
							? { success: batchSuccess, total: batchLineTotal, failures: batchFailures }
							: null,
					);
				};

				for (let i = 0; i < paintLines.length; i++) {
					if (submitStopRequested) { batchInterrupted = true; break; }
					batchCurrent = i + 1;
					const outcome = await paintBatchLine(paintLines[i]);
					if (outcome === null) { batchInterrupted = true; break; }
					if (outcome !== true) {
						batchFailures = [
							...batchFailures,
							{ line: paintLines[i].line, input: paintLines[i].input, message: outcome },
						];
					}
					publishFailureReport();
				}

				// Retry the lines that failed, if the author asked for retries. An
				// interrupted batch is never retried: the lines that never ran are not
				// failures, and the author stopped the run on purpose.
				let completedRetryRounds = 0;
				for (;;) {
					const round = planRetryRound(
						batchFailures,
						completedRetryRounds,
						batchSettings.maxRetries,
						batchInterrupted || submitStopRequested || abortController.signal.aborted,
					);
					if (!round) break;
					batchRetryRound = round.round;
					batchTotal = round.items.length;
					for (let i = 0; i < round.items.length; i++) {
						if (submitStopRequested) { batchInterrupted = true; break; }
						batchCurrent = i + 1;
						const item = round.items[i];
						const outcome = await paintBatchLine(item);
						if (outcome === null) { batchInterrupted = true; break; }
						if (outcome === true) {
							batchFailures = dropFailedLine(batchFailures, item.line);
						} else {
							batchFailures = batchFailures.map((failure) =>
								failure.line === item.line ? { ...failure, message: outcome } : failure,
							);
						}
						publishFailureReport();
					}
					if (batchInterrupted) break;
					completedRetryRounds += 1;
				}
				batchRetryRound = 0;
				batchTotal = batchLineTotal;

				elapsedTotalMs = Date.now() - _timerStart;
				await refreshHistoryAfterRun();
				publishFailureReport();
				// A run that was stopped leaves lines to finish; one that reached the
				// end leaves none. Either way the answer is now different.
				await refreshBatchResume();
			}
		} catch (e) {
			if (!(submitStopRequested || abortController.signal.aborted)) {
				error = e instanceof Error ? e.message : String(e); result = null;
			}
		} finally {
			if (submitAbortController === abortController) submitAbortController = null;
			submitStopRequested = false;
			stopTimer(); loading = false; reloading = false; activeRunMode = null; stageLabel = ''; batchCurrent = 0; batchRetryRound = 0; batchActiveLine = null; batchActiveDdl = null; batchObservedLine = null; batchActiveTokensIn = null; batchActiveTokensOut = null;
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
					description: replayInput,
					...sketchPayloadFor(replayInput),
					instruction_lang: instructionLang,
					ui_lang: uiLang,
					canvas_aspect: effectiveCanvasAspectId(),
					auto_repair: ddlAutoRepairEnabled,
					...renderSettingsPayload('compose')
				})
			});
			if (!r.ok) {
				const d = await r.json().catch(() => ({})) as { detail?: unknown };
				throw new Error(describeApiError(d.detail, r.status));
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
				render_wild?: boolean | null;
				composition_seed?: number | null;
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
				composition_seed: d.composition_seed,
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
				catalog_id: colorCatalogSettings.effectiveId !== 'default' ? colorCatalogSettings.effectiveId : null
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
	// A prediction, used only for the first fetch made before the manager opens.
	// The canonical page size is what the manager measures on its own grid
	// (calculatePageSize() in HistoryManager.svelte); this estimate never
	// overrides it. minCardWidth mirrors the minmax() in that component's
	// .history-thumb-grid rule and must move whenever the CSS does.
	function estimatedHistoryManagerPageSize(): number {
		const modalWidth = Math.max(320, windowWidth * 0.8);
		const modalHeight = Math.max(280, windowHeight * 0.8);
		const gridWidth = Math.max(1, modalWidth - 20);
		const gridHeight = Math.max(1, modalHeight - 94);
		const gap = 8;
		const minCardWidth = 142;
		const columns = Math.max(1, Math.floor((gridWidth + gap) / (minCardWidth + gap)));
		const cardWidth = Math.max(minCardWidth, (gridWidth - gap * (columns - 1)) / columns);
		const imageWidth = Math.max(1, cardWidth - 12);
		const cardHeight = imageWidth * 58 / 82 + 75;
		const rows = Math.max(1, Math.floor((gridHeight + gap) / (cardHeight + gap)));
		return Math.max(historyWindowSize, Math.min(100, columns * rows));
	}

	async function fetchHistoryOffset(offset: number, options: { preserveSelection?: boolean; anchorId?: string } = {}): Promise<boolean> {
		if (!authToken) {
			historyItems = [];
			historyTotal = 0;
			historyOffset = 0;
			return false;
		}
		const safeOffset = Math.max(0, offset);
		// Taken before anything is asked for, so an answer can tell whether it is
		// still the answer to the current question. This function writes the four
		// quantities the whole strip is read from, and had nothing stopping a slow
		// answer from putting its page back over a newer one -- four of its
		// callers do not even await it, one of them the resize effect, which fires
		// on every 89-pixel boundary the window edge is dragged across.
		const requestId = ++historyFetchRequest;
		historyFetchInFlight += 1;
		const selectedHistoryId = options.anchorId ?? (options.preserveSelection
			? historyItems[historyCursor]?.id ?? displayedHistoryItem?.id ?? result?.history_id ?? null
			: null);
		try {
			const listLimit = historyListLimit({
				anchorId: options.anchorId ?? null,
				offset: safeOffset,
				starredOnly: historyStarredOnly,
				windowSize: historyWindowSize,
				managerPageSize: estimatedHistoryManagerPageSize()
			});
			const params = new URLSearchParams({
				offset: String(safeOffset),
				limit: String(listLimit),
				// The strip draws thumbnails. A work that is opened, replayed, put
				// on a sheet or saved again fetches its own drawing then.
				include_svg: 'false',
			});
			if (historyStarredOnly) params.set('starred', 'true');
			// The two marks are independent, so asking for both means both.
			if (historyForRevisionOnly) params.set('for_revision', 'true');
			if (options.anchorId) params.set('anchor_id', options.anchorId);
			const r = await apiFetch(`/api/history?${params.toString()}`);
			if (requestId !== historyFetchRequest) return false;
			if (!r.ok) return false;
			const data = await r.json();
			const resolvedOffset = Number.isFinite(data.offset) ? Number(data.offset) : safeOffset;
			if (data.items.length === 0 && data.total > 0 && resolvedOffset > 0 && !options.anchorId) {
				const lastOffset = Math.floor((data.total - 1) / historyWindowSize) * historyWindowSize;
				return await fetchHistoryOffset(lastOffset);
			}
			const stripItems = resolvedOffset === 0 && !historyStripFiltered
				? data.items.slice(0, historyWindowSize)
				: data.items;
			// Immediately before the four quantities are written, so no await added
			// later can slip between the check and what it is protecting.
			if (requestId !== historyFetchRequest) return false;
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
			if (!historyManager.open && resolvedOffset === 0 && !historyStripFiltered) {
				// The strip's items are what we have; the manager's page size is a
				// different quantity, so it is passed separately. The manager is
				// seeded, not filled: it fetches its own page when it opens.
				historyManager.seedFromStrip(data.items, data.total, trashTotal, estimatedHistoryManagerPageSize());
			}
			return options.anchorId ? historyCursor >= 0 && historyItems[historyCursor]?.id === options.anchorId : true;
		} catch {
			return false;
		} finally {
			historyFetchInFlight = Math.max(0, historyFetchInFlight - 1);
		}
	}

	async function syncHistoryStripToItem(item: Pick<Iteration, 'id' | 'trashed' | 'history_visibility'>): Promise<void> {
		const requestId = ++historySelectionSyncRequest;
		if (!item.id || item.trashed || item.history_visibility === 'lineage_only') {
			historyCursor = -1;
			return;
		}
		const localIndex = resolveStripSelection(historyItems, item);
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
		if (!found && historyStripFiltered) {
			// Both filters come off together: which of them was hiding the work
			// is not known from here, and the point is to show it.
			const clearedStarred = historyStarredOnly;
			historyStarredOnly = false;
			historyForRevisionOnly = false;
			if (clearedStarred) showHistoryStarredFilterClearedNotice();
			else showHistoryForRevisionFilterClearedNotice();
			found = await fetchHistoryOffset(0, { anchorId: item.id });
		}
		if (requestId !== historySelectionSyncRequest) {
			if (displayedHistoryItem) void syncHistoryStripToItem(displayedHistoryItem);
			return;
		}
		if (!found) historyCursor = -1;
	}

	async function fetchHistoryState(): Promise<HistoryState | null> {
		try {
			const r = await apiFetch('/api/history/state');
			if (!r.ok) return null;
			const data = await r.json();
			if (!Number.isFinite(data?.total)) return null;
			return {
				total: Number(data.total),
				newest_at: data.newest_at ?? null,
				newest_id: data.newest_id ?? null,
			};
		} catch {
			return null;
		}
	}

	async function refreshHistoryForExternalSave(): Promise<void> {
		const now = Date.now();
		if (historyRefreshBlockedBy({
			signedIn: !!authToken,
			managerOpen: historyManager.open,
			starredOnly: historyStarredOnly,
			offset: historyOffset,
			loading,
			visible: document.visibilityState === 'visible',
			inFlight: externalHistoryRefreshInFlight,
			now,
			lastRefreshAt: lastExternalHistoryRefreshAt,
			minGapMs: EXTERNAL_HISTORY_REFRESH_MIN_GAP_MS,
		})) return;
		externalHistoryRefreshInFlight = true;
		lastExternalHistoryRefreshAt = now;
		try {
			// Ask what changed before carrying the gallery. Most rounds find
			// nothing and stop here; a failed answer falls through and fetches,
			// so a server that cannot answer degrades to the old behaviour.
			// The guards above mean the strip is at offset 0 and unstarred, so
			// its first item is the newest work and its total is the same count.
			const state = await fetchHistoryState();
			if (state && historyStripIsCurrent(state, {
				total: historyTotal,
				newestId: historyItems[0]?.id ?? null,
				newestAt: historyItems[0]?.at ?? null,
				showsTheNewestFirst: historyOffset === 0 && !historyStripFiltered,
			})) return;
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

	/**
	 * One page newer.
	 *
	 * Lands on the oldest work of that page, which is the work immediately newer
	 * than the one that was on screen. Landing on its newest instead -- what this
	 * did before -- stepped over everything in between, and was the only one of
	 * the four steps that did not read continuously.
	 */
	async function gotoHistoryNewerPage(): Promise<void> {
		const target = historyPageTarget(historyNavState, 'newer');
		if (!target) return;
		if (!(await fetchHistoryOffset(target.offset))) return;
		loadIteration(historyNavIndex(target));
	}

	async function gotoHistoryLatestPage(): Promise<void> {
		const target = historyPageTarget(historyNavState, 'latest');
		if (!target) return;
		if (!(await fetchHistoryOffset(target.offset))) return;
		loadIteration(historyNavIndex(target));
	}

	async function gotoHistoryOlderPage(): Promise<void> {
		const target = historyPageTarget(historyNavState, 'older');
		if (!target) return;
		if (!(await fetchHistoryOffset(target.offset))) return;
		loadIteration(historyNavIndex(target));
	}

	async function gotoHistoryOldestPage(): Promise<void> {
		const target = historyPageTarget(historyNavState, 'oldest');
		if (!target) return;
		if (!(await fetchHistoryOffset(target.offset))) return;
		loadIteration(historyNavIndex(target));
	}

	async function fetchTrashPage(): Promise<void> {
		if (!authToken) {
			trashItems = [];
			trashTotal = 0;
			return;
		}
		// Same reason as the listing above: this one also writes state a late
		// answer could put back over a newer one.
		const requestId = ++trashFetchRequest;
		try {
			// No drawings: what this call is for is the count, and the manager owns
			// what the trash view puts on screen. Asking for a hundred works with
			// their pictures cost 11 MB for a single heavy work, and every one of
			// those bytes was thrown away -- nothing reads `trashItems`.
			const r = await apiFetch(`/api/history?offset=0&limit=100&trashed=true&include_svg=false`);
			if (requestId !== trashFetchRequest) return;
			if (!r.ok) return;
			const data = await r.json();
			if (requestId !== trashFetchRequest) return;
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
		if (lineageGraph) {
			lineageGraph = {
				...lineageGraph,
				nodes: lineageGraph.nodes.map((node) => node.history && node.history.id === item.id
					? { ...node, history: { ...node.history, starred: item.starred, note: hasNote ? item.note : node.history.note } }
					: node)
			};
		}
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

	type HistoryForRevisionTarget = { id?: string; for_revision?: boolean };

	// The revision mark rides the same paths as the star and never touches it:
	// the two are separate columns, and a work can carry either, both or neither.
	function updateHistoryForRevisionState(item: HistoryForRevisionTarget) {
		if (!item.id) return;
		historyItems = historyItems.map((it) => it.id === item.id ? { ...it, for_revision: item.for_revision } : it);
		historyManager.applyForRevisionState(item);
		trashItems = trashItems.map((it) => it.id === item.id ? { ...it, for_revision: item.for_revision } : it);
		if (displayedHistoryItem?.id === item.id) displayedHistoryItem = { ...displayedHistoryItem, for_revision: item.for_revision };
		if (lineageGraph) {
			lineageGraph = {
				...lineageGraph,
				nodes: lineageGraph.nodes.map((node) => node.history && node.history.id === item.id
					? { ...node, history: { ...node.history, for_revision: item.for_revision } }
					: node)
			};
		}
	}

	async function toggleHistoryForRevision(item: HistoryForRevisionTarget | null | undefined, event?: Event): Promise<void> {
		event?.stopPropagation();
		if (!item?.id) return;
		const nextForRevision = !item.for_revision;
		updateHistoryForRevisionState({ ...item, for_revision: nextForRevision });
		try {
			const r = await apiFetch(`/api/history/${item.id}/for-revision`, {
				method: 'PATCH',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ for_revision: nextForRevision })
			});
			if (!r.ok) throw new Error(`HTTP ${r.status}`);
			const updated = await r.json() as Iteration;
			updateHistoryForRevisionState(updated);
			const refreshes: Promise<unknown>[] = [];
			if (historyForRevisionOnly) {
				// The work just left the listing the strip is showing, so the
				// filter comes off rather than leaving the strip on a work it no
				// longer holds -- the same rule the starred filter follows.
				if (!updated.for_revision) historyForRevisionOnly = false;
				refreshes.push(fetchHistoryOffset(0, { anchorId: updated.id }));
			}
			if (historyManager.forRevisionOnly) refreshes.push(historyManager.fetch());
			if (refreshes.length > 0) await Promise.all(refreshes);
		} catch (e) {
			updateHistoryForRevisionState(item);
			console.warn('failed to update the revision mark', e);
		}
	}

	async function refreshCurrentUserOnly(): Promise<void> {
		try {
			const r = await apiFetch('/api/auth/me', { cache: 'no-store' });
			if (!r.ok) return;
			currentUser = await r.json() as UserItem;
			applyUserTheme(currentUser);
			applyDownloadFolderSettings(currentUser);
		} catch {
			/* ignore */
		}
	}

	async function pushHistory(it: Iteration, options: { selectSaved?: boolean; countGeneration?: boolean; sourceText?: string; displayLabel?: string; batchLineNumber?: number; batchRunId?: string; historyVisibility?: 'normal' | 'lineage_only'; lineageParentNodeId?: string | null; derivationKind?: DerivationKind | null; derivationMetadata?: Record<string, unknown> } = {}): Promise<Iteration | null> {
		if (!authToken) return null;
		// Saving a work again stores the drawing it already has. An item that
		// came from the listing does not carry one, and saving it as it stands
		// would store a work with no picture -- a failure that shows up only when
		// somebody opens the copy.
		const svgToSave = await ensureIterationSvg(it);
		let saved: Iteration | null = null;
		try {
			const r = await apiFetch('/api/history', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ input: it.input, ddl: it.ddl, expanded_ddl: it.expanded_ddl ?? null, focus: it.focus ?? null, score: it.score, svg: svgToSave, at: it.at, elapsed_ms: it.elapsed_ms ?? 0, stage1_model: it.stage1_model ?? null, stage2_model: it.stage2_model ?? null, tokens_in: it.tokens_in ?? null, tokens_out: it.tokens_out ?? null, catalog_id: it.catalog_id ?? colorCatalogSettings.effectiveId, catalog_mode: it.catalog_mode ?? (colorCatalogSettings.isAuto ? 'auto' : 'fixed'), render_build_number: it.render_build_number ?? null, render_color_profile: it.render_color_profile ?? null, render_engine_id: it.render_engine_id ?? null, render_engine_version: it.render_engine_version ?? null, render_color_catalog_id: it.render_color_catalog_id ?? null, render_color_catalog_name: it.render_color_catalog_name ?? null, render_color_catalog_sub: it.render_color_catalog_sub ?? null, render_color_map: it.render_color_map ?? null, render_canvas_aspect: it.render_canvas_aspect ?? it.render_canvas_aspect_id ?? effectiveCanvasAspectId(), render_canvas_aspect_id: it.render_canvas_aspect_id ?? it.render_canvas_aspect ?? effectiveCanvasAspectId(), render_canvas_aspect_ratio: it.render_canvas_aspect_ratio ?? null, render_seed: it.render_seed == null ? null : Number(it.render_seed), composition_seed: it.composition_seed == null ? null : Number(it.composition_seed), interpretation_seed: it.interpretation_seed ?? null, variation_amplitude: it.variation_amplitude ?? null, variation_seed: it.variation_seed == null ? null : Number(it.variation_seed), save_artifacts: true, count_generation: options.countGeneration ?? false, canvas_aspect: it.render_canvas_aspect_id ?? it.render_canvas_aspect ?? effectiveCanvasAspectId(), instruction_lang_requested: it.instruction_lang_requested ?? instructionLang, instruction_lang_resolved: it.instruction_lang_resolved ?? null, ui_lang: it.ui_lang ?? getLang(), source_text: options.sourceText ?? it.source_text ?? it.input, display_label: options.displayLabel ?? it.display_label ?? null, batch_line_number: options.batchLineNumber ?? it.batch_line_number ?? null, batch_run_id: options.batchRunId ?? it.batch_run_id ?? null, history_visibility: options.historyVisibility ?? 'normal', lineage_parent_node_id: options.lineageParentNodeId ?? null, derivation_kind: options.derivationKind ?? null, derivation_metadata: options.derivationMetadata ?? {}, sketch_text: it.sketch_text ?? null, sketch_grain: it.sketch_grain ?? null, ...(it.sketch_state ? { sketch_state: it.sketch_state } : {}) })
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
					catalog_id: result.render_color_catalog_id ?? (colorCatalogSettings.effectiveId !== 'default' ? colorCatalogSettings.effectiveId : null),
					save_artifacts: demoSettings.save_files,
					canvas_aspect: effectiveCanvasAspectId(),
					instruction_lang_requested: result.instruction_lang_requested ?? instructionLang,
					instruction_lang_resolved: result.instruction_lang_resolved ?? null,
					ui_lang: result.ui_lang ?? getLang(),
					// The second sender to this endpoint. It was dropping the prose
					// as well as the state, so a demo work drawn through the layer
					// was saved as though it had never been near it.
					sketch_text: result.sketch_text ?? null,
					sketch_grain: result.sketch_grain ?? null,
					...(result.sketch_state ? { sketch_state: result.sketch_state } : {}),
				})
			});
			if (!r.ok) {
				const d = await r.json().catch(() => ({})) as { detail?: unknown };
				throw new Error(describeApiError(d.detail, r.status));
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
		expandedDdl = null;
		ddlGeneratedBaseline = inputMode === 'single' ? '' : null;
		thinking = null;
		result = null;
		stage1UserPrompt = '';
		error = null;
		reloadError = null;
		batchFailures = [];
		batchFailureReportStore.set(null);
		batchActiveLine = null;
		batchActiveDdl = null;
		batchObservedLine = null;
		batchLatestPrompt = '';
		outputTab = 'canvas';
		elapsedStage1Ms = 0;
		elapsedStage2Ms = 0;
		elapsedTotalMs = 0;
		tokensInStage1 = null;
		tokensOutStage1 = null;
		tokensInStage2 = null;
		tokensOutStage2 = null;
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
		// Taken before the flag below rewrites it: whether the work on the canvas
		// is one of the works leaving the listing.
		const displayedLeavesTheListing = !!displayedHistoryItem?.id
			&& ids.includes(displayedHistoryItem.id)
			&& (path === '/api/history/trash' || path === '/api/history/permanent-delete');
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
		// The strip re-seats its cursor once the listing has been read again, and
		// the canvas has to be showing the work the badge is on. Left to itself
		// the canvas kept the work that just left the listing, so the badge sat
		// on one work and the artwork beside it was another.
		if (displayedLeavesTheListing) {
			if (historyCursor >= 0 && historyCursor < historyItems.length) {
				loadIteration(historyCursor);
			} else {
				// Nothing left to seat the cursor on: the canvas empties rather
				// than holding the last work the listing no longer has.
				displayedHistoryItem = null;
				result = null;
			}
		}
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


	// Model comparison and language comparison own their selection, their results
	// and their run state; the page lends the artwork, the two paint stages and
	// the history writes.
	const modelInspection = createModelInspection({
		availableModelCatalog: () => availableModelCatalog,
		result: () => result,
		stage1Provider: () => stage1Provider,
		stage1Model: () => stage1Model,
		stage2Provider: () => stage2Provider,
		stage2Model: () => stage2Model,
		loading: () => loading,
		input: () => input,
		currentUser: () => currentUser,
		setCurrentUser: (user) => { currentUser = user as UserItem; },
		targetContextVersion: () => targetContextVersion,
		apiFetch,
		interpretOne,
		composeOne,
		ensureVisibleLineageParentId,
		pushHistory: (it, options) => pushHistory(it as unknown as Iteration, options),
		toggleHistoryStar,
		addTokens,
		statusModelName,
		effectiveCanvasAspectId,
	});

	async function replayHistoryItem(it: Iteration, source: ReplaySource = outputTab) {
		if (demoRunning || reloading) return;
		const contextVersion = targetContextVersion;
		const hasRecordedSeed = it.render_seed != null;
		const hasSeedText = Boolean(it.seed_text?.trim());
		const provisionalSeed = !hasRecordedSeed && !hasSeedText ? 0 : null;
		const replaySeed = hasRecordedSeed ? Number(it.render_seed) : provisionalSeed;
		reloading = true;
		reloadError = null;
		try {
			const catalogId = it.render_color_catalog_id ?? it.catalog_id ?? colorCatalogSettings.effectiveId;
			const canvasId = it.render_canvas_aspect_id ?? it.render_canvas_aspect ?? it.score?.canvas ?? effectiveCanvasAspectId();
			const r = await apiFetch('/api/render-svg', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({
					score: it.score,
					canvas_aspect: canvasId,
					render_seed: replaySeed,
					// The comparison this feeds is meant to show what the engine
					// version did. Leaving the placement seed behind moved the
					// marks as well, and that difference was read as the
					// engine's -- it is the one thing this screen must not lie
					// about. Raw, not `?? replaySeed`: renderer.py:3486 already
					// falls back to the performance seed when there is none.
					composition_seed: it.composition_seed ?? null,
					seed_text: it.seed_text,
					...workReferencePayload(it.id),
					...renderSettingsPayload('render-svg', { ...colorCatalogOverride(catalogId), ...wildOverride(Boolean(it.render_wild)) }),
				})
			});
			if (!r.ok) throw await apiError(r);
			const svg = await r.text();
			if (contextVersion !== targetContextVersion) return;
			const versionMessage = currentRenderEngineVersion
				? (it.render_engine_version
					? (it.render_engine_version === currentRenderEngineVersion
						? null
						: t().historyReplayVersionMismatch(it.render_engine_version, currentRenderEngineVersion))
					: t().historyReplayVersionNotRecorded(currentRenderEngineVersion))
				: null;
			replayComparison = {
				source,
				originalSvg: await ensureIterationSvg(it),
				replayedSvg: svg,
				recordedVersion: it.render_engine_version ?? null,
				currentVersion: currentRenderEngineVersion,
				versionMessage,
				provisionalSeed,
			};
		} catch (e) {
			if (contextVersion === targetContextVersion) reloadError = e instanceof Error ? e.message : String(e);
		} finally {
			reloading = false;
		}
	}

	function closeReplayComparison() {
		const source = replayComparison?.source;
		replayComparison = null;
		if (!source) return;
		if (source === 'history-manager') {
			historyManager.open = true;
			return;
		}
		outputTab = source;
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

// 系譜タブ: ダブルクリックは作品タブへ移す（シングルクリックは選択のまま）。
async function openLineageNodeInCanvas(node: LineageNode): Promise<void> {
	if (!node.history) return;
	loadIterationItem(node.history);
	outputTab = 'canvas';
}

async function toggleLineageStar(node: LineageNode, event?: Event): Promise<void> {
	if (!node.history?.id) return;
	await toggleHistoryStar({ id: node.history.id, starred: !!node.history.starred }, event);
}

async function toggleLineageForRevision(node: LineageNode, event?: Event): Promise<void> {
	if (!node.history?.id) return;
	await toggleHistoryForRevision({ id: node.history.id, for_revision: !!node.history.for_revision }, event);
}

function lineageCatalogId(node: LineageNode): string {
	return node.history?.render_color_catalog_id ?? node.history?.catalog_id ?? colorCatalogSettings.effectiveId;
}

function lineageCanvasAspectId(node: LineageNode): CanvasAspectId {
	return normalizeCanvasAspectId(node.history?.render_canvas_aspect_id ?? node.history?.render_canvas_aspect ?? node.history?.score?.canvas ?? effectiveCanvasAspectId());
}

async function showNewLineageChild(historyId: string | null | undefined, nodeId: string | null | undefined): Promise<void> {
	if (!historyId || !nodeId) throw new Error(getLang() === 'ja' ? '描画結果を系譜へ保存できませんでした。' : 'The finished work could not be saved to the lineage.');
	let found = await fetchHistoryOffset(0, { anchorId: historyId });
	if (!found && historyStripFiltered) {
		historyStarredOnly = false;
		historyForRevisionOnly = false;
		found = await fetchHistoryOffset(0, { anchorId: historyId });
	}
	const saved = historyItems.find((item) => item.id === historyId);
	if (!saved) throw new Error(getLang() === 'ja' ? '保存した作品を読み込めませんでした。' : 'The saved work could not be loaded.');
	// Description / DDL edits produce a single artwork, not a candidate set, so
	// land on the canvas tab and show it. The lineage is still refreshed below.
	outputTab = 'canvas';
	loadIterationItem(saved);
	await fetchLineage(nodeId, true);
}

async function drawLineageDescriptionEdit(node: LineageNode, text: string, signal?: AbortSignal, wild?: boolean | null): Promise<void> {
	const sourceText = text.trim();
	if (!sourceText || !node.history) return;
	const rendered = await paintOne(sourceText, {
		sourceText,
		historyInput: sourceText,
		canvasAspectId: lineageCanvasAspectId(node),
		lineageParentNodeId: node.id,
		derivationKind: 'description_edit',
		derivationMetadata: { edited_from_history_id: node.history.id ?? null },
		signal,
		// null override = inherit the parent work's setting.
		renderOverrides: {
			...colorCatalogOverride(lineageCatalogId(node)),
			...wildOverride(wild ?? node.history.render_wild === true)
		},
	});
	await showNewLineageChild(rendered.history_id, rendered.lineage_node_id);
}

/** 写生 (Stage 0.5): redraw a saved work at a different grain, as its child.
 *  The prose is written again -- the grain is what changed, so replaying the
 *  stored prose would leave the parameter dead. */
async function drawLineageSketchGrain(node: LineageNode, grain: 'fine' | 'coarse', signal?: AbortSignal): Promise<void> {
	if (!node.history) return;
	const sourceText = node.history.source_text ?? node.history.input ?? '';
	if (!sourceText.trim()) return;
	const rendered = await paintOne(sourceText, {
		sourceText,
		historyInput: sourceText,
		canvasAspectId: lineageCanvasAspectId(node),
		lineageParentNodeId: node.id,
		sketchMode: grain,
		derivationKind: 'sketch_grain_change',
		derivationMetadata: {
			edited_from_history_id: node.history.id ?? null,
			from_sketch_grain: node.history.sketch_grain ?? null,
			to_sketch_grain: grain
		},
		signal,
		renderOverrides: {
			...colorCatalogOverride(lineageCatalogId(node)),
			...wildOverride(node.history.render_wild === true)
		},
	});
	await showNewLineageChild(rendered.history_id, rendered.lineage_node_id);
}

async function drawLineageDdlEdit(node: LineageNode, editedDdl: string, signal?: AbortSignal): Promise<void> {
	const nextDdl = editedDdl.trim();
	if (!nextDdl || !node.history) return;
	const sourceText = node.history.source_text ?? node.history.input ?? '';
	const composed = await composeOne(nextDdl, sourceText, signal, undefined, undefined, {
		canvasAspectId: lineageCanvasAspectId(node),
		lineageParentNodeId: node.id,
		renderOverrides: {
			...colorCatalogOverride(lineageCatalogId(node)),
			...wildOverride(ddlDialogWildOverride ?? node.history.render_wild === true)
		},
	});
	const resolvedEditStage1Model = node.history.stage1_model ?? qualifiedModelId(stage1Provider, stage1Model);
	const resolvedEditStage2Model = composed.stage2_model ?? qualifiedModelId(stage2Provider, stage2Model);
	const saved = await pushHistory({
		input: sourceText,
		source_text: sourceText,
		ddl: nextDdl,
		expanded_ddl: composed.ddl,
		sketch_text: composed.sketch_text ?? null,
		sketch_grain: composed.sketch_grain ?? null,
		sketch_state: composed.sketch_state ?? null,
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
		composition_seed: composed.composition_seed,
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
async function drawNewDdl(rawDdl: string, signal?: AbortSignal): Promise<void> {
	const nextDdl = rawDdl.trim();
	if (!nextDdl) return;
	const firstLine = (nextDdl.split('\n').find((line) => line.trim().length > 0) ?? nextDdl).trim().slice(0, 80);
	const composed = await composeOne(nextDdl, '', signal, undefined, undefined, {
		canvasAspectId: effectiveCanvasAspectId(),
	});
	const saved = await pushHistory({
		input: '',
		source_text: firstLine,
		ddl: nextDdl,
		expanded_ddl: composed.ddl,
		sketch_text: composed.sketch_text ?? null,
		sketch_grain: composed.sketch_grain ?? null,
		sketch_state: composed.sketch_state ?? null,
		score: composed.score,
		svg: composed.svg,
		at: Date.now(),
		elapsed_ms: composed.elapsed_ms,
		stage1_model: null,
		stage2_model: composed.stage2_model ?? qualifiedModelId(stage2Provider, stage2Model),
		tokens_in: composed.tokens_in,
		tokens_out: composed.tokens_out,
		catalog_id: colorCatalogSettings.effectiveId,
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
		composition_seed: composed.composition_seed,
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
}

function openNewDdlDialog(): void {
	ddlDialogWildOverride = null;
	ddlDialogMode = 'new';
	ddlDialogNode = null;
	ddlDialogInitial = '';
	ddlDialogError = null;
	ddlDialogOpen = true;
}

// Description tab entry to the same dialog. Edit mode needs a lineage node, so
// resolve the displayed artwork's node from the loaded graph, fetching the
// lineage first when that tab has not been opened in this session.
async function openCurrentDdlEditor(): Promise<void> {
	const nodeId = currentLineageNodeId;
	if (!nodeId) return;
	const item = displayedHistoryItem ?? historyItems.find((entry) => entry.id === result?.history_id) ?? null;
	if (!lineageGraph?.nodes.some((entry) => entry.id === nodeId)) await fetchLineage(nodeId, true);
	const node = lineageGraph?.nodes.find((entry) => entry.id === nodeId) ?? null;
	if (!node) return;
	openLineageDdlEditor(node.history ? node : { ...node, history: item });
}

function openLineageDdlEditor(node: LineageNode): void {
	ddlDialogWildOverride = null;
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

// The DDL dialog draws through Stage 2 only, so its picker moves the global
// Stage 2 selection (same target as the main-screen model selection) and
// persists it. Unlike setStage2Model it leaves the history selection alone:
// the dialog stays open over the current view and its draw selects the saved
// result anyway.
async function selectDdlDialogDrawingModel(provider: Provider, model: string): Promise<void> {
	stage2Provider = provider;
	stage2Model = model;
	await persistModelSelection();
}

async function handleDdlDialogDraw(nextDdl: string, signal?: AbortSignal): Promise<void> {
	if (ddlDialogDrawing) return;
	ddlDialogDrawing = true;
	ddlDialogError = null;
	try {
		if (ddlDialogMode === 'edit' && ddlDialogNode) await drawLineageDdlEdit(ddlDialogNode, nextDdl, signal);
		else await drawNewDdl(nextDdl, signal);
		ddlDialogOpen = false;
	} catch (cause) {
		// Aborted by the dialog stop button: keep the dialog open, no error.
		if (!(cause instanceof DOMException && cause.name === 'AbortError') && !(cause instanceof Error && cause.name === 'AbortError')) {
			ddlDialogError = cause instanceof Error ? cause.message : String(cause);
		}
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

const currentLineageNodeId = $derived(displayedHistoryItem?.lineage_node_id ?? result?.lineage_node_id ?? null);
// The description tab's edit button needs both a node to branch from and a DDL
// to load into the editor.
const canEditCurrentDdl = $derived(!!currentLineageNodeId && !!(displayedHistoryItem?.ddl ?? ddl));

$effect(() => {
	if (outputTab === 'lineage' && currentLineageNodeId) void fetchLineage(currentLineageNodeId);
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
			variationGridDone = 0;
			variationGridTotal = 0;
			variationGridSlots = [];
			variationGridSlotLabels = [];
			variationGridStatus = null;
		}

		modelInspection.reset();

		interpretationDiffParts = [];
		reloadError = null;
		replayComparison = null;
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
		const itemDDL = it.ddl ?? '';
		const sourceText = it.source_text ?? it.input;
		expandedDdl = it.expanded_ddl ?? null;
		input = sourceText; ddl = itemDDL; ddlGeneratedBaseline = itemDDL; thinking = it.thinking ?? null;
		stage1UserPrompt = sourceText;
		adoptSketch(it.sketch_text ?? null, it.sketch_grain, sourceText, it.sketch_state);
		result = {
			score: it.score,
			svg: it.svg,
			stage1_model: it.stage1_model,
			stage2_model: it.stage2_model,
			render_build_number: it.render_build_number,
			render_color_profile: it.render_color_profile,
			render_engine_id: it.render_engine_id,
			render_engine_version: it.render_engine_version,
			ddl_version: it.ddl_version,
			ddl_engine_version: it.ddl_engine_version,
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
			composition_seed: it.composition_seed == null ? null : Number(it.composition_seed),
			interpretation_seed: it.interpretation_seed ?? null,
			variation_amplitude: it.variation_amplitude ?? null,
			variation_seed: it.variation_seed == null ? null : Number(it.variation_seed),
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
		// The listing carries thumbnails, not drawings, so the work being put on
		// the canvas fetches its own. One request for the one work being looked
		// at, rather than a page of them for the one that gets opened.
		if (!it.svg && it.id) void fillCanvasSvg(it);
	}

	/** Put the fetched drawing on the canvas, unless the reader has moved on. */
	async function fillCanvasSvg(it: Iteration): Promise<void> {
		const target = it.id;
		const svg = await ensureIterationSvg(it);
		if (!svg || displayedHistoryItem?.id !== target || !result) return;
		result = { ...result, svg };
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


	/** One work older. */
	async function gotoPrev() {
		const target = historyNavTarget(historyNavState, 'older');
		if (!target) return;
		if (target.offset !== historyOffset && !(await fetchHistoryOffset(target.offset))) return;
		// Read after the await, not before it. Read before, a tab the user chose
		// while the page was arriving was quietly put back to the one they left.
		const preservedTab = outputTab;
		loadIteration(historyNavIndex(target));
		outputTab = preservedTab;
	}

	/** One work newer. */
	async function gotoNext() {
		const target = historyNavTarget(historyNavState, 'newer');
		if (!target) return;
		if (target.offset !== historyOffset && !(await fetchHistoryOffset(target.offset))) return;
		const preservedTab = outputTab;
		loadIteration(historyNavIndex(target));
		outputTab = preservedTab;
	}

	async function gotoLatest() {
		const target = historyNavTarget(historyNavState, 'latest');
		if (!target) return;
		if (target.offset !== historyOffset && !(await fetchHistoryOffset(target.offset))) return;
		loadIteration(historyNavIndex(target));
	}

	// Where the strip is standing, as historyNavigation.ts reads it. The canvas's
	// six buttons and the strip's three all decide from this one value.
	const historyNavState = $derived({
		cursor: historyCursor,
		offset: historyOffset,
		total: historyTotal,
		windowSize: historyWindowSize,
		busy: historyFetchInFlight > 0,
		locked: demoRunning
	});
	const historyNavButtonsDisabled = $derived(historyNavDisabled(historyNavState));
	// The strip's pager. "Latest" is counted in works so it agrees with the
	// canvas's; the other two step a page and are disabled when there is no page
	// that way to step to.
	const historyPageNavDisabled = $derived({
		latest: historyNavButtonsDisabled.latest,
		newer: historyPageTarget(historyNavState, 'newer') === null,
		older: historyPageTarget(historyNavState, 'older') === null,
		oldest: historyPageTarget(historyNavState, 'oldest') === null
	});
	// Left as it was: 0 / N is how "nothing is selected" is shown, and is not a
	// claim about which work is current.
	const navPos       = $derived(historyOffset + historyCursor + 1);

	/**
	 * The index a target names, once the page it names is in hand.
	 *
	 * 'oldest-on-page' cannot be a number in the module: how many works the page
	 * actually holds is only known after the answer arrives.
	 */
	function historyNavIndex(target: HistoryNavTarget): number {
		return target.select === 'oldest-on-page' ? historyItems.length - 1 : target.select;
	}

	// ── Saijiki ─────────────────────────────────────────────
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

	/**
	 * Say that a strip filter was cleared, because nothing else says it.
	 *
	 * Clearing it is a rescue and stays: a work reached from somewhere else --
	 * a lineage, a shared link, the manager -- can be unstarred, and leaving the
	 * filter on would put the user in front of a strip their work is not in. But
	 * the filter button goes back to off on its own, which reads as the press
	 * having failed. Same mechanism as the lineage notice above: a string and a
	 * five second timer.
	 */
	function showHistoryFilterClearedNotice(text: string): void {
		historyStarredFilterNotice = text;
		if (historyStarredFilterNoticeTimer !== null) window.clearTimeout(historyStarredFilterNoticeTimer);
		historyStarredFilterNoticeTimer = window.setTimeout(() => {
			historyStarredFilterNotice = null;
			historyStarredFilterNoticeTimer = null;
		}, 5000);
	}

	function showHistoryStarredFilterClearedNotice(): void {
		showHistoryFilterClearedNotice(t().historyStarredFilterClearedNotice);
	}

	function showHistoryForRevisionFilterClearedNotice(): void {
		showHistoryFilterClearedNotice(t().historyForRevisionFilterClearedNotice);
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
		colorCatalogSettings.selected = id;
	}

	async function varyPerformance() {
		if (!result || variationBusy) return;
		const parentNodeId = await ensureVisibleLineageParentId();
		variationBusy = true;
		variationTokensIn = null;
		variationTokensOut = null;
		variationElapsed.start();
		reloading = true;
		reloadError = null;
		try {
			const usedSeeds = new Set<number>();
			if (Number.isFinite(result.render_seed ?? NaN)) usedSeeds.add(Number(result.render_seed));
			const nextSeed = createSafeIntegerSeed(usedSeeds);
			// The placement on screen was drawn with composition_seed when the work has one and
			// with render_seed otherwise (renderer.py:3058). Send that same value so changing the
			// touch keeps the composition, which is what this operation says it does. It is also
			// carried onto the result below: without that, a second touch change would find no
			// composition_seed and fall back to the new performance seed, moving the composition.
			const placementSeed = result.composition_seed ?? result.render_seed ?? null;
			const r = await apiFetch('/api/render-svg', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({
					score: result.score,
					canvas_aspect: refinementCanvasAspectId(),
					render_seed: nextSeed,
					composition_seed: placementSeed,
					...workReferencePayload(refinementWorkId()),
					...renderSettingsPayload('render-svg', colorCatalogOverride(refinementCatalogId())),
				})
			});
			if (!r.ok) throw await apiError(r);
			const svg = await r.text();
			result = { ...result, svg, render_seed: nextSeed, composition_seed: placementSeed, render_hash: null, render_hash_short: null, history_id: null, history_at: null, lineage_node_id: null, lineage_parent_node_id: parentNodeId, derivation_kind: parentNodeId ? 'touch_change' : null, derivation_metadata: { render_seed_from: result.render_seed ?? null, render_seed_to: nextSeed } };
			displayedHistoryItem = null;
			historyCursor = -1;
			outputTab = 'canvas';
			fitCanvasZoom();
		} catch (e) {
			reloadError = e instanceof Error ? e.message : String(e);
		} finally {
			reloading = false;
			variationBusy = false;
			variationElapsed.stop();
		}
	}

	async function varyComposition() {
		if (!result || variationBusy || loading) return;
		const source = input.trim();
		if (!source) return;
		const parentNodeId = await ensureVisibleLineageParentId();
		variationBusy = true;
		variationTokensIn = null;
		variationTokensOut = null;
		variationElapsed.start();
		loading = true;
		error = null;
		try {
			const usedSeeds = new Set<number>();
			if (Number.isFinite(result.composition_seed ?? NaN)) usedSeeds.add(Number(result.composition_seed));
			const nextVarySeed = createSafeIntegerSeed(usedSeeds);
			const r = await paintOne(source, { compositionSeed: nextVarySeed, historyInput: source, sourceText: source, canvasAspectId: refinementCanvasAspectId(), renderOverrides: inPlaceRedrawOverrides(), lineageParentNodeId: parentNodeId, derivationKind: parentNodeId ? 'layout_change' : null, derivationMetadata: { composition_seed: nextVarySeed } });
			ddl = r.source_ddl ?? r.ddl;
			expandedDdl = r.ddl;
			ddlGeneratedBaseline = ddl;
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
			variationElapsed.stop();
			stopTimer();
		}
	}

	async function varyInterpretation() {
		if (!result || variationBusy || loading) return;
		const source = input.trim();
		if (!source) return;
		const parentNodeId = await ensureVisibleLineageParentId();
		variationBusy = true;
		variationTokensIn = null;
		variationTokensOut = null;
		variationElapsed.start();
		loading = true;
		error = null;
		const previousDdl = ddl;
		try {
			const interpretationSeed = createInterpretationSeed();
			const r = await paintOne(source, { historyInput: source, sourceText: source, canvasAspectId: refinementCanvasAspectId(), renderOverrides: inPlaceRedrawOverrides(), interpretationSeed, lineageParentNodeId: parentNodeId, derivationKind: parentNodeId ? 'reinterpretation' : null, derivationMetadata: { interpretation_seed: interpretationSeed } });
			interpretationDiffParts = buildDdlDiffParts(previousDdl, r.ddl);
			ddl = r.source_ddl ?? r.ddl;
			expandedDdl = r.ddl;
			ddlGeneratedBaseline = ddl;
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
			variationElapsed.stop();
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

	// The saved work a redraw is a redraw OF. The server reads that work's own
	// recorded colors, so a catalog definition that has since changed, been
	// renamed, or been retired no longer repaints it. The catalog id keeps being
	// sent alongside -- it is the nameplate, and only the colors moved.
	//
	// Null means there is no saved work yet: an unsaved result was just drawn
	// from today's definition, so today's definition is the one it remembers.
	function refinementWorkId(): string | null {
		return result?.history_id ?? displayedHistoryItem?.id ?? null;
	}

	function workReferencePayload(workId: string | null | undefined): Record<string, string> {
		return workId ? { work_id: workId } : {};
	}

	// The two in-place redraws (vary the layout, reinterpret) keep the artwork's
	// catalog but have never carried the level or the switch: they omit the level
	// so the parent's is inherited, and draw tame. Preserved as-is.
	function inPlaceRedrawOverrides(): RenderOverrides {
		return {
			...colorCatalogOverride(refinementCatalogId()),
			...wildOverride(false)
		};
	}

	// A refinement redraws against the artwork it refines: its catalog, the level
	// the author chose for this round, and the switch the artwork was drawn with.
	function refinementRenderOverrides(): RenderOverrides {
		return {
			...colorCatalogOverride(refinementCatalogId()),
			...wildOverride(effectiveRefineWild)
		};
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
				canvas_aspect: refinementCanvasAspectId(),
				// Same reasoning as varyPerformance: the placement on screen followed render_seed
				// when the work carries no composition_seed, so sending the raw field would send
				// null and let the placement follow the new performance seed instead.
				composition_seed: result.composition_seed ?? result.render_seed ?? null,
				interpretation_seed: result.interpretation_seed,
				seed_text: normalizedSeedText,
				...workReferencePayload(refinementWorkId()),
				...renderSettingsPayload('render-score', colorCatalogOverride(refinementCatalogId())),
			}),
		});
		if (!r.ok) throw await apiError(r);
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
				derivation_kind: currentLineageParentId() ? 'touch_change' : null,
				derivation_metadata: { render_seed_from: result.render_seed ?? null, render_seed_to: data.render_seed, seed_text: normalizedSeedText },
			},
		};
	}

	async function composeVariationCandidate(compositionSeed: number, label: string, signal?: AbortSignal): Promise<VariationCandidate> {
		const source = input.trim();
		const baseDdl = ddl ?? "";
		const r = await apiFetch("/api/compose", {
			method: "POST",
			signal,
			headers: { "Content-Type": "application/json" },
			body: JSON.stringify({
				ddl: baseDdl,
				description: source,
				...sketchPayloadFor(source),
				model: qualifiedModelId(stage2Provider, stage2Model),
				instruction_lang: instructionLang,
				ui_lang: getLang(),
				canvas_aspect: refinementCanvasAspectId(),
				auto_repair: ddlAutoRepairEnabled,
				composition_seed: compositionSeed,
				...renderSettingsPayload('compose', refinementRenderOverrides()),
				...(currentLineageParentId() ? { lineage_parent_node_id: currentLineageParentId() } : {}),
			})
		});
		if (!r.ok) throw await apiError(r);
		const data = await r.json();
		return { id: `comp-${compositionSeed}`, label, selected: false, result: { ...composeCandidateResult(source, baseDdl, data), lineage_parent_node_id: currentLineageParentId(), derivation_kind: currentLineageParentId() ? 'layout_change' : null, derivation_metadata: { composition_seed: compositionSeed } } };
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
			canvasAspectId: refinementCanvasAspectId(),
			sketchText: sketchTextFor(source),
			interpretationSeed,
			signal,
			renderOverrides: refinementRenderOverrides(),
			lineageParentNodeId: currentLineageParentId(),
		});
		return { id: "interp-" + interpretationSeed, label, selected: false, result: { ...r, lineage_parent_node_id: currentLineageParentId(), derivation_kind: currentLineageParentId() ? "reinterpretation" : null, derivation_metadata: { interpretation_seed: interpretationSeed } } };
	}

	// Refinement keeps its draw (author's ruling, 2026-08-01). The batch and the
	// demo now send catalog_mode=auto and let the server read each description,
	// but this fills a grid of alternatives for the author to choose between:
	// reading the description would answer once and collapse four cards into one.
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
				canvas_aspect: refinementCanvasAspectId(),
				render_seed: result.render_seed,
				composition_seed: result.composition_seed,
				interpretation_seed: result.interpretation_seed,
				...renderSettingsPayload('render-score', colorCatalogOverride(catalogId)),
			}),
		});
		if (!r.ok) throw await apiError(r);
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

	async function variationCandidateLabel(amplitude: VariationAmplitude, seed: number, label: string, signal?: AbortSignal): Promise<VariationCandidate> {
		const source = input.trim();
		const baseDdl = ddl ?? "";
		const r = await apiFetch("/api/compose", {
			method: "POST",
			signal,
			headers: { "Content-Type": "application/json" },
			body: JSON.stringify({
				ddl: baseDdl,
				description: source,
				...sketchPayloadFor(source),
				model: qualifiedModelId(stage2Provider, stage2Model),
				instruction_lang: instructionLang,
				ui_lang: getLang(),
				canvas_aspect: refinementCanvasAspectId(),
				auto_repair: ddlAutoRepairEnabled,
				variation_amplitude: amplitude,
				variation_seed: seed,
				...renderSettingsPayload('compose', refinementRenderOverrides()),
				...(currentLineageParentId() ? { lineage_parent_node_id: currentLineageParentId() } : {}),
			})
		});
		if (!r.ok) throw await apiError(r);
		const data = await r.json();
		return {
			id: `variation-${amplitude}-${seed}`,
			label,
			selected: false,
			result: {
				...composeCandidateResult(source, baseDdl, data),
				lineage_parent_node_id: currentLineageParentId(),
				derivation_kind: currentLineageParentId() ? 'variation' : null,
				derivation_metadata: { variation_amplitude: amplitude, variation_seed: seed },
			},
		};
	}

	// Fan-out cap for candidate grids, served by GET /api/client-config so it can
	// track the server's own render slot count. The 503 retry in apiFetch covers
	// slots taken by other work.

	// The hooks are per job rather than per completion: a fan-out that only counts
	// finishes cannot say which jobs are in flight, and the progress it draws
	// looks like nothing happening until everything lands at once.
	async function runWithLimit<T>(
		thunks: Array<() => Promise<T>>,
		limit: number,
		hooks?: { onStart?: (index: number) => void; onDone?: (index: number) => void }
	): Promise<T[]> {
		const results = new Array<T>(thunks.length);
		let next = 0;
		const workers = Array.from({ length: Math.max(1, Math.min(limit, thunks.length)) }, async () => {
			for (let index = next++; index < thunks.length; index = next++) {
				hooks?.onStart?.(index);
				results[index] = await thunks[index]();
				hooks?.onDone?.(index);
			}
		});
		await Promise.all(workers);
		return results;
	}

	// 変奏の seed はサーバーが採番する。seed 空間の管理と重複回避を UI に持ち込まない。
	async function allocateVariationSeeds(amplitude: VariationAmplitude, count: number): Promise<number[]> {
		const r = await apiFetch("/api/variation/seeds", {
			method: "POST",
			headers: { "Content-Type": "application/json" },
			body: JSON.stringify({ amplitude, count })
		});
		if (!r.ok) throw await apiError(r);
		return (await r.json()).seeds as number[];
	}

	async function generateVariationCandidates(kind: RefineKind, count: 1 | 4, touchWords?: string, amplitude?: VariationAmplitude) {
		if (!result || variationGridBusy || loading) return;
		const source = input.trim();
		if (!source || !ddl) return;
		const normalizedTouchWords = touchWords?.trim() ?? '';
		if (kind === 'touch' && !normalizedTouchWords) {
			variationGridStatus = getLang() === 'ja' ? 'タッチを変える言葉を入力してください。' : 'Enter words to vary the touch.';
			return;
		}
		if (kind === 'touch' && count === 4) {
			variationGridStatus = getLang() === 'ja' ? '同じ言葉は同じタッチ(Seed)になります。1案だけ生成可能です。' : 'The same words produce the same touch (Seed). Only one option can be made.';
			return;
		}
		const contextVersion = targetContextVersion;
		await ensureVisibleLineageParentId();
		if (contextVersion !== targetContextVersion) return;
		const abortController = new AbortController();
		variationGridAbortController = abortController;
		variationGridBusy = true;
		variationGridCanAbort = false;
		variationTokensIn = null;
		variationTokensOut = null;
		variationElapsed.start();
		variationGridIncludesReading = kind === "reading";
		variationGridTaskLabel = kind === "touch"
			? t().canvasVaryPerformance
			: kind === "layout"
				? t().canvasVaryComposition
				: kind === "reading"
					? t().canvasVaryInterpretation
					: kind === "variation"
						? t().variationTitle
						: t().canvasVaryColor;
		variationGridStatus = null;
		variationGridDone = 0;
		variationGridTotal = count;
		// Seated before the seeds are asked for, so the lanes are on screen for
		// the whole run rather than appearing once the first job starts.
		variationGridSlotLabels = Array.from({ length: count }, () => '');
		variationGridSlots = Array.from({ length: count }, () => 'waiting' as VariationSlotState);
		const abortTimer = window.setTimeout(() => {
			if (variationGridAbortController === abortController && variationGridBusy) variationGridCanAbort = true;
		}, 3000);
		try {
			const usedVarySeeds = new Set<number>();
			if (Number.isFinite(result.composition_seed ?? NaN)) usedVarySeeds.add(Number(result.composition_seed));
			for (const candidate of variationCandidates) {
				if (Number.isFinite(candidate.result.composition_seed ?? NaN)) usedVarySeeds.add(Number(candidate.result.composition_seed));
			}
			const catalogIds = kind === "color" ? colorCatalogCandidateIds(count) : [];
			// 変奏の seed 採番はサーバー側なので、候補生成前に count 個まとめて確保する。
			const variationSeeds = kind === "variation" ? await allocateVariationSeeds(amplitude ?? "medium", count) : [];
			// The label is lifted out of the job so the lane can be named before the
			// job that fills it has started.
			const plans = Array.from({ length: count }, (_, index) => {
				const sequence = index + 1;
				if (kind === "touch") {
					const label = t().canvasVaryPerformance;
					return { label, run: () => renderWordTouchCandidate(normalizedTouchWords, label, abortController.signal) };
				}
				if (kind === "layout") {
					const compositionSeed = createSafeIntegerSeed(usedVarySeeds);
					usedVarySeeds.add(compositionSeed);
					const label = t().canvasVaryComposition + " " + sequence;
					return { label, run: () => composeVariationCandidate(compositionSeed, label, abortController.signal) };
				}
				if (kind === "reading") {
					const label = t().canvasVaryInterpretation + " " + sequence;
					return { label, run: () => interpretationVariationCandidate(label, abortController.signal) };
				}
				if (kind === "variation") {
					const label = t().variationTitle + " " + sequence;
					return { label, run: () => variationCandidateLabel(amplitude ?? "medium", variationSeeds[index], label, abortController.signal) };
				}
				const catalogId = catalogIds[index];
				const label = t().canvasVaryColor + " " + sequence + " · " + catalogName(catalogId);
				return { label, run: () => renderColorCatalogCandidate(catalogId, label, abortController.signal) };
			});
			variationGridSlotLabels = plans.map((plan) => plan.label);
			variationGridSlots = plans.map(() => 'waiting' as VariationSlotState);
			const seatSlot = (index: number, state: VariationSlotState) => {
				if (variationGridAbortController !== abortController) return;
				variationGridSlots = variationGridSlots.map((current, i) => i === index ? state : current);
			};
			variationCandidates = await runWithLimit(plans.map((plan) => plan.run), renderFanoutLimit, {
				onStart: (index) => seatSlot(index, 'running'),
				onDone: (index) => {
					seatSlot(index, 'done');
					if (variationGridAbortController === abortController) variationGridDone += 1;
				},
			});
			for (const candidate of variationCandidates) {
				variationTokensIn = addTokens(variationTokensIn, paintTokensIn(candidate.result));
				variationTokensOut = addTokens(variationTokensOut, paintTokensOut(candidate.result));
			}
		} catch (e) {
			if (!(e instanceof DOMException && e.name === "AbortError")) variationGridStatus = e instanceof Error ? e.message : String(e);
		} finally {
			window.clearTimeout(abortTimer);
			if (variationGridAbortController === abortController) {
				variationGridAbortController = null;
				variationGridBusy = false;
				variationGridCanAbort = false;
				variationElapsed.stop();
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
		ddl = candidate.result.source_ddl ?? candidate.result.ddl;
		expandedDdl = candidate.result.ddl;
		ddlGeneratedBaseline = ddl;
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
					catalog_id: candidate.result.render_color_catalog_id ?? colorCatalogSettings.effectiveId,
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
	// Exporting owns the profile round trip, the canvas rasterisation and the
	// capture-date stamp; the page only lends it the artwork and the fetch wrapper.
	const { downloadSVG, downloadPNG } = createExportActions({
		result: () => result,
		input: () => input,
		displayedHistoryItem: () => displayedHistoryItem,
		apiFetch,
		apiError,
		exportFilename,
		refinementCatalogId,
		refinementCanvasAspectId,
		effectiveCanvasAspectId,
	});

	// The canvas toolbar builds the card from the work it is showing, which is
	// the listed item when one is selected and the fresh drawing otherwise. The
	// page shape and the seal come from the same settings the history modal uses.
	async function downloadCurrentCard(): Promise<void> {
		const id = displayedHistoryItem?.id ?? result?.history_id ?? null;
		if (!id) return;
		await downloadCard(apiFetch, id, exportSettings.card);
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

	function shortModelName(m: string): string {
		if (m.includes('opus')) return 'opus';
		if (m.includes('haiku')) return 'haiku';
		if (m.includes('sonnet')) return 'sonnet';
		if (m.includes('qwen3')) return 'qwen3';
		if (m.includes('qwen')) return 'qwen';
		if (m.includes('gemma')) return 'gemma';
		return (m.split('/').pop() ?? m).slice(0, 8);
	}

	// The narrow history columns keep the shortened model name, but they still
	// say which provider ran it: the same id can be served by two of them.
	function shortModel(m: string | null | undefined): string {
		if (!m) return '';
		const { provider, model } = resolveModelRefForDisplay(m);
		const owner = providerLabel(provider);
		const short = shortModelName(model);
		return owner ? `${owner}/${short}` : short;
	}

	function statusModelName(m: string | null | undefined): string {
		return modelDisplayName(m);
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
	const nextCatalogName = $derived(colorCatalogSettings.isAuto ? t().colorCatalogAuto : currentCatalog.name);
	// The catalog a work was drawn with, named as it stands today. Two things
	// the bare name cannot say are said here instead of being papered over: an
	// id nothing current answers to is marked retired rather than shown as the
	// default, and a work saved before the colors were recorded is marked as
	// having no record -- that one draws from today's definition, not its own.
	const statusCatalogName = $derived.by(() => {
		const work = displayedHistoryItem ?? result ?? null;
		if (!work) return '-';
		const catalogId = work.render_color_catalog_id
			?? (displayedHistoryItem ? displayedHistoryItem.catalog_id : null)
			?? null;
		if (!catalogId) return '-';
		const plate = catalogNameplate(colorCatalogs, renamedCatalogIds, catalogId, work.render_color_catalog_name);
		const notes: string[] = [];
		if (plate.retired) notes.push(t().colorCatalogRetired);
		const colorMap = work.render_color_map;
		if (!colorMap || Object.keys(colorMap).length === 0) notes.push(t().colorCatalogNoRecord);
		return notes.length ? t().colorCatalogNote(plate.name, notes) : plate.name;
	});
	const currentCanvasAspect = $derived(getCanvasAspectOption(effectiveCanvasAspectId()));
	const nextCanvasName = $derived(currentCanvasAspect.label);
	const displayCanvasAspect = $derived(svgAspect(result?.svg) ?? currentCanvasAspect);
	const statusCanvasName = $derived.by(() => {
		const canvasId = displayedHistoryItem?.render_canvas_aspect_id ?? displayedHistoryItem?.render_canvas_aspect ?? displayedHistoryItem?.score?.canvas ?? result?.render_canvas_aspect_id ?? result?.render_canvas_aspect ?? result?.score?.canvas ?? null;
		return canvasId ? getCanvasAspectOption(canvasId).label : '-';
	});
	// The digest, not the stored `<scheme>:<digest>`: the scheme is a property of
	// the value rather than part of it, and nothing in the app takes a prefixed
	// string as input. See lib/hashIdentity.ts.
	const statusHashFull = $derived(hashDigest(
		displayedHistoryItem?.render_hash
			?? result?.render_hash
			?? ''
	));
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
	const replayableStatusHistoryItem = $derived(
		statusHistoryItem && "score" in statusHistoryItem && "svg" in statusHistoryItem
			? statusHistoryItem as Iteration
			: null
	);
	// What a refine inherits when nothing is overridden: the work on screen, or
	// the global setting when nothing is on screen.
	const targetWild = $derived(displayedHistoryItem?.render_wild ?? result?.render_wild ?? wildSettings.enabled);
	const effectiveRefineWild = $derived(refineWildOverride ?? targetWild === true);
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

	function setHistoryForRevisionOnly(value: boolean) {
		historyForRevisionOnly = value;
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
		if (result.composition_seed !== undefined) payload.composition_seed = result.composition_seed;
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
		// Seated on the new grid before the request goes out. Fetching the old
		// offset under the new page size is what made the pager show works twice
		// going older and step over them going newer.
		historyOffset = alignHistoryOffset(historyOffset, size, historyTotal);
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
		// Coming back to the tab still refreshes at once; what it no longer does
		// is jump the floor. Both of these fire on a single alt-tab.
		function onHistoryVisibilityChange() {
			if (document.visibilityState === 'visible') void refreshHistoryForExternalSave();
		}
		function onHistoryWindowFocus() {
			void refreshHistoryForExternalSave();
		}
		document.addEventListener('visibilitychange', onHistoryVisibilityChange);
		window.addEventListener('focus', onHistoryWindowFocus);

		initLang();
		initMascot();
		try {
			const p1 = localStorage.getItem(PROVIDER_STAGE1_KEY) as Provider | null; if (p1) stage1Provider = p1;
			const m1 = localStorage.getItem(MODEL_STAGE1_KEY); if (m1) stage1Model = m1;
			const p2 = localStorage.getItem(PROVIDER_STAGE2_KEY) as Provider | null; if (p2) stage2Provider = p2;
			const m2 = localStorage.getItem(MODEL_STAGE2_KEY); if (m2) stage2Model = m2;
			// Anything but 'detailed' means standard, so a cleared or corrupted
			// entry opens the dialog at its narrow width rather than throwing.
			settingsDetail = normalizeSettingsDetail(localStorage.getItem(SETTINGS_DETAIL_KEY));
			loadPersistedSettings();
		} catch {}
		void (async () => {
			await Promise.all([loadColorCatalogs(), loadPublicAppInfo(), loadCurrentUser(), fetchPrompts()]);
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
	// persist() reads every field it writes, so this effect tracks them all
	// without the page having to name them one by one.
	$effect(() => exportSettings.persist());
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
		// Asked on arrival rather than kept up to date: works are saved from other
		// windows too, and the answer is only ever read here.
		if (mode === 'batch') void untrack(refreshBatchResume);
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
		appVersion={APP_VERSION}
		buildNumber={__BUILD_NUMBER__}
		{developerMode}
	/>
{:else}
<div
	class="root"
	class:tooltips-disabled={!tooltipsEnabled}
	class:ui-hide-input-modes={!uiVisibility.input_modes}
	class:ui-hide-drawing-settings={!uiVisibility.drawing_settings}
	class:ui-hide-ddl-tools={!uiVisibility.ddl_tools}
	class:ui-hide-detail-status={!uiVisibility.detail_status}
	class:ui-hide-work-tools={!uiVisibility.work_tools}
	class:ui-hide-history={!uiVisibility.history}
>
	<AppRail
		{currentUser}
		bind:userMenuOpen
		bind:userMenuWrapEl
		{settingsOpen}
		{darkMode}
		buildNumber={__BUILD_NUMBER__}
		{developerMode}
		{singleUserMode}
		showAuxiliary={uiVisibility.auxiliary}
		{uiMode}
		{tooltipsEnabled}
		onSetUiMode={(mode) => void updateUiMode(mode)}
		onToggleTooltips={() => void updateTooltipsEnabled(!tooltipsEnabled)}
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
						{sketchMode}
						onSelectSketchMode={(mode) => (sketchMode = mode)}
						bind:inputMode
						bind:input
						bind:batchInput
						{lineNumbersText}
						{batchNonEmpty}
						{batchRunning}
						{singleRunning}
						hideRunStatus={reloading}
						singleDdlReady={ddl !== null}
						{batchActiveLine}
						{batchObservedLine}
						{batchRunningLineText}
						{batchSketchText}
						{batchSketchGrainLabel}
						{batchActiveDdlHighlighted}
						{batchTotal}
						{batchCurrent}
						{batchRetryRound}
						{batchActiveTokensIn}
						{batchActiveTokensOut}
						{batchTokensInTotal}
						{batchTokensOutTotal}
						{liveMs}
						batchFailureReport={batchFailureReportStore.report}
						{batchPromptHistory}
						canResumeBatch={batchResume !== null}
						onResumeBatch={() => void resumeInterruptedBatch()}
						bind:demoSettings
						demoModelProviderGroups={availableModelCatalog}
						{demoRunning}
						{demoTimedOut}
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
						generationDisabled={variationGridBusy || reloading}
						{error}
						{stageLabel}
						{canvasAspectEnabled}
						{canvasAspectId}
						{canvasAspectMenuOpen}
						{stage1ModelLabel}
						{stage2ModelLabel}
						runTokensIn={activeRunTokensIn}
						runTokensOut={activeRunTokensOut}
						{nextStage1Model}
						{nextStage2Model}
						{nextCatalogName}
						{nextCanvasName}
						onToggleCanvasAspectMenu={() => (canvasAspectMenuOpen = !canvasAspectMenuOpen)}
						onSelectCanvasAspect={selectCanvasAspect}
						onOpenModelSelection={() => openModelSelection(false)}
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
							<Tooltip placement="left" text={t().tooltipDdlEdit}>
								<button class="ddl-new-btn" type="button" disabled={!canEditCurrentDdl} onclick={openCurrentDdlEditor}>{t().ddlEditButton}</button>
							</Tooltip>
							<Tooltip placement="left" text={t().tooltipDdlNew}>
								<button class="ddl-new-btn" type="button" onclick={openNewDdlDialog}>{t().ddlNewButton}</button>
							</Tooltip>
						</section>
					{/if}

					<!-- 指示書から描画したときの状況表示。入力欄ではなくボタンの下に出す -->
					{#snippet ddlRunStatus()}
						<RunStatus
							label={stageLabel || t().stageDdlGenerating}
							stage2Model={stage2ModelLabel}
							elapsedMs={liveMs}
							tokensIn={activeRunTokensIn}
							tokensOut={activeRunTokensOut}
							onStop={stopDdlRender}
						/>
					{/snippet}

					<!-- 写生 (Stage 0.5). Above the instructions because it comes before
					     them: the author reads the prose the layer wrote, and may
					     rewrite it. What is left here is what Stage 1 reads. -->
					{#if inputMode === 'single' && (sketchText !== null || result !== null)}
						<section class="panel-section sketch-section">
							<div class="sketch-head">
								<Tooltip placement="right" text={t().tooltipSketchToggle}>
									<button class="sketch-toggle" type="button" onclick={describePanelSettings.toggleSketch}>
										<span class="sketch-arrow" class:open={describePanelSettings.sketchOpen}>▶</span>
										<span class="sketch-title">{t().sketchLabel}</span>
									</button>
								</Tooltip>
								{#if sketchText !== null}
									<span class="sketch-grain">{t().sketchGrainLabel}: {sketchModeLabel(sketchModeOf(result?.sketch_grain ?? sketchGrainOf(sketchMode)), getLang() === 'ja')}</span>
									<!-- Editing needs the prose on screen, so the button unfolds the
									     section rather than acting on what the author cannot see. -->
									<button type="button" class="sketch-edit-btn" onclick={() => { sketchEditing = !sketchEditing; if (sketchEditing) describePanelSettings.revealSketch(); }}>
										{sketchEditing ? t().ddlDoneBtn : t().ddlEditBtn}
									</button>
								{/if}
							</div>
							{#if describePanelSettings.sketchOpen}
								{#if result?.sketch_fallback_used}
									<p class="sketch-note">{t().sketchFallbackNote}</p>
								{:else if sketchText === null}
									<!-- No prose. Which of the silences this is comes from the
									     record, not from the absence: a work drawn with the
									     layer off and a work drawn before the layer was
									     recorded read the same here otherwise. -->
									<p class="sketch-note">{sketchStateNote(sketchState, getLang() === 'ja')}</p>
								{:else if sketchEditing}
									<textarea class="sketch-editor" rows="7" bind:value={sketchDraft} spellcheck="true"></textarea>
									<p class="sketch-note">{t().sketchEditHint}</p>
								{:else}
									<p class="sketch-body">{sketchDraft}</p>
								{/if}
							{/if}
						</section>
					{/if}

					<!-- 解釈 (正規化DDL・閲覧専用) -->
					{#if ddl !== null && inputMode === 'single'}
						<section class="panel-section">
							<DdlViewer
								{ddl}
								{expandedDdl}
								label={t().ddlLabel}
								expandedLabel={t().ddlExpandedLabel}
								onPaint={() => { void replay(); }}
								paintDisabled={loading || reloading || variationGridBusy}
								runStatus={reloading ? ddlRunStatus : null}
							/>
						</section>
					{/if}

					<!-- 展開層が落としたもの。編集中の指摘 (DDL エディタ) と対で、
					     消えた後にしか分からない側をここが受け持つ。 -->
					{#if pluginWarningsShown.length > 0 && inputMode === 'single'}
						<section class="panel-section plugin-warnings">
							<div class="plugin-warnings-title">{t().ddlPluginWarningsTitle}</div>
							{#each pluginWarningsShown as warning}
								<p class="plugin-warning-line">{warning}</p>
							{/each}
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
							<Tooltip placement="right" text={t().tooltipStatsToggle}>
								<button class="stats-toggle" onclick={resultLogSettings.toggle}>
									<span class="stats-arrow" class:open={resultLogSettings.open}>▶</span>
									<span>{t().resultLogLabel}</span>
								</button>
							</Tooltip>
							{#if resultLogSettings.open}
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
										{#if interpretFallbackReason}
											<div class="stats-row">
												<span class="stats-key">{t().interpretFallbackBadge}</span>
												<span class="stats-value"><span>{t().interpretFallbackHint(interpretFallbackReason)}</span></span>
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
				title={leftPanelCollapsed ? (getLang() === 'ja' ? '記述エリアを開く' : 'Open the description area') : (getLang() === 'ja' ? '記述エリアを畳む' : 'Collapse the description area')}
				aria-label={leftPanelCollapsed ? (getLang() === 'ja' ? '記述エリアを開く' : 'Open the description area') : (getLang() === 'ja' ? '記述エリアを畳む' : 'Collapse the description area')}
				aria-expanded={!leftPanelCollapsed}
			>{leftPanelCollapsed ? '›' : '‹'}</button>

			<CanvasPanel
				{catalogName}
				{formatHistoryDate}
				{historyPreviewText}
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
				navLatestDisabled={historyNavButtonsDisabled.latest}
				navNewerDisabled={historyNavButtonsDisabled.newer}
				navOlderDisabled={historyNavButtonsDisabled.older}
				interactionLocked={demoRunning}
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
				{stageLabel}
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
				onReplayCurrent={() => {
					if (replayableStatusHistoryItem) return replayHistoryItem(replayableStatusHistoryItem, outputTab);
				}}
				replayDisabled={!replayableStatusHistoryItem || reloading}
				onDownloadSVG={downloadSVG}
				onDownloadPNG={downloadPNG}
				currentHistoryId={displayedHistoryItem?.id ?? result?.history_id ?? null}
				onDownloadCard={downloadCurrentCard}
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
				{variationGridDone}
				{variationGridTotal}
				{variationGridSlots}
				{variationGridSlotLabels}
				{variationGridStatus}
				runTokensIn={activeRunTokensIn}
				runTokensOut={activeRunTokensOut}
				variationElapsedMs={variationElapsed.ms}
				{variationTokensIn}
				{variationTokensOut}
				{modelInspection}
				bind:touchSeedText
				onGenerateVariationCandidates={generateVariationCandidates}
				onAbortVariationCandidates={abortVariationCandidates}
				onSaveSelectedVariationCandidates={saveSelectedVariationCandidates}
				onShowVariationCandidate={showVariationCandidate}
				onToggleVariationCandidate={toggleVariationCandidate}
				{activeComparisonItem}
				{lineageGraph}
				{lineageLoading}
				{lineageError}
				isJapanese={getLang() === 'ja'}
				onOpenLineageNode={openLineageNode}
				onOpenLineageNodeInCanvas={openLineageNodeInCanvas}
				onToggleLineageStar={toggleLineageStar}
				onToggleLineageForRevision={toggleLineageForRevision}
				onDrawLineageDescription={drawLineageDescriptionEdit}
				onDrawLineageDdl={drawLineageDdlEdit}
				onOpenLineageDdlEditor={openLineageDdlEditor}
				onDrawLineageSketchGrain={drawLineageSketchGrain}
				onToggleSaijiki={() => (saijikiOpen = !saijikiOpen)}
				onCloseRefinement={refreshLineageAfterRefine}
				statusDdlOrigin={statusDdlOrigin}
				statusTenkei={displayedHistoryItem?.tenkei ?? null}
				{developerMode}
				refineDrawingModelId={qualifiedModelId(stage2Provider, stage2Model)}
				refineDrawingModelGroups={availableModelCatalog}
				onSelectRefineDrawingModel={selectDdlDialogDrawingModel}
				refineWildValue={effectiveRefineWild}
				refineWildInherited={refineWildOverride === null}
				onSetRefineWild={setRefineWild}
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
				animationExportSettings={exportSettings.animation}
				{apiFetch}
			/>
		</div><!-- /body -->

			{#if uiVisibility.history}
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
			onOldestPage={gotoHistoryOldestPage}
			onLoadItem={loadIterationItem}
			onToggleStar={toggleHistoryStar}
			interactionLocked={demoRunning}
			navLatestDisabled={historyPageNavDisabled.latest}
			navNewerPageDisabled={historyPageNavDisabled.newer}
			navOlderPageDisabled={historyPageNavDisabled.older}
			navOldestDisabled={historyPageNavDisabled.oldest}
			starredFilterClearedNotice={historyStarredFilterNotice}
			{historyStarredOnly}
			onSetStarredOnly={setHistoryStarredOnly}
			{historyForRevisionOnly}
			onSetForRevisionOnly={setHistoryForRevisionOnly}
			{historyIndexLabel}
			{historyModelStage1Short}
			{historyModelStage1Full}
			{historyModelStage2Full}
			{formatHistoryDate}
			{catalogName}
			isJapanese={getLang() === 'ja'}
			{developerMode}
		/>
			{/if}
	</div><!-- /main-shell -->

</div><!-- /root -->

{#await import('$lib/components/SaijikiDrawer.svelte') then { default: SaijikiDrawer }}
	<SaijikiDrawer
		open={saijikiOpen}
		{pluginEntries}
		bind:activePreview={activeSaijikiPreview}
		onClose={() => (saijikiOpen = false)}
		previewForWord={saijikiPreview}
		previewForPlugin={pluginPreview}
	/>
{/await}

{#if ddlDialogOpen}
	{#await import('$lib/components/DdlEditorDialog.svelte') then { default: DdlEditorDialog }}
		<DdlEditorDialog
			open={ddlDialogOpen}
			isJapanese={getLang() === 'ja'}
			title={ddlDialogMode === 'new' ? t().ddlNewDialogTitle : t().ddlEditButton}
			subtitle={ddlDialogMode === 'new' ? t().ddlNewDialogSubtitle : t().ddlEditDialogSubtitle}
			initialDdl={ddlDialogInitial}
			drawing={ddlDialogDrawing}
			{stage1ModelLabel}
			{stage2ModelLabel}
			drawingModelId={qualifiedModelId(stage2Provider, stage2Model)}
			drawingModelGroups={availableModelCatalog}
			onSelectDrawingModel={selectDdlDialogDrawingModel}
			runTokensIn={activeRunTokensIn}
			runTokensOut={activeRunTokensOut}
			error={ddlDialogError}
			previewForWord={saijikiPreview}
		previewForPlugin={pluginPreview}
			{pluginEntries}
			showSettings={ddlDialogMode === 'edit'}
			wildValue={ddlDialogWildOverride ?? (ddlDialogNode?.history?.render_wild === true)}
			wildInherited={ddlDialogWildOverride === null}
			onSelectWild={(next) => (ddlDialogWildOverride = next)}
			onDraw={handleDdlDialogDraw}
			onClose={closeDdlDialog}
		/>
	{/await}
{/if}

<!-- ══ SETTINGS MODAL ══ -->
{#if settingsOpen}
	{#await import('$lib/components/SettingsModal.svelte') then { default: SettingsModal }}
		<SettingsModal
			{singleUserMode}
			{settingsMode}
			{settingsTab}
			{settingsDetail}
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
			{renderLimitsStatus}
			{currentUser}
			{uiMode}
			{uiCustom}
			{uiModeSaving}
			{uiModeSaveError}
			onSetUiMode={(mode) => void updateUiMode(mode)}
			onSetUiCustomItem={updateUiCustomItem}
			{userSettingsStatus}
			{userSettingsLoading}
			bind:loginUserName
			bind:loginPassword
			{users}
			{groups}
			bind:newUserName
			bind:newUserEmail
			bind:newUserPassword
			bind:newUserPermissionGroups
			bind:newUserGroupId
			{selectedUserId}
			bind:editUserName
			bind:editUserEmail
			bind:editUserPassword
			bind:editUserPermissionGroups
			bind:editUserGroupId
			bind:newGroupName
			bind:editGroupName
			{editGroupId}
			bind:autoRepairEnabled={ddlAutoRepairEnabled}
			bind:pngAlphaWhite={exportSettings.pngAlphaWhite}
			bind:animationExportSettings={exportSettings.animation}
			bind:cardExportSettings={exportSettings.card}
			{exportTemplates}
			{exportTemplateStatus}
			{canvasAspectEnabled}
			onSetCanvasAspectEnabled={setCanvasAspectEnabled}
			onChooseDownloadFolder={chooseDownloadFolder}
			onClearDownloadFolder={clearDownloadFolder}
			onClose={closeSettingsModal}
			onSelectSettingsTab={selectSettingsTab}
			onSetSettingsDetail={setSettingsDetail}
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
			{renderConcurrencyStatus}
			onUpdateRenderConcurrencySettings={updateRenderConcurrencySettings}
			onUpdateLogRetentionSettings={updateLogRetentionSettings}
			onUpdateRenderLimits={updateRenderLimits}
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
	{/await}
{/if}

{#if appInfoOpen}
	<div class="modal-backdrop app-info-backdrop" onclick={() => (appInfoOpen = false)} aria-hidden="true"></div>
	<div class="app-info-modal" role="dialog" aria-modal="true" aria-labelledby="app-info-title">
		<div class="app-info-head">
			<div class="app-info-brand">
				<img class="app-info-icon" src="/favicon-192.png" alt="" aria-hidden="true" />
				<div id="app-info-title" class="app-info-title">{t().appInfoTitle}</div>
			</div>
			<button class="app-info-close" onclick={() => (appInfoOpen = false)} aria-label={t().appInfoClose}>×</button>
		</div>
		<div class="app-info-body">
			<dl class="app-info-meta">
				<div class="app-info-row">
					<dt>{t().appInfoVersionLabel}</dt>
					<dd>{APP_VERSION}</dd>
					<dt>{t().appInfoBuildLabel}</dt>
					<dd>{__BUILD_NUMBER__}</dd>
					<dt>{t().appInfoBuildDateLabel}</dt>
					<dd>{buildDateLabel ?? t().historyVersionNotRecorded}</dd>
				</div>
				<!-- The three layer versions the server is running, in the same order
				     and under the same names the provenance drawer uses. -->
				<div class="app-info-row">
					<dt>Render engine version</dt>
					<dd>{currentRenderEngineVersion ?? t().historyVersionNotRecorded}</dd>
					<dt>DDL version</dt>
					<dd>{currentDdlVersion ?? t().historyVersionNotRecorded}</dd>
					<dt>DDL engine version</dt>
					<dd>{currentDdlEngineVersion ?? t().historyVersionNotRecorded}</dd>
				</div>
				<div>
					<dt>{t().appInfoRepositoryLabel}</dt>
					<dd><a href={REPOSITORY_URL} target="_blank" rel="noreferrer">{REPOSITORY_URL}</a></dd>
				</div>
			</dl>
			<section>
				<h2>{t().appInfoConceptTitle}</h2>
				<p>{t().appInfoConceptBody}</p>
			</section>
			<section>
				<h2>{t().appInfoVocabTitle}</h2>
				<p>{t().appInfoVocabIntro}</p>
				<table class="app-info-vocab">
					<thead>
						<tr>
							<th scope="col">{t().appInfoVocabColTerm}</th>
							<th scope="col">{t().appInfoVocabColMeaning}</th>
						</tr>
					</thead>
					<tbody>
						{#each t().appInfoVocabRows as row (row.term)}
							<tr>
								<th scope="row">{row.term}</th>
								<td>{row.meaning}</td>
							</tr>
						{/each}
					</tbody>
				</table>
			</section>
			<section>
				<h2>{t().appInfoCreatorTitle}</h2>
				<div class="app-info-creator">{t().appInfoCreatorName}</div>
				<p>{t().appInfoCreatorBody}</p>
			</section>
		</div>
	</div>
{/if}

{#if profileOpen && currentUser}
		{#await import('$lib/components/ProfileModal.svelte') then { default: ProfileModal }}
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
		{/await}
{/if}

<!-- ══ CATALOG MODAL ══ -->
{#if catalogOpen}
	{#await import('$lib/components/ColorCatalogModal.svelte') then { default: ColorCatalogModal }}
		<ColorCatalogModal
			catalogs={colorCatalogs}
			selectedCatalog={colorCatalogSettings.selected}
			{currentCatalog}
			onSelectCatalog={setSelectedCatalog}
			onCancel={cancelCatalogSelection}
			onConfirm={confirmCatalogSelection}
		/>
	{/await}
{/if}

<!-- ══ HISTORY MANAGER MODAL ══ -->
{#if historyManager.open}
	{#await import('$lib/components/HistoryManager.svelte') then { default: HistoryManager }}
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
			{trashTotal}
			selectedHistoryIds={historyManager.selectedIds}
			animationExportSettings={exportSettings.animation}
			cardExportSettings={exportSettings.card}
			historyManagerStarredOnly={historyManager.starredOnly}
			historyManagerForRevisionOnly={historyManager.forRevisionOnly}
			onClose={() => (historyManager.open = false)}
			onSetView={historyManager.setView}
			onSetPage={historyManager.setPage}
			onSetLatestPage={() => historyManager.setPage(0)}
			onSetFirstPage={() => historyManager.setPage(historyManager.totalPages - 1)}
			onSetPageSize={historyManager.setPageSize}
			onSetStarredOnly={historyManager.setStarredOnly}
			onSetForRevisionOnly={historyManager.setForRevisionOnly}
			onToggleForRevision={toggleHistoryForRevision}
			onSelectAll={selectAllManagedHistory}
			onAskTrash={askTrash}
			onAskRestore={askRestore}
			onAskPermanentDelete={askPermanentDelete}
			onToggleSelection={toggleHistorySelection}
			onLoadItem={loadIterationItem}
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
			isJapanese={getLang() === 'ja'}
			onShareItem={singleUserMode ? null : (item) => (shareTarget = item)}
		/>
	{/await}
{/if}

{#if shareTarget?.id}
	{#await import('$lib/components/ShareModal.svelte') then { default: ShareModal }}
		<ShareModal
			itemId={shareTarget.id}
			itemLabel={shareTarget.source_text ?? shareTarget.input ?? shareTarget.id}
			users={users.map((u) => ({ id: u.id, name: u.username }))}
			groups={groups.map((g) => ({ id: g.id, name: g.name }))}
			isJapanese={getLang() === 'ja'}
			onClose={() => (shareTarget = null)}
		/>
	{/await}
{/if}

{#if replayComparison}
	{#await import('$lib/components/ReplayComparisonModal.svelte') then { default: ReplayComparisonModal }}
		<ReplayComparisonModal
			originalSvg={replayComparison.originalSvg}
			replayedSvg={replayComparison.replayedSvg}
			recordedVersion={replayComparison.recordedVersion}
			currentVersion={replayComparison.currentVersion}
			versionMessage={replayComparison.versionMessage}
			provisionalSeed={replayComparison.provisionalSeed}
			onClose={closeReplayComparison}
		/>
	{/await}
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
		/* Tooltips keep a dark plate in both themes, so their label is one value. */
		--tooltip-fg:   #ffffff;
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
		/* Label colour for anything filled with --accent. The accent flips from a
		   dark navy to a light blue between themes, so the label has to flip too. */
		--accent-fg:    #ffffff;
		--accent-light: #e8eef5;
		--border:       #d4d0c8;
		--border2:      #c4c0b8;
		--danger:       #a2342a;
		/* Fill pair for destructive buttons. --danger itself is a text colour and
		   flips to a pale red in dark, so a filled control cannot borrow it. The
		   saturated red carries enough contrast on both themes, so — like
		   --ddl-btn-* — this pair has one value (author's ruling, 2026-07-28). */
		--danger-bg:    #c0392b;
		--danger-fg:    #ffffff;
		--r:            4px;
		--r-lg:         8px;
		/* 小型ボタン (ghost / ツールバー) の寸法。テーマに依らないので light 側にのみ置く。
		   個々のコンポーネントで px を書かず、必ずこのトークンを参照する。 */
		--btn-sm-font-size: 11px;
		--btn-sm-padding:   4px 10px;
		--btn-sm-radius:    var(--r);
		/* 指示書 (DDL) を扱うボタンの琥珀色。3 コンポーネントで同じリテラルが
		   複製されていたものをトークン化した (Build 739)。両テーマ共通。 */
		--ddl-btn-bg:           #fff7e8;
		--ddl-btn-border:       #d8b36a;
		--ddl-btn-fg:           #6c4a10;
		--ddl-btn-bg-hover:     #ffefd0;
		--ddl-btn-border-hover: #bd8f34;
		--ddl-btn-fg-hover:     #4f360b;
		--ddl-btn-shadow:       0 1px 3px rgba(108,74,16,0.12);
		/* 名前空間付きの参照のうち、このサーバーが持っていない名前の色。
		   赤 (--danger) は使わない: プラグインは後から足せるので、いま無い名前が
		   明日は有効になる。琥珀は「間違い」ではなく「まだ無い」を言う。 */
		--ddl-token-unknown-fg:     #8a5a12;
		--ddl-token-unknown-bg:     rgba(191, 136, 32, 0.12);
		--ddl-token-unknown-border: rgba(191, 136, 32, 0.42);
		/* 系譜で、起点からスター付き作品までの経路を引く色 */
		--star-path:    #d97a1f;
		/* 星を付けた状態のボタン。5 コンポーネントが同じリテラルを複製し、
		   ダークの値を持っていたのは履歴マネージャの 1 箇所だけだった。
		   その 1 箇所の値をダーク側の正本として採った。 */
		--star-fg:      #d59b21;
		--star-bg:      #fff6ce;
		--star-border:  rgba(213,155,33,0.45);
		/* サムネイルの上に浮く星の台座。下地は作品そのもの (どちらのテーマでも
		   紙の色) なので、--floating-control-* と違いテーマで反転させない。 */
		--thumb-plate-bg:     rgba(255,255,255,0.86);
		--thumb-plate-fg:     rgba(40,36,30,0.42);
		--thumb-plate-border: rgba(0,0,0,0.12);
		/* 同じ台座でも数字は読ませる必要があるので、星より濃い字の色を持つ。 */
		--thumb-plate-fg-read: rgba(40,36,30,0.72);
	}

	/* Shared controls are global because Svelte scopes component styles. */
	:global(.ghost-btn) {
		padding: var(--btn-sm-padding);
		border: 1px solid var(--border2);
		border-radius: var(--btn-sm-radius);
		background: var(--panel);
		color: var(--fg2);
		font-family: inherit;
		font-size: var(--btn-sm-font-size);
		cursor: pointer;
	}
	:global(.ghost-btn:hover:not(:disabled)) { background: var(--bg2); }
	:global(.ghost-btn:disabled) { opacity: 0.55; cursor: not-allowed; }
	:global(.ghost-btn.ghost-active) {
		background: var(--action-bg);
		color: var(--action-fg);
		border-color: var(--action-bg);
	}
	:global(.saijiki-chip.plugin-chip) {
		color: var(--accent);
		border-color: var(--accent);
		background: var(--accent-light);
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
		--accent-fg:    #11151a;
		--accent-light: #253246;
		--border:       #38342f;
		--border2:      #514b43;
		--danger:       #ff9a86;
		--ddl-token-unknown-fg:     #f0c368;
		--ddl-token-unknown-bg:     rgba(191, 136, 32, 0.26);
		--ddl-token-unknown-border: rgba(240, 195, 104, 0.48);
		--star-path:    #f0a44f;
		--star-fg:      #ffd166;
		--star-bg:      rgba(213,155,33,0.18);
		--star-border:  rgba(255,209,102,0.55);
	}

	/* UI modes change visibility only. The underlying features and saved work stay intact. */
	.ui-hide-input-modes :global(.panel-tabs),
	.ui-hide-drawing-settings :global(.section-head),
	.ui-hide-drawing-settings :global(.current-selection),
	.ui-hide-drawing-settings :global(.input-label .tooltip-wrap),
	.ui-hide-ddl-tools .ddl-tools-section,
	.ui-hide-ddl-tools :global(.ddl-viewer),
	.ui-hide-ddl-tools .interpretation-diff,
	.ui-hide-detail-status .thinking-details,
	.ui-hide-detail-status .stats-section,
	.ui-hide-detail-status :global(.render-meta-strip),
	.ui-hide-detail-status :global(.status-hash-btn),
	.ui-hide-detail-status :global(.provenance-button),
	.ui-hide-work-tools :global(.right-tabs),
	.ui-hide-work-tools :global(.canvas-corner-controls),
	.ui-hide-work-tools :global(.zoom-controls),
	.ui-hide-work-tools :global(.status-star),
	.ui-hide-work-tools :global(.replay-button),
	.ui-hide-work-tools :global(.saijiki-open-btn),
	.ui-hide-work-tools :global(.png-wrap),
	.ui-hide-history :global(.nav-left),
	.ui-hide-history :global(.nav-right),
	.ui-hide-history :global(.nearby-mirror) {
		display: none;
	}
	.tooltips-disabled :global(.tooltip-bubble) {
		display: none;
	}

	/* DDL token palette (v1.98): one definition for every surface that renders
	   highlighted DDL — interpretation view, batch observer, demo observer,
	   DDL editor dialog. Previously each component carried its own copy and
	   only some had dark-theme values. */
	:global(.ddl-token) { border-radius: 2px; font-weight: inherit; }
	:global(.ddl-token-shape) { color: #2c5fb8; background: rgba(44, 95, 184, 0.08); }
	:global(.ddl-token-touch) { color: #7a5b2f; background: rgba(122, 91, 47, 0.10); }
	:global(.ddl-token-line) { color: #53606b; background: rgba(83, 96, 107, 0.10); }
	:global(.ddl-token-color) { color: #b12a6b; background: rgba(177, 42, 107, 0.09); }
	:global(.ddl-token-motion) { color: #197a74; background: rgba(25, 122, 116, 0.10); }
	:global(.ddl-token-place) { color: #6b4cb3; background: rgba(107, 76, 179, 0.09); }
	:global(.ddl-token-action) { color: #9a4a1d; background: rgba(154, 74, 29, 0.10); }
	:global(.ddl-token-angle) { color: #3d6f2c; background: rgba(61, 111, 44, 0.10); }
	:global(.ddl-token-ratio) { color: #9a3d3d; background: rgba(154, 61, 61, 0.09); }
	:global(.ddl-token-plugin) { color: #9f4b3b; background: rgba(185, 88, 69, 0.10); }
	/* A namespaced name this server does not hold. It takes its colour from the
	   :root pair so the editor's strip below the text can say the same thing in
	   the same amber, in both themes. */
	:global(.ddl-token-unknown) {
		color: var(--ddl-token-unknown-fg);
		background: var(--ddl-token-unknown-bg);
		text-decoration: underline wavy var(--ddl-token-unknown-border);
		text-underline-offset: 3px;
	}
	:global(.ddl-token-word) { color: #2c3e91; background: rgba(44, 62, 145, 0.08); }
	:global(.ddl-token-emotion) { color: #9b7a66; font-style: inherit; }
	:global(html[data-theme='dark'] .ddl-token-shape) { color: #9cc4ff; background: rgba(92, 143, 220, 0.26); }
	:global(html[data-theme='dark'] .ddl-token-touch) { color: #e2bf82; background: rgba(188, 139, 62, 0.24); }
	:global(html[data-theme='dark'] .ddl-token-line) { color: #c4ccd5; background: rgba(147, 160, 176, 0.22); }
	:global(html[data-theme='dark'] .ddl-token-color) { color: #ff91c7; background: rgba(215, 80, 149, 0.24); }
	:global(html[data-theme='dark'] .ddl-token-motion) { color: #7ce1d4; background: rgba(50, 157, 147, 0.24); }
	:global(html[data-theme='dark'] .ddl-token-place) { color: #c2a9ff; background: rgba(133, 99, 214, 0.26); }
	:global(html[data-theme='dark'] .ddl-token-action) { color: #f0aa73; background: rgba(197, 105, 45, 0.24); }
	:global(html[data-theme='dark'] .ddl-token-angle) { color: #a7d88e; background: rgba(89, 142, 65, 0.25); }
	:global(html[data-theme='dark'] .ddl-token-ratio) { color: #f0a0a0; background: rgba(196, 78, 78, 0.24); }
	:global(html[data-theme='dark'] .ddl-token-plugin) { color: #f0a58f; background: rgba(185, 88, 69, 0.26); }
	:global(html[data-theme='dark'] .ddl-token-word) { color: #b8c7ff; background: rgba(92, 111, 205, 0.26); }
	:global(html[data-theme='dark'] .ddl-token-emotion) { color: #d8b8a6; }

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
	.ddl-tools-section { flex-direction: row; justify-content: flex-end; gap: 6px; }
	.ddl-new-btn {
		padding: var(--btn-sm-padding);
		border: 1px solid var(--ddl-btn-border);
		border-radius: var(--btn-sm-radius);
		background: var(--ddl-btn-bg);
		color: var(--ddl-btn-fg);
		font-family: inherit;
		font-size: var(--btn-sm-font-size);
		font-weight: 600;
		box-shadow: var(--ddl-btn-shadow);
		white-space: nowrap;
		cursor: pointer;
	}
	.ddl-new-btn:hover:not(:disabled) { background: var(--ddl-btn-bg-hover); border-color: var(--ddl-btn-border-hover); color: var(--ddl-btn-fg-hover); }
	.ddl-new-btn:disabled { opacity: 0.45; cursor: not-allowed; }

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
		width: min(780px, calc(100vw - 32px));
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
	.app-info-brand {
		display: flex;
		align-items: center;
		gap: 10px;
		min-width: 0;
	}
	.app-info-icon {
		width: 32px;
		height: 32px;
		object-fit: contain;
		flex: 0 0 auto;
	}
	.app-info-title {
		font-size: 24px;
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
	/* A row that carries several label/value pairs on one line, rather than one
	   pair per grid row. It spans both columns and wraps on a narrow window. */
	.app-info-meta .app-info-row {
		display: flex;
		flex-wrap: wrap;
		align-items: baseline;
		gap: 2px 14px;
		grid-column: 1 / -1;
	}
	.app-info-meta .app-info-row dd {
		margin-right: 4px;
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
	.app-info-vocab {
		width: 100%;
		border-collapse: collapse;
		font-size: 12px;
		line-height: 1.6;
	}
	.app-info-vocab th,
	.app-info-vocab td {
		padding: 5px 10px 5px 0;
		text-align: left;
		vertical-align: top;
		border-bottom: 1px solid var(--border);
	}
	.app-info-vocab thead th {
		color: var(--fg3);
		font-weight: 500;
		white-space: nowrap;
	}
	.app-info-vocab tbody th {
		color: var(--fg);
		font-weight: 500;
		white-space: nowrap;
		padding-right: 16px;
	}
	.app-info-vocab tbody td {
		color: var(--fg2);
		min-width: 0;
	}
	.app-info-vocab tbody tr:last-child th,
	.app-info-vocab tbody tr:last-child td {
		border-bottom: none;
	}

	/* 写生 (Stage 0.5). Reads as prose, not as code: the instructions below it
	   are monospace because they are a score, this is the author's own language. */
	.sketch-section { display: grid; gap: 6px; }
	.sketch-head { display: flex; align-items: center; gap: 8px; }
	.sketch-title { font-size: 11px; color: var(--fg3); }
	/* Matches the expanded-DDL toggle: the two folds in this panel are one
	   control repeated, so they read and behave the same. */
	.sketch-toggle {
		display: flex;
		align-items: center;
		gap: 5px;
		padding: 2px 0;
		border: 0;
		background: none;
		color: var(--fg3);
		font-family: inherit;
		cursor: pointer;
		text-align: left;
	}
	.sketch-arrow {
		display: inline-block;
		font-size: 8px;
		transition: transform 0.15s ease;
	}
	.sketch-arrow.open { transform: rotate(90deg); }
	.sketch-grain { font-size: 11px; color: var(--fg3); margin-left: auto; }
	.sketch-edit-btn {
		padding: var(--btn-sm-padding);
		border: 1px solid var(--border2);
		border-radius: var(--btn-sm-radius);
		background: var(--panel);
		color: var(--fg2);
		font-family: inherit;
		font-size: var(--btn-sm-font-size);
		cursor: pointer;
	}
	.sketch-edit-btn:hover { background: var(--bg2); }
	.sketch-body, .sketch-editor {
		padding: 8px 10px;
		border: 1px solid var(--border);
		background: color-mix(in srgb, var(--bg2) 68%, transparent);
		font-size: 12px;
		line-height: 1.7;
		color: var(--fg2);
		white-space: pre-wrap;
		margin: 0;
	}
	.sketch-editor { font-family: inherit; width: 100%; resize: vertical; }
	.sketch-note { margin: 0; font-size: 11px; color: var(--fg3); }

	/* The same amber as the editor's mark: one meaning, one colour. */
	.plugin-warnings {
		border: 1px solid var(--ddl-token-unknown-border);
		background: var(--ddl-token-unknown-bg);
	}
	.plugin-warnings-title {
		color: var(--ddl-token-unknown-fg);
		font-size: 11px;
		font-weight: 500;
		margin-bottom: 4px;
	}
	.plugin-warning-line {
		color: var(--fg2);
		font-size: 11px;
		line-height: 1.5;
		word-break: break-word;
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

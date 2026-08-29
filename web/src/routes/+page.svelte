<script module lang="ts">
	declare const __APP_VERSION__: string;
	declare const __BUILD_NUMBER__: string;
	declare const __BUILD_DATE__: string;
</script>

<script lang="ts">
	import { onMount, untrack } from 'svelte';
	import { pipelineDescription } from '$lib/description-labels';
	import { highlightDDL } from '$lib/highlight';
	import { pluginWarningsToShow } from '$lib/plugin-names';
	import { limitNotesToShow } from '$lib/limitNotes';
	import { hydrateSaijiki, hydrateSaijikiEn } from '$lib/saijiki';
	import { SURFACE_PREVIEWS, localizePreview, shapeSvg, type PreviewEntry } from '$lib/saijiki-surface';
	import { instructionLangOf, type ResolvedInstructionLang } from '$lib/instructionLang';
	import AppRail from '$lib/components/AppRail.svelte';
	import AuthPanel from '$lib/components/AuthPanel.svelte';
	import CanvasPanel from '$lib/components/CanvasPanel.svelte';
	import { CanvasViewportState } from '$lib/features/canvas/viewport-state.svelte';
	import { createRefinementCoordinator } from '$lib/features/canvas/refinement-coordinator.svelte';
	import { RefinementSessionState } from '$lib/features/canvas/refinement-session.svelte';
	import { LineageQueryState } from '$lib/features/history/lineage-state.svelte';
	import type { LineageNode } from '$lib/features/history/types';
	import ConfirmDialog from '$lib/components/ConfirmDialog.svelte';
	import { DEFAULT_SKETCH_MODE, normalizeSketchGrain, normalizeSketchState, sketchGrainOf, sketchModeLabel, sketchModeOf, sketchStateNote, type SketchMode, type SketchState } from '$lib/sketch';
	import { composeFallbackReason, composeFallbackState, composeFallbackValue } from '$lib/composeFallback';
	import { needsFallbackRefineConfirm, rememberFallbackRefineConfirm, type FallbackRefineParent } from '$lib/fallbackRefineGate';
	import { submitDerivationKind as submitDerivationKindOf, type DerivationKind } from '$lib/derivation';
	import DdlViewer from '$lib/components/DdlViewer.svelte';
	import HistoryStrip from '$lib/components/HistoryStrip.svelte';
	import InputPanel from '$lib/components/InputPanel.svelte';
	import RunStatus from '$lib/components/RunStatus.svelte';
	import Tooltip from '$lib/components/Tooltip.svelte';
	import { toggleHistoryStripField, type HistoryStripField } from '$lib/historyStripFields';
	import {
		PROVIDER_GROUPS,
		DEFAULT_PROVIDER,
		DEFAULT_MODEL,
		modelsForProvider,
		modelDisplayName,
		modelShortName,
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
	import { createElapsed } from '$lib/elapsed.svelte';
	import { createApiFetch } from '$lib/transport/api-fetch';
	import { createSessionState, type UserItem, type UserModelSettings } from '$lib/features/session/state.svelte';
	import { createWorkState } from '$lib/features/work/state.svelte';
	import { createSettingsController } from '$lib/features/settings/state.svelte';
	import { DEFAULT_EXPORT_TEMPLATES, normalizeExportTemplates, type ExportTemplate } from '$lib/exportTemplates';
	// Persisted settings: one feature, one file.  Adding a setting must not send
	// every branch back into this file -- see lib/features/*/settings.svelte.ts.
	import { bindColorCatalogPersist, colorCatalogSettings } from '$lib/features/color-catalog/settings.svelte';
	import { bindDescribePanelPersist, describePanelSettings } from '$lib/features/describe-panel/settings.svelte';
	import { bindColorCatalogFallback } from '$lib/features/color-catalog/render';
	import { AUTO_CATALOG_ID, colorCatalogOverride } from '$lib/features/color-catalog/render';
	import { renderSettingsPayload } from '$lib/features/render-payload';
	import {
		runCurrentWork,
		type InstructionLang,
		type PaintOptions,
		type PaintResult
	} from '$lib/features/run/current-work';
	import { loadPersistedSettings } from '$lib/features/persisted-settings';
	import { applyUserSettings, collectUserSettings } from '$lib/features/user-settings';
	import { batchSettings } from '$lib/features/batch/settings.svelte';
	import { BatchState } from '$lib/features/batch/state.svelte';
	import { DemoState } from '$lib/features/demo/state.svelte';
	import type { BatchRunConditions, NumberedLine } from '$lib/features/batch/resume';
	import { wildSettings } from '$lib/features/wild/settings.svelte';
	import { wildOverride } from '$lib/features/wild/render';
	import { exportSettings } from '$lib/features/export/settings.svelte';
	import { downloadCard } from '$lib/cardExport';
	import { createExportActions } from '$lib/features/export/download';
	import { createModelInspection } from '$lib/features/model-inspection/state.svelte';
	import { resultLogSettings } from '$lib/features/result-log/settings.svelte';
	import { batchFailureReportStore } from '$lib/features/batch/failure-report.svelte';
	import {
		CANVAS_ASPECT_PLUGIN_ID,
		DEFAULT_CANVAS_ASPECT_ID,
		getCanvasAspectOption,
		normalizeCanvasAspectId,
		type CanvasAspectId,
	} from '$lib/plugins/system/canvas-aspect';
	import {
		type HistoryItem,
		type Score
	} from '$lib/historyManagerState.svelte';
	import {
		HISTORY_EXTERNAL_REFRESH_MS,
		HistoryBrowsingState,
		type HistoryStarProjection
	} from '$lib/features/history/browsing-state.svelte';
	import { HistoryMutations } from '$lib/features/history/mutations';
	import { saveHistoryItem, type SaveHistoryOptions } from '$lib/features/history/save';
	import {
		replayHistoryItem as replaySavedHistoryItem,
		type ReplayComparison,
		type ReplaySource
	} from '$lib/features/history/replay';
	import { projectHistoryCurrentWork } from '$lib/features/history/current-work';
	import {
		focusSavedLineageChild,
		promoteLineageNode as promoteSavedLineageNode,
		saveLineageNote as saveSavedLineageNote
	} from '$lib/features/history/lineage-actions';
	import { hashDigest } from '$lib/hashIdentity';
	import { setThumbnailHidpi } from '$lib/thumbnailSource';

	const PROVIDER_STAGE1_KEY = 'inku-provider-stage1';
	const MODEL_STAGE1_KEY    = 'inku-model-stage1';
	const PROVIDER_STAGE2_KEY = 'inku-provider-stage2';
	const MODEL_STAGE2_KEY    = 'inku-model-stage2';
	const DEFAULT_VISION_MODEL = 'meta/llama-3.2-90b-vision-instruct';
	// Injected by vite.config from web/APP_VERSION, the single source shared with
	// the server (/api/info) and the CLI. Never write the version here again.
	const APP_VERSION = __APP_VERSION__;
	const REPOSITORY_URL = 'https://github.com/oikawas/inku-lang';
	// vite.config embeds BUILD_NUMBER's mtime. Treat an unreadable value as null.
	const buildDateLabel = $derived.by(() => {
		const stamp = new Date(__BUILD_DATE__);
		if (Number.isNaN(stamp.getTime())) return null;
		return stamp.toLocaleString(getLang() === 'ja' ? 'ja-JP' : 'en-US', { dateStyle: 'medium', timeStyle: 'short' });
	});
	type Iteration = HistoryItem;
	type BatchPaintResult = PaintResult & { ddl: string; thinking: string | null };

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
	type CopyKind = 'stage1' | 'stage2' | 'score';
	let copiedPrompt = $state<CopyKind | null>(null);
	let statusHashCopied = $state(false);
	let previousInputMode = $state<'single' | 'batch' | 'demo'>('single');
	type DdlDiffPart = { kind: "same" | "removed" | "added"; text: string };
	type TextDiffPart = { kind: "same" | "removed" | "added"; text: string };
	const refinementSession = new RefinementSessionState();
	let interpretationDiffParts = $state<DdlDiffPart[]>([]);
	let lineageIntermediateNotice = $state<string | null>(null);
	let lineageIntermediateNoticeTimer: number | null = null;
	let historyStarredFilterNotice = $state<string | null>(null);
	let historyStarredFilterNoticeTimer: number | null = null;

	// ── UI ──────────────────────────────────────────────────
	let windowWidth  = $state(1200);
	let windowHeight = $state(800);
	let saijikiOpen  = $state(false);
	let activeSaijikiPreview = $state<SaijikiPreview | null>(null);
	// DDL editor dialog (new / edit), shared by the Description-tab new button and lineage card menu.
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
	let exportMenuOpen = $state(false);
	let userMenuOpen = $state(false);
	let catalogOpen  = $state(false);
	let canvasAspectMenuOpen = $state(false);
	let canvasAspectEnabled = $state(true);
	let canvasAspectId = $state<CanvasAspectId>(DEFAULT_CANVAS_ASPECT_ID);
	let catalogSelectionSnapshot = $state<string | null>(null);
	let instructionCaptionVisible = $state(true);
	let outputTab    = $state<'canvas' | 'refine' | 'lineage'>('canvas');
	const canvasViewport = new CanvasViewportState();
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
	// The Server config supplies the candidate-grid cap so it tracks render slots;
	// apiFetch handles 503 retries when other work temporarily occupies a slot.
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
	let exportWrapEl   = $state<HTMLDivElement | null>(null);
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
	function saijikiPreview(categoryKey: string, canonicalWord: string, word: string, wordLang: ResolvedInstructionLang): SaijikiPreview {
		const uiLang = instructionLangOf(getLang());
		const base = {
			categoryKey,
			word,
			canonicalWord,
			effect: '',
			example: '',
			svg: '',
		};
		// The effect is prose for the reader and the example is a fragment of
		// DDL, so the two do not follow the same language when the DDL is not in
		// the UI's -- see localizePreview.
		const localized = (entry: PreviewEntry) => ({
			...localizePreview(entry, { uiLang, wordLang }),
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
			// Surface: eleven words, one contour, eleven interiors (saijiki-surface.ts).
			...SURFACE_PREVIEWS,
			白: { effect: '白系の色で描く。背景との対比に注意。', example: '白い円', effectEn: 'Draws in a white tone. Mind the contrast against the ground.', exampleEn: 'A white circle', svg: shapeSvg('<rect x="48" y="18" width="84" height="56" fill="#2b2b2b" opacity="0.16"/><circle cx="90" cy="46" r="24" fill="#ffffff" stroke="#c9c2b5" stroke-width="4"/>') },
			黒: { effect: '黒で描く。最も強い輪郭になる。', example: '黒い円', effectEn: 'Draws in black, giving the strongest contour.', exampleEn: 'A black circle', svg: shapeSvg('<circle cx="90" cy="46" r="25" fill="#2b2b2b"/>') },
			青: { effect: '青系の色で描く。', example: '青い線', effectEn: 'Draws in a blue tone.', exampleEn: 'A blue line', svg: lineSvg('', 5, 'round', '#2c5fb8') },
			赤: { effect: '赤系の色で描く。', example: '赤い三角', effectEn: 'Draws in a red tone.', exampleEn: 'A red triangle', svg: shapeSvg('<path d="M90 20 L132 70 L48 70 Z" fill="none" stroke="#c9362d" stroke-width="6" stroke-linejoin="round"/>') },
			緑: { effect: '緑系の色で描く。', example: '緑の点を散らす', effectEn: 'Draws in a green tone.', exampleEn: 'Scatter green dots', svg: scatter.replaceAll('#2b2b2b', '#2f8a4b') },
			灰: { effect: '灰色で描く。弱い輪郭や背景に向く。', example: '灰色の四角', effectEn: 'Draws in gray. Suits weak contours and grounds.', exampleEn: 'A gray square', svg: shapeSvg('<rect x="58" y="24" width="64" height="44" fill="none" stroke="#777777" stroke-width="6" rx="2"/>') },
			黄: { effect: '黄色系の色で描く。', example: '黄色い円', effectEn: 'Draws in a yellow tone.', exampleEn: 'A yellow circle', svg: shapeSvg('<circle cx="90" cy="46" r="25" fill="#d8a51d"/>') },
			橙: { effect: '橙色系の色で描く。', example: '橙色の楕円', effectEn: 'Draws in an orange tone.', exampleEn: 'An orange ellipse', svg: shapeSvg('<ellipse cx="90" cy="46" rx="38" ry="22" fill="#d66a28"/>') },
			紫: { effect: '紫系の色で描く。', example: '紫の三角', effectEn: 'Draws in a purple tone.', exampleEn: 'A purple triangle', svg: shapeSvg('<path d="M90 20 L132 70 L48 70 Z" fill="#7650a6"/>') },
			細かく: { effect: '小さな揺らぎを加える。', example: '細かく揺れる線', effectEn: 'Adds a small-amplitude sway.', exampleEn: 'A finely swaying line', svg: lineSvg() },
			大きく: { effect: '振幅の大きな揺らぎを加える。', example: '大きく波打つ線', effectEn: 'Adds a large-amplitude sway.', exampleEn: 'A largely undulating line', svg: shapeSvg('<path d="M20 48 C42 8 64 84 88 48 S134 8 160 48" fill="none" stroke="#2b2b2b" stroke-width="5" stroke-linecap="round"/>') },
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
			...localizePreview(
				{
					effect: '記述の解釈に影響する語彙です。',
					effectEn: 'A vocabulary word that shapes how the description is read.',
					example: `${word}を使う`,
					exampleEn: `Use "${word}"`,
				},
				{ uiLang, wordLang }
			),
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
	}, wordLang: ResolvedInstructionLang): SaijikiPreview {
		const uiLang = instructionLangOf(getLang());
		// The note explains the word, so it is the reader's language; the firing
		// phrase is what a description would say to reach it, so it is the DDL's.
		const firesOn = (wordLang === 'ja' ? entry.fires_on_ja : entry.fires_on_en) ?? [];
		return {
			categoryKey: 'plugin',
			word: entry.qualified_name,
			canonicalWord: entry.qualified_name,
			effect: (uiLang === 'ja' ? entry.note_ja : entry.note_en) || '',
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
	let pluginEntries = $state<PluginEntry[]>([]);
	let availableModelCatalog = $state<ProviderGroup[]>(PROVIDER_GROUPS.filter((group) => group.id !== 'nvidia'));
	let availableVisionModelCatalog = $state<ProviderGroup[]>([]);
	let availableModelsLoaded = $state(false);
	// Teach models.ts which providers this server serves, so that a reference
	// qualified with an operator-added provider is recognised as qualified.
	$effect(() => {
		registerModelCatalog(settings.modelCatalog);
		registerModelCatalog(availableModelCatalog);
		registerModelCatalog(availableVisionModelCatalog);
	});

	type ProviderFailure = {
		code: 'model_gone' | 'provider_auth' | 'provider_rate_limit' | 'provider_error';
		stage: string;
		provider_status: number;
		message: string;
	};

	/**
	 * v1.98: Turn a Server failure detail into one human-readable line.
	 * Provider failures (retirement, authentication, and rate limiting) lead
	 * with their category and retain the provider's original message for diagnosis.
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

	const apiFetch = createApiFetch();
	const session = createSessionState({
		apiFetch,
		describeApiError,
		applyModelSettings: applyUserModelSettings,
		afterAuthenticated: completeAuthentication,
		afterSignedOut: resetAfterSignedOut,
		refreshUserAdministration: () => settings.userAdministration.load(),
		onVisibilityChanged: (visibility) => {
			if (!visibility.input_modes) work.inputMode = 'single';
			if (!visibility.work_tools) outputTab = 'canvas';
		}
	});
	const batch = new BatchState<BatchPaintResult, Iteration>({
		apiFetch,
		signedIn: () => session.currentUser !== null,
		paintable: (text) => !!pipelineDescription(text).trim(),
		setFailureReport: batchFailureReportStore.set,
		describeApiError,
	});
	const demo = new DemoState({
		apiFetch,
		signedIn: () => session.currentUser !== null,
		instructionLang: () => work.instructionLang,
		uiLang: getLang,
		describeApiError,
	});
	const lineageState = new LineageQueryState(apiFetch);
	const work = createWorkState({
		apiFetch,
		describeApiError,
		session,
		batch,
		demo,
		refinementSession,
		history: () => history,
		lineageState,
		canvasViewport,
		models: {
			stage1Provider: () => stage1Provider,
			stage1Model: () => stage1Model,
			stage2Provider: () => stage2Provider,
			stage2Model: () => stage2Model,
			includeThinking: () => includeThinking,
			available: () => availableModelCatalog
		},
		canvasAspectId: effectiveCanvasAspectId,
		resetTargetScopedState,
		ensureVisibleLineageParentId,
		showCanvas: () => { outputTab = 'canvas'; },
		requestConfirmation: (confirmation) => { confirmAction = confirmation; },
		displayLatestBatchRender,
		pushHistory
	});
	const settings = createSettingsController({
		apiFetch,
		currentUser: () => session.currentUser,
		setCurrentUser: (actor) => session.setCurrentUser(actor),
		loadAvailableModels,
		refreshCurrentUserSettings: () => session.refreshCurrentUserSettings(),
		loadExportTemplates,
		cancelModelSelection: restoreModelSelection,
		requestConfirmation: (confirmation) => { confirmAction = confirmation; },
		setRenderFanoutLimit: (limit) => { renderFanoutLimit = limit; },
		describeApiError
	});

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

	function modelsFor(provider: Provider) {
		const group = availableModelCatalog.find((item) => item.id === provider);
		if (group) return group.models;
		return availableModelsLoaded ? [] : modelsForProvider(provider);
	}

	function visionModelsFor(provider: Provider) {
		return availableVisionModelCatalog.find((group) => group.id === provider)?.models ?? [];
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
		if (!session.currentUser) return;
		try {
			const r = await apiFetch('/api/auth/me/settings', { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ model_settings: { instruction_caption_visible: visible } }) });
			if (!r.ok) throw new Error(`HTTP ${r.status}`);
			session.setCurrentUser(await r.json() as UserItem);
		} catch (e) { console.warn('failed to save instruction caption setting', e); }
	}

	async function persistOkugakiModel(provider: Provider, model: string): Promise<void> {
		const nextModel = qualifiedModelId(provider, model.trim());
		if (!nextModel || nextModel === okugakiModel) return;
		const previous = okugakiModel;
		okugakiModel = nextModel;
		if (!session.currentUser) return;
		try {
			const r = await apiFetch('/api/auth/me/settings', {
				method: 'PATCH',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ model_settings: { okugaki_provider: provider, okugaki_model: model.trim() } })
			});
			if (!r.ok) throw new Error(`HTTP ${r.status}`);
			session.setCurrentUser(await r.json() as UserItem);
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
		if (!session.currentUser) return;
		try {
			const r = await apiFetch('/api/auth/me/settings', {
				method: 'PATCH',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ model_settings: { vision_provider: provider, vision_model: model } })
			});
			if (!r.ok) throw new Error(`HTTP ${r.status}`);
			session.setCurrentUser(await r.json() as UserItem);
		} catch (e) {
			visionProvider = prevProvider;
			visionModel = prevModel;
			console.warn('failed to save vision model', e);
			throw e;
		}
	}

	/** Put back the conditions the last work of the stopped run was drawn under. */
	function applyBatchRunConditions(conditions: BatchRunConditions) {
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
		work.sketchMode = sketchModeOf(conditions.sketchGrain);
		if (conditions.wild !== null) wildSettings.set(conditions.wild);
		if (conditions.canvasAspectId) canvasAspectId = normalizeCanvasAspectId(conditions.canvasAspectId);
	}

	async function resumeInterruptedBatch() {
		try {
			await batch.resumeInterrupted({
				blocked: () => work.loading || refinementSession.gridBusy,
				applyConditions: applyBatchRunConditions,
				run: (lines) => work.submit({ resumeLines: lines }),
			});
		} catch (e) {
			work.error = e instanceof Error ? e.message : String(e);
		}
	}

	async function loadPluginStorage() {
		if (!session.currentUser) {
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
		if (!session.currentUser) return;
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
		if (!session.isAdmin) return;
		canvasAspectEnabled = value;
		canvasAspectMenuOpen = false;
		if (!value) {
			work.result = null;
			work.displayedHistoryItem = null;
			history.clearSelection();
			outputTab = 'canvas';
			exportMenuOpen = false;
			canvasViewport.fit();
		}
		await saveCanvasAspectPluginValue();
	}

	async function selectCanvasAspect(id: CanvasAspectId) {
		if (!session.isAdmin) return;
		const nextAspectId = normalizeCanvasAspectId(id);
		const currentAspectId = effectiveCanvasAspectId();
		canvasAspectMenuOpen = false;
		if (nextAspectId === currentAspectId) {
			await saveCanvasAspectPluginValue();
			return;
		}
		const existingPending = work.pendingCanvasAspectDerivation;
		const parentNodeId = existingPending?.parentNodeId ?? await ensureVisibleLineageParentId();
		work.pendingCanvasAspectDerivation = parentNodeId
			? { parentNodeId, fromAspectId: existingPending?.fromAspectId ?? currentAspectId, toAspectId: nextAspectId }
			: null;
		canvasAspectId = nextAspectId;
		work.result = null;
		work.displayedHistoryItem = null;
		history.clearSelection();
		outputTab = 'canvas';
		exportMenuOpen = false;
		canvasViewport.fit();
		await saveCanvasAspectPluginValue();
	}

	async function loadExportTemplates() {
		if (!session.currentUser) {
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
		if (!session.currentUser) return;
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

	function openModelSelection(allowVision = true) {
		modelSelectionAllowVision = allowVision;
		modelSelectionSnapshot = { stage1Provider, stage1Model, stage2Provider, stage2Model, visionProvider, visionModel };
		settings.openModelSelection();
	}

	async function persistModelSelection() {
		if (!session.currentUser) return;
		const previousUser = session.currentUser;
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
			const actor = await r.json() as UserItem;
			session.setCurrentUser(actor);
			applyUserModelSettings(actor);
		} catch (e) {
			session.setCurrentUser(previousUser);
			console.warn('failed to update model selection', e);
		}
	}

	async function confirmModelSelection() {
		modelSelectionSnapshot = null;
		await persistModelSelection();
		settings.finishModelSelection();
	}

	function restoreModelSelection() {
		if (modelSelectionSnapshot) {
			stage1Provider = modelSelectionSnapshot.stage1Provider;
			stage1Model = modelSelectionSnapshot.stage1Model;
			stage2Provider = modelSelectionSnapshot.stage2Provider;
			stage2Model = modelSelectionSnapshot.stage2Model;
			visionProvider = modelSelectionSnapshot.visionProvider;
			visionModel = modelSelectionSnapshot.visionModel;
		}
		modelSelectionSnapshot = null;
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
		if (!session.currentUser) return;
		try {
			const r = await apiFetch('/api/auth/me/settings', { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ model_settings: { color_catalog_id: selected } }) });
			if (!r.ok) throw new Error(`HTTP ${r.status}`);
			session.setCurrentUser(await r.json() as UserItem);
		} catch (e) { console.warn('failed to save color catalog selection', e); }
	}
	bindColorCatalogPersist((selected) => { void persistColorCatalogSelection(selected); });

	// The folds ride in the user's model_settings for the same reason the
	// catalogue does: neither section has anything to show without a session.
	// A failed save leaves the fold as the user just set it -- it is a view
	// state, and refolding it under them would be worse than forgetting it.
	async function persistDescribePanelFolds(fields: Record<string, boolean>) {
		if (!session.currentUser) return;
		try {
			const r = await apiFetch('/api/auth/me/settings', { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ model_settings: fields }) });
			if (!r.ok) throw new Error(`HTTP ${r.status}`);
			session.setCurrentUser(await r.json() as UserItem);
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

	async function loadAvailableModels() {
		if (!session.currentUser) {
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
				applyUserModelSettings({ ...session.currentUser, model_settings: data.settings.model_settings });
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
			demo.reconcilePromptModel(availableModelCatalog, availableModelsLoaded);
		} catch (e) {
			console.warn('failed to load model catalog', e);
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

	async function completeAuthentication(source: 'resume' | 'login'): Promise<void> {
		if (source === 'login') history.clear();
		await Promise.all([
			loadAvailableModels(),
			settings.userAdministration.load(),
			settings.loadStatus(),
			batch.loadPromptHistory(),
			demo.loadSettings(),
			loadPluginStorage(),
			loadPluginVocabulary(),
			loadExportTemplates(),
			loadClientConfig(),
			...(source === 'login' ? [loadColorCatalogs(), fetchPrompts()] : [])
		]);
		demo.reconcilePromptModel(availableModelCatalog, availableModelsLoaded);
		await Promise.all([history.fetchOffset(0), history.fetchTrashPage()]);
		if (historyItems.length > 0) loadIteration(0);
	}

	function resetAfterSignedOut(): void {
		userMenuOpen = false;
		batch.clearPromptHistory();
		demo.resetForSignedOut();
		exportTemplates = DEFAULT_EXPORT_TEMPLATES.map((item) => ({ ...item }));
		exportTemplateStatus = null;
		canvasAspectEnabled = true;
		canvasAspectId = DEFAULT_CANVAS_ASPECT_ID;
		settings.resetForLoggedOut();
		history.clear();
	}

	// ── Export filenames ────────────────────────────────────
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
	let currentResultStarState = $state<HistoryStarProjection | null>(null);
	$effect(() => {
		const historyId = work.displayedHistoryItem?.id ?? work.result?.history_id ?? null;
		void lineageState.loadNearby(historyId);
	});
	const visibleThumbCount = $derived(Math.max(1, Math.floor((windowWidth - 40) / 89)));
	const history = new HistoryBrowsingState({
		apiFetch,
		signedIn: () => !!session.authToken,
		drawing: () => work.loading,
		visible: () => document.visibilityState === 'visible',
		navigationLocked: () => demoRunning,
		currentHistoryId: () => work.displayedHistoryItem?.id ?? work.result?.history_id ?? null,
		currentItem: () => work.displayedHistoryItem,
		managerPageSize: estimatedHistoryManagerPageSize,
		onStarredFilterCleared: showHistoryStarredFilterClearedNotice,
		onOtherFilterCleared: showHistoryForRevisionFilterClearedNotice
	});
	const historyManager = history.manager;
	const historyMutations = new HistoryMutations({
		apiFetch,
		signedIn: () => !!session.authToken,
		browsing: history,
		currentItem: () => work.displayedHistoryItem,
		setCurrentItem: (item) => { work.displayedHistoryItem = item; },
		applyCurrentResultStarState: (item) => {
			const historyId = work.result?.history_id ?? null;
			if (!work.displayedHistoryItem && historyId && item.id === historyId) {
				currentResultStarState = { id: historyId, starred: item.starred, note: item.note };
			}
		},
		applyLineageStarState: (item) => lineageState.applyStarState(item),
		applyLineageForRevisionState: (item) => lineageState.applyForRevisionState(item),
		applyLineageForShareState: (item) => lineageState.applyForShareState(item),
		focusedLineageNodeId: () => lineageState.graph?.focus_node_id ?? null,
		reloadLineage: (nodeId) => lineageState.load(nodeId, true),
		displayCurrentItem: loadIterationItem,
		clearCurrentWork: () => {
			work.displayedHistoryItem = null;
			work.result = null;
		}
	});
	const toggleHistoryStar = historyMutations.toggleStar;
	const toggleHistoryForRevision = historyMutations.toggleForRevision;
	const toggleHistoryForShare = historyMutations.toggleForShare;
	const historyItems = $derived(history.items);
	const historyTotal = $derived(history.total);
	const historyOffset = $derived(history.offset);
	const historyCursor = $derived(history.cursor);
	const historyWindowSize = $derived(history.windowSize);
	const historyPage = $derived(history.page);
	const historyTotalPages = $derived(history.totalPages);
	const historyStarredOnly = $derived(history.starredOnly);
	const historyForRevisionOnly = $derived(history.forRevisionOnly);
	const historyForShareOnly = $derived(history.forShareOnly);
	const historyStripFiltered = $derived(history.filtered);
	const trashItems = $derived(history.trashItems);
	const trashTotal = $derived(history.trashTotal);
	let confirmAction = $state<{ message: string; run: () => void; destructive?: boolean; runLabel?: string; secondaryLabel?: string; secondaryRun?: () => void; hideCancel?: boolean; cancelRun?: () => void } | null>(null);

	let promptsData = $state<{ stage1_system: string; stage2_system: string } | null>(null);

	// ── Batch derived ────────────────────────────────────────
	const batchRunning = $derived(batch.running);
	const batchSketchGrainLabel = $derived(
		sketchModeLabel(sketchModeOf(batch.sketchGrain), getLang() === 'ja')
	);
	const demoRunning = $derived(demo.running);

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


	async function pushHistory(it: Iteration, options: SaveHistoryOptions = {}): Promise<Iteration | null> {
		return saveHistoryItem(it, options, {
			catalogId: colorCatalogSettings.effectiveId,
			catalogMode: colorCatalogSettings.isAuto ? 'auto' : 'fixed',
			canvasAspectId: effectiveCanvasAspectId(),
			instructionLang: work.instructionLang,
			uiLang: getLang()
		}, {
			apiFetch,
			signedIn: () => !!session.authToken,
			ensureSvg: ensureIterationSvg,
			composeFallbackFor: (item) => item.compose_fallback
				?? (typeof item.compose_fallback_used === 'boolean' ? composeFallbackValue(item) : null),
			refreshCountedUser: async () => { await session.refreshCurrentUserSettings(); },
			activeHistoryId: () => work.displayedHistoryItem?.id ?? work.result?.history_id ?? historyItems[historyCursor]?.id ?? null,
			currentOffset: () => historyOffset,
			fetchOffset: (offset, fetchOptions) => history.fetchOffset(offset, fetchOptions),
			clearSelection: () => history.clearSelection()
		});
	}

	async function saveCurrentDemoToHistory(): Promise<void> {
		await demo.saveCurrent({
			stage1Model: qualifiedModelId(stage1Provider, stage1Model),
			stage2Model: qualifiedModelId(stage2Provider, stage2Model),
			effectiveCatalogId: colorCatalogSettings.effectiveId,
			canvasAspectId: effectiveCanvasAspectId(),
			instructionLang: work.instructionLang,
			uiLang: getLang(),
			savedStatus: t().demoSavedCurrent,
			onSaved: (saved) => { work.result = saved; },
			refreshHistory: async () => {
				await history.fetchOffset(0);
				history.setCursor(0);
			},
		});
	}

	function toggleHistorySelection(id: string) {
		historyManager.toggleSelection(id);
	}

	function selectAllManagedHistory() {
		historyManager.toggleSelectAll();
	}

	function askTrash(ids: string[]) {
		if (ids.length === 0) return;
		confirmAction = {
			message: t().confirmTrashMessage(ids.length),
			run: () => { void historyMutations.postIds('/api/history/trash', ids); }
		};
	}

	function askRestore(ids: string[]) {
		if (ids.length === 0) return;
		confirmAction = {
			message: t().confirmRestoreMessage(ids.length),
			run: () => { void historyMutations.postIds('/api/history/restore', ids); }
		};
	}

	function askPermanentDelete(ids: string[]) {
		if (ids.length === 0) return;
		confirmAction = {
			message: t().confirmPermanentDeleteMessage(ids.length),
			destructive: true,
			run: () => { void historyMutations.postIds('/api/history/permanent-delete', ids); }
		};
	}

	function loadIteration(idx: number) {
		if (demoRunning) return;
		const item = history.select(idx);
		if (item) loadIterationItem(item);
	}

	function currentComparisonItem(): Iteration | null {
		if (work.displayedHistoryItem) return work.displayedHistoryItem;
		if (!work.result) return null;
		return {
			input: work.input,
			ddl: work.ddl,
			score: work.result.score,
			svg: work.result.svg,
			at: Date.now(),
			elapsed_ms: work.result.elapsed_total_ms,
			stage1_model: work.result.stage1_model ?? qualifiedModelId(stage1Provider, stage1Model),
			stage2_model: work.result.stage2_model ?? qualifiedModelId(stage2Provider, stage2Model),
		};
	}

	const activeComparisonItem = $derived(currentComparisonItem());


	// Model comparison and language comparison own their selection, their results
	// and their run state; the page lends the artwork, the two paint stages and
	// the history writes.
	const refinement = createRefinementCoordinator({
		apiFetch,
		apiError,
		work,
		session: refinementSession,
		history: {
			clearSelection: () => history.clearSelection(),
			fetchOffset: (offset, options) => history.fetchOffset(offset, options),
			items: () => historyItems,
			syncToItem: (item) => history.syncToItem(item)
		},
		models: {
			stage1: () => qualifiedModelId(stage1Provider, stage1Model),
			stage2: () => qualifiedModelId(stage2Provider, stage2Model)
		},
		catalog: {
			defaultId: () => defaultCatalogId,
			effectiveId: () => colorCatalogSettings.effectiveId,
			available: () => colorCatalogs,
			name: catalogName
		},
		render: {
			canvasAspectId: effectiveCanvasAspectId,
			wild: () => effectiveRefineWild,
			fanoutLimit: () => renderFanoutLimit
		},
		seeds: {
			composition: createSafeIntegerSeed,
			interpretation: createInterpretationSeed
		},
		lineageParentId: currentLineageParentId,
		ensureVisibleLineageParentId,
		buildDdlDiffParts,
		setInterpretationDiffParts: (parts) => { interpretationDiffParts = parts; },
		pushHistory,
		resetTargetScopedState,
		showCanvas: () => { outputTab = 'canvas'; },
		fitCanvas: () => canvasViewport.fit()
	});

	const modelInspection = createModelInspection({
		availableModelCatalog: () => availableModelCatalog,
		result: () => work.result,
		stage1Provider: () => stage1Provider,
		stage1Model: () => stage1Model,
		stage2Provider: () => stage2Provider,
		stage2Model: () => stage2Model,
		loading: () => work.loading,
		input: () => work.input,
		currentUser: () => session.currentUser,
		setCurrentUser: (user) => session.setCurrentUser(user as UserItem),
		targetContextVersion: () => refinement.contextVersion,
		apiFetch,
		interpretOne: work.interpretOne,
		composeOne: work.composeOne,
		ensureVisibleLineageParentId,
		pushHistory: (it, options) => pushHistory(it as unknown as Iteration, options),
		toggleHistoryStar,
		addTokens: work.addTokens,
		statusModelName,
		effectiveCanvasAspectId,
	});

	async function replayHistoryItem(it: Iteration, source: ReplaySource = outputTab) {
		if (demoRunning || work.reloading) return;
		const contextVersion = refinement.contextVersion;
		work.reloading = true;
		work.reloadError = null;
		try {
			const comparison = await replaySavedHistoryItem(it, source, {
				effectiveCatalogId: colorCatalogSettings.effectiveId,
				effectiveCanvasAspectId: effectiveCanvasAspectId(),
				currentRenderEngineVersion,
				renderPayload: (item, catalogId) => ({
					...refinement.workReferencePayload(item.id),
					...renderSettingsPayload('render-svg', {
						...colorCatalogOverride(catalogId),
						...wildOverride(Boolean(item.render_wild))
					})
				}),
				versionMismatchMessage: (recorded, current) => t().historyReplayVersionMismatch(recorded, current),
				versionNotRecordedMessage: (current) => t().historyReplayVersionNotRecorded(current)
			}, {
				apiFetch,
				apiError,
				ensureSvg: ensureIterationSvg,
				acceptRendered: () => contextVersion === refinement.contextVersion
			});
			if (!comparison) return;
			work.replayComparison = comparison;
		} catch (e) {
			if (contextVersion === refinement.contextVersion) work.reloadError = e instanceof Error ? e.message : String(e);
		} finally {
			work.reloading = false;
		}
	}

	function closeReplayComparison() {
		const source = work.replayComparison?.source;
		work.replayComparison = null;
		if (!source) return;
		if (source === 'history-manager') {
			historyManager.open = true;
			return;
		}
		outputTab = source;
	}

async function openLineageNode(node: LineageNode): Promise<void> {
	if (!node.history) return;
	loadIterationItem(node.history);
	outputTab = 'lineage';
	work.lineageDetached = false;
	await lineageState.load(node.id, true);
}

// In the Lineage tab, double-click opens the work in Canvas; single-click only selects it.
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
	await focusSavedLineageChild(historyId, nodeId, {
		fetchOffset: (offset, options) => history.fetchOffset(offset, options),
		filtered: () => historyStripFiltered,
		clearFilters: () => history.clearFilters(),
		items: () => historyItems,
		displayCurrentItem: (item) => {
			// Description / DDL edits produce one artwork, not a candidate set.
			outputTab = 'canvas';
			loadIterationItem(item);
		},
		loadLineage: (id) => lineageState.load(id, true),
		missingIdentityError: () => new Error(getLang() === 'ja' ? '描画結果を系譜へ保存できませんでした。' : 'The finished work could not be saved to the lineage.'),
		missingWorkError: () => new Error(getLang() === 'ja' ? '保存した作品を読み込めませんでした。' : 'The saved work could not be loaded.')
	});
}

async function drawLineageDescriptionEdit(node: LineageNode, text: string, signal?: AbortSignal, wild?: boolean | null): Promise<void> {
	const sourceText = text.trim();
	if (!sourceText || !node.history) return;
	// Ask before the words are carried into a child (contract § stage 4).
	if (!(await work.confirmFallbackRefine(node.history))) return;
	const rendered = await work.paintOne(sourceText, {
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

/** Sketching (Stage 0.5): redraw a saved work at a different grain, as its child.
 *  The prose is written again -- the grain is what changed, so replaying the
 *  stored prose would leave the parameter dead. */
async function drawLineageSketchGrain(node: LineageNode, grain: 'fine' | 'coarse', signal?: AbortSignal): Promise<void> {
	if (!node.history) return;
	// Ask before the words are carried into a child (contract § stage 4).
	if (!(await work.confirmFallbackRefine(node.history))) return;
	const sourceText = node.history.source_text ?? node.history.input ?? '';
	if (!sourceText.trim()) return;
	const rendered = await work.paintOne(sourceText, {
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
	// Ask before the words are carried into a child (contract § stage 4).
	if (!(await work.confirmFallbackRefine(node.history))) return;
	const sourceText = node.history.source_text ?? node.history.input ?? '';
	const composed = await work.composeOne(nextDdl, sourceText, signal, undefined, undefined, {
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
	const composed = await work.composeOne(nextDdl, '', signal, undefined, undefined, {
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
	const item = work.displayedHistoryItem ?? historyItems.find((entry) => entry.id === work.result?.history_id) ?? null;
	if (!lineageState.graph?.nodes.some((entry) => entry.id === nodeId)) await lineageState.load(nodeId, true);
	const node = lineageState.graph?.nodes.find((entry) => entry.id === nodeId) ?? null;
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
	const focusId = lineageState.graph?.focus_node_id ?? work.displayedHistoryItem?.lineage_node_id ?? work.result?.lineage_node_id ?? null;
	if (focusId) void lineageState.load(focusId, true);
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
	await promoteSavedLineageNode(node, {
		apiFetch,
		contextVersion: () => refinement.contextVersion,
		currentItem: () => work.displayedHistoryItem,
		setCurrentItem: (item) => { work.displayedHistoryItem = item; },
		activeHistoryId: () => work.displayedHistoryItem?.id ?? work.result?.history_id ?? historyItems[historyCursor]?.id ?? null,
		currentOffset: () => historyOffset,
		syncToItem: (item) => history.syncToItem(item),
		fetchOffset: (offset, options) => history.fetchOffset(offset, options),
		loadLineage: (id) => lineageState.load(id, true)
	});
}

async function saveLineageNote(node: LineageNode, note: string): Promise<void> {
	await saveSavedLineageNote(node, note, {
		apiFetch,
		contextVersion: () => refinement.contextVersion,
		applyStarState: (item) => historyMutations.applyStarState(item),
		loadLineage: (id) => lineageState.load(id, true)
	});
}

function detachLineage(): void {
	resetTargetScopedState();
	work.pendingCanvasAspectDerivation = null;
	work.lineageDetached = true;
	work.displayedHistoryItem = null;
	history.clearSelection();
	outputTab = 'canvas';
}

const currentLineageNodeId = $derived(work.displayedHistoryItem?.lineage_node_id ?? work.result?.lineage_node_id ?? null);
// The description tab's edit button needs both a node to branch from and a DDL
// to load into the editor.
const canEditCurrentDdl = $derived(!!currentLineageNodeId && !!(work.displayedHistoryItem?.ddl ?? work.ddl));

$effect(() => {
	if (outputTab === 'lineage' && currentLineageNodeId) void lineageState.load(currentLineageNodeId);
});

	function resetTargetScopedState(options: { preserveVariationCandidates?: boolean } = {}): void {
		refinement.resetTarget(options);

		modelInspection.reset();

		interpretationDiffParts = [];
		work.reloadError = null;
		work.replayComparison = null;
		if (lineageIntermediateNoticeTimer !== null) {
			window.clearTimeout(lineageIntermediateNoticeTimer);
			lineageIntermediateNoticeTimer = null;
		}
		lineageIntermediateNotice = null;

		lineageState.reset();
	}

	function loadIterationItem(it: Iteration) {
		if (demoRunning) return;
		const preserveLineageTab = outputTab === 'lineage';
		const projection = projectHistoryCurrentWork(it);
		resetTargetScopedState();
		work.pendingCanvasAspectDerivation = null;
		work.inputMode = 'single';
		work.displayedHistoryItem = it;
		void history.syncToItem(it);
		work.lineageDetached = false;
		work.expandedDdl = projection.expandedDdl;
		work.input = projection.sourceText;
		work.ddl = projection.ddl;
		work.ddlGeneratedBaseline = projection.ddl;
		work.thinking = projection.thinking;
		work.stage1UserPrompt = projection.sourceText;
		work.adoptSketch(projection.sketchText, projection.sketchGrain, projection.sourceText, projection.sketchState);
		work.result = projection.result;
		work.error = null;
		outputTab = preserveLineageTab ? 'lineage' : 'canvas';
		if (preserveLineageTab && it.lineage_node_id) void lineageState.load(it.lineage_node_id, true);
		canvasViewport.fit();
		// The listing carries thumbnails, not drawings, so the work being put on
		// the canvas fetches its own. One request for the one work being looked
		// at, rather than a page of them for the one that gets opened.
		if (!it.svg && it.id) void fillCanvasSvg(it);
	}

	/** Put the fetched drawing on the canvas, unless the reader has moved on. */
	async function fillCanvasSvg(it: Iteration): Promise<void> {
		const target = it.id;
		const svg = await ensureIterationSvg(it);
		if (!svg || work.displayedHistoryItem?.id !== target || !work.result) return;
		work.result = { ...work.result, svg };
		canvasViewport.fit();
	}

	function openNearbyHistory(id: string): void {
		const item = lineageState.nearby.find((candidate) => candidate.id === id);
		if (item) loadIterationItem(item);
	}

	const currentRenderedAt = $derived.by(() => {
		const at = work.displayedHistoryItem?.at ?? work.result?.history_at ?? null;
		return at == null ? null : new Date(at).toLocaleString(getLang() === 'ja' ? 'ja-JP' : 'en-US', {
			year: 'numeric',
			month: 'numeric',
			day: 'numeric',
			hour: '2-digit',
			minute: '2-digit'
		});
	});


	/** One work older. */
	async function gotoPrev() {
		const item = await history.move('older');
		if (!item) return;
		// Read after the await, not before it. Read before, a tab the user chose
		// while the page was arriving was quietly put back to the one they left.
		const preservedTab = outputTab;
		loadIterationItem(item);
		outputTab = preservedTab;
	}

	/** One work newer. */
	async function gotoNext() {
		const item = await history.move('newer');
		if (!item) return;
		const preservedTab = outputTab;
		loadIterationItem(item);
		outputTab = preservedTab;
	}

	async function gotoLatest() {
		const item = await history.move('latest');
		if (item) loadIterationItem(item);
	}

	async function gotoHistoryNewerPage(): Promise<void> {
		const item = await history.movePage('newer');
		if (item) loadIterationItem(item);
	}

	async function gotoHistoryOlderPage(): Promise<void> {
		const item = await history.movePage('older');
		if (item) loadIterationItem(item);
	}

	async function gotoHistoryLatestPage(): Promise<void> {
		const item = await history.movePage('latest');
		if (item) loadIterationItem(item);
	}

	async function gotoHistoryOldestPage(): Promise<void> {
		const item = await history.movePage('oldest');
		if (item) loadIterationItem(item);
	}

	// Both canvas controls and the strip pager read one owner projection.
	const historyNavButtonsDisabled = $derived(history.navDisabled);
	const historyPageNavDisabled = $derived(history.pageDisabled);
	// Left as it was: 0 / N is how "nothing is selected" is shown, and is not a
	// claim about which work is current.
	const navPos       = $derived(historyOffset + historyCursor + 1);
	// ── Saijiki ─────────────────────────────────────────────
	function handleKeydown(e: KeyboardEvent) {
		if (e.key === 'Escape') {
			saijikiOpen = false;
			userMenuOpen = false;
			if (session.profileOpen) session.closeProfile();
			if (settings.opened) settings.close();
			if (catalogOpen) cancelCatalogSelection();
			historyManager.open = false;
			confirmAction = null;
		}
		if (!shouldIgnoreCanvasShortcut(e)) handleCanvasKeydown(e);
	}

	function shouldIgnoreCanvasShortcut(e: KeyboardEvent) {
		if (!session.currentUser || session.profileOpen || settings.opened || catalogOpen || historyManager.open || confirmAction) return true;
		const target = e.target;
		if (!(target instanceof HTMLElement)) return false;
		if (target.isContentEditable) return true;
		return !!target.closest('input, textarea, select, [contenteditable="true"]');
	}

	function handleDocClick(e: MouseEvent) {
		if (exportMenuOpen && exportWrapEl && !exportWrapEl.contains(e.target as Node)) exportMenuOpen = false;
		if (userMenuOpen && userMenuWrapEl && !userMenuWrapEl.contains(e.target as Node)) userMenuOpen = false;
		if (canvasAspectMenuOpen) canvasAspectMenuOpen = false;
	}

	// ── Model selection ─────────────────────────────────────
	function setStage1Provider(v: Provider) {
		work.displayedHistoryItem = null;
		history.clearSelection();
		stage1Provider = v; stage1Model = modelsFor(v)[0]?.id ?? stage1Model;
	}
	function setStage1Model(v: string) {
		work.displayedHistoryItem = null;
		history.clearSelection();
		stage1Model = v;
	}
	function setStage2Provider(v: Provider) {
		work.displayedHistoryItem = null;
		history.clearSelection();
		stage2Provider = v; stage2Model = modelsFor(v)[0]?.id ?? stage2Model;
	}
	function setStage2Model(v: string) {
		work.displayedHistoryItem = null;
		history.clearSelection();
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

	const unsavedRefinementPreview = $derived(!!work.result && !work.result.lineage_node_id && !!work.result.lineage_parent_node_id && !!work.result.derivation_kind);

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
		if (work.lineageDetached) return null;
		return work.displayedHistoryItem?.lineage_node_id ?? work.result?.lineage_node_id ?? null;
	}

async function ensureLineageParentId(): Promise<string | null> {
	const existing = currentLineageParentId();
	if (existing || !work.result || !work.ddl || !work.result.lineage_parent_node_id || !work.result.derivation_kind) return existing;
	const saved = await pushHistory({
		...work.result,
		input: work.input.trim(), ddl: work.ddl, score: work.result.score, svg: work.result.svg, at: Date.now(),
		elapsed_ms: work.result.elapsed_total_ms ?? 0,
		tokens_in: (work.result.tokens_in_stage1 ?? 0) + (work.result.tokens_in_stage2 ?? 0) || null,
		tokens_out: (work.result.tokens_out_stage1 ?? 0) + (work.result.tokens_out_stage2 ?? 0) || null,
	}, {
		sourceText: work.input.trim(), historyVisibility: 'lineage_only',
		lineageParentNodeId: work.result.lineage_parent_node_id,
		derivationKind: work.result.derivation_kind,
		derivationMetadata: work.result.derivation_metadata ?? {},
	});
	if (!saved?.lineage_node_id) return null;
	work.result = { ...work.result, history_id: saved.id, history_at: saved.at, lineage_node_id: saved.lineage_node_id, description_hash: saved.description_hash };
	return saved.lineage_node_id;
}

async function ensureVisibleLineageParentId(): Promise<string | null> {
	const materializingIntermediate = unsavedRefinementPreview;
	const nodeId = await ensureLineageParentId();
	if (materializingIntermediate && !nodeId) {
		work.error = t().lineageIntermediateSaveFailed;
		throw new Error(work.error);
	}
	if (materializingIntermediate) showLineageIntermediateNotice();
	return nodeId;
}

	function setSelectedCatalog(id: string) {
		work.displayedHistoryItem = null;
		history.clearSelection();
		colorCatalogSettings.selected = id;
	}

	// ── Download ────────────────────────────────────────────
	// Exporting owns the profile round trip, the canvas rasterisation and the
	// capture-date stamp; the page only lends it the artwork and the fetch wrapper.
	const { downloadSVG, downloadPNG } = createExportActions({
		result: () => work.result,
		input: () => work.input,
		displayedHistoryItem: () => work.displayedHistoryItem,
		apiFetch,
		apiError,
		exportFilename,
		refinementCatalogId: refinement.refinementCatalogId,
		refinementCanvasAspectId: refinement.refinementCanvasAspectId,
		effectiveCanvasAspectId,
	});

	// The canvas toolbar builds the card from the work it is showing, which is
	// the listed item when one is selected and the fresh drawing otherwise. The
	// page shape and the seal come from the same settings the history modal uses.
	async function downloadCurrentCard(): Promise<void> {
		const id = work.displayedHistoryItem?.id ?? work.result?.history_id ?? null;
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
		if (!batch.latestResult) return;
		work.result = batch.latestResult;
		work.ddl = batch.latestDdl;
		work.ddlGeneratedBaseline = batch.latestDdl;
		work.thinking = batch.latestThinking;
		outputTab = 'canvas';
		canvasViewport.fit();
	}

	function resumeBatchLatestFollow(): void {
		resetTargetScopedState();
		batch.startFollowingLatest();
		work.displayedHistoryItem = null;
		history.clearSelection();
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

	const statusStage1Model = $derived(work.displayedHistoryItem
		? (work.displayedHistoryItem.stage1_model ? statusModelName(work.displayedHistoryItem.stage1_model) : '-')
		: (work.result?.stage1_model ? statusModelName(work.result.stage1_model) : '-'));
	const statusStage2Model = $derived(work.displayedHistoryItem
		? (work.displayedHistoryItem.stage2_model ? statusModelName(work.displayedHistoryItem.stage2_model) : '-')
		: (work.result?.stage2_model ? statusModelName(work.result.stage2_model) : '-'));
	const statusStage1ModelOnly = $derived(work.displayedHistoryItem
		? (work.displayedHistoryItem.stage1_model ? modelShortName(work.displayedHistoryItem.stage1_model) : '-')
		: (work.result?.stage1_model ? modelShortName(work.result.stage1_model) : '-'));
	const statusStage2ModelOnly = $derived(work.displayedHistoryItem
		? (work.displayedHistoryItem.stage2_model ? modelShortName(work.displayedHistoryItem.stage2_model) : '-')
		: (work.result?.stage2_model ? modelShortName(work.result.stage2_model) : '-'));
	const nextStage1Model = $derived(statusModelName(qualifiedModelId(stage1Provider, stage1Model)));
	const nextStage2Model = $derived(statusModelName(qualifiedModelId(stage2Provider, stage2Model)));
	const nextCatalogName = $derived(colorCatalogSettings.isAuto ? t().colorCatalogAuto : currentCatalog.name);
	// The catalog a work was drawn with, named as it stands today. Two things
	// the bare name cannot say are said here instead of being papered over: an
	// id nothing current answers to is marked retired rather than shown as the
	// default, and a work saved before the colors were recorded is marked as
	// having no record -- that one draws from today's definition, not its own.
	const statusCatalogName = $derived.by(() => {
		const renderedWork = work.displayedHistoryItem ?? work.result ?? null;
		if (!renderedWork) return '-';
		const catalogId = renderedWork.render_color_catalog_id
			?? (work.displayedHistoryItem ? work.displayedHistoryItem.catalog_id : null)
			?? null;
		if (!catalogId) return '-';
		const plate = catalogNameplate(colorCatalogs, renamedCatalogIds, catalogId, renderedWork.render_color_catalog_name);
		const notes: string[] = [];
		if (plate.retired) notes.push(t().colorCatalogRetired);
		const colorMap = renderedWork.render_color_map;
		if (!colorMap || Object.keys(colorMap).length === 0) notes.push(t().colorCatalogNoRecord);
		return notes.length ? t().colorCatalogNote(plate.name, notes) : plate.name;
	});
	const currentCanvasAspect = $derived(getCanvasAspectOption(effectiveCanvasAspectId()));
	const nextCanvasName = $derived(currentCanvasAspect.label);
	const displayCanvasAspect = $derived(svgAspect(work.result?.svg) ?? currentCanvasAspect);
	const statusCanvasName = $derived.by(() => {
		const canvasId = work.displayedHistoryItem?.render_canvas_aspect_id ?? work.displayedHistoryItem?.render_canvas_aspect ?? work.displayedHistoryItem?.score?.canvas ?? work.result?.render_canvas_aspect_id ?? work.result?.render_canvas_aspect ?? work.result?.score?.canvas ?? null;
		return canvasId ? getCanvasAspectOption(canvasId).label : '-';
	});
	// The digest, not the stored `<scheme>:<digest>`: the scheme is a property of
	// the value rather than part of it, and nothing in the app takes a prefixed
	// string as input. See lib/hashIdentity.ts.
	const statusHashFull = $derived(hashDigest(
		work.displayedHistoryItem?.render_hash
			?? work.result?.render_hash
			?? ''
	));
	const statusHashLabel = $derived((
		work.displayedHistoryItem?.render_hash_short
			?? work.displayedHistoryItem?.render_hash?.slice(-4)
			?? work.result?.render_hash_short
			?? work.result?.render_hash?.slice(-4)
			?? ''
	).toUpperCase());
	const statusHistoryItem = $derived.by(() => {
		if (work.displayedHistoryItem) return work.displayedHistoryItem;
		if (work.result?.history_id) {
			const historyId = work.result.history_id;
			const projected = currentResultStarState?.id === historyId ? currentResultStarState : null;
			return historyItems.find((item) => item.id === historyId) ?? {
				id: historyId,
				starred: projected?.starred ?? false,
				note: projected?.note ?? null,
			};
		}
		if (work.inputMode === 'demo' || work.activeRunMode === 'demo') return null;
		return historyCursor >= 0 && historyItems[historyCursor] ? historyItems[historyCursor] : null;
	});
	const replayableStatusHistoryItem = $derived(
		statusHistoryItem && "score" in statusHistoryItem && "svg" in statusHistoryItem
			? statusHistoryItem as Iteration
			: null
	);
	// What a refine inherits when nothing is overridden: the work on screen, or
	// the global setting when nothing is on screen.
	const targetWild = $derived(work.displayedHistoryItem?.render_wild ?? work.result?.render_wild ?? wildSettings.enabled);
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
		history.openManager();
	}

	function setHistoryStarredOnly(value: boolean) {
		history.setStarredOnly(value);
	}

	function setHistoryForRevisionOnly(value: boolean) {
		history.setForRevisionOnly(value);
	}

	function setHistoryForShareOnly(value: boolean) {
		history.setForShareOnly(value);
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
		if (!work.result) return null;
		const payload: Record<string, unknown> = {};
		if (work.result.stage1_model !== undefined) payload.stage1_model = work.result.stage1_model;
		if (work.result.stage2_model !== undefined) payload.stage2_model = work.result.stage2_model;
		if (work.result.render_build_number !== undefined) payload.render_build_number = work.result.render_build_number;
		if (work.result.render_color_profile !== undefined) payload.render_color_profile = work.result.render_color_profile;
		if (work.result.render_engine_id !== undefined) payload.render_engine_id = work.result.render_engine_id;
		if (work.result.render_engine_version !== undefined) payload.render_engine_version = work.result.render_engine_version;
		if (work.result.render_canvas_aspect !== undefined) payload.render_canvas_aspect = work.result.render_canvas_aspect;
		if (work.result.render_canvas_aspect_id !== undefined) payload.render_canvas_aspect_id = work.result.render_canvas_aspect_id;
		if (work.result.render_canvas_aspect_ratio !== undefined) payload.render_canvas_aspect_ratio = work.result.render_canvas_aspect_ratio;
		if (work.result.instruction_lang_requested !== undefined) payload.instruction_lang_requested = work.result.instruction_lang_requested;
		if (work.result.instruction_lang_resolved !== undefined) payload.instruction_lang_resolved = work.result.instruction_lang_resolved;
		if (work.result.seed_text !== undefined) payload.seed_text = work.result.seed_text;
		const derivationMetadata = work.result.derivation_metadata ?? {};
		const resolvedLang = work.result.instruction_lang_resolved ?? null;
		payload.stage1_instruction_lang = typeof derivationMetadata.stage1_language === 'string' ? derivationMetadata.stage1_language : resolvedLang;
		payload.stage2_instruction_lang = typeof derivationMetadata.stage2_language === 'string' ? derivationMetadata.stage2_language : resolvedLang;
		if (work.result.ui_lang !== undefined) payload.ui_lang = work.result.ui_lang;
		if (work.result.render_hash !== undefined) payload.render_hash = work.result.render_hash;
		if (work.result.render_hash_short !== undefined) payload.render_hash_short = work.result.render_hash_short;
		if (work.result.render_color_catalog_id !== undefined) payload.render_color_catalog_id = work.result.render_color_catalog_id;
		if (work.result.render_color_catalog_name !== undefined) payload.render_color_catalog_name = work.result.render_color_catalog_name;
		if (work.result.render_color_catalog_sub !== undefined) payload.render_color_catalog_sub = work.result.render_color_catalog_sub;
		if (work.result.render_color_map !== undefined) payload.render_color_map = work.result.render_color_map;
		if (work.result.render_seed !== undefined) payload.render_seed = work.result.render_seed;
		if (work.result.composition_seed !== undefined) payload.composition_seed = work.result.composition_seed;
		if (work.result.interpretation_seed !== undefined) payload.interpretation_seed = work.result.interpretation_seed;
		if (work.result.description_hash !== undefined) payload.description_hash = work.result.description_hash;
		payload.elapsed_ms = work.displayedHistoryItem?.elapsed_ms ?? work.result.elapsed_total_ms;
		payload.tokens_in = work.displayedHistoryItem?.tokens_in ?? ((work.result.tokens_in_stage1 ?? 0) + (work.result.tokens_in_stage2 ?? 0) || null);
		payload.tokens_out = work.displayedHistoryItem?.tokens_out ?? ((work.result.tokens_out_stage1 ?? 0) + (work.result.tokens_out_stage2 ?? 0) || null);
		if (work.result.derivation_kind !== undefined) payload.derivation_kind = work.result.derivation_kind;
		if (work.result.derivation_metadata !== undefined) payload.derivation_metadata = work.result.derivation_metadata;
		payload.score = work.result.score;
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
	const batchActiveDdlHighlighted = $derived(batch.activeDdl !== null
		? highlightDDL(batch.activeDdl)
		: escapeHtml(t().batchActiveDdlPending));
	const demoGeneratedDdlHighlighted = $derived(demo.generatedDdl !== null
		? highlightDDL(demo.generatedDdl)
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

	function handleCanvasKeydown(event: KeyboardEvent) {
		canvasViewport.handleKeydown(event, outputTab === 'canvas');
	}

	const historyNavSpan = $derived(history.windowSize);

	$effect(() => {
		void history.resize(visibleThumbCount);
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
			void history.refreshExternal();
		}, HISTORY_EXTERNAL_REFRESH_MS);
		// Coming back to the tab still refreshes at once; what it no longer does
		// is jump the floor. Both of these fire on a single alt-tab.
		function onHistoryVisibilityChange() {
			if (document.visibilityState === 'visible') void history.refreshExternal();
		}
		function onHistoryWindowFocus() {
			void history.refreshExternal();
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
			settings.restoreDetail();
			loadPersistedSettings();
		} catch {}
		void (async () => {
			await Promise.all([loadColorCatalogs(), loadPublicAppInfo(), session.loadCurrentUser(), fetchPrompts()]);
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
		document.documentElement.dataset.theme = session.darkMode ? 'dark' : 'light';
	});
	$effect(() => {
		const mode = work.inputMode;
		const wasMode = previousInputMode;
		if (mode === wasMode) return;
		previousInputMode = mode;
		if (mode === 'batch' && (work.activeRunMode === 'batch' || batch.latestResult)) {
			untrack(resumeBatchLatestFollow);
		} else if (wasMode === 'batch') {
			batch.stopFollowingLatest();
		}
		// Asked on arrival rather than kept up to date: works are saved from other
		// windows too, and the answer is only ever read here.
		if (mode === 'batch') void untrack(() => batch.refreshResume());
	});
</script>

<svelte:window onclick={handleDocClick} />

<!-- ══════════════════════════════════════════════════════════ -->
<!--  ROOT                                                       -->
<!-- ══════════════════════════════════════════════════════════ -->
{#if !session.currentUser}
	<AuthPanel
		bind:loginUserName={session.loginUserName}
		bind:loginPassword={session.loginPassword}
		bind:loginPasswordVisible={session.loginPasswordVisible}
		loginStatus={session.loginStatus}
		onLogin={() => session.login()}
		appVersion={APP_VERSION}
		buildNumber={__BUILD_NUMBER__}
		{developerMode}
	/>
{:else}
<div
	class="root"
	class:tooltips-disabled={!session.tooltipsEnabled}
	class:ui-hide-input-modes={!session.uiVisibility.input_modes}
	class:ui-hide-drawing-settings={!session.uiVisibility.drawing_settings}
	class:ui-hide-ddl-tools={!session.uiVisibility.ddl_tools}
	class:ui-hide-detail-status={!session.uiVisibility.detail_status}
	class:ui-hide-work-tools={!session.uiVisibility.work_tools}
	class:ui-hide-history={!session.uiVisibility.history}
>
	<AppRail
		currentUser={session.currentUser}
		bind:userMenuOpen
		bind:userMenuWrapEl
		settingsOpen={settings.opened}
		darkMode={session.darkMode}
		buildNumber={__BUILD_NUMBER__}
		{developerMode}
		{singleUserMode}
		showAuxiliary={session.uiVisibility.auxiliary}
		uiMode={session.uiMode}
		tooltipsEnabled={session.tooltipsEnabled}
		onSetUiMode={(mode) => void session.updateUiMode(mode)}
		onToggleTooltips={() => void session.updateTooltipsEnabled(!session.tooltipsEnabled)}
		onToggleUserMenu={() => (userMenuOpen = !userMenuOpen)}
		onOpenProfile={() => { session.openProfile(); userMenuOpen = false; }}
		onLogout={() => session.logout()}
		onOpenSettings={() => settings.openSettings()}
		onToggleTheme={() => void session.updateUiTheme(!session.darkMode)}
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
						sketchMode={work.sketchMode}
						onSelectSketchMode={(mode) => (work.sketchMode = mode)}
						bind:inputMode={work.inputMode}
						bind:input={work.input}
						bind:batchInput={batch.input}
						lineNumbersText={batch.lineNumbersText}
						batchNonEmpty={batch.nonEmpty}
						{batchRunning}
						singleRunning={work.singleRunning}
						hideRunStatus={work.reloading}
						singleDdlReady={work.ddl !== null}
						batchActiveLine={batch.activeLine}
						batchObservedLine={batch.observedLine}
						batchRunningLineText={batch.runningLineText}
						batchSketchText={batch.sketchText}
						{batchSketchGrainLabel}
						{batchActiveDdlHighlighted}
						batchTotal={batch.total}
						batchCurrent={batch.current}
						batchRetryRound={batch.retryRound}
						batchActiveTokensIn={batch.activeTokensIn}
						batchActiveTokensOut={batch.activeTokensOut}
						batchTokensInTotal={batch.tokensInTotal}
						batchTokensOutTotal={batch.tokensOutTotal}
						liveMs={work.liveMs}
						batchFailureReport={batchFailureReportStore.report}
						batchPromptHistory={batch.promptHistory}
						canResumeBatch={batch.canResume}
						onResumeBatch={() => void resumeInterruptedBatch()}
						bind:demoSettings={demo.settings}
						demoModelProviderGroups={availableModelCatalog}
						{demoRunning}
						demoTimedOut={demo.timedOut}
						demoWaitingSeconds={demo.waitingSeconds}
						demoCurrentLiveMs={demo.currentLiveMs}
						demoCurrentElapsedMs={demo.currentElapsedMs}
						demoCurrentTokensIn={demo.currentTokensIn}
						demoCurrentTokensOut={demo.currentTokensOut}
						demoTotalElapsedMs={demo.totalElapsedMs}
						demoTotalTokensIn={demo.totalTokensIn}
						demoTotalTokensOut={demo.totalTokensOut}
						demoRenderCount={demo.renderCount}
						demoGeneratedPrompt={demo.generatedPrompt}
						{demoGeneratedDdlHighlighted}
						demoCanSaveCurrent={demo.canSaveCurrent}
						demoSavingCurrent={demo.savingCurrent}
						demoSaveStatus={demo.saveStatus}
						demoError={demo.error}
						lockNonDemo={demoRunning}
						canSubmit={work.canSubmit}
						generationDisabled={refinementSession.gridBusy || work.reloading}
						error={work.error}
						stageLabel={work.stageLabel}
						{canvasAspectEnabled}
						{canvasAspectId}
						{canvasAspectMenuOpen}
						stage1ModelLabel={work.stage1ModelLabel}
						stage2ModelLabel={work.stage2ModelLabel}
						runTokensIn={work.activeRunTokensIn}
						runTokensOut={work.activeRunTokensOut}
						{nextStage1Model}
						{nextStage2Model}
						{nextCatalogName}
						{nextCanvasName}
						onToggleCanvasAspectMenu={() => (canvasAspectMenuOpen = !canvasAspectMenuOpen)}
						onSelectCanvasAspect={selectCanvasAspect}
						onOpenModelSelection={() => openModelSelection(false)}
						onOpenCatalogModal={openCatalogModal}
						onClearInput={work.clearInput}
						onRememberBatchPrompt={(prompt) => batch.rememberPrompt(prompt)}
						onDemoSettingsChange={(next) => demo.saveSettings(next)}
						onSaveCurrentDemo={saveCurrentDemoToHistory}
						onStartDemo={work.startDemo}
						onStopDemo={work.stopDemo}
						onSubmit={work.requestSubmit}
						onStop={work.stopBatch}
					/>

					<!-- thinking -->
					{#if work.thinking}
						<section class="panel-section">
							<details class="thinking-details">
								<summary>{t().thinkingLabel}</summary>
								<pre>{work.thinking}</pre>
							</details>
						</section>
					{/if}

					<!-- DDL tools -->
					{#if work.inputMode === 'single'}
						<section class="panel-section ddl-tools-section">
							<Tooltip placement="left" text={t().tooltipDdlEdit}>
								<button class="ddl-new-btn" type="button" disabled={!canEditCurrentDdl} onclick={openCurrentDdlEditor}>{t().ddlEditButton}</button>
							</Tooltip>
							<Tooltip placement="left" text={t().tooltipDdlNew}>
								<button class="ddl-new-btn" type="button" onclick={openNewDdlDialog}>{t().ddlNewButton}</button>
							</Tooltip>
						</section>
					{/if}

					<!-- DDL-run status belongs below the action buttons, not inside the input field. -->
					{#snippet ddlRunStatus()}
						<RunStatus
							label={work.stageLabel || t().stageDdlGenerating}
							stage2Model={work.stage2ModelLabel}
							elapsedMs={work.liveMs}
							tokensIn={work.activeRunTokensIn}
							tokensOut={work.activeRunTokensOut}
							onStop={work.stopDdlRender}
						/>
					{/snippet}

					<!-- Sketching (Stage 0.5). Above the instructions because it comes before
					     them: the author reads the prose the layer wrote, and may
					     rewrite it. What is left here is what Stage 1 reads. -->
					{#if work.inputMode === 'single' && (work.sketchText !== null || work.result !== null)}
						<section class="panel-section sketch-section">
							<div class="sketch-head">
								<Tooltip placement="right" text={t().tooltipSketchToggle}>
									<button class="sketch-toggle" type="button" onclick={describePanelSettings.toggleSketch}>
										<span class="sketch-arrow" class:open={describePanelSettings.sketchOpen}>▶</span>
										<span class="sketch-title">{t().sketchLabel}</span>
									</button>
								</Tooltip>
								{#if work.sketchText !== null}
									<span class="sketch-grain">{t().sketchGrainLabel}: {sketchModeLabel(sketchModeOf(work.result?.sketch_grain ?? sketchGrainOf(work.sketchMode)), getLang() === 'ja')}</span>
									<!-- Editing needs the prose on screen, so the button unfolds the
									     section rather than acting on what the author cannot see. -->
									<button type="button" class="sketch-edit-btn" onclick={() => { work.sketchEditing = !work.sketchEditing; if (work.sketchEditing) describePanelSettings.revealSketch(); }}>
										{work.sketchEditing ? t().ddlDoneBtn : t().ddlEditBtn}
									</button>
								{/if}
							</div>
							{#if describePanelSettings.sketchOpen}
								{#if work.result?.sketch_fallback_used}
									<p class="sketch-note">{t().sketchFallbackNote}</p>
								{:else if work.sketchText === null}
									<!-- No prose. Which of the silences this is comes from the
									     record, not from the absence: a work drawn with the
									     layer off and a work drawn before the layer was
									     recorded read the same here otherwise. -->
									<p class="sketch-note">{sketchStateNote(work.sketchState, getLang() === 'ja')}</p>
								{:else if work.sketchEditing}
									<textarea class="sketch-editor" rows="7" bind:value={work.sketchDraft} spellcheck="true"></textarea>
									<p class="sketch-note">{t().sketchEditHint}</p>
								{:else}
									<p class="sketch-body">{work.sketchDraft}</p>
								{/if}
							{/if}
						</section>
					{/if}

					<!-- Interpretation: normalized DDL, read-only. -->
					{#if work.ddl !== null && work.inputMode === 'single'}
						<section class="panel-section">
							<DdlViewer
								ddl={work.ddl}
								expandedDdl={work.expandedDdl}
								label={t().ddlLabel}
								expandedLabel={t().ddlExpandedLabel}
								onPaint={() => { void work.replay(); }}
								paintDisabled={work.loading || work.reloading || refinementSession.gridBusy}
								runStatus={work.reloading ? ddlRunStatus : null}
							/>
						</section>
					{/if}

					<!-- What the expansion layer removed. This complements editor-time
					     DDL warnings by reporting the side only known after expansion. -->
					{#if work.pluginWarningsShown.length > 0 && work.inputMode === 'single'}
						<section class="panel-section plugin-warnings">
							<div class="plugin-warnings-title">{t().ddlPluginWarningsTitle}</div>
							{#each work.pluginWarningsShown as warning}
								<p class="plugin-warning-line">{warning}</p>
							{/each}
						</section>
					{/if}

					<!-- Which limits took effect. The image cannot explain why ink was
					     reduced; only this response can name the active settings. -->
					{#if work.limitNotesShown.length > 0 && work.inputMode === 'single'}
						<section class="panel-section limit-notes">
							<div class="limit-notes-title">{t().renderLimitNotesTitle}</div>
							{#each work.limitNotesShown as note}
								<p class="limit-note-line">{note}</p>
							{/each}
						</section>
					{/if}

					{#if interpretationDiffParts.length > 0 && work.inputMode === "single"}
						<section class="panel-section interpretation-diff">
							{#each interpretationDiffParts as part}
								<div class:removed={part.kind === "removed"} class:added={part.kind === "added"} class:same={part.kind === "same"}>{part.kind === "removed" ? "−" : part.kind === "added" ? "+" : " "} {part.text}</div>
							{/each}
						</section>
					{/if}

					<!-- Statistics -->
					{#if work.result && work.elapsedTotalMs > 0}
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
										{#if work.elapsedStage1Ms > 0}
											<div class="stats-row">
												<span class="stats-key">{t().statsInterp}</span>
												<span class="stats-value">
													<span><span class="stats-metric-label">{t().statsElapsed}</span>{(work.elapsedStage1Ms / 1000).toFixed(1)}s</span>
													<span><span class="stats-metric-label">{t().statsTokens}</span>{tokenPair(work.tokensInStage1, work.tokensOutStage1)}</span>
												</span>
											</div>
										{/if}
										{#if work.interpretFallbackReason}
											<div class="stats-row">
												<span class="stats-key">{t().interpretFallbackBadge}</span>
												<span class="stats-value"><span>{t().interpretFallbackHint(work.interpretFallbackReason)}</span></span>
											</div>
										{/if}
										<!-- Three states, always shown: see CanvasPanel's drawer. -->
										<div class="stats-row">
											<span class="stats-key">{t().composeFallbackBadge}</span>
											<span class="stats-value"><span>{t().composeFallbackRecord(work.composeFallbackRecord)}{work.composeFallbackDrawnReason ? ` (${t().composeFallbackHint(work.composeFallbackDrawnReason)})` : ''}</span></span>
										</div>
										<div class="stats-row">
											<span class="stats-key">{t().statsStruct}</span>
											<span class="stats-value">
												<span><span class="stats-metric-label">{t().statsElapsed}</span>{(work.elapsedStage2Ms / 1000).toFixed(1)}s</span>
												<span><span class="stats-metric-label">{t().statsTokens}</span>{tokenPair(work.tokensInStage2, work.tokensOutStage2)}</span>
											</span>
										</div>
										<div class="stats-row stats-total">
											<span class="stats-key">{t().statsTotal}</span>
											<span class="stats-value">
												<span><span class="stats-metric-label">{t().statsElapsed}</span>{(work.elapsedTotalMs / 1000).toFixed(1)}s</span>
												<span><span class="stats-metric-label">{t().statsTokens}</span>{totalTokenPair(work.tokensInStage1, work.tokensOutStage1, work.tokensInStage2, work.tokensOutStage2)}</span>
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
				bind:exportMenuOpen
				bind:exportWrapEl
				exportCardOnly={!session.uiVisibility.work_tools}
				result={work.result}
				nearbyHistory={lineageState.nearby}
				onOpenNearbyHistory={openNearbyHistory}
				{unsavedRefinementPreview}
				{lineageIntermediateNotice}
				allowEmptyOutputTabs={work.inputMode === 'demo' || work.activeRunMode === 'demo'}
				{currentRenderedAt}
				navLatestDisabled={historyNavButtonsDisabled.latest}
				navNewerDisabled={historyNavButtonsDisabled.newer}
				navOlderDisabled={historyNavButtonsDisabled.older}
				interactionLocked={demoRunning}
				{historyTotal}
				{navPos}
				canvasAspectWidth={displayCanvasAspect.ratioW}
				canvasAspectHeight={displayCanvasAspect.ratioH}
				viewport={canvasViewport}
				{promptsData}
				stage1PromptText={work.stage1UserPrompt || (work.inputMode === 'single' ? work.input : work.inputMode === 'batch' ? batch.input : demo.generatedPrompt)}
				instructionText={work.currentInstructionText}
				ddl={work.ddl}
				{copiedPrompt}
				{scoreJsonText}
				{scoreJsonLines}
				{scoreJsonHighlighted}
				{scoreJsonSeparatorLine}
				{statusStage1Model}
				{statusStage2Model}
				{statusStage1ModelOnly}
				{statusStage2ModelOnly}
				visionModel={qualifiedModelId(visionProvider, visionModel)}
				{okugakiModel}
				visionProviderGroups={availableVisionModelCatalog}
				{statusCatalogName}
				{statusCanvasName}
				{statusGeneration}
				stageLabel={work.stageLabel}
				{statusHistoryItem}
				{statusHashLabel}
				{statusHashCopied}
				onGotoNext={gotoNext}
				onGotoPrev={gotoPrev}
				onGotoLatest={gotoLatest}
				onCopyPromptText={copyPromptText}
				onCopyStatusHash={copyStatusHash}
				onToggleStar={toggleHistoryStar}
				onToggleForRevision={toggleHistoryForRevision}
				onToggleForShare={toggleHistoryForShare}
				onReplayCurrent={() => {
					if (replayableStatusHistoryItem) return replayHistoryItem(replayableStatusHistoryItem, outputTab);
				}}
				replayDisabled={!replayableStatusHistoryItem || work.reloading}
				onDownloadSVG={downloadSVG}
				onDownloadPNG={downloadPNG}
				currentHistoryId={work.displayedHistoryItem?.id ?? work.result?.history_id ?? null}
				onDownloadCard={downloadCurrentCard}
				onVaryPerformance={refinement.varyPerformance}
				onVaryComposition={refinement.varyComposition}
				onVaryInterpretation={refinement.varyInterpretation}
				bind:instructionCaptionVisible
				onInstructionCaptionVisibleChange={persistInstructionCaptionVisible}
				{refinementSession}
				runTokensIn={work.activeRunTokensIn}
				runTokensOut={work.activeRunTokensOut}
				{modelInspection}
				bind:touchSeedText={work.touchSeedText}
				onGenerateVariationCandidates={refinement.generateVariationCandidates}
				onSaveSelectedVariationCandidates={refinement.saveSelectedVariationCandidates}
				onShowVariationCandidate={refinement.showVariationCandidate}
				{activeComparisonItem}
				lineageGraph={lineageState.graph}
				lineageLoading={lineageState.loading}
				lineageError={lineageState.error}
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
				statusDdlOrigin={work.statusDdlOrigin}
				statusTenkei={work.displayedHistoryItem?.tenkei ?? null}
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
				onLoadLineageOverview={() => lineageState.loadOverview(currentLineageNodeId)}
				onLoadLineageBranch={lineageState.loadBranch}
				onPaintOne={work.paintOne}
				onVisionAdvice={work.requestVisionRefineAdvice}
				pngTemplates={exportTemplates}
				animationExportSettings={exportSettings.animation}
				{apiFetch}
			/>
		</div><!-- /body -->

			{#if session.uiVisibility.history}
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
			{historyForShareOnly}
			onSetForShareOnly={setHistoryForShareOnly}
			{historyIndexLabel}
			{historyModelStage1Short}
			{historyModelStage1Full}
			{historyModelStage2Full}
			{formatHistoryDate}
			{catalogName}
			isJapanese={getLang() === 'ja'}
			{developerMode}
			historyStripFields={session.historyStripFields}
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
			stage1ModelLabel={work.stage1ModelLabel}
			stage2ModelLabel={work.stage2ModelLabel}
			drawingModelId={qualifiedModelId(stage2Provider, stage2Model)}
			drawingModelGroups={availableModelCatalog}
			onSelectDrawingModel={selectDdlDialogDrawingModel}
			runTokensIn={work.activeRunTokensIn}
			runTokensOut={work.activeRunTokensOut}
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
{#if settings.opened}
	{#await import('$lib/components/SettingsModal.svelte') then { default: SettingsModal }}
		<SettingsModal
			settings={settings}
			{singleUserMode}
			{stage1Provider}
			{stage1Model}
			{stage2Provider}
			{stage2Model}
			{visionProvider}
			{visionModel}
			providerGroups={settings.mode === 'model' ? availableModelCatalog : settings.modelCatalog}
			visionProviderGroups={availableVisionModelCatalog}
			allowVisionSelection={modelSelectionAllowVision}
			bind:includeThinking
			currentUser={session.currentUser}
			uiMode={session.uiMode}
			uiCustom={session.uiCustom}
			uiModeSaving={session.uiModeSaving}
			uiModeSaveError={session.uiModeSaveError}
			historyStripFields={session.historyStripFields}
			historyStripFieldsSaving={session.historyStripFieldsSaving}
			historyStripFieldsSaveError={session.historyStripFieldsSaveError}
			onToggleHistoryStripField={(field) => void session.updateHistoryStripFields(toggleHistoryStripField(session.historyStripFields, field))}
			onSetUiMode={(mode) => void session.updateUiMode(mode)}
			onSetUiCustomItem={(key, visible) => session.updateUiCustomItem(key, visible)}
			loginStatus={session.loginStatus}
			bind:loginUserName={session.loginUserName}
			bind:loginPassword={session.loginPassword}
			bind:autoRepairEnabled={work.ddlAutoRepairEnabled}
			bind:pngAlphaWhite={exportSettings.pngAlphaWhite}
			bind:animationExportSettings={exportSettings.animation}
			bind:cardExportSettings={exportSettings.card}
			{exportTemplates}
			{exportTemplateStatus}
			{canvasAspectEnabled}
			onSetCanvasAspectEnabled={setCanvasAspectEnabled}
			onChooseDownloadFolder={() => session.chooseDownloadFolder()}
			onClearDownloadFolder={() => session.clearDownloadFolder()}
			onSetStage1Provider={setStage1Provider}
			onSetStage1Model={setStage1Model}
			onSetStage2Provider={setStage2Provider}
			onSetStage2Model={setStage2Model}
			onSetVisionProvider={setVisionProvider}
			onSetVisionModel={setVisionModel}
			onLogin={() => session.login()}
			onLogout={() => session.logout()}
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

{#if session.profileOpen && session.currentUser}
		{#await import('$lib/components/ProfileModal.svelte') then { default: ProfileModal }}
			<ProfileModal
				username={session.currentUser.username}
				email={session.currentUser.email}
				generationCount={session.currentUser.image_generation_count}
				status={session.profileStatus}
			saving={session.profileSaving}
			bind:profileEmail={session.profileEmail}
			bind:profileCurrentPassword={session.profileCurrentPassword}
			bind:profileNewPassword={session.profileNewPassword}
			onClose={() => session.closeProfile()}
			onSave={() => session.saveProfile()}
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
			historyManagerForShareOnly={historyManager.forShareOnly}
			onClose={() => (historyManager.open = false)}
			onSetView={historyManager.setView}
			onSetPage={historyManager.setPage}
			onSetLatestPage={() => historyManager.setPage(0)}
			onSetFirstPage={() => historyManager.setPage(historyManager.totalPages - 1)}
			onSetPageSize={historyManager.setPageSize}
			onSetStarredOnly={historyManager.setStarredOnly}
			onSetForRevisionOnly={historyManager.setForRevisionOnly}
			onSetForShareOnly={historyManager.setForShareOnly}
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
			currentHistoryId={work.displayedHistoryItem?.id ?? work.result?.history_id ?? null}
			currentLineageRootId={work.displayedHistoryItem?.lineage_root_node_id ?? null}
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
			users={settings.userAdministration.users.map((u) => ({ id: u.id, name: u.username }))}
			groups={settings.userAdministration.groups.map((g) => ({ id: g.id, name: g.name }))}
			isJapanese={getLang() === 'ja'}
			onClose={() => (shareTarget = null)}
		/>
	{/await}
{/if}

{#if work.replayComparison}
	{#await import('$lib/components/ReplayComparisonModal.svelte') then { default: ReplayComparisonModal }}
		<ReplayComparisonModal
			originalSvg={work.replayComparison.originalSvg}
			replayedSvg={work.replayComparison.replayedSvg}
			recordedVersion={work.replayComparison.recordedVersion}
			currentVersion={work.replayComparison.currentVersion}
			versionMessage={work.replayComparison.versionMessage}
			provisionalSeed={work.replayComparison.provisionalSeed}
			onClose={closeReplayComparison}
		/>
	{/await}
{/if}

{#if confirmAction}
	<ConfirmDialog
		action={confirmAction}
		onCancel={() => { const cancel = confirmAction?.cancelRun; confirmAction = null; cancel?.(); }}
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
		/* Small-button dimensions for ghost and toolbar controls. They are
		   theme-independent, so define them once here and reference the tokens. */
		--btn-sm-font-size: 11px;
		--btn-sm-padding:   4px 10px;
		--btn-sm-radius:    var(--r);
		/* Amber colors for DDL controls. Build 739 replaced literals duplicated
		   across three components with these tokens, shared by both themes. */
		--ddl-btn-bg:           #fff7e8;
		--ddl-btn-border:       #d8b36a;
		--ddl-btn-fg:           #6c4a10;
		--ddl-btn-bg-hover:     #ffefd0;
		--ddl-btn-border-hover: #bd8f34;
		--ddl-btn-fg-hover:     #4f360b;
		--ddl-btn-shadow:       0 1px 3px rgba(108,74,16,0.12);
		/* A namespaced reference that this Server does not currently provide.
		   Avoid danger red: a later plugin may make the name valid. Amber says
		   "not available yet", rather than "incorrect". */
		--ddl-token-unknown-fg:     #8a5a12;
		--ddl-token-unknown-bg:     rgba(191, 136, 32, 0.12);
		--ddl-token-unknown-border: rgba(191, 136, 32, 0.42);
		/* Lineage path from the origin to a starred work. */
		--star-path:    #d97a1f;
		/* Starred-button colors. Five components duplicated the literals, while
		   only History Manager had dark-theme values; those values became canonical. */
		--star-fg:      #d59b21;
		--star-bg:      #fff6ce;
		--star-border:  rgba(213,155,33,0.45);
		/* Plate behind a star over a thumbnail. Its ground is the artwork's paper
		   in either theme, so it does not invert like --floating-control-*. */
		--thumb-plate-bg:     rgba(255,255,255,0.86);
		--thumb-plate-fg:     rgba(40,36,30,0.42);
		--thumb-plate-border: rgba(0,0,0,0.12);
		/* Numbers on the same plate need a darker foreground than the star. */
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
	.ui-hide-detail-status :global(.canvas-hash-btn),
	.ui-hide-detail-status :global(.canvas-provenance-btn),
	.ui-hide-work-tools :global(.right-tabs),
	/* The canvas corner rows are named button by button rather than as whole
	   rows. Two of the controls now standing there answer to detail_status and
	   not to work_tools, and a rule on the row would take them with it in any
	   custom mode that keeps one group and drops the other. */
	.ui-hide-work-tools :global(.canvas-caption-btn),
	.ui-hide-work-tools :global(.canvas-presentation-btn),
	.ui-hide-work-tools :global(.zoom-controls),
	.ui-hide-work-tools :global(.canvas-star-btn),
	.ui-hide-work-tools :global(.canvas-revision-btn),
	.ui-hide-work-tools :global(.canvas-share-btn),
	.ui-hide-work-tools :global(.canvas-replay-btn),
	.ui-hide-work-tools :global(.canvas-saijiki-btn),
	/* .canvas-export is deliberately absent. Hiding it took the share card with
	   SVG and PNG when the three merged into one door, and the card is not a
	   work tool -- it is how a work leaves for someone else. The button stays
	   and calls the card directly instead; CanvasPanel decides that from
	   exportCardOnly, so the rule here and the behaviour there must agree. */
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

	/* Sketching (Stage 0.5). Reads as prose, not as code: the instructions below it
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
	/* A limit taking effect is not a warning: nothing went wrong, a setting was
	   honoured. So it reads in the ordinary border, not the amber one. */
	.limit-notes {
		border: 1px solid var(--border);
		background: color-mix(in srgb, var(--bg2) 68%, transparent);
	}
	.limit-notes-title {
		color: var(--fg2);
		font-size: 11px;
		font-weight: 500;
		margin-bottom: 4px;
	}
	.limit-note-line {
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

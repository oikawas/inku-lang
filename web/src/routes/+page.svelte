<script module lang="ts">
	declare const __BUILD_NUMBER__: string;
</script>

<script lang="ts">
	import { onMount } from 'svelte';
	import { SAIJIKI } from '$lib/saijiki';
	import { annotate } from '$lib/highlight';
	import {
		PROVIDER_GROUPS,
		DEFAULT_PROVIDER,
		DEFAULT_MODEL,
		modelsForProvider,
		type Provider
	} from '$lib/models';
	import { t, setLang, getLang, PACK_LIST, initLang } from '$lib/i18n/index.svelte';
	import { COLOR_CATALOGS, getCatalogById, getColorMap, type ColorMap } from '$lib/colors';

	const HISTORY_PAGE_SIZE = 20;
	const PROVIDER_STAGE1_KEY = 'inku-provider-stage1';
	const MODEL_STAGE1_KEY    = 'inku-model-stage1';
	const PROVIDER_STAGE2_KEY = 'inku-provider-stage2';
	const MODEL_STAGE2_KEY    = 'inku-model-stage2';
	const CATALOG_KEY         = 'inku-color-catalog';

	type Score = { instructions: unknown[] };

	type PaintResult = {
		svg: string;
		score: Score;
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

	type PluginItem = {
		id: string;
		name: string;
		version: string;
		enabled: boolean;
	};

	// ── Input ───────────────────────────────────────────────
	let inputMode   = $state<'single' | 'batch'>('single');
	let input       = $state('山の向こうに月が昇る');
	let batchInput  = $state('');
	let textareaEl  = $state<HTMLTextAreaElement | null>(null);

	// ── Loading ─────────────────────────────────────────────
	let loading    = $state(false);
	let stageLabel = $state('');
	let batchCurrent = $state(0);
	let batchTotal   = $state(0);
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
	let settingsOpen = $state(false);
	let settingsTab  = $state<'connection' | 'db' | 'plugins'>('connection');
	let pngMenuOpen  = $state(false);
	let catalogOpen  = $state(false);
	let statsOpen    = $state(false);
	let outputTab    = $state<'canvas' | 'prompts' | 'score'>('canvas');
	let ddlEditing   = $state(false);
	let baseDDL      = $state<string | null>(null);
	let zoom         = $state(1);
	let promptStage1Expanded = $state(false);
	let promptStage2Expanded = $state(false);

	// DOM refs for outside-click handling
	let pngWrapEl      = $state<HTMLDivElement | null>(null);

	// ── Color catalog ────────────────────────────────────────
	let selectedCatalog = $state('default');
	const currentCatalog = $derived(getCatalogById(selectedCatalog) ?? COLOR_CATALOGS[0]);

	function activeColorMap(): ColorMap | null {
		if (selectedCatalog === 'default') return null;
		return getColorMap(selectedCatalog);
	}

	function isLightColor(hex: string): boolean {
		const value = hex.replace('#', '');
		const r = parseInt(value.slice(0, 2), 16);
		const g = parseInt(value.slice(2, 4), 16);
		const b = parseInt(value.slice(4, 6), 16);
		return (r * 299 + g * 587 + b * 114) / 1000 > 224;
	}

	// ── Settings tabs ────────────────────────────────────────
	let dbType = $state<'sqlite' | 'postgres'>('sqlite');
	let sqlitePath = $state('~/.local/share/inku/inku.db');
	let pgHost = $state('');
	let pgPort = $state('5432');
	let pgUser = $state('');
	let pgPassword = $state('');
	let pgDatabase = $state('');
	let showPgPassword = $state(false);
	let dbTestResult = $state<string | null>(null);
	let plugins = $state<PluginItem[]>([
		{ id: 'nature', name: 'inku-nature', version: 'v0.1.0', enabled: true },
		{ id: 'bamboo', name: 'inku-bamboo', version: 'v0.1.0', enabled: false },
	]);
	let pluginAddOpen = $state(false);
	let pluginPath = $state('');
	let pluginPendingDelete = $state<PluginItem | null>(null);

	function testDbConnection() {
		dbTestResult = dbType === 'sqlite'
			? `SQLite path is set: ${sqlitePath || '(empty)'}`
			: pgHost && pgUser && pgDatabase
				? `Ready to test PostgreSQL at ${pgHost}:${pgPort}`
				: 'PostgreSQL settings are incomplete.';
	}

	function addPlugin() {
		const name = pluginPath.trim();
		if (!name) return;
		plugins = [...plugins, { id: `${Date.now()}`, name, version: 'local', enabled: true }];
		pluginPath = '';
		pluginAddOpen = false;
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

	// ── Snapshots ───────────────────────────────────────────
	type SnapshotMeta = { id: string; name: string; at: number };
	let snapshots       = $state<SnapshotMeta[]>([]);
	let activeSnapshotId = $state<string | null>(null);

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
	let historyPage  = $state(0);
	let historyCursor = $state(-1);
	const historyTotalPages = $derived(Math.ceil(historyTotal / HISTORY_PAGE_SIZE));
	let historyManagerOpen = $state(false);
	let historyManagerView = $state<'active' | 'trash'>('active');
	let trashItems = $state<Iteration[]>([]);
	let trashTotal = $state(0);
	let historySearch = $state('');
	let selectedHistoryIds = $state<string[]>([]);
	let confirmAction = $state<{ message: string; run: () => void; destructive?: boolean } | null>(null);
	const managedHistoryItems = $derived(historyManagerView === 'trash' ? trashItems : historyItems);
	const filteredManagedHistory = $derived.by(() => {
		const q = historySearch.trim().toLowerCase();
		if (!q) return managedHistoryItems;
		return managedHistoryItems.filter((it) =>
			[it.input, it.ddl ?? '', it.stage1_model ?? '', it.stage2_model ?? '', it.catalog_id ?? '']
				.some((v) => v.toLowerCase().includes(q))
		);
	});

	let promptsData = $state<{ stage1_system: string; stage2_system: string } | null>(null);

	// ── Batch derived ────────────────────────────────────────
	const batchLines    = $derived(batchInput.split('\n'));
	const lineNumbersText = $derived(batchLines.map((_, i) => String(i + 1)).join('\n'));
	const batchNonEmpty = $derived(batchLines.filter((l) => l.trim()).length);
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

	// ── Core paint (2-stage) ─────────────────────────────────
	async function paintOne(text: string): Promise<{ ddl: string; thinking: string | null } & PaintResult> {
		const t0  = Date.now();
		const lang = getLang();
		stageLabel = t().stageInterpreting;

		const augmented = text + buildEmotionHint(text);
		const r1 = await fetch('/api/interpret', {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({ text: augmented, model: stage1Model, include_thinking: includeThinking, snapshot_id: activeSnapshotId, lang })
		});
		if (!r1.ok) {
			const d = await r1.json().catch(() => ({})) as { detail?: string };
			throw new Error(d.detail ?? `HTTP ${r1.status}`);
		}
		const d1 = await r1.json() as { ddl: string; thinking: string | null; tokens_in: number | null; tokens_out: number | null };
		const t1  = Date.now();
		const tokLabel = d1.tokens_in != null ? ` (${d1.tokens_in}→${d1.tokens_out ?? '?'}tok)` : '';

		stageLabel = t().stageStructuring(tokLabel);
		const r2 = await fetch('/api/compose', {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({ ddl: d1.ddl, model: stage2Model, original_text: text, snapshot_id: activeSnapshotId, lang, color_map: activeColorMap() })
		});
		if (!r2.ok) {
			const d = await r2.json().catch(() => ({})) as { detail?: string };
			throw new Error(d.detail ?? `HTTP ${r2.status}`);
		}
		const d2 = await r2.json() as { score: Score; svg: string; tokens_in: number | null; tokens_out: number | null };
		const t2  = Date.now();

		return {
			ddl: d1.ddl, thinking: d1.thinking, score: d2.score, svg: d2.svg,
			elapsed_stage1_ms: t1 - t0, elapsed_stage2_ms: t2 - t1, elapsed_total_ms: t2 - t0,
			tokens_in_stage1: d1.tokens_in, tokens_out_stage1: d1.tokens_out,
			tokens_in_stage2: d2.tokens_in, tokens_out_stage2: d2.tokens_out,
		};
	}

	// ── Submit ──────────────────────────────────────────────
	async function submit() {
		if (!canSubmit || loading) return;
		loading = true; error = null;
		ddl = null; thinking = null; baseDDL = null; ddlEditing = false;
		elapsedStage1Ms = 0; elapsedStage2Ms = 0; elapsedTotalMs = 0;
		tokensInStage1 = null; tokensOutStage1 = null; tokensInStage2 = null; tokensOutStage2 = null;
		batchCurrent = 0; batchTotal = 0;
		startTimer();

		try {
			if (inputMode === 'single') {
				const r = await paintOne(input);
				ddl = r.ddl; thinking = r.thinking; result = r; outputTab = 'canvas';
				elapsedStage1Ms = r.elapsed_stage1_ms; elapsedStage2Ms = r.elapsed_stage2_ms; elapsedTotalMs = r.elapsed_total_ms;
				tokensInStage1 = r.tokens_in_stage1; tokensOutStage1 = r.tokens_out_stage1;
				tokensInStage2 = r.tokens_in_stage2; tokensOutStage2 = r.tokens_out_stage2;
				const totalIn  = (r.tokens_in_stage1 ?? 0)  + (r.tokens_in_stage2 ?? 0);
				const totalOut = (r.tokens_out_stage1 ?? 0) + (r.tokens_out_stage2 ?? 0);
				await pushHistory({ input, ddl: r.ddl, thinking: r.thinking, score: r.score, svg: r.svg, at: Date.now(), elapsed_ms: r.elapsed_total_ms, stage1_model: stage1Model, stage2_model: stage2Model, tokens_in: totalIn || null, tokens_out: totalOut || null, catalog_id: selectedCatalog !== 'default' ? selectedCatalog : null });
			} else {
				const lines = batchLines.map((l) => l.trim()).filter((l) => l);
				batchTotal = lines.length; outputTab = 'canvas';
				for (let i = 0; i < lines.length; i++) {
					if (!loading) break;
					batchCurrent = i + 1;
					try {
						const r = await paintOne(lines[i]);
						result = r;
						const totalIn  = (r.tokens_in_stage1 ?? 0)  + (r.tokens_in_stage2 ?? 0);
						const totalOut = (r.tokens_out_stage1 ?? 0) + (r.tokens_out_stage2 ?? 0);
						await pushHistory({ input: `#${i + 1} ${lines[i]}`, ddl: r.ddl, thinking: r.thinking, score: r.score, svg: r.svg, at: Date.now(), elapsed_ms: r.elapsed_total_ms, stage1_model: stage1Model, stage2_model: stage2Model, tokens_in: totalIn || null, tokens_out: totalOut || null, catalog_id: selectedCatalog !== 'default' ? selectedCatalog : null });
					} catch { /* continue */ }
				}
				elapsedTotalMs = Date.now() - _timerStart;
			}
		} catch (e) {
			error = e instanceof Error ? e.message : String(e); result = null;
		} finally {
			stopTimer(); loading = false; stageLabel = ''; batchCurrent = 0; batchTotal = 0;
		}
	}

	function stopBatch() { loading = false; }

	// ── Replay (Stage 2 のみ) ────────────────────────────────
	async function replay() {
		if (!ddl || reloading) return;
		reloading = true; reloadError = null;
		const lang = getLang();
		try {
			const r = await fetch('/api/compose', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ ddl, model: stage2Model, original_text: input, snapshot_id: activeSnapshotId, lang, color_map: activeColorMap() })
			});
			if (!r.ok) {
				const d = await r.json().catch(() => ({})) as { detail?: string };
				throw new Error(d.detail ?? `HTTP ${r.status}`);
			}
			const d = await r.json() as { score: Score; svg: string; tokens_in: number | null; tokens_out: number | null };
			result = result
				? { ...result, score: d.score, svg: d.svg }
				: { score: d.score, svg: d.svg, elapsed_stage1_ms: 0, elapsed_stage2_ms: 0, elapsed_total_ms: 0, tokens_in_stage1: null, tokens_out_stage1: null, tokens_in_stage2: d.tokens_in, tokens_out_stage2: d.tokens_out };
			outputTab = 'canvas';
		} catch (e) {
			reloadError = e instanceof Error ? e.message : String(e);
		} finally {
			reloading = false;
		}
	}

	// ── History ─────────────────────────────────────────────
	async function fetchHistoryPage(page: number): Promise<void> {
		const offset = page * HISTORY_PAGE_SIZE;
		try {
			const r = await fetch(`/api/history?offset=${offset}&limit=${HISTORY_PAGE_SIZE}`);
			if (!r.ok) return;
			const data = await r.json();
			historyItems = data.items; historyTotal = data.total; historyPage = page;
		} catch { /* ignore */ }
	}

	async function fetchTrashPage(): Promise<void> {
		try {
			const r = await fetch(`/api/history?offset=0&limit=100&trashed=true`);
			if (!r.ok) return;
			const data = await r.json();
			trashItems = data.items; trashTotal = data.total;
		} catch { /* ignore */ }
	}

	async function pushHistory(it: Iteration): Promise<void> {
		try {
			await fetch('/api/history', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ input: it.input, ddl: it.ddl, score: it.score, svg: it.svg, at: it.at, elapsed_ms: it.elapsed_ms ?? 0, stage1_model: it.stage1_model ?? null, stage2_model: it.stage2_model ?? null, tokens_in: it.tokens_in ?? null, tokens_out: it.tokens_out ?? null, catalog_id: it.catalog_id ?? null })
			});
		} catch { /* ignore */ }
		await fetchHistoryPage(0);
		historyCursor = 0;
	}

	function clearInput() {
		if (inputMode === 'single') input = ''; else batchInput = '';
	}

	function toggleHistorySelection(id: string) {
		selectedHistoryIds = selectedHistoryIds.includes(id)
			? selectedHistoryIds.filter((x) => x !== id)
			: [...selectedHistoryIds, id];
	}

	function selectAllManagedHistory() {
		const ids = filteredManagedHistory.map((it) => it.id).filter((id): id is string => !!id);
		selectedHistoryIds = selectedHistoryIds.length === ids.length ? [] : ids;
	}

	async function postHistoryIds(path: string, ids: string[]) {
		await fetch(path, {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({ ids })
		});
		selectedHistoryIds = [];
		await Promise.all([fetchHistoryPage(historyPage), fetchTrashPage()]);
		if (historyItems.length === 0 && historyPage > 0) await fetchHistoryPage(historyPage - 1);
	}

	function askTrash(ids: string[]) {
		if (ids.length === 0) return;
		confirmAction = {
			message: `${ids.length}件をごみ箱に移動しますか？`,
			run: () => { void postHistoryIds('/api/history/trash', ids); }
		};
	}

	function askRestore(ids: string[]) {
		if (ids.length === 0) return;
		confirmAction = {
			message: `${ids.length}件を復元しますか？`,
			run: () => { void postHistoryIds('/api/history/restore', ids); }
		};
	}

	function askPermanentDelete(ids: string[]) {
		if (ids.length === 0) return;
		confirmAction = {
			message: `${ids.length}件を完全に削除しますか？`,
			destructive: true,
			run: () => { void postHistoryIds('/api/history/permanent-delete', ids); }
		};
	}

	type DiffPart = { text: string; changed: boolean };
	function diffDDL(base: string, current: string): DiffPart[] {
		const m = base.length, n = current.length;
		const dp: Uint16Array[] = Array.from({ length: m + 1 }, () => new Uint16Array(n + 1));
		for (let i = 1; i <= m; i++)
			for (let j = 1; j <= n; j++)
				dp[i][j] = base[i - 1] === current[j - 1] ? dp[i - 1][j - 1] + 1 : Math.max(dp[i - 1][j], dp[i][j - 1]);
		const chars: DiffPart[] = [];
		let i = m, j = n;
		while (i > 0 || j > 0) {
			if (i > 0 && j > 0 && base[i - 1] === current[j - 1]) { chars.push({ text: current[j - 1], changed: false }); i--; j--; }
			else if (j > 0 && (i === 0 || dp[i][j - 1] >= dp[i - 1][j])) { chars.push({ text: current[j - 1], changed: true }); j--; }
			else { i--; }
		}
		chars.reverse();
		const parts: DiffPart[] = [];
		for (const c of chars) {
			const last = parts[parts.length - 1];
			if (last && last.changed === c.changed) last.text += c.text;
			else parts.push({ text: c.text, changed: c.changed });
		}
		return parts;
	}

	function loadIteration(idx: number) {
		if (idx < 0 || idx >= historyItems.length) return;
		historyCursor = idx; ddlEditing = false;
		const it = historyItems[idx];
		input = it.input; ddl = it.ddl; baseDDL = it.ddl; thinking = it.thinking ?? null;
		result = { score: it.score, svg: it.svg, elapsed_stage1_ms: 0, elapsed_stage2_ms: 0, elapsed_total_ms: it.elapsed_ms ?? 0, tokens_in_stage1: null, tokens_out_stage1: null, tokens_in_stage2: null, tokens_out_stage2: null };
		error = null;
	}

	const currentRenderedAt = $derived(
		historyCursor >= 0 && historyItems[historyCursor]
			? new Date(historyItems[historyCursor].at).toLocaleString(getLang() === 'ja' ? 'ja-JP' : 'en-US')
			: null
	);

	async function gotoPrev() {
		if (historyCursor < historyItems.length - 1) { loadIteration(historyCursor + 1); }
		else if (historyPage < historyTotalPages - 1) { await fetchHistoryPage(historyPage + 1); loadIteration(0); }
	}
	async function gotoNext() {
		if (historyCursor > 0) { loadIteration(historyCursor - 1); }
		else if (historyPage > 0) { await fetchHistoryPage(historyPage - 1); loadIteration(historyItems.length - 1); }
	}

	const prevDisabled = $derived(historyCursor >= historyItems.length - 1 && historyPage >= historyTotalPages - 1);
	const nextDisabled = $derived(historyCursor <= 0 && historyPage <= 0);
	const navPos       = $derived(historyPage * HISTORY_PAGE_SIZE + historyCursor + 1);

	// ── Saijiki ─────────────────────────────────────────────
	function insertWord(word: string) {
		if (inputMode === 'batch') { batchInput = batchInput ? batchInput + word : word; return; }
		const ta = textareaEl;
		if (!ta) { input = input + word; return; }
		const start = ta.selectionStart ?? input.length;
		const end   = ta.selectionEnd   ?? input.length;
		input = input.slice(0, start) + word + input.slice(end);
		requestAnimationFrame(() => {
			if (!textareaEl) return;
			textareaEl.focus();
			const pos = start + word.length;
			textareaEl.setSelectionRange(pos, pos);
		});
	}

	function handleKeydown(e: KeyboardEvent) {
		if (e.key === 'Escape') { saijikiOpen = false; settingsOpen = false; catalogOpen = false; historyManagerOpen = false; confirmAction = null; }
	}

	function handleDocClick(e: MouseEvent) {
		if (pngMenuOpen  && pngWrapEl     && !pngWrapEl.contains(e.target as Node))      pngMenuOpen  = false;
	}

	// ── Model selection ─────────────────────────────────────
	function setStage1Provider(v: Provider) {
		stage1Provider = v; stage1Model = modelsForProvider(v)[0]?.id ?? stage1Model;
		try { localStorage.setItem(PROVIDER_STAGE1_KEY, v); localStorage.setItem(MODEL_STAGE1_KEY, stage1Model); } catch {}
	}
	function setStage1Model(v: string) {
		stage1Model = v; try { localStorage.setItem(MODEL_STAGE1_KEY, v); } catch {}
	}
	function setStage2Provider(v: Provider) {
		stage2Provider = v; stage2Model = modelsForProvider(v)[0]?.id ?? stage2Model;
		try { localStorage.setItem(PROVIDER_STAGE2_KEY, v); localStorage.setItem(MODEL_STAGE2_KEY, stage2Model); } catch {}
	}
	function setStage2Model(v: string) {
		stage2Model = v; try { localStorage.setItem(MODEL_STAGE2_KEY, v); } catch {}
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
				ctx.fillStyle = '#ffffff'; ctx.fillRect(0, 0, size, size);
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

	// ── Snapshots ───────────────────────────────────────────
	async function fetchSnapshots() {
		try { const r = await fetch('/api/saijiki/snapshots'); if (r.ok) snapshots = await r.json(); } catch {}
	}

	// ── Prompts ─────────────────────────────────────────────
	async function fetchPrompts(): Promise<void> {
		try { const r = await fetch(`/api/prompts?lang=${getLang()}`); if (r.ok) promptsData = await r.json(); } catch {}
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

	function catalogName(id: string | null | undefined): string {
		return getCatalogById(id ?? 'default')?.name ?? 'inku Default';
	}

	function formatHistoryDate(at: number): string {
		return new Date(at).toLocaleString(getLang() === 'ja' ? 'ja-JP' : 'en-US');
	}

	const tokenSummary = $derived.by(() =>
		t().tokenSummary(tokensInStage1, tokensOutStage1, tokensInStage2, tokensOutStage2)
	);

	// ── Stats string ─────────────────────────────────────────
	const statsLine = $derived.by(() => {
		if (!result) return '';
		const s1 = (result.elapsed_stage1_ms / 1000).toFixed(1);
		const s2 = (result.elapsed_stage2_ms / 1000).toFixed(1);
		const total = (result.elapsed_total_ms / 1000).toFixed(1);
		if (result.elapsed_stage1_ms > 0) return `解釈 ${s1}s + 構造化 ${s2}s = ${total}s`;
		return `${total}s`;
	});

	const visibleThumbCount = $derived(Math.max(1, Math.floor((windowWidth - 40) / 89)));

	// ── Mount ───────────────────────────────────────────────
	onMount(() => {
		windowWidth = window.innerWidth;
		function onResize() { windowWidth = window.innerWidth; }
		window.addEventListener('resize', onResize);

		initLang();
		void (async () => {
			await Promise.all([fetchHistoryPage(0), fetchTrashPage(), fetchSnapshots(), fetchPrompts()]);
			if (historyItems.length > 0) loadIteration(0);
		})();
		try {
			const p1 = localStorage.getItem(PROVIDER_STAGE1_KEY) as Provider | null; if (p1) stage1Provider = p1;
			const m1 = localStorage.getItem(MODEL_STAGE1_KEY); if (m1) stage1Model = m1;
			const p2 = localStorage.getItem(PROVIDER_STAGE2_KEY) as Provider | null; if (p2) stage2Provider = p2;
			const m2 = localStorage.getItem(MODEL_STAGE2_KEY); if (m2) stage2Model = m2;
			const cat = localStorage.getItem(CATALOG_KEY); if (cat) selectedCatalog = cat;
		} catch {}

		return () => window.removeEventListener('resize', onResize);
	});

	$effect(() => { const _lang = getLang(); fetchPrompts(); });
</script>

<svelte:window onkeydown={handleKeydown} onclick={handleDocClick} />

<!-- ══════════════════════════════════════════════════════════ -->
<!--  ROOT                                                       -->
<!-- ══════════════════════════════════════════════════════════ -->
<div class="root">

	<!-- ══ HEADER ══ -->
	<header class="header">
		<div class="logo-area">
			<div class="logo">inku</div>
			<div class="logo-sub">{t().subtitle}</div>
		</div>

		<div class="header-right">
			<button
				class="settings-btn"
				class:active={settingsOpen}
				onclick={() => { settingsTab = 'connection'; settingsOpen = true; }}
			>⚙ 接続設定</button>

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
		{#if loading || reloading}
			<div class="flying-bird-layer" aria-hidden="true">
				<div class="flying-bird-y">
					<div class="flying-bird-x">
						<svg class="flying-bird" width="38" height="28" viewBox="0 0 38 28">
							<ellipse cx="18" cy="17" rx="8" ry="5" fill="#6b7b2a" opacity="0.92" />
							<path d="M25,18 Q31,22 30,16" fill="#4a5820" opacity="0.85" />
							<path d="M10,15.5 L6,13.5" stroke="#b8940a" stroke-width="1.5" fill="none" stroke-linecap="round" />
							<circle cx="12" cy="14.5" r="1.5" fill="#fff" />
							<circle cx="12.4" cy="14.5" r="0.7" fill="#1a1917" />
							<path fill="#8b9b3a" opacity="0.88">
								<animate attributeName="d" values="M14,17 Q19,6 24,17;M14,17 Q19,26 24,17;M14,17 Q19,6 24,17" dur="0.38s" repeatCount="indefinite" />
							</path>
							<path fill="#a8b855" opacity="0.5">
								<animate attributeName="d" values="M15,16 Q19,9 23,16;M15,16 Q19,23 23,16;M15,16 Q19,9 23,16" dur="0.38s" repeatCount="indefinite" />
							</path>
						</svg>
					</div>
				</div>
			</div>
		{/if}

		<!-- ── LEFT PANEL ── -->
		<div class="left-panel">
			<!-- Input mode tabs -->
			<div class="panel-tabs">
				{#each [['single', t().modeSingle], ['batch', t().modeBatch]] as [mode, label] (mode)}
					<button class="panel-tab" class:active={inputMode === mode} onclick={() => (inputMode = mode as 'single' | 'batch')}>{label}</button>
				{/each}
			</div>

			<div class="panel-scroll">

				<!-- 指示 section -->
				<section class="panel-section">
					<div class="section-head">
						<span class="section-label">指示</span>
						<div class="section-actions">
							<button class="ghost-btn" onclick={() => (saijikiOpen = !saijikiOpen)}>歳時記</button>
							<button class="ghost-btn" onclick={() => (catalogOpen = true)}>カタログ設定</button>
							<button class="ghost-btn" onclick={clearInput}>新規作成</button>
						</div>
					</div>

					{#if inputMode === 'single'}
						<textarea
							bind:this={textareaEl}
							bind:value={input}
							rows="5"
							spellcheck="false"
							placeholder={t().inputPlaceholder}
							class="input-ta"
						></textarea>
					{:else}
						<div class="batch-wrap">
							<div class="line-nums" aria-hidden="true">{lineNumbersText}</div>
							<textarea class="batch-ta" bind:value={batchInput} rows="5" spellcheck="false" placeholder={t().batchPlaceholder}></textarea>
						</div>
						{#if batchNonEmpty > 0}<p class="batch-info">{t().batchCount(batchNonEmpty)}</p>{/if}
					{/if}

					<!-- 描画する / progress -->
					{#if loading && inputMode === 'single'}
						<div class="progress-wrap">
							<div class="progress-phases">
								{#each ['解釈', '構造化'] as ph, i (ph)}
									{#if i > 0}<span class="phase-sep">›</span>{/if}
									<span class="phase-item" class:phase-done={stageLabel.includes('構造化') && ph === '解釈'} class:phase-active={stageLabel.includes(ph === '解釈' ? '解釈' : '構造化') && !(stageLabel.includes('構造化') && ph === '解釈')}>
										{#if stageLabel.includes('構造化') && ph === '解釈'}<span class="phase-check">✓</span>{/if}
										{#if !(stageLabel.includes('構造化') && ph === '解釈') && stageLabel.includes(ph === '解釈' ? '解釈' : '構造化')}<span class="phase-dot"></span>{/if}
										{ph}
									</span>
								{/each}
							</div>
							<div class="progress-right">
								<span class="progress-time">{(liveMs / 1000).toFixed(1)}s</span>
								<button class="stop-sm" onclick={stopBatch}>{t().stopBtn}</button>
							</div>
						</div>
						<div class="progress-bar-track">
							<div class="progress-bar-fill" style="width: {stageLabel.includes('構造化') ? '65' : '30'}%"></div>
							<svg class="progress-bird" class:done={!loading} width="8" height="6" viewBox="0 0 8 6" aria-hidden="true">
								<path fill="none" stroke="#6b7b2a" stroke-width="1.2" opacity="0.7">
									<animate attributeName="d" values="M0,3 Q2,1 4,3 Q6,1 8,3;M0,3 Q2,5 4,3 Q6,5 8,3;M0,3 Q2,1 4,3 Q6,1 8,3" dur="0.4s" repeatCount="indefinite" />
								</path>
							</svg>
						</div>
						<div class="progress-stage-text">{stageLabel}</div>
					{:else if loading && batchTotal > 0}
						<div class="batch-progress">
							<span>{t().batchProgress(batchCurrent, batchTotal)}</span>
							<span class="progress-time">{(liveMs / 1000).toFixed(1)}s</span>
							<button class="stop-sm" onclick={stopBatch}>{t().stopBtn}</button>
						</div>
					{:else}
						<button class="play-btn" onclick={submit} disabled={!canSubmit}>▶ <span>{t().submitBtn}</span></button>
					{/if}

					{#if error}<p class="error-text">{error}</p>{/if}
				</section>

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
				{#if ddl !== null}
					<section class="panel-section">
						<div class="section-head">
							<span class="section-label">{t().ddlLabel}</span>
							{#if historyCursor >= 0}
								<button class="ghost-btn" class:ghost-active={ddlEditing} onclick={() => (ddlEditing = !ddlEditing)}>{ddlEditing ? t().ddlDoneBtn : t().ddlEditBtn}</button>
							{/if}
						</div>
						{#if ddlEditing}
							<textarea class="ddl-edit-ta" bind:value={ddl} rows="4" spellcheck="false"></textarea>
						{:else}
							<div class="annot-box ddl-box">
								{#if baseDDL !== null && baseDDL !== ddl}
									{#each diffDDL(baseDDL, ddl) as part, i (i)}<span class={part.changed ? 'tok tok-diff-added' : 'tok tok-plain'}>{part.text}</span>{/each}
								{:else}
									{#each annotate(ddl) as part, i (i)}
										{#if part.kind === 'saijiki'}<span class="tok tok-saijiki" title={part.category}>{part.text}</span>
										{:else if part.kind === 'emotion'}<span class="tok tok-emotion">{part.text}</span>
										{:else}<span class="tok tok-plain">{part.text}</span>{/if}
									{/each}
								{/if}
							</div>
						{/if}

						<!-- 描画（解釈から） progress -->
						{#if reloading}
							<div class="progress-wrap">
								<div class="progress-phases">
									<span class="phase-item phase-active"><span class="phase-dot"></span>構造化</span>
								</div>
								<div class="progress-right">
									<span class="progress-time">…</span>
								</div>
							</div>
							<div class="progress-bar-track">
								<div class="progress-bar-fill" style="width: 55%"></div>
								<svg class="progress-bird" width="8" height="6" viewBox="0 0 8 6" aria-hidden="true">
									<path fill="none" stroke="#6b7b2a" stroke-width="1.2" opacity="0.7">
										<animate attributeName="d" values="M0,3 Q2,1 4,3 Q6,1 8,3;M0,3 Q2,5 4,3 Q6,5 8,3;M0,3 Q2,1 4,3 Q6,1 8,3" dur="0.4s" repeatCount="indefinite" />
									</path>
								</svg>
							</div>
						{/if}
						{#if reloadError}<p class="error-text">{reloadError}</p>{/if}

						<button
							class="replay-btn"
							onclick={replay}
							disabled={reloading || !ddl}
						>↺ 描画（解釈から）</button>
					</section>
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
										<span class="stats-key">解釈</span><span>{(elapsedStage1Ms / 1000).toFixed(1)}s{tokensInStage1 != null ? ` — ${tokensInStage1}→${tokensOutStage1}tok` : ''}</span>
										<span class="stats-key">構造化</span><span>{(elapsedStage2Ms / 1000).toFixed(1)}s{tokensInStage2 != null ? ` — ${tokensInStage2}→${tokensOutStage2}tok` : ''}</span>
										<span class="stats-key">合計</span><span class="stats-total">{(elapsedTotalMs / 1000).toFixed(1)}s</span>
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

		<!-- ── RIGHT PANEL ── -->
		<div class="right-panel">

			<!-- Tab bar -->
			<div class="right-tabs">
				<button class="rtab" class:active={outputTab === 'canvas'}  onclick={() => (outputTab = 'canvas')}>{t().tabCanvas}</button>
				<button class="rtab" class:active={outputTab === 'prompts'} onclick={() => (outputTab = 'prompts')} disabled={!result}>{t().tabPrompts}</button>
				<button class="rtab" class:active={outputTab === 'score'}   onclick={() => (outputTab = 'score')}   disabled={!result}>{t().tabScore}</button>
				<div class="rtab-spacer"></div>
				{#if currentRenderedAt}
					<span class="rendered-at">{currentRenderedAt}</span>
				{/if}
			</div>

			<!-- Canvas area -->
			<div class="canvas-area">

				<!-- Prev nav (newer items = left) -->
				<div class="nav-left">
					<button class="nav-circle" onclick={gotoNext} disabled={nextDisabled}>‹</button>
				</div>

				<!-- Content -->
				<div class="canvas-content">
					{#if outputTab === 'canvas'}
						<div
							class="canvas-box"
							style="transform: scale({zoom}); transform-origin: center center; transition: transform 0.15s;"
						>
							{#if result}
								{@html result.svg}
							{:else}
								<div class="canvas-placeholder">{t().canvasPlaceholder}</div>
							{/if}
						</div>
					{:else if outputTab === 'prompts'}
						{#if promptsData}
							<div class="prompt-section">
								<p class="prompt-label">{t().promptStage1Input}</p>
								<textarea class="prompt-textarea prompt-user" readonly value={inputMode === 'single' ? input : `(${t().modeBatch})`}></textarea>
								<div class="prompt-collapsible-head">
									<p class="prompt-label">{t().promptStage1System}</p>
									<button class="ghost-btn" onclick={() => (promptStage1Expanded = !promptStage1Expanded)}>{promptStage1Expanded ? '折りたたむ' : '展開'}</button>
								</div>
								<div class="prompt-collapse" class:expanded={promptStage1Expanded}>
									<textarea class="prompt-textarea prompt-system" readonly value={promptsData.stage1_system}></textarea>
									{#if !promptStage1Expanded}<div class="prompt-fade"></div>{/if}
								</div>
								{#if ddl}
									<p class="prompt-label">{t().promptStage2Input}</p>
									<textarea class="prompt-textarea prompt-user" readonly value={ddl}></textarea>
								{/if}
								<div class="prompt-collapsible-head">
									<p class="prompt-label">{t().promptStage2System}</p>
									<button class="ghost-btn" onclick={() => (promptStage2Expanded = !promptStage2Expanded)}>{promptStage2Expanded ? '折りたたむ' : '展開'}</button>
								</div>
								<div class="prompt-collapse" class:expanded={promptStage2Expanded}>
									<textarea class="prompt-textarea prompt-system" readonly value={promptsData.stage2_system}></textarea>
									{#if !promptStage2Expanded}<div class="prompt-fade"></div>{/if}
								</div>
							</div>
						{:else}
							<p class="muted-center">{t().promptLoading}</p>
						{/if}
					{:else if outputTab === 'score'}
						<pre class="score-pre">{JSON.stringify(result?.score, null, 2)}</pre>
					{/if}
				</div>

				<!-- Zoom controls (canvas tab only) -->
				{#if outputTab === 'canvas'}
					<div class="zoom-controls">
						<button onclick={() => (zoom = Math.max(0.5, +(zoom - 0.25).toFixed(2)))}>−</button>
						<span class="zoom-pct">{Math.round(zoom * 100)}%</span>
						<button onclick={() => (zoom = Math.min(3, +(zoom + 0.25).toFixed(2)))}>＋</button>
						<button class="zoom-reset" onclick={() => (zoom = 1)}>⊙</button>
					</div>
				{/if}

				<!-- Next nav (older items = right) -->
				<div class="nav-right">
					<button class="nav-circle" onclick={gotoPrev} disabled={prevDisabled}>›</button>
					{#if historyTotal > 0}
						<span class="nav-counter">{navPos} / {historyTotal}</span>
					{/if}
				</div>

			</div><!-- /canvas-area -->

			<!-- Export bar -->
			<div class="export-bar">
				<span class="export-label">エクスポート</span>
				<button class="ghost-btn" onclick={downloadSVG} disabled={!result}>↓ SVG</button>
				<div class="png-wrap" bind:this={pngWrapEl}>
					<button class="ghost-btn" onclick={(e) => { e.stopPropagation(); pngMenuOpen = !pngMenuOpen; }} disabled={!result}>↓ PNG ▾</button>
					{#if pngMenuOpen}
						<div class="png-menu" onclick={(e) => e.stopPropagation()}>
							{#each [[1080,'標準'],[2160,'高解像度 (2×)'],[1024,'正方形'],[2048,'正方形 高解像度']] as [size, label]}
								<button onclick={() => { downloadPNG(size as number); pngMenuOpen = false; }}>
									<span class="png-size">PNG {size}px</span>
									<span class="png-sub">{label}</span>
								</button>
							{/each}
						</div>
					{/if}
				</div>
			</div>

		</div><!-- /right-panel -->
	</div><!-- /body -->

	<!-- ══ HISTORY STRIP ══ -->
	{#if historyTotal > 0}
		<div class="history-strip">
			<div class="history-head">
				<button class="history-title-btn" onclick={() => { historyManagerOpen = true; historyManagerView = 'active'; selectedHistoryIds = []; void fetchTrashPage(); }}>
					{t().historyTitle} <span class="history-count">({historyTotal})</span> ▸
				</button>
				{#if historyTotalPages > 1}
					<div class="history-page-nav">
						<button class="ghost-btn" onclick={async () => { await fetchHistoryPage(historyPage - 1); loadIteration(0); }} disabled={historyPage <= 0}>← 前のページ</button>
						<span class="history-page-indicator">{historyPage + 1} / {historyTotalPages}</span>
						<button class="ghost-btn" onclick={async () => { await fetchHistoryPage(historyPage + 1); loadIteration(0); }} disabled={historyPage >= historyTotalPages - 1}>次のページ →</button>
					</div>
				{/if}
			</div>
			<div class="thumb-strip">
				{#each historyItems.slice(0, visibleThumbCount) as it, i (it.id ?? it.at)}
					<button
						class="thumb"
						class:current={i === historyCursor}
						onclick={() => loadIteration(i)}
					>
						<div class="thumb-tooltip">
							<div class="tooltip-title">#{historyPage * HISTORY_PAGE_SIZE + i + 1}</div>
							<div>モデル: {shortModel(it.stage2_model)}</div>
							<div>時間: {it.elapsed_ms ? (it.elapsed_ms / 1000).toFixed(1) + 's' : '-'}</div>
							<div>色: {catalogName(it.catalog_id)}</div>
							<div class="tooltip-date">{formatHistoryDate(it.at)}</div>
						</div>
						<div class="thumb-svg">{@html it.svg}</div>
						<div class="thumb-meta">
							<span class="thumb-time">{it.elapsed_ms ? (it.elapsed_ms / 1000).toFixed(1) + 's' : String(historyPage * HISTORY_PAGE_SIZE + i + 1)}</span>
							{#if it.stage2_model}<span class="thumb-model">{shortModel(it.stage2_model)}</span>{/if}
						</div>
						{#if i === historyCursor}
							<div class="thumb-current-badge">表示中</div>
						{/if}
					</button>
				{/each}
			</div>
		</div>
	{/if}

</div><!-- /root -->

<!-- ══ SAIJIKI DRAWER (fixed right) ══ -->
<div class="saijiki-drawer" class:open={saijikiOpen} aria-hidden={!saijikiOpen}>
	<div class="saijiki-inner">
		<div class="saijiki-head">
			<div>
				<div class="saijiki-title">歳時記</div>
				<div class="saijiki-hint">{t().saijikiHint}</div>
			</div>
			<button class="saijiki-close" onclick={() => (saijikiOpen = false)} aria-label="閉じる">×</button>
		</div>
		<div class="saijiki-body">
			{#each SAIJIKI as cat, ci (cat.key)}
				{@const words = t().saijikiWords[cat.key] ?? cat.words}
				<div class="saijiki-cat" style="border-bottom: {ci < SAIJIKI.length - 1 ? '1px solid var(--border)' : 'none'}">
					<div class="saijiki-cat-head">
						<span class="saijiki-cat-ja">{cat.label}</span>
						<span class="saijiki-cat-en">{cat.en}</span>
					</div>
					<div class="saijiki-chips">
						{#each words as word (word)}
							<button class="saijiki-chip" onclick={() => insertWord(word)}>{word}</button>
						{/each}
					</div>
				</div>
			{/each}
		</div>
	</div>
</div>

<!-- ══ SETTINGS MODAL ══ -->
{#if settingsOpen}
	<div class="modal-backdrop" onclick={() => (settingsOpen = false)} aria-hidden="true"></div>
	<div class="settings-modal" role="dialog" aria-modal="true" onclick={(e) => e.stopPropagation()}>
		<div class="modal-head">
			<div class="catalog-modal-title">接続設定</div>
			<button class="catalog-close" onclick={() => (settingsOpen = false)}>×</button>
		</div>
		<div class="settings-tabs">
			<button class:active={settingsTab === 'connection'} onclick={() => (settingsTab = 'connection')}>接続設定</button>
			<button class:active={settingsTab === 'db'} onclick={() => (settingsTab = 'db')}>DB設定</button>
			<button class:active={settingsTab === 'plugins'} onclick={() => (settingsTab = 'plugins')}>プラグイン</button>
		</div>
		<div class="settings-body">
			{#if settingsTab === 'connection'}
				<div class="popover-group">
					<div class="popover-group-label">{t().stage1Label}</div>
					<div class="form-row">
						<label>{t().providerLabel}</label>
						<select value={stage1Provider} onchange={(e) => setStage1Provider((e.currentTarget as HTMLSelectElement).value as Provider)}>
							{#each PROVIDER_GROUPS as pg (pg.id)}<option value={pg.id}>{pg.label}</option>{/each}
						</select>
					</div>
					<div class="form-row">
						<label>{t().modelLabel}</label>
						<select value={stage1Model} onchange={(e) => setStage1Model((e.currentTarget as HTMLSelectElement).value)}>
							{#each modelsForProvider(stage1Provider) as m (m.id)}<option value={m.id}>{m.label}{m.notes ? ` — ${m.notes}` : ''}</option>{/each}
						</select>
					</div>
					{#if stage1Model.includes('qwen3')}
						<label class="check-row">
							<input type="checkbox" bind:checked={includeThinking} />
							<span>{t().showThinkingLabel}</span>
						</label>
					{/if}
				</div>
				<div class="popover-group">
					<div class="popover-group-label">{t().stage2Label}</div>
					<div class="form-row">
						<label>{t().providerLabel}</label>
						<select value={stage2Provider} onchange={(e) => setStage2Provider((e.currentTarget as HTMLSelectElement).value as Provider)}>
							{#each PROVIDER_GROUPS as pg (pg.id)}<option value={pg.id}>{pg.label}</option>{/each}
						</select>
					</div>
					<div class="form-row">
						<label>{t().modelLabel}</label>
						<select value={stage2Model} onchange={(e) => setStage2Model((e.currentTarget as HTMLSelectElement).value)}>
							{#each modelsForProvider(stage2Provider) as m (m.id)}<option value={m.id}>{m.label}{m.notes ? ` — ${m.notes}` : ''}</option>{/each}
						</select>
					</div>
				</div>
				{#if snapshots.length > 0}
					<div class="popover-group">
						<div class="popover-group-label">{t().saijikiLabel}</div>
						<select class="full-select" value={activeSnapshotId ?? ''} onchange={(e) => { const v = (e.currentTarget as HTMLSelectElement).value; activeSnapshotId = v || null; }}>
							<option value="">{t().currentSetting}</option>
							{#each snapshots as s (s.id)}<option value={s.id}>{s.name}</option>{/each}
						</select>
					</div>
				{/if}
			{:else if settingsTab === 'db'}
				<div class="popover-group">
					<div class="form-row">
						<label>DBタイプ:</label>
						<select bind:value={dbType}>
							<option value="sqlite">内蔵SQLite</option>
							<option value="postgres">PostgreSQL</option>
						</select>
					</div>
				</div>
				{#if dbType === 'sqlite'}
					<div class="popover-group">
						<div class="popover-group-label">SQLite</div>
						<div class="form-row">
							<label>保存先パス:</label>
							<input bind:value={sqlitePath} />
						</div>
					</div>
				{:else}
					<div class="popover-group">
						<div class="popover-group-label">PostgreSQL</div>
						<div class="form-row"><label>サーバー:</label><input bind:value={pgHost} /></div>
						<div class="form-row"><label>ポート:</label><input bind:value={pgPort} /></div>
						<div class="form-row"><label>ユーザー:</label><input bind:value={pgUser} /></div>
						<div class="form-row">
							<label>パスワード:</label>
							<input type={showPgPassword ? 'text' : 'password'} bind:value={pgPassword} />
							<button class="ghost-btn" onclick={() => (showPgPassword = !showPgPassword)}>{showPgPassword ? '隠す' : '表示'}</button>
						</div>
						<div class="form-row"><label>DB名:</label><input bind:value={pgDatabase} /></div>
					</div>
				{/if}
				<div class="settings-inline-actions">
					<button class="ghost-btn" onclick={testDbConnection}>接続テスト</button>
					{#if dbTestResult}<span class="db-test-result">{dbTestResult}</span>{/if}
				</div>
			{:else}
				<div class="plugin-list">
					{#each plugins as plugin (plugin.id)}
						<div class="plugin-row">
							<label class="check-row">
								<input type="checkbox" checked={plugin.enabled} onchange={(e) => { plugin.enabled = (e.currentTarget as HTMLInputElement).checked; plugins = [...plugins]; }} />
								<span>{plugin.name}</span>
							</label>
							<span class="plugin-version">{plugin.version}</span>
							<button class="ghost-btn" onclick={() => (pluginPendingDelete = plugin)}>削除</button>
						</div>
					{/each}
				</div>
				<button class="ghost-btn" onclick={() => (pluginAddOpen = !pluginAddOpen)}>＋ プラグインを追加</button>
				{#if pluginAddOpen}
					<div class="plugin-add">
						<input bind:value={pluginPath} placeholder="plugin path or name" />
						<button class="ghost-btn" onclick={addPlugin}>追加</button>
					</div>
				{/if}
				{#if pluginPendingDelete}
					<div class="inline-confirm">
						<span>{pluginPendingDelete.name} を削除しますか？</span>
						<button class="ghost-btn" onclick={() => (pluginPendingDelete = null)}>キャンセル</button>
						<button class="danger-btn" onclick={() => { plugins = plugins.filter((p) => p.id !== pluginPendingDelete?.id); pluginPendingDelete = null; }}>削除</button>
					</div>
				{/if}
			{/if}
		</div>
	</div>
{/if}

<!-- ══ CATALOG MODAL ══ -->
{#if catalogOpen}
	<div class="modal-backdrop" onclick={() => (catalogOpen = false)} aria-hidden="true"></div>
	<div class="catalog-modal" role="dialog" aria-modal="true" onclick={(e) => e.stopPropagation()}>
		<div class="catalog-modal-head">
			<div class="catalog-modal-title">カタログ設定</div>
			<button class="catalog-close" onclick={() => (catalogOpen = false)}>×</button>
		</div>
		<div class="catalog-scroll">
			{#each COLOR_CATALOGS as cat (cat.id)}
				{@const active = selectedCatalog === cat.id}
				<button
					class="catalog-item"
					class:active
					onclick={() => { selectedCatalog = cat.id; try { localStorage.setItem(CATALOG_KEY, cat.id); } catch {} }}
				>
					<div class="catalog-swatches">
						{#each cat.swatches as hex (hex)}
							<div class="catalog-swatch" style="background:{hex}"></div>
						{/each}
					</div>
					<div class="catalog-info">
						<div class="catalog-name">{cat.name}</div>
						<div class="catalog-sub">{cat.sub}</div>
					</div>
					{#if active}<span class="catalog-check">✓</span>{/if}
				</button>
			{/each}
		</div>
		<div class="catalog-detail">
			<div class="section-label">{currentCatalog.name} — 詳細</div>
			<div class="catalog-detail-list">
				{#each currentCatalog.palette as color (color.code)}
					<div class="catalog-color-row">
						<div class="catalog-color-box" class:light={isLightColor(color.code)} style="background:{color.code}"></div>
						<span class="catalog-color-name">{color.name}</span>
						<span class="catalog-color-code">{color.code}</span>
					</div>
				{/each}
			</div>
		</div>
	</div>
{/if}

<!-- ══ HISTORY MANAGER MODAL ══ -->
{#if historyManagerOpen}
	<div class="modal-backdrop" onclick={() => (historyManagerOpen = false)} aria-hidden="true"></div>
	<div class="history-modal" role="dialog" aria-modal="true" onclick={(e) => e.stopPropagation()}>
		<div class="modal-head">
			<div class="catalog-modal-title">履歴管理</div>
			<div class="modal-head-actions">
				<button class="ghost-btn" class:ghost-active={historyManagerView === 'trash'} onclick={() => { historyManagerView = historyManagerView === 'trash' ? 'active' : 'trash'; selectedHistoryIds = []; void fetchTrashPage(); }}>ごみ箱 ({trashTotal})</button>
				<button class="catalog-close" onclick={() => (historyManagerOpen = false)}>×</button>
			</div>
		</div>
		<div class="history-tools">
			<button class="ghost-btn" onclick={selectAllManagedHistory}>すべて選択</button>
			{#if historyManagerView === 'active'}
				<button class="ghost-btn" onclick={() => askTrash(selectedHistoryIds)} disabled={selectedHistoryIds.length === 0}>選択削除</button>
			{:else}
				<button class="ghost-btn" onclick={() => askRestore(selectedHistoryIds)} disabled={selectedHistoryIds.length === 0}>選択復元</button>
				<button class="danger-btn" onclick={() => askPermanentDelete(selectedHistoryIds)} disabled={selectedHistoryIds.length === 0}>完全削除</button>
			{/if}
			<label class="history-search">検索: <input bind:value={historySearch} /></label>
		</div>
		<div class="history-table-wrap">
			<table class="history-table">
				<thead>
					<tr><th></th><th>画像</th><th>作成日時</th><th>モデル</th><th>時間</th><th>操作</th></tr>
				</thead>
				<tbody>
					{#each filteredManagedHistory as it (it.id ?? it.at)}
						<tr>
							<td><input type="checkbox" checked={!!it.id && selectedHistoryIds.includes(it.id)} onchange={() => it.id && toggleHistorySelection(it.id)} /></td>
							<td><div class="history-mini">{@html it.svg}</div></td>
							<td>{formatHistoryDate(it.at)}</td>
							<td>{shortModel(it.stage2_model)}</td>
							<td>{it.elapsed_ms ? (it.elapsed_ms / 1000).toFixed(1) + 's' : '-'}</td>
							<td>
								{#if historyManagerView === 'active'}
									<button class="ghost-btn" onclick={() => it.id && askTrash([it.id])}>削除</button>
								{:else}
									<button class="ghost-btn" onclick={() => it.id && askRestore([it.id])}>復元</button>
									<button class="danger-btn" onclick={() => it.id && askPermanentDelete([it.id])}>完全削除</button>
								{/if}
							</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</div>
	</div>
{/if}

{#if confirmAction}
	<div class="confirm-layer">
		<div class="confirm-backdrop" onclick={() => (confirmAction = null)}></div>
		<div class="confirm-box">
			<p>{confirmAction.message}</p>
			<div class="confirm-actions">
				<button class="ghost-btn" onclick={() => (confirmAction = null)}>キャンセル</button>
				<button class={confirmAction.destructive ? 'danger-btn' : 'confirm-btn'} onclick={() => { const run = confirmAction?.run; confirmAction = null; run?.(); }}>{confirmAction.destructive ? '削除' : '実行'}</button>
			</div>
		</div>
	</div>
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

	.settings-wrap { position: relative; }

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

	.settings-popover {
		position: absolute;
		top: calc(100% + 6px);
		right: 0;
		z-index: 200;
		background: #fff;
		border: 1px solid var(--border2);
		border-radius: var(--r-lg);
		padding: 16px;
		box-shadow: 0 6px 24px rgba(0,0,0,0.13);
		width: 340px;
	}

	.popover-title { font-weight: 500; margin-bottom: 12px; font-size: 13px; }

	.popover-group {
		background: var(--bg);
		border-radius: var(--r);
		padding: 10px;
		margin-bottom: 8px;
	}
	.popover-group-label {
		font-size: 10px; color: var(--fg3); font-weight: 500;
		letter-spacing: 0.07em; text-transform: uppercase;
		margin-bottom: 7px;
	}
	.popover-row {
		display: flex; align-items: center; gap: 8px; margin-bottom: 6px;
	}
	.popover-row-label { width: 50px; color: var(--fg2); font-size: 11px; flex-shrink: 0; }
	.popover-row select {
		flex: 1; padding: 4px 6px;
		border: 1px solid var(--border2); border-radius: var(--r);
		background: #fff; color: var(--fg); font-size: 12px; font-family: inherit;
	}
	.popover-think-label {
		display: flex; align-items: center; gap: 6px; font-size: 12px; color: var(--fg2);
		cursor: pointer; margin-top: 4px;
	}
	.popover-close {
		margin-top: 4px; width: 100%; padding: 7px;
		background: var(--fg); color: #fff;
		border: none; border-radius: var(--r);
		font-size: 12px; cursor: pointer; font-family: inherit;
	}

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

	.header-link {
		padding: 4px 0; border: none; border-bottom: 1px solid transparent;
		background: none; color: var(--fg3); font-size: 12px; cursor: pointer; font-family: inherit;
		transition: color 0.15s;
	}
	.header-link:hover { color: var(--fg); }
	.header-link.underlined { color: var(--fg); border-bottom-color: var(--fg); }

	.header-sep { color: var(--border); font-size: 11px; }
	.build-badge { font-size: 11px; color: var(--fg3); font-variant-numeric: tabular-nums; }

	/* ── Body ───────────────────────────────────────────────── */
	.body {
		display: flex;
		flex: 1;
		overflow: hidden;
		position: relative;
	}

	.flying-bird-layer {
		position: fixed;
		top: 54px;
		left: 0;
		width: 440px;
		height: calc(100vh - 136px);
		pointer-events: none;
		z-index: 50;
		overflow: hidden;
	}
	.flying-bird-y {
		position: absolute;
		animation: freeBirdY 6.5s ease-in-out infinite;
	}
	.flying-bird-x {
		position: relative;
		animation: freeBirdX 4.8s ease-in-out infinite;
	}
	.flying-bird {
		filter: drop-shadow(0 2px 4px rgba(107,123,42,0.3));
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

	.panel-tabs {
		display: flex;
		border-bottom: 1px solid var(--border);
		background: var(--bg);
		flex-shrink: 0;
	}
	.panel-tab {
		padding: 9px 16px; border: none; border-bottom: 2px solid transparent;
		background: none; color: var(--fg2); font-size: 13px; cursor: pointer;
		font-family: inherit; transition: color 0.1s;
	}
	.panel-tab.active { border-bottom-color: var(--fg); color: var(--fg); font-weight: 500; }
	.panel-tab:hover:not(.active) { color: var(--fg); }

	.panel-scroll {
		flex: 1;
		overflow-y: auto;
		padding: 14px 16px;
		display: flex;
		flex-direction: column;
		gap: 14px;
	}

	.panel-section { display: flex; flex-direction: column; gap: 6px; }

	.section-head {
		display: flex;
		justify-content: space-between;
		align-items: center;
	}

	.section-label {
		font-size: 10px; font-weight: 500; letter-spacing: 0.08em;
		color: var(--fg3); text-transform: uppercase;
	}

	.section-actions { display: flex; gap: 5px; }

	.ghost-btn {
		padding: 4px 10px;
		border: 1px solid var(--border2);
		border-radius: var(--r);
		background: #fff;
		color: var(--fg2);
		font-size: 11px;
		cursor: pointer;
		font-family: inherit;
	}
	.ghost-btn:hover { background: var(--bg2); }
	.ghost-btn:disabled { opacity: 0.4; cursor: not-allowed; }
	.ghost-btn.ghost-active { background: var(--fg); color: #fff; border-color: var(--fg); }

	/* Input textarea */
	.input-ta, .batch-ta {
		width: 100%; padding: 9px 10px;
		border: 1px solid var(--border2); border-radius: var(--r);
		background: #fff; color: var(--fg);
		font-family: inherit; font-size: 13px; line-height: 1.65;
		resize: vertical; outline: none;
	}
	.input-ta:focus, .batch-ta:focus { border-color: var(--accent); }

	.batch-wrap {
		display: flex;
		border: 1px solid var(--border2);
		border-radius: var(--r);
		overflow: hidden;
	}
	.line-nums {
		background: var(--bg2); border-right: 1px solid var(--border);
		padding: 9px 6px; font-size: 12px; line-height: 1.65;
		text-align: right; color: var(--fg3); user-select: none;
		white-space: pre; min-width: 2rem; font-variant-numeric: tabular-nums;
	}
	.batch-ta { flex: 1; border: none; border-radius: 0; }
	.batch-wrap .batch-ta { min-height: 240px; }
	.batch-info { font-size: 11px; color: var(--fg3); }

	/* Progress */
	.progress-wrap {
		display: flex; align-items: center; justify-content: space-between;
		padding: 8px 10px 6px;
		border: 1px solid var(--border2); border-radius: var(--r) var(--r) 0 0;
		background: #fff;
		margin-top: 8px;
	}
	.progress-phases { display: flex; align-items: center; gap: 4px; }
	.phase-sep { color: var(--border); font-size: 9px; margin: 0 1px; }
	.phase-item { font-size: 11px; color: var(--border2); display: flex; align-items: center; gap: 3px; }
	.phase-item.phase-active { color: var(--fg); font-weight: 500; }
	.phase-item.phase-done { color: var(--fg3); }
	.phase-dot {
		display: inline-block; width: 6px; height: 6px; border-radius: 50%;
		background: var(--accent); flex-shrink: 0;
		animation: inkupulse 1s ease-in-out infinite;
	}
	.phase-check { color: #27ae60; font-size: 10px; }
	.progress-right { display: flex; align-items: center; gap: 7px; }
	.progress-time { font-size: 11px; color: var(--fg3); font-variant-numeric: tabular-nums; }
	.stop-sm {
		padding: 2px 7px; border: 1px solid var(--border2);
		border-radius: var(--r); background: none;
		color: var(--fg2); font-size: 11px; cursor: pointer; font-family: inherit;
	}
	.progress-bar-track {
		position: relative;
		height: 20px; background: transparent;
		border-left: 1px solid var(--border2); border-right: 1px solid var(--border2);
		overflow: visible;
	}
	.progress-bar-track::before {
		content: "";
		position: absolute; top: 8px; left: 0; right: 0; height: 3px;
		background: var(--bg3);
	}
	.progress-bar-fill {
		position: absolute; top: 8px; left: 0; height: 3px;
		background: var(--accent); transition: width 0.3s ease;
	}
	.progress-bird {
		position: absolute; top: 1px; left: -20px;
		animation: birdFly 2.4s linear infinite;
		pointer-events: none;
	}
	.progress-bird.done { animation: none; left: calc(100% - 16px); }
	.progress-stage-text {
		font-size: 11px; color: var(--fg3);
		padding: 5px 10px 7px;
		border: 1px solid var(--border2); border-top: none;
		border-radius: 0 0 var(--r) var(--r);
		background: #fff;
	}

	.batch-progress {
		display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
		padding: 8px 10px;
		border: 1px solid var(--border2); border-radius: var(--r);
		background: #fff; font-size: 12px; color: var(--fg2);
		margin-top: 8px;
	}

	/* Play button */
	.play-btn {
		width: 100%; margin-top: 8px; padding: 9px;
		font-size: 14px; font-weight: 500;
		background: var(--fg); color: #fff;
		border: none; border-radius: var(--r);
		letter-spacing: 0.08em; cursor: pointer;
		display: flex; align-items: center; justify-content: center; gap: 8px;
		font-family: inherit; transition: background 0.15s;
	}
	.play-btn:hover:not(:disabled) { background: #333; }
	.play-btn:disabled { background: var(--fg3); cursor: not-allowed; }

	.error-text { color: #a2342a; font-size: 12px; }

	/* Annotations */
	.annot-box {
		padding: 9px 10px; background: #fff;
		border: 1px solid var(--border); border-radius: var(--r);
		font-size: 13px; line-height: 1.85; white-space: pre-wrap; word-break: break-word;
	}
	.ddl-box { border-left: 3px solid var(--border2); border-radius: 0 var(--r) var(--r) 0; }

	.tok { }
	.tok-saijiki { color: #2c3e91; font-weight: 500; }
	.tok-plain   { color: var(--fg3); }
	.tok-emotion { color: #c9a08a; font-style: italic; text-decoration: line-through; text-decoration-color: rgba(162,52,42,0.4); }
	.tok-diff-added { color: #a2342a; font-weight: 500; }

	.ddl-edit-ta {
		width: 100%; padding: 9px 10px;
		border: 1px solid var(--accent); border-left: 3px solid var(--border2);
		border-radius: 0 var(--r) var(--r) 0;
		background: #fff; color: var(--fg);
		font-family: inherit; font-size: 13px; line-height: 1.75; resize: vertical; outline: none;
	}

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

	/* Replay */
	.replay-btn {
		width: 100%; margin-top: 6px; padding: 10px;
		font-size: 14px; font-weight: 500; background: var(--fg); color: #fff;
		border: none; border-radius: var(--r);
		letter-spacing: 0.08em; cursor: pointer;
		display: flex; align-items: center; justify-content: center; gap: 6px;
		font-family: inherit; transition: background 0.15s;
	}
	.replay-btn:hover:not(:disabled) { background: #333; }
	.replay-btn:disabled { background: var(--fg3); cursor: not-allowed; }

	/* Stats */
	.stats-section { }
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

	/* ── Right panel ────────────────────────────────────────── */
	.right-panel {
		flex: 1; min-width: 0;
		display: flex; flex-direction: column;
		overflow: hidden;
	}

	.right-tabs {
		display: flex; align-items: center;
		border-bottom: 1px solid var(--border);
		background: var(--bg); padding: 0 16px; flex-shrink: 0;
	}
	.rtab {
		padding: 9px 16px; border: none; border-bottom: 2px solid transparent;
		background: none; color: var(--fg2); font-size: 13px; cursor: pointer;
		font-family: inherit; white-space: nowrap;
	}
	.rtab.active { border-bottom-color: var(--fg); color: var(--fg); font-weight: 500; }
	.rtab:hover:not(.active):not(:disabled) { color: var(--fg); }
	.rtab:disabled { opacity: 0.35; cursor: not-allowed; }
	.rtab-spacer { flex: 1; }
	.rendered-at { font-size: 11px; color: var(--fg3); font-variant-numeric: tabular-nums; }

	/* Canvas area */
	.canvas-area {
		flex: 1; display: flex; align-items: center; justify-content: center;
		background: var(--bg2); position: relative; overflow: hidden;
	}

	.nav-left {
		position: absolute; left: 14px; z-index: 10;
		display: flex; flex-direction: column; align-items: center; gap: 6px;
	}
	.nav-right {
		position: absolute; right: 14px; z-index: 10;
		display: flex; flex-direction: column; align-items: center; gap: 6px;
	}
	.nav-circle {
		width: 38px; height: 38px; border-radius: 50%;
		background: rgba(255,255,255,0.88); border: 1px solid var(--border2);
		font-size: 20px; box-shadow: 0 1px 6px rgba(0,0,0,0.1);
		display: flex; align-items: center; justify-content: center;
		color: var(--fg); cursor: pointer; font-family: inherit;
		transition: background 0.1s;
	}
	.nav-circle:hover:not(:disabled) { background: #fff; }
	.nav-circle:disabled { opacity: 0.35; cursor: not-allowed; }
	.nav-counter { font-size: 11px; color: var(--fg3); font-variant-numeric: tabular-nums; white-space: nowrap; }

	.canvas-content {
		position: relative; width: 100%; height: 100%;
		display: flex; align-items: center; justify-content: center; overflow: hidden;
	}

	.canvas-box {
		width: 400px;
		height: 400px;
		background: #fff;
		box-shadow: 0 8px 32px rgba(0,0,0,0.18);
		overflow: hidden;
		flex-shrink: 0;
	}

	.canvas-box :global(svg) { width: 100%; height: 100%; display: block; }

	.canvas-placeholder {
		width: 100%; height: 100%; min-height: 200px;
		display: flex; align-items: center; justify-content: center;
		color: var(--fg3); font-size: 13px;
	}

	/* Zoom controls */
	.zoom-controls {
		position: absolute; bottom: 14px; left: 50%; transform: translateX(-50%);
		z-index: 10;
		display: flex; align-items: center; gap: 0;
		background: rgba(255,255,255,0.9); border: 1px solid var(--border2);
		border-radius: 20px; box-shadow: 0 1px 6px rgba(0,0,0,0.1); overflow: hidden;
	}
	.zoom-controls button {
		width: 32px; height: 28px; border: none; background: none;
		font-size: 16px; color: var(--fg); cursor: pointer;
		display: flex; align-items: center; justify-content: center; font-family: inherit;
	}
	.zoom-controls button:hover { background: var(--bg2); }
	.zoom-pct {
		font-size: 11px; color: var(--fg2); font-variant-numeric: tabular-nums;
		min-width: 38px; text-align: center; user-select: none;
	}
	.zoom-reset { border-left: 1px solid var(--border) !important; font-size: 11px !important; color: var(--fg3) !important; }

	/* Prompts / Score tabs */
	.prompt-section {
		flex: 1; display: flex; flex-direction: column; gap: 4px;
		overflow-y: auto; padding: 12px;
		width: 100%;
		align-self: stretch; min-height: 0;
	}
	.prompt-label { margin: 8px 0 3px; font-size: 11px; font-weight: 600; color: var(--fg2); }
	.prompt-collapsible-head {
		display: flex; align-items: center; justify-content: space-between;
		margin-top: 8px;
	}
	.prompt-collapsible-head .prompt-label { margin: 0; }
	.prompt-textarea {
		width: 100%;
		background: var(--bg2); padding: 8px 10px; border-radius: var(--r);
		border: 1px solid var(--border); overflow: auto;
		white-space: pre-wrap; word-break: break-word; font-size: 11px; line-height: 1.5; margin: 0;
		font-family: inherit; color: var(--fg);
		resize: vertical;
	}
	.prompt-user { min-height: 120px; }
	.prompt-system { min-height: 120px; height: 220px; }
	.prompt-collapse {
		position: relative;
		max-height: 80px;
		overflow: hidden;
	}
	.prompt-collapse.expanded {
		max-height: none;
		overflow: visible;
	}
	.prompt-collapse:not(.expanded) .prompt-system {
		height: 120px;
		resize: none;
	}
	.prompt-fade {
		position: absolute; left: 0; right: 0; bottom: 0; height: 32px;
		background: linear-gradient(transparent, var(--bg));
		pointer-events: none;
	}
	.prompt-pre {
		background: var(--bg2); padding: 8px 10px; border-radius: var(--r);
		border: 1px solid var(--border); overflow-x: auto; max-height: 140px;
		white-space: pre-wrap; word-break: break-word; font-size: 11px; line-height: 1.5; margin: 0;
		font-family: inherit;
	}
	.prompt-pre-lg { max-height: 320px; }
	.score-pre {
		background: #fff; border: 1px solid var(--border); border-radius: var(--r);
		padding: 12px; overflow: auto; font-size: 12px; line-height: 1.5;
		white-space: pre-wrap; word-break: break-word;
		width: 100%; height: 100%; margin: 0;
		font-family: inherit;
		align-self: stretch; min-height: 0;
	}
	.muted-center { color: var(--fg3); font-size: 13px; padding: 16px; }

	/* Export bar */
	.export-bar {
		display: flex; align-items: center; gap: 6px;
		padding: 8px 16px; border-top: 1px solid var(--border);
		background: var(--bg); flex-shrink: 0;
	}
	.export-label { font-size: 11px; color: var(--fg3); margin-right: auto; }

	.png-wrap { position: relative; }
	.png-menu {
		position: absolute; bottom: calc(100% + 6px); right: 0; z-index: 100;
		background: #fff; border: 1px solid var(--border2);
		border-radius: var(--r-lg); overflow: hidden;
		box-shadow: 0 4px 18px rgba(0,0,0,0.12); min-width: 190px;
	}
	.png-menu button {
		display: flex; align-items: center; gap: 8px;
		width: 100%; text-align: left;
		padding: 8px 14px; background: none; border: none;
		border-bottom: 1px solid var(--border); color: var(--fg); cursor: pointer;
		font-family: inherit; font-size: 13px;
	}
	.png-menu button:last-child { border-bottom: none; }
	.png-menu button:hover { background: var(--bg); }
	.png-size { font-weight: 500; }
	.png-sub { color: var(--fg3); font-size: 11px; }

	/* ── History strip ───────────────────────────────────────── */
	.history-strip {
		border-top: 1px solid var(--border);
		background: var(--bg);
		padding: 8px 16px 10px;
		flex-shrink: 0;
	}
	.history-head {
		display: flex; justify-content: space-between; align-items: center;
		margin-bottom: 7px;
	}
	.history-title { font-size: 12px; font-weight: 500; color: var(--fg2); }
	.history-title-btn {
		border: none; background: none; color: var(--fg2);
		font-size: 12px; font-weight: 500; cursor: pointer; font-family: inherit;
	}
	.history-title-btn:hover { color: var(--fg); }
	.history-count { color: var(--fg3); font-weight: 400; }
	.history-page-nav { display: flex; align-items: center; gap: 6px; }
	.history-page-indicator { font-size: 11px; color: var(--fg3); font-variant-numeric: tabular-nums; min-width: 30px; text-align: center; }

	.thumb-strip {
		display: flex; gap: 7px; overflow: hidden;
	}

	.thumb {
		flex-shrink: 0; width: 82px;
		border: 2px solid transparent;
		border-radius: var(--r); overflow: hidden; background: #fff;
		cursor: pointer; padding: 0; font-family: inherit; position: relative;
		transition: border-color 0.1s;
	}
	.thumb:hover { overflow: visible; z-index: 20; }
	.thumb.current { border-color: var(--accent); }
	.thumb-tooltip {
		position: absolute; bottom: calc(100% + 6px); left: 50%;
		transform: translateX(-50%) translateY(4px);
		opacity: 0; pointer-events: none;
		background: rgba(26,25,23,0.92); color: #fff;
		font-size: 11px; border-radius: var(--r);
		padding: 7px 10px; white-space: nowrap;
		z-index: 500; line-height: 1.7;
		transition: opacity 0.15s, transform 0.15s;
		box-shadow: 0 4px 18px rgba(0,0,0,0.18);
	}
	.thumb:hover .thumb-tooltip {
		opacity: 1;
		transform: translateX(-50%) translateY(0);
	}
	.tooltip-title { font-weight: 500; margin-bottom: 3px; }
	.tooltip-date { color: rgba(255,255,255,0.55); margin-top: 3px; }
	.thumb-svg { width: 82px; height: 58px; overflow: hidden; }
	.thumb-svg :global(svg) { width: 100%; height: 100%; display: block; }
	.thumb-meta {
		padding: 3px 5px; border-top: 1px solid var(--border);
		display: flex; flex-direction: column; gap: 1px;
	}
	.thumb-time  { font-size: 11px; font-weight: 500; color: var(--fg2); }
	.thumb-model { font-size: 10px; color: var(--fg3); }
	.thumb-current-badge {
		position: absolute; bottom: 22px; right: 3px;
		background: var(--accent); color: #fff;
		font-size: 9px; padding: 1px 4px; border-radius: 2px;
	}

	/* ── Saijiki drawer ─────────────────────────────────────── */
	.saijiki-drawer {
		position: fixed; top: 0; right: 0; bottom: 0;
		width: 0; overflow: hidden; z-index: 300;
		transition: width 0.25s cubic-bezier(0.4,0,0.2,1);
		pointer-events: none;
	}
	.saijiki-drawer.open { width: 280px; pointer-events: all; }

	.saijiki-inner {
		width: 280px; height: 100%;
		background: #faf9f6; border-left: 1px solid var(--border);
		display: flex; flex-direction: column;
		box-shadow: -4px 0 24px rgba(0,0,0,0.08);
	}

	.saijiki-head {
		padding: 16px 18px 12px;
		border-bottom: 1px solid var(--border);
		display: flex; align-items: flex-start; justify-content: space-between;
		flex-shrink: 0;
	}
	.saijiki-title {
		font-size: 17px; font-weight: 300; letter-spacing: 0.06em; color: var(--fg);
	}
	.saijiki-hint { font-size: 10px; color: var(--fg3); margin-top: 3px; line-height: 1.5; }
	.saijiki-close {
		width: 24px; height: 24px; border: none; background: none;
		color: var(--fg3); font-size: 16px; cursor: pointer; flex-shrink: 0; margin-top: 2px;
	}
	.saijiki-body { flex: 1; overflow-y: auto; padding: 8px 0; }

	.saijiki-cat { padding: 10px 18px; }
	.saijiki-cat-head { display: flex; align-items: baseline; gap: 7px; margin-bottom: 8px; }
	.saijiki-cat-ja { font-size: 13px; font-weight: 400; color: var(--fg); letter-spacing: 0.05em; }
	.saijiki-cat-en { font-size: 9px; color: var(--fg3); letter-spacing: 0.1em; text-transform: uppercase; font-weight: 500; }

	.saijiki-chips { display: flex; flex-wrap: wrap; gap: 5px; }
	.saijiki-chip {
		padding: 4px 9px; border: 1px solid var(--border2); border-radius: 3px;
		background: #fff; color: var(--fg); font-size: 12px; cursor: pointer;
		font-family: inherit; line-height: 1.3; transition: background 0.1s, border-color 0.1s;
	}
	.saijiki-chip:hover { background: var(--bg2); border-color: var(--fg3); }

	/* ── Catalog modal ───────────────────────────────────────── */
	.modal-backdrop {
		position: fixed; inset: 0; z-index: 400;
		background: rgba(0,0,0,0.25); backdrop-filter: blur(2px);
	}
	.catalog-modal {
		position: fixed; top: 50%; left: 50%; transform: translate(-50%, -50%);
		z-index: 401;
		width: 540px; max-height: 88vh;
		background: #faf9f6; border-radius: var(--r-lg);
		box-shadow: 0 12px 48px rgba(0,0,0,0.18);
		display: flex; flex-direction: column; overflow: hidden;
	}
	.catalog-modal-head {
		display: flex; align-items: center; justify-content: space-between;
		padding: 14px 18px 10px; border-bottom: 1px solid var(--border); flex-shrink: 0;
	}
	.catalog-modal-title { font-size: 15px; font-weight: 300; letter-spacing: 0.05em; }
	.catalog-close {
		width: 24px; height: 24px; border: none; background: none;
		color: var(--fg3); font-size: 18px; cursor: pointer; line-height: 1;
	}
	.catalog-scroll { flex: 1; overflow-y: auto; padding: 12px; display: flex; flex-direction: column; gap: 6px; }

	.catalog-item {
		display: flex; align-items: center; gap: 12px; padding: 10px 12px;
		border: 1px solid var(--border); border-radius: var(--r);
		background: #fff; cursor: pointer; text-align: left;
		transition: border-color 0.12s, background 0.12s; font-family: inherit; width: 100%;
	}
	.catalog-item.active { border: 1.5px solid var(--accent); background: var(--accent-light); }
	.catalog-item:hover:not(.active) { background: var(--bg); }

	.catalog-swatches {
		display: flex; flex-shrink: 0; border-radius: 3px; overflow: hidden; height: 32px; width: 64px;
	}
	.catalog-swatch { flex: 1; }

	.catalog-info { flex: 1; min-width: 0; }
	.catalog-name { font-size: 12px; font-weight: 500; color: var(--fg); margin-bottom: 1px; }
	.catalog-sub  { font-size: 11px; color: var(--fg3); }
	.catalog-check { color: var(--accent); font-size: 13px; flex-shrink: 0; }
	.catalog-detail {
		border-top: 1px solid var(--border);
		padding: 12px 16px 14px;
		background: #fff;
		flex-shrink: 0;
	}
	.catalog-detail-list { display: flex; flex-direction: column; gap: 4px; margin-top: 8px; }
	.catalog-color-row {
		display: flex; align-items: center; gap: 10px;
		font-size: 12px;
	}
	.catalog-color-box {
		width: 28px; height: 28px; border-radius: 3px; flex-shrink: 0;
	}
	.catalog-color-box.light { border: 1px solid var(--border); }
	.catalog-color-name { color: var(--fg); flex: 1; }
	.catalog-color-code {
		font-size: 11px; color: var(--fg3);
		font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
	}

	/* ── Modal shared / settings / history ─────────────────── */
	.modal-head {
		display: flex; align-items: center; justify-content: space-between;
		padding: 14px 18px 10px; border-bottom: 1px solid var(--border); flex-shrink: 0;
	}
	.settings-modal, .history-modal {
		position: fixed; top: 50%; left: 50%; transform: translate(-50%, -50%);
		z-index: 401;
		background: #faf9f6; border-radius: var(--r-lg);
		box-shadow: 0 12px 48px rgba(0,0,0,0.18);
		display: flex; flex-direction: column; overflow: hidden;
	}
	.settings-modal { width: min(680px, calc(100vw - 32px)); max-height: 88vh; }
	.history-modal { width: min(920px, calc(100vw - 32px)); max-height: 88vh; }
	.settings-tabs {
		display: flex; gap: 0; border-bottom: 1px solid var(--border); background: var(--bg);
	}
	.settings-tabs button {
		padding: 9px 16px; border: none; border-bottom: 2px solid transparent;
		background: none; color: var(--fg2); font-size: 13px; cursor: pointer; font-family: inherit;
	}
	.settings-tabs button.active { color: var(--fg); border-bottom-color: var(--fg); font-weight: 500; }
	.settings-body {
		padding: 14px 16px; overflow-y: auto;
		display: flex; flex-direction: column; gap: 10px;
	}
	.form-row {
		display: flex; align-items: center; gap: 8px; margin-bottom: 7px;
	}
	.form-row label { width: 90px; color: var(--fg2); font-size: 12px; flex-shrink: 0; }
	.form-row input, .form-row select, .full-select, .plugin-add input, .history-search input {
		flex: 1; min-width: 0; padding: 5px 7px;
		border: 1px solid var(--border2); border-radius: var(--r);
		background: #fff; color: var(--fg); font-size: 12px; font-family: inherit;
	}
	.check-row { display: flex; align-items: center; gap: 7px; color: var(--fg2); font-size: 12px; }
	.settings-inline-actions { display: flex; align-items: center; gap: 10px; }
	.db-test-result { color: var(--fg2); font-size: 12px; }
	.plugin-list {
		border: 1px solid var(--border); border-radius: var(--r);
		background: #fff; overflow: hidden;
	}
	.plugin-row {
		display: grid; grid-template-columns: 1fr auto auto; gap: 10px;
		align-items: center; padding: 9px 10px; border-bottom: 1px solid var(--border);
	}
	.plugin-row:last-child { border-bottom: none; }
	.plugin-version { color: var(--fg3); font-size: 11px; }
	.plugin-add { display: flex; gap: 8px; align-items: center; }
	.inline-confirm {
		display: flex; align-items: center; gap: 8px; justify-content: flex-end;
		background: #fff; border: 1px solid var(--border); border-radius: var(--r);
		padding: 9px 10px; font-size: 12px; color: var(--fg2);
	}
	.danger-btn, .confirm-btn {
		padding: 4px 10px; border: none; border-radius: var(--r);
		color: #fff; font-size: 11px; cursor: pointer; font-family: inherit;
	}
	.danger-btn { background: #c0392b; }
	.confirm-btn { background: var(--fg); }
	.danger-btn:disabled { opacity: 0.4; cursor: not-allowed; }
	.modal-head-actions { display: flex; align-items: center; gap: 8px; }
	.history-tools {
		display: flex; align-items: center; gap: 8px;
		padding: 10px 14px; border-bottom: 1px solid var(--border);
	}
	.history-search { margin-left: auto; display: flex; align-items: center; gap: 6px; color: var(--fg2); font-size: 12px; }
	.history-table-wrap { overflow: auto; padding: 0 14px 14px; }
	.history-table {
		width: 100%; border-collapse: collapse; background: #fff;
		font-size: 12px; margin-top: 12px;
	}
	.history-table th, .history-table td {
		border: 1px solid var(--border); padding: 7px 8px; text-align: left; vertical-align: middle;
	}
	.history-table th { color: var(--fg3); font-weight: 500; background: var(--bg); }
	.history-mini { width: 48px; height: 36px; overflow: hidden; background: #fff; border: 1px solid var(--border); }
	.history-mini :global(svg) { width: 100%; height: 100%; display: block; }
	.confirm-layer {
		position: fixed; inset: 0; z-index: 600;
		display: flex; align-items: center; justify-content: center;
	}
	.confirm-backdrop {
		position: absolute; inset: 0; background: rgba(0,0,0,0.3);
	}
	.confirm-box {
		position: relative; background: #fff; border-radius: var(--r-lg);
		padding: 22px 24px; box-shadow: 0 8px 32px rgba(0,0,0,0.18);
		min-width: 280px; text-align: center;
	}
	.confirm-box p { margin-bottom: 16px; font-size: 13px; color: var(--fg); }
	.confirm-actions { display: flex; gap: 8px; justify-content: center; }

	/* ── Animations ─────────────────────────────────────────── */
	@keyframes inkupulse {
		0%, 100% { opacity: 1; transform: scale(1); }
		50%       { opacity: 0.4; transform: scale(0.7); }
	}
	@keyframes birdFly {
		0% { left: -20px; }
		100% { left: calc(100% + 4px); }
	}
	@keyframes freeBirdX {
		0% { transform: translateX(30px); }
		18% { transform: translateX(340px); }
		35% { transform: translateX(120px); }
		52% { transform: translateX(390px); }
		68% { transform: translateX(60px); }
		83% { transform: translateX(280px); }
		100% { transform: translateX(30px); }
	}
	@keyframes freeBirdY {
		0% { top: 70px; }
		22% { top: 220px; }
		38% { top: 40px; }
		55% { top: 180px; }
		70% { top: 20px; }
		85% { top: 140px; }
		100% { top: 70px; }
	}
</style>

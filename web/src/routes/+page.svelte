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

	declare const __BUILD_NUMBER__: string;

	const HISTORY_PAGE_SIZE = 10;
	const PROVIDER_STAGE1_KEY = 'inku-provider-stage1';
	const MODEL_STAGE1_KEY = 'inku-model-stage1';
	const PROVIDER_STAGE2_KEY = 'inku-provider-stage2';
	const MODEL_STAGE2_KEY = 'inku-model-stage2';

	type Score = { instructions: unknown[] };

	type PaintResult = {
		svg: string;
		score: Score;
		elapsed_stage1_ms: number;
		elapsed_stage2_ms: number;
		elapsed_total_ms: number;
	};

	type Iteration = {
		input: string;
		ddl: string | null;
		thinking?: string | null;
		score: Score;
		svg: string;
		at: number;
		elapsed_ms?: number;
		stage1_model?: string | null;
		stage2_model?: string | null;
	};

	// ── Input ───────────────────────────────────────────────
	let inputMode = $state<'single' | 'batch'>('single');
	let input = $state('山の向こうに月が昇る');
	let batchInput = $state('');
	let textareaEl = $state<HTMLTextAreaElement | null>(null);

	// ── Loading ─────────────────────────────────────────────
	let loading = $state(false);
	let stageLabel = $state('');
	let batchCurrent = $state(0);
	let batchTotal = $state(0);
	let error = $state<string | null>(null);

	// ── Result ──────────────────────────────────────────────
	let ddl = $state<string | null>(null);
	let thinking = $state<string | null>(null);
	let result = $state<PaintResult | null>(null);

	// ── UI ──────────────────────────────────────────────────
	let saijikiOpen = $state(false);
	let outputTab = $state<'canvas' | 'prompts' | 'score'>('canvas');

	// ── Models ──────────────────────────────────────────────
	let stage1Provider = $state<Provider>(DEFAULT_PROVIDER);
	let stage1Model = $state<string>(DEFAULT_MODEL);
	let stage2Provider = $state<Provider>(DEFAULT_PROVIDER);
	let stage2Model = $state<string>(DEFAULT_MODEL);
	let includeThinking = $state(false);

	// ── Snapshots ───────────────────────────────────────────
	type SnapshotMeta = { id: string; name: string; at: number };
	let snapshots = $state<SnapshotMeta[]>([]);
	let activeSnapshotId = $state<string | null>(null);
	let newSnapshotName = $state('');
	let snapshotPanelOpen = $state(false);

	// ── Timer ───────────────────────────────────────────────
	let elapsedStage1Ms = $state(0);
	let elapsedStage2Ms = $state(0);
	let elapsedTotalMs = $state(0);
	let liveMs = $state(0);
	let _timerStart = 0;
	let _timerHandle: ReturnType<typeof setInterval> | null = null;

	// ── History ─────────────────────────────────────────────
	let historyItems = $state<Iteration[]>([]);
	let historyTotal = $state(0);
	let historyPage = $state(0);
	let historyCursor = $state(-1);
	const historyTotalPages = $derived(Math.ceil(historyTotal / HISTORY_PAGE_SIZE));

	let promptsData = $state<{ stage1_system: string; stage2_system: string } | null>(null);

	// ── Batch derived ────────────────────────────────────────
	const batchLines = $derived(batchInput.split('\n'));
	const lineNumbersText = $derived(batchLines.map((_, i) => String(i + 1)).join('\n'));
	const batchNonEmpty = $derived(batchLines.filter((l) => l.trim()).length);
	const canSubmit = $derived(
		inputMode === 'single' ? !!input.trim() : batchNonEmpty > 0
	);

	// ── Timer ───────────────────────────────────────────────
	function startTimer() {
		_timerStart = Date.now();
		liveMs = 0;
		_timerHandle = setInterval(() => {
			liveMs = Date.now() - _timerStart;
		}, 100);
	}

	function stopTimer() {
		if (_timerHandle !== null) {
			clearInterval(_timerHandle);
			_timerHandle = null;
		}
	}

	// ── Core paint function (2-stage call) ──────────────────
	async function paintOne(text: string): Promise<{ ddl: string; thinking: string | null } & PaintResult> {
		const t0 = Date.now();

		stageLabel = '解釈中…';
		const r1 = await fetch('/api/interpret', {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({ text, model: stage1Model, include_thinking: includeThinking, snapshot_id: activeSnapshotId })
		});
		if (!r1.ok) {
			const d = await r1.json().catch(() => ({})) as { detail?: string };
			throw new Error(d.detail ?? `HTTP ${r1.status}`);
		}
		const d1 = (await r1.json()) as { ddl: string; thinking: string | null };
		const t1 = Date.now();

		stageLabel = '構造化中…';
		const r2 = await fetch('/api/compose', {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({ ddl: d1.ddl, model: stage2Model, original_text: text, snapshot_id: activeSnapshotId })
		});
		if (!r2.ok) {
			const d = await r2.json().catch(() => ({})) as { detail?: string };
			throw new Error(d.detail ?? `HTTP ${r2.status}`);
		}
		const d2 = (await r2.json()) as { score: Score; svg: string };
		const t2 = Date.now();

		return {
			ddl: d1.ddl,
			thinking: d1.thinking,
			score: d2.score,
			svg: d2.svg,
			elapsed_stage1_ms: t1 - t0,
			elapsed_stage2_ms: t2 - t1,
			elapsed_total_ms: t2 - t0
		};
	}

	// ── Submit ──────────────────────────────────────────────
	async function submit() {
		if (!canSubmit || loading) return;
		loading = true;
		error = null;
		ddl = null;
		thinking = null;
		elapsedStage1Ms = 0;
		elapsedStage2Ms = 0;
		elapsedTotalMs = 0;
		batchCurrent = 0;
		batchTotal = 0;
		startTimer();

		try {
			if (inputMode === 'single') {
				const r = await paintOne(input);
				ddl = r.ddl;
				thinking = r.thinking;
				result = r;
				outputTab = 'canvas';
				elapsedStage1Ms = r.elapsed_stage1_ms;
				elapsedStage2Ms = r.elapsed_stage2_ms;
				elapsedTotalMs = r.elapsed_total_ms;
				await pushHistory({
					input,
					ddl: r.ddl,
					thinking: r.thinking,
					score: r.score,
					svg: r.svg,
					at: Date.now(),
					elapsed_ms: r.elapsed_total_ms,
					stage1_model: stage1Model,
					stage2_model: stage2Model
				});
			} else {
				const lines = batchLines.map((l) => l.trim()).filter((l) => l);
				batchTotal = lines.length;
				outputTab = 'canvas';
				for (let i = 0; i < lines.length; i++) {
					if (!loading) break;
					batchCurrent = i + 1;
					try {
						const r = await paintOne(lines[i]);
						result = r;
						await pushHistory({
							input: lines[i],
							ddl: r.ddl,
							thinking: r.thinking,
							score: r.score,
							svg: r.svg,
							at: Date.now(),
							elapsed_ms: r.elapsed_total_ms,
							stage1_model: stage1Model,
							stage2_model: stage2Model
						});
					} catch {
						// continue with next line
					}
				}
				elapsedTotalMs = Date.now() - _timerStart;
			}
		} catch (e) {
			error = e instanceof Error ? e.message : String(e);
			result = null;
		} finally {
			stopTimer();
			loading = false;
			stageLabel = '';
			batchCurrent = 0;
			batchTotal = 0;
		}
	}

	function stopBatch() {
		loading = false;
	}

	// ── History ─────────────────────────────────────────────
	async function fetchHistoryPage(page: number): Promise<void> {
		const offset = page * HISTORY_PAGE_SIZE;
		try {
			const r = await fetch(`/api/history?offset=${offset}&limit=${HISTORY_PAGE_SIZE}`);
			if (!r.ok) return;
			const data = await r.json();
			historyItems = data.items;
			historyTotal = data.total;
			historyPage = page;
		} catch {
			// ignore
		}
	}

	async function pushHistory(it: Iteration): Promise<void> {
		try {
			await fetch('/api/history', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({
					input: it.input,
					ddl: it.ddl,
					score: it.score,
					svg: it.svg,
					at: it.at,
					elapsed_ms: it.elapsed_ms ?? 0,
					stage1_model: it.stage1_model ?? null,
					stage2_model: it.stage2_model ?? null
				})
			});
		} catch {
			// ignore
		}
		await fetchHistoryPage(0);
		historyCursor = 0;
	}

	async function clearHistory(): Promise<void> {
		try {
			await fetch('/api/history', { method: 'DELETE' });
		} catch {
			// ignore
		}
		historyItems = [];
		historyTotal = 0;
		historyPage = 0;
		historyCursor = -1;
		result = null;
		ddl = null;
	}

	function loadIteration(idx: number) {
		if (idx < 0 || idx >= historyItems.length) return;
		historyCursor = idx;
		const it = historyItems[idx];
		input = it.input;
		ddl = it.ddl;
		thinking = it.thinking ?? null;
		result = {
			score: it.score,
			svg: it.svg,
			elapsed_stage1_ms: 0,
			elapsed_stage2_ms: 0,
			elapsed_total_ms: it.elapsed_ms ?? 0
		};
		error = null;
	}

	function gotoPrev() {
		if (historyCursor < historyItems.length - 1) loadIteration(historyCursor + 1);
	}

	function gotoNext() {
		if (historyCursor > 0) loadIteration(historyCursor - 1);
	}

	// ── Saijiki ─────────────────────────────────────────────
	function insertWord(word: string) {
		if (inputMode === 'batch') {
			batchInput = batchInput ? batchInput + word : word;
			return;
		}
		const ta = textareaEl;
		if (!ta) {
			input = input + word;
			return;
		}
		const start = ta.selectionStart ?? input.length;
		const end = ta.selectionEnd ?? input.length;
		input = input.slice(0, start) + word + input.slice(end);
		requestAnimationFrame(() => {
			if (!textareaEl) return;
			textareaEl.focus();
			const pos = start + word.length;
			textareaEl.setSelectionRange(pos, pos);
		});
	}

	function handleKeydown(e: KeyboardEvent) {
		if (e.key === 'Escape' && saijikiOpen) saijikiOpen = false;
	}

	// ── Model selection ─────────────────────────────────────
	function setStage1Provider(v: Provider) {
		stage1Provider = v;
		stage1Model = modelsForProvider(v)[0]?.id ?? stage1Model;
		try {
			localStorage.setItem(PROVIDER_STAGE1_KEY, v);
			localStorage.setItem(MODEL_STAGE1_KEY, stage1Model);
		} catch {}
	}

	function setStage1Model(v: string) {
		stage1Model = v;
		try { localStorage.setItem(MODEL_STAGE1_KEY, v); } catch {}
	}

	function setStage2Provider(v: Provider) {
		stage2Provider = v;
		stage2Model = modelsForProvider(v)[0]?.id ?? stage2Model;
		try {
			localStorage.setItem(PROVIDER_STAGE2_KEY, v);
			localStorage.setItem(MODEL_STAGE2_KEY, stage2Model);
		} catch {}
	}

	function setStage2Model(v: string) {
		stage2Model = v;
		try { localStorage.setItem(MODEL_STAGE2_KEY, v); } catch {}
	}

	// ── Snapshots ───────────────────────────────────────────
	async function fetchSnapshots() {
		try {
			const r = await fetch('/api/saijiki/snapshots');
			if (r.ok) snapshots = await r.json();
		} catch {}
	}

	async function saveSnapshot() {
		const name = newSnapshotName.trim();
		if (!name) return;
		try {
			const r = await fetch('/api/saijiki/snapshots', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ name })
			});
			if (r.ok) {
				newSnapshotName = '';
				await fetchSnapshots();
			}
		} catch {}
	}

	async function deleteSnapshot(id: string) {
		try {
			await fetch(`/api/saijiki/snapshots/${id}`, { method: 'DELETE' });
			if (activeSnapshotId === id) activeSnapshotId = null;
			await fetchSnapshots();
		} catch {}
	}

	const activeSnapshotName = $derived(
		activeSnapshotId
			? (snapshots.find((s) => s.id === activeSnapshotId)?.name ?? '?')
			: '現在の設定'
	);

	// ── Mount ───────────────────────────────────────────────
	onMount(async () => {
		await Promise.all([fetchHistoryPage(0), fetchSnapshots()]);
		if (historyItems.length > 0) loadIteration(0);
		try {
			const p1 = localStorage.getItem(PROVIDER_STAGE1_KEY) as Provider | null;
			if (p1) stage1Provider = p1;
			const m1 = localStorage.getItem(MODEL_STAGE1_KEY);
			if (m1) stage1Model = m1;
			const p2 = localStorage.getItem(PROVIDER_STAGE2_KEY) as Provider | null;
			if (p2) stage2Provider = p2;
			const m2 = localStorage.getItem(MODEL_STAGE2_KEY);
			if (m2) stage2Model = m2;
		} catch {}
		try {
			const r = await fetch('/api/prompts');
			if (r.ok) promptsData = await r.json();
		} catch {}
	});
</script>

<main>
	<header>
		<div class="header-inner">
			<div>
				<h1>inku</h1>
				<p class="sub">視覚的な短歌を書く</p>
			</div>
			<span class="build-badge">#{__BUILD_NUMBER__}</span>
		</div>
	</header>

	<div class="model-row">
		<div class="model-group">
			<span class="model-label">解釈</span>
			<span class="field-label">接続先：</span>
			<select
				value={stage1Provider}
				onchange={(e) => setStage1Provider((e.currentTarget as HTMLSelectElement).value as Provider)}
			>
				{#each PROVIDER_GROUPS as pg (pg.id)}
					<option value={pg.id}>{pg.label}</option>
				{/each}
			</select>
			<span class="field-label">モデル：</span>
			<select
				value={stage1Model}
				onchange={(e) => setStage1Model((e.currentTarget as HTMLSelectElement).value)}
			>
				{#each modelsForProvider(stage1Provider) as m (m.id)}
					<option value={m.id}>{m.label}{m.notes ? ` — ${m.notes}` : ''}</option>
				{/each}
			</select>
		</div>
		<div class="model-group">
			<span class="model-label">構造化</span>
			<span class="field-label">接続先：</span>
			<select
				value={stage2Provider}
				onchange={(e) => setStage2Provider((e.currentTarget as HTMLSelectElement).value as Provider)}
			>
				{#each PROVIDER_GROUPS as pg (pg.id)}
					<option value={pg.id}>{pg.label}</option>
				{/each}
			</select>
			<span class="field-label">モデル：</span>
			<select
				value={stage2Model}
				onchange={(e) => setStage2Model((e.currentTarget as HTMLSelectElement).value)}
			>
				{#each modelsForProvider(stage2Provider) as m (m.id)}
					<option value={m.id}>{m.label}{m.notes ? ` — ${m.notes}` : ''}</option>
				{/each}
			</select>
		</div>
		{#if stage1Model.includes('qwen3')}
			<label class="think-toggle">
				<input type="checkbox" bind:checked={includeThinking} />
				<span>思考を表示</span>
			</label>
		{/if}
	</div>

	<div class="snapshot-row">
		<span class="snapshot-label">歳時記:</span>
		<button
			class="snapshot-active-btn"
			class:snapshot-default={!activeSnapshotId}
			onclick={() => (snapshotPanelOpen = !snapshotPanelOpen)}
		>{activeSnapshotName} ▾</button>

		{#if snapshotPanelOpen}
			<div class="snapshot-panel">
				<div class="snapshot-save-row">
					<input
						class="snapshot-name-input"
						type="text"
						bind:value={newSnapshotName}
						placeholder="スナップショット名 (例: 歳時記v1)"
						onkeydown={(e) => { if (e.key === 'Enter') saveSnapshot(); }}
					/>
					<button class="snapshot-save-btn" onclick={saveSnapshot} disabled={!newSnapshotName.trim()}>現在を保存</button>
				</div>
				<div class="snapshot-list">
					<label class="snapshot-item">
						<input
							type="radio"
							name="snapshot"
							checked={!activeSnapshotId}
							onchange={() => (activeSnapshotId = null)}
						/>
						<span class="snapshot-item-name">現在の設定</span>
					</label>
					{#each snapshots as snap (snap.id)}
						<div class="snapshot-item">
							<label>
								<input
									type="radio"
									name="snapshot"
									checked={activeSnapshotId === snap.id}
									onchange={() => (activeSnapshotId = snap.id)}
								/>
								<span class="snapshot-item-name">{snap.name}</span>
								<span class="snapshot-item-date">{new Date(snap.at).toLocaleDateString('ja-JP')}</span>
							</label>
							<button class="snapshot-delete-btn" onclick={() => deleteSnapshot(snap.id)}>✕</button>
						</div>
					{/each}
					{#if snapshots.length === 0}
						<p class="snapshot-empty">保存済みスナップショットはありません</p>
					{/if}
				</div>
			</div>
		{/if}
	</div>

	<div class="row">
		<section class="input">
			<div class="input-header">
				<div class="input-mode-tabs">
					<button
						class="mode-btn"
						class:active={inputMode === 'single'}
						onclick={() => (inputMode = 'single')}
					>記述</button>
					<button
						class="mode-btn"
						class:active={inputMode === 'batch'}
						onclick={() => (inputMode = 'batch')}
					>バッチ</button>
				</div>
				<button
					class="saijiki-toggle"
					aria-expanded={saijikiOpen}
					onclick={() => (saijikiOpen = !saijikiOpen)}
				>歳時記</button>
			</div>

			{#if inputMode === 'single'}
				<textarea
					id="input-ta"
					bind:this={textareaEl}
					bind:value={input}
					rows="8"
					spellcheck="false"
					placeholder="山の向こうに月が昇る"
				></textarea>
			{:else}
				<div class="batch-wrapper">
					<div class="line-nums" aria-hidden="true">{lineNumbersText}</div>
					<textarea
						class="batch-ta"
						bind:value={batchInput}
						rows="8"
						spellcheck="false"
						placeholder="山の向こうに月が昇る&#10;夜の霧が広がる&#10;青いクレヨンの線"
					></textarea>
				</div>
				{#if batchNonEmpty > 0}
					<p class="batch-info">{batchNonEmpty} 件</p>
				{/if}
			{/if}

			<div class="submit-row">
				<button class="submit" onclick={submit} disabled={!canSubmit || (loading && inputMode === 'single')}>
					{#if loading}
						{#if batchTotal > 0}
							{batchCurrent} / {batchTotal} 番目を演奏中…
						{:else}
							{stageLabel || '演奏中…'}
						{/if}
					{:else}
						演奏する
					{/if}
				</button>
				{#if loading && batchTotal > 0}
					<span class="stage-label">{stageLabel}</span>
					<button class="stop-btn" onclick={stopBatch}>停止</button>
				{/if}
				{#if loading}
					<span class="elapsed elapsed-live">{(liveMs / 1000).toFixed(1)}s</span>
				{:else if elapsedTotalMs > 0}
					{#if elapsedStage1Ms > 0}
						<span class="elapsed">
							解釈 {(elapsedStage1Ms / 1000).toFixed(1)}s + 構造化 {(elapsedStage2Ms / 1000).toFixed(1)}s = {(elapsedTotalMs / 1000).toFixed(1)}s
						</span>
					{:else}
						<span class="elapsed">{(elapsedTotalMs / 1000).toFixed(1)}s</span>
					{/if}
				{/if}
			</div>
			{#if error}
				<p class="error">{error}</p>
			{/if}

			{#if result && inputMode === 'single'}
				<div class="interpreted">
					<label for="input-feedback">入力に含まれた語彙</label>
					<div id="input-feedback" class="annot-box">
						{#each annotate(input) as part, i (i)}
							{#if part.kind === 'saijiki'}
								<span class="tok tok-saijiki" title={part.category}>{part.text}</span>
							{:else if part.kind === 'emotion'}
								<span class="tok tok-emotion" title="感情語彙 (正規化で置換)">{part.text}</span>
							{:else}
								<span class="tok tok-plain">{part.text}</span>
							{/if}
						{/each}
					</div>
				</div>
			{/if}

			{#if thinking}
				<details class="thinking" open>
					<summary>思考 (qwen3 内部)</summary>
					<pre>{thinking}</pre>
				</details>
			{/if}

			{#if ddl}
				<div class="interpreted">
					<label for="ddl-interpret">解釈 (正規化DDL)</label>
					<div id="ddl-interpret" class="annot-box ddl-box">
						{#each annotate(ddl) as part, i (i)}
							{#if part.kind === 'saijiki'}
								<span class="tok tok-saijiki" title={part.category}>{part.text}</span>
							{:else if part.kind === 'emotion'}
								<span class="tok tok-emotion">{part.text}</span>
							{:else}
								<span class="tok tok-plain">{part.text}</span>
							{/if}
						{/each}
					</div>
				</div>
			{/if}
		</section>

		<section class="output">
			<div class="output-head">
				<div class="output-tabs">
					<button
						class="tab-btn"
						class:active={outputTab === 'canvas'}
						onclick={() => (outputTab = 'canvas')}
					>演奏</button>
					<button
						class="tab-btn"
						class:active={outputTab === 'prompts'}
						onclick={() => (outputTab = 'prompts')}
						disabled={!result}
					>プロンプト</button>
					<button
						class="tab-btn"
						class:active={outputTab === 'score'}
						onclick={() => (outputTab = 'score')}
						disabled={!result}
					>楽譜</button>
				</div>
				{#if historyTotal > 0}
					<div class="nav" aria-label="履歴ナビゲーション">
						<button
							class="nav-btn"
							onclick={gotoPrev}
							disabled={historyCursor >= historyItems.length - 1}
							aria-label="古い演奏"
						>◀</button>
						<span class="counter">{historyPage * HISTORY_PAGE_SIZE + historyCursor + 1} / {historyTotal}</span>
						<button
							class="nav-btn"
							onclick={gotoNext}
							disabled={historyCursor <= 0}
							aria-label="新しい演奏"
						>▶</button>
					</div>
				{/if}
			</div>

			{#if outputTab === 'canvas'}
				<div id="canvas" class="canvas">
					{#if result}
						{@html result.svg}
					{:else}
						<div class="placeholder">（まだ演奏されていない）</div>
					{/if}
				</div>
			{:else if outputTab === 'prompts'}
				{#if promptsData}
					<div class="prompt-section">
						<p class="prompt-label">Stage 1 ユーザー入力</p>
						<pre class="prompt-pre">{inputMode === 'single' ? input : '(バッチモード)'}</pre>
						<p class="prompt-label">Stage 1 システムプロンプト</p>
						<pre class="prompt-pre prompt-pre-lg">{promptsData.stage1_system}</pre>
						{#if ddl}
							<p class="prompt-label">Stage 2 ユーザー入力 (正規化DDL)</p>
							<pre class="prompt-pre">{ddl}</pre>
						{/if}
						<p class="prompt-label">Stage 2 システムプロンプト</p>
						<pre class="prompt-pre prompt-pre-lg">{promptsData.stage2_system}</pre>
					</div>
				{:else}
					<p class="muted">読み込み中…</p>
				{/if}
			{:else if outputTab === 'score'}
				<pre class="score-pre">{JSON.stringify(result?.score, null, 2)}</pre>
			{/if}
		</section>
	</div>

	{#if historyTotal > 1}
		<section class="history" aria-label="演奏履歴">
			<div class="history-head">
				<h2>履歴 <span class="muted">({historyTotal})</span></h2>
				{#if historyTotalPages > 1}
					<div class="page-nav">
						<button
							onclick={() => fetchHistoryPage(historyPage - 1)}
							disabled={historyPage <= 0}
							aria-label="新しいページ"
						>← 新</button>
						<span>{historyPage + 1} / {historyTotalPages}</span>
						<button
							onclick={() => fetchHistoryPage(historyPage + 1)}
							disabled={historyPage >= historyTotalPages - 1}
							aria-label="古いページ"
						>旧 →</button>
					</div>
				{/if}
				<button class="clear-btn" onclick={clearHistory}>全て消す</button>
			</div>
			<div class="strip">
				{#each historyItems as it, i (it.at)}
					<button
						class="thumb"
						class:current={i === historyCursor}
						onclick={() => loadIteration(i)}
						title="{it.input}{it.stage1_model ? ` [${it.stage1_model}]` : ''}"
					>
						<div class="thumb-svg">{@html it.svg}</div>
						<div class="thumb-label">
							{#if it.elapsed_ms && it.elapsed_ms > 0}
								{(it.elapsed_ms / 1000).toFixed(1)}s
							{:else}
								{historyPage * HISTORY_PAGE_SIZE + i + 1}
							{/if}
						</div>
					</button>
				{/each}
			</div>
		</section>
	{/if}
</main>

<svelte:window onkeydown={handleKeydown} />

{#if saijikiOpen}
	<div
		class="saijiki-backdrop"
		onclick={() => (saijikiOpen = false)}
		aria-hidden="true"
	></div>
	<aside class="saijiki" aria-label="歳時記 - 語彙一覧">
		<div class="saijiki-head">
			<h2>歳時記 <span class="en">Saijiki</span></h2>
			<button class="saijiki-close" onclick={() => (saijikiOpen = false)} aria-label="閉じる">×</button>
		</div>
		<p class="saijiki-hint">語彙をクリックすると記述欄に挿入されます。</p>
		{#each SAIJIKI as cat (cat.key)}
			<section class="saijiki-cat">
				<h3>{cat.label} <span class="en">{cat.en}</span></h3>
				<div class="chips">
					{#each cat.words as word (word)}
						<button class="chip" onclick={() => insertWord(word)}>{word}</button>
					{/each}
				</div>
			</section>
		{/each}
	</aside>
{/if}

<style>
	:global(body) {
		background: #f7f5ef;
		color: #111;
		font-family:
			-apple-system, 'Hiragino Kaku Gothic ProN', 'Yu Gothic', 'Meiryo', sans-serif;
		margin: 0;
	}

	main {
		max-width: 1200px;
		margin: 0 auto;
		padding: 2rem 1.5rem;
	}

	header { margin-bottom: 1.5rem; }

	.header-inner {
		display: flex;
		justify-content: space-between;
		align-items: flex-end;
	}

	.build-badge {
		font-size: 0.75rem;
		color: #aaa;
		font-variant-numeric: tabular-nums;
		align-self: flex-start;
		padding-top: 0.25rem;
	}

	h1 { font-size: 2rem; margin: 0; letter-spacing: 0.2em; }
	.sub { color: #666; margin: 0.25rem 0 0; }

	/* ── Model row ─────────────────────────────────────────── */
	.model-row {
		display: flex;
		gap: 1rem;
		margin-bottom: 1.5rem;
		flex-wrap: wrap;
	}

	.model-group {
		display: flex;
		align-items: center;
		gap: 0.35rem;
		font-size: 0.85rem;
	}

	.model-label { color: #888; min-width: 2.5rem; }
	.field-label { color: #aaa; font-size: 0.8rem; white-space: nowrap; }

	.model-group select {
		font-family: inherit;
		font-size: 0.85rem;
		padding: 0.25rem 0.5rem;
		border: 1px solid #ccc;
		border-radius: 3px;
		background: #fff;
		color: #333;
	}

	.think-toggle {
		display: flex;
		align-items: center;
		gap: 0.35rem;
		font-size: 0.85rem;
		color: #666;
		cursor: pointer;
	}

	/* ── Snapshot row ──────────────────────────────────────── */
	.snapshot-row {
		display: flex;
		align-items: flex-start;
		gap: 0.5rem;
		margin-bottom: 1.5rem;
		position: relative;
		font-size: 0.85rem;
	}

	.snapshot-label {
		color: #888;
		white-space: nowrap;
		padding-top: 0.3rem;
	}

	.snapshot-active-btn {
		font-family: inherit;
		font-size: 0.85rem;
		padding: 0.25rem 0.6rem;
		border: 1px solid #ccc;
		border-radius: 3px;
		background: #fff;
		color: #333;
		cursor: pointer;
		white-space: nowrap;
	}

	.snapshot-active-btn.snapshot-default {
		color: #888;
	}

	.snapshot-panel {
		position: absolute;
		top: calc(100% + 4px);
		left: 0;
		z-index: 200;
		background: #fff;
		border: 1px solid #ccc;
		border-radius: 4px;
		padding: 0.75rem;
		min-width: 320px;
		box-shadow: 0 4px 12px rgba(0,0,0,0.1);
	}

	.snapshot-save-row {
		display: flex;
		gap: 0.5rem;
		margin-bottom: 0.75rem;
	}

	.snapshot-name-input {
		flex: 1;
		font-family: inherit;
		font-size: 0.85rem;
		padding: 0.25rem 0.5rem;
		border: 1px solid #ccc;
		border-radius: 3px;
	}

	.snapshot-save-btn {
		font-family: inherit;
		font-size: 0.82rem;
		padding: 0.25rem 0.6rem;
		border: 1px solid #999;
		border-radius: 3px;
		background: #f0f0f0;
		cursor: pointer;
		white-space: nowrap;
	}

	.snapshot-save-btn:disabled {
		opacity: 0.4;
		cursor: default;
	}

	.snapshot-list {
		display: flex;
		flex-direction: column;
		gap: 0.3rem;
		max-height: 200px;
		overflow-y: auto;
	}

	.snapshot-item {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 0.4rem;
		font-size: 0.85rem;
	}

	.snapshot-item label {
		display: flex;
		align-items: center;
		gap: 0.4rem;
		cursor: pointer;
		flex: 1;
	}

	.snapshot-item-name {
		font-weight: 500;
	}

	.snapshot-item-date {
		color: #aaa;
		font-size: 0.78rem;
	}

	.snapshot-delete-btn {
		border: none;
		background: none;
		color: #bbb;
		font-size: 0.8rem;
		cursor: pointer;
		padding: 0 0.2rem;
		line-height: 1;
	}

	.snapshot-delete-btn:hover {
		color: #e55;
	}

	.snapshot-empty {
		color: #aaa;
		font-size: 0.82rem;
		margin: 0.25rem 0;
	}

	/* ── Layout ────────────────────────────────────────────── */
	.row {
		display: grid;
		grid-template-columns: 1fr 1fr;
		gap: 2rem;
	}

	/* ── Input section ─────────────────────────────────────── */
	.input-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
		margin-bottom: 0.5rem;
	}

	.input-mode-tabs {
		display: flex;
		gap: 0;
		border: 1px solid #ccc;
		border-radius: 4px;
		overflow: hidden;
	}

	.mode-btn {
		background: #fff;
		border: none;
		border-right: 1px solid #ccc;
		color: #666;
		padding: 0.3rem 0.9rem;
		cursor: pointer;
		font-family: inherit;
		font-size: 0.85rem;
		line-height: 1;
	}

	.mode-btn:last-child { border-right: none; }

	.mode-btn:hover:not(.active) { background: #f5f5f5; }

	.mode-btn.active {
		background: #111;
		color: #fff;
	}

	textarea {
		width: 100%;
		padding: 0.75rem;
		font-family: inherit;
		font-size: 1rem;
		line-height: 1.6;
		border: 1px solid #ccc;
		border-radius: 4px;
		background: #fff;
		box-sizing: border-box;
		resize: vertical;
	}

	/* ── Batch ─────────────────────────────────────────────── */
	.batch-wrapper {
		display: flex;
		border: 1px solid #ccc;
		border-radius: 4px;
		overflow: hidden;
	}

	.line-nums {
		background: #f5f5f5;
		border-right: 1px solid #ddd;
		padding: 0.75rem 0.5rem;
		font-family: 'SF Mono', 'Menlo', monospace;
		font-size: 1rem;
		line-height: 1.6;
		text-align: right;
		color: #bbb;
		user-select: none;
		white-space: pre;
		min-width: 2rem;
	}

	.batch-ta {
		flex: 1;
		border: none;
		border-radius: 0;
		padding: 0.75rem;
		font-family: inherit;
		font-size: 1rem;
		line-height: 1.6;
		resize: vertical;
		min-height: 8rem;
	}

	.batch-info {
		margin: 0.3rem 0 0;
		font-size: 0.8rem;
		color: #999;
	}

	/* ── Submit row ────────────────────────────────────────── */
	.submit-row {
		display: flex;
		align-items: center;
		gap: 0.75rem;
		margin-top: 0.75rem;
		flex-wrap: wrap;
	}

	button.submit {
		padding: 0.5rem 1.25rem;
		background: #111;
		color: #fff;
		border: none;
		border-radius: 4px;
		cursor: pointer;
		font-size: 0.95rem;
		font-family: inherit;
	}

	button.submit:disabled {
		background: #999;
		cursor: not-allowed;
	}

	.stop-btn {
		padding: 0.4rem 0.9rem;
		background: transparent;
		border: 1px solid #a2342a;
		color: #a2342a;
		border-radius: 4px;
		cursor: pointer;
		font-size: 0.85rem;
		font-family: inherit;
	}

	.stop-btn:hover { background: #a2342a; color: #fff; }

	.stage-label {
		font-size: 0.8rem;
		color: #888;
		font-style: italic;
	}

	.elapsed { font-size: 0.8rem; color: #888; font-variant-numeric: tabular-nums; }
	.elapsed-live { color: #c9a08a; }

	.error { color: #a2342a; margin-top: 0.75rem; }

	/* ── Annotations ───────────────────────────────────────── */
	.interpreted { margin-top: 1.5rem; }

	label {
		display: block;
		font-size: 0.85rem;
		color: #666;
		margin-bottom: 0.5rem;
	}

	.annot-box {
		padding: 0.75rem;
		background: #fff;
		border: 1px solid #ddd;
		border-radius: 4px;
		font-size: 0.95rem;
		line-height: 1.9;
		white-space: pre-wrap;
		word-break: break-word;
	}

	.ddl-box { border-left: 3px solid #888; border-radius: 0 4px 4px 0; }

	.tok { transition: color 0.15s; }
	.tok-saijiki { color: #2c3e91; font-weight: 500; }
	.tok-plain { color: #9a9a9a; }
	.tok-emotion {
		color: #c9a08a;
		font-style: italic;
		text-decoration: line-through;
		text-decoration-color: rgba(162, 52, 42, 0.4);
		text-decoration-thickness: 1px;
	}

	.thinking {
		margin-top: 1rem;
		font-size: 0.85rem;
		background: #f3efe6;
		border-left: 3px solid #c9a08a;
		border-radius: 0 3px 3px 0;
		padding: 0.5rem 0.75rem;
	}

	.thinking summary { cursor: pointer; color: #8a6f5a; font-style: italic; }

	.thinking pre {
		white-space: pre-wrap;
		word-break: break-word;
		color: #6b5340;
		font-family: inherit;
		line-height: 1.6;
		margin: 0.5rem 0 0;
		max-height: 240px;
		overflow-y: auto;
		background: transparent;
		border: none;
		padding: 0;
	}

	/* ── Output section ────────────────────────────────────── */
	.output-head {
		display: flex;
		justify-content: space-between;
		align-items: center;
		margin-bottom: 0.5rem;
		gap: 0.5rem;
	}

	.output-tabs {
		display: flex;
		gap: 0;
		border: 1px solid #ccc;
		border-radius: 4px;
		overflow: hidden;
	}

	.tab-btn {
		background: #fff;
		border: none;
		border-right: 1px solid #ccc;
		color: #666;
		padding: 0.3rem 0.9rem;
		cursor: pointer;
		font-family: inherit;
		font-size: 0.85rem;
		line-height: 1;
	}

	.tab-btn:last-child { border-right: none; }
	.tab-btn:hover:not(:disabled):not(.active) { background: #f5f5f5; }
	.tab-btn.active { background: #111; color: #fff; }
	.tab-btn:disabled { opacity: 0.4; cursor: not-allowed; }

	.canvas {
		aspect-ratio: 1 / 1;
		border: 1px solid #ccc;
		border-radius: 4px;
		background: #fff;
		overflow: hidden;
	}

	.canvas :global(svg) { width: 100%; height: 100%; display: block; }

	.placeholder {
		height: 100%;
		display: flex;
		align-items: center;
		justify-content: center;
		color: #999;
	}

	/* ── Prompts tab ───────────────────────────────────────── */
	.prompt-section {
		display: flex;
		flex-direction: column;
		gap: 0.25rem;
		max-height: 680px;
		overflow-y: auto;
		border: 1px solid #ddd;
		border-radius: 4px;
		padding: 0.75rem;
		background: #fff;
	}

	.prompt-label {
		margin: 0.5rem 0 0.2rem;
		font-size: 0.8rem;
		font-weight: 600;
		color: #555;
	}

	.prompt-pre {
		background: #f8f6f0;
		padding: 0.65rem 0.75rem;
		border-radius: 4px;
		border: 1px solid #ddd;
		overflow-x: auto;
		max-height: 160px;
		white-space: pre-wrap;
		word-break: break-word;
		font-size: 0.78rem;
		line-height: 1.5;
		margin: 0;
	}

	.prompt-pre-lg {
		max-height: 400px;
	}

	/* ── Score tab ─────────────────────────────────────────── */
	.score-pre {
		background: #fff;
		border: 1px solid #ddd;
		border-radius: 4px;
		padding: 0.75rem;
		overflow: auto;
		max-height: 620px;
		font-size: 0.82rem;
		line-height: 1.5;
		white-space: pre-wrap;
		word-break: break-word;
		box-sizing: border-box;
		width: 100%;
	}

	/* ── Nav ───────────────────────────────────────────────── */
	.nav { display: flex; align-items: center; gap: 0.5rem; font-size: 0.85rem; }

	.nav-btn {
		background: transparent;
		border: 1px solid #bbb;
		color: #333;
		width: 28px;
		height: 28px;
		border-radius: 50%;
		cursor: pointer;
		font-size: 0.7rem;
		padding: 0;
		line-height: 1;
		display: inline-flex;
		align-items: center;
		justify-content: center;
		font-family: inherit;
	}

	.nav-btn:hover:not(:disabled) { background: #111; color: #fff; border-color: #111; }
	.nav-btn:disabled { opacity: 0.35; cursor: not-allowed; }
	.counter { color: #666; min-width: 3rem; text-align: center; }

	/* ── History ───────────────────────────────────────────── */
	.history {
		margin-top: 2.5rem;
		border-top: 1px solid #ddd;
		padding-top: 1.5rem;
	}

	.history-head {
		display: flex;
		justify-content: space-between;
		align-items: center;
		gap: 0.75rem;
		margin-bottom: 0.75rem;
	}

	.history h2 { font-size: 1rem; font-weight: 600; color: #555; margin: 0; }

	.page-nav {
		display: flex;
		align-items: center;
		gap: 0.35rem;
		font-size: 0.8rem;
		color: #666;
	}

	.page-nav button {
		background: transparent;
		border: 1px solid #ccc;
		color: #555;
		padding: 0.2rem 0.5rem;
		border-radius: 3px;
		cursor: pointer;
		font-size: 0.75rem;
		font-family: inherit;
	}

	.page-nav button:disabled { opacity: 0.35; cursor: not-allowed; }
	.page-nav button:hover:not(:disabled) { background: #111; color: #fff; border-color: #111; }

	.muted { color: #aaa; font-weight: normal; font-size: 0.85rem; margin-left: 0.25rem; }

	.clear-btn {
		background: transparent;
		border: 1px solid #ccc;
		color: #888;
		padding: 0.3rem 0.7rem;
		border-radius: 3px;
		cursor: pointer;
		font-size: 0.8rem;
		font-family: inherit;
	}

	.clear-btn:hover { color: #a2342a; border-color: #a2342a; }

	.strip {
		display: flex;
		gap: 0.75rem;
		overflow-x: auto;
		padding-bottom: 0.5rem;
	}

	.thumb {
		flex: 0 0 auto;
		width: 96px;
		background: #fff;
		border: 1px solid #ddd;
		border-radius: 4px;
		padding: 0;
		cursor: pointer;
		overflow: hidden;
		font-family: inherit;
	}

	.thumb.current { border-color: #111; box-shadow: 0 0 0 2px #11111133; }

	.thumb-svg { width: 96px; height: 96px; overflow: hidden; }
	.thumb-svg :global(svg) { width: 100%; height: 100%; display: block; }

	.thumb-label {
		padding: 0.2rem;
		font-size: 0.75rem;
		color: #888;
		text-align: center;
		border-top: 1px solid #eee;
	}

	/* ── Saijiki panel ─────────────────────────────────────── */
	.saijiki-toggle {
		background: transparent;
		border: 1px solid #888;
		color: #333;
		padding: 0.4rem 1rem;
		border-radius: 999px;
		cursor: pointer;
		font-size: 0.9rem;
		font-family: inherit;
	}

	.saijiki-toggle:hover { background: #111; color: #fff; border-color: #111; }

	.saijiki-backdrop {
		position: fixed;
		inset: 0;
		background: rgba(0, 0, 0, 0.2);
		z-index: 10;
	}

	.saijiki {
		position: fixed;
		top: 0;
		right: 0;
		bottom: 0;
		width: min(380px, 90vw);
		background: #fbf9f3;
		border-left: 1px solid #ccc;
		box-shadow: -4px 0 16px rgba(0, 0, 0, 0.08);
		overflow-y: auto;
		padding: 1.5rem;
		z-index: 11;
	}

	.saijiki-head {
		display: flex;
		justify-content: space-between;
		align-items: baseline;
		margin-bottom: 0.25rem;
	}

	.saijiki-head h2 { margin: 0; font-size: 1.3rem; letter-spacing: 0.1em; }
	.saijiki-head .en { font-size: 0.75rem; color: #888; font-weight: normal; }

	.saijiki-close {
		background: transparent;
		border: none;
		font-size: 1.5rem;
		color: #666;
		cursor: pointer;
		line-height: 1;
		padding: 0 0.25rem;
	}

	.saijiki-hint { color: #888; font-size: 0.8rem; margin: 0 0 1rem; }
	.saijiki-cat { margin-bottom: 1.5rem; }
	.saijiki-cat h3 { margin: 0 0 0.5rem; font-size: 0.95rem; color: #333; font-weight: 600; }
	.saijiki-cat .en { font-size: 0.7rem; color: #aaa; font-weight: normal; margin-left: 0.25rem; }

	.chips { display: flex; flex-wrap: wrap; gap: 0.4rem; }

	.chip {
		background: #fff;
		border: 1px solid #ddd;
		color: #333;
		padding: 0.3rem 0.7rem;
		border-radius: 3px;
		cursor: pointer;
		font-size: 0.9rem;
		font-family: inherit;
	}

	.chip:hover { background: #111; color: #fff; border-color: #111; }

	@media (max-width: 720px) {
		.row { grid-template-columns: 1fr; }
	}

	pre {
		background: #fff;
		padding: 0.75rem;
		border-radius: 4px;
		border: 1px solid #ddd;
		overflow: auto;
		max-height: 300px;
	}

	details { margin-top: 1rem; font-size: 0.85rem; }
</style>

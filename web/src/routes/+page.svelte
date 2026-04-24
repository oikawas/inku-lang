<script lang="ts">
	import { onMount } from 'svelte';
	import { browser } from '$app/environment';
	import { SAIJIKI } from '$lib/saijiki';
	import { annotate } from '$lib/highlight';
	import {
		PROVIDER_GROUPS,
		DEFAULT_PROVIDER,
		DEFAULT_MODEL,
		modelsForProvider,
		providerOfModel,
		type Provider
	} from '$lib/models';

	const STORAGE_KEY = 'inku-history-v1';
	const PROVIDER_STAGE1_KEY = 'inku-provider-stage1';
	const MODEL_STAGE1_KEY = 'inku-model-stage1';
	const PROVIDER_STAGE2_KEY = 'inku-provider-stage2';
	const MODEL_STAGE2_KEY = 'inku-model-stage2';

	type Score = { instructions: unknown[] };

	type PaintResponse = {
		text: string;
		ddl: string;
		thinking: string | null;
		score: Score;
		svg: string;
		elapsed_stage1_ms: number;
		elapsed_stage2_ms: number;
		elapsed_total_ms: number;
	};

	type ComposeResponse = {
		score: Score;
		svg: string;
		elapsed_ms: number;
	};

	type Iteration = {
		mode?: string;
		input: string;
		ddl: string | null;
		thinking?: string | null;
		score: Score;
		svg: string;
		at: number;
		elapsed_ms?: number;
	};

	const MAX_HISTORY = 20;

	let input = $state('山の向こうに月が昇る');
	let loading = $state(false);
	let error = $state<string | null>(null);
	let ddl = $state<string | null>(null);
	let thinking = $state<string | null>(null);
	let result = $state<PaintResponse | ComposeResponse | null>(null);
	let saijikiOpen = $state(false);
	let textareaEl = $state<HTMLTextAreaElement | null>(null);

	let stage1Provider = $state<Provider>(DEFAULT_PROVIDER);
	let stage1Model = $state<string>(DEFAULT_MODEL);
	let stage2Provider = $state<Provider>(DEFAULT_PROVIDER);
	let stage2Model = $state<string>(DEFAULT_MODEL);
	let includeThinking = $state(false);

	let elapsedStage1Ms = $state(0);
	let elapsedStage2Ms = $state(0);
	let elapsedTotalMs = $state(0);
	let liveMs = $state(0);
	let _timerStart = 0;
	let _timerHandle: ReturnType<typeof setInterval> | null = null;

	let history = $state<Iteration[]>([]);
	let cursor = $state(-1);

	let promptsData = $state<{ stage1_system: string; stage2_system: string } | null>(null);

	function loadHistory(): Iteration[] {
		if (!browser) return [];
		try {
			const raw = localStorage.getItem(STORAGE_KEY);
			if (!raw) return [];
			const parsed = JSON.parse(raw);
			if (!Array.isArray(parsed)) return [];
			return parsed.filter(
				(it: unknown): it is Iteration =>
					!!it &&
					typeof it === 'object' &&
					'svg' in (it as Record<string, unknown>) &&
					'input' in (it as Record<string, unknown>)
			);
		} catch {
			return [];
		}
	}

	function persistHistory(items: Iteration[]) {
		if (!browser) return;
		try {
			localStorage.setItem(STORAGE_KEY, JSON.stringify(items));
		} catch {
			// quota / disabled: silently skip
		}
	}

	function clearHistory() {
		history = [];
		cursor = -1;
		result = null;
		ddl = null;
		persistHistory([]);
	}

	function pushHistory(it: Iteration) {
		const next = [...history, it];
		history = next.length > MAX_HISTORY ? next.slice(next.length - MAX_HISTORY) : next;
		cursor = history.length - 1;
		persistHistory(history);
	}

	function loadIteration(idx: number) {
		if (idx < 0 || idx >= history.length) return;
		cursor = idx;
		const it = history[idx];
		input = it.input;
		ddl = it.ddl;
		thinking = it.thinking ?? null;
		result = { score: it.score, svg: it.svg } as ComposeResponse;
		error = null;
	}

	function gotoPrev() {
		if (cursor > 0) loadIteration(cursor - 1);
	}

	function gotoNext() {
		if (cursor < history.length - 1) loadIteration(cursor + 1);
	}

	function insertWord(word: string) {
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
		if (e.key === 'Escape' && saijikiOpen) {
			saijikiOpen = false;
		}
	}

	onMount(async () => {
		const loaded = loadHistory();
		if (loaded.length > 0) {
			history = loaded;
			loadIteration(loaded.length - 1);
		}
		try {
			const p1 = localStorage.getItem(PROVIDER_STAGE1_KEY) as Provider | null;
			if (p1) stage1Provider = p1;
			const m1 = localStorage.getItem(MODEL_STAGE1_KEY);
			if (m1) stage1Model = m1;
			const p2 = localStorage.getItem(PROVIDER_STAGE2_KEY) as Provider | null;
			if (p2) stage2Provider = p2;
			const m2 = localStorage.getItem(MODEL_STAGE2_KEY);
			if (m2) stage2Model = m2;
		} catch {
			// ignore
		}

		try {
			const r = await fetch('/api/prompts');
			if (r.ok) promptsData = await r.json();
		} catch {
			// ignore prompt load failure
		}
	});

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
		try {
			localStorage.setItem(MODEL_STAGE1_KEY, v);
		} catch {}
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
		try {
			localStorage.setItem(MODEL_STAGE2_KEY, v);
		} catch {}
	}

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

	async function submit() {
		if (!input.trim()) return;
		loading = true;
		error = null;
		ddl = null;
		thinking = null;
		elapsedStage1Ms = 0;
		elapsedStage2Ms = 0;
		elapsedTotalMs = 0;
		startTimer();
		try {
			const r = await fetch('/api/paint', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({
					text: input,
					stage1_model: stage1Model,
					stage2_model: stage2Model,
					include_thinking: includeThinking
				})
			});
			if (!r.ok) {
				const d = await r.json().catch(() => ({}));
				throw new Error(d.detail ?? `HTTP ${r.status}`);
			}
			const data = (await r.json()) as PaintResponse;
			ddl = data.ddl;
			thinking = data.thinking;
			result = data;
			elapsedStage1Ms = data.elapsed_stage1_ms ?? 0;
			elapsedStage2Ms = data.elapsed_stage2_ms ?? 0;
			elapsedTotalMs = data.elapsed_total_ms ?? 0;
			pushHistory({
				input,
				ddl: data.ddl,
				thinking: data.thinking,
				score: data.score,
				svg: data.svg,
				at: Date.now(),
				elapsed_ms: data.elapsed_total_ms ?? 0
			});
		} catch (e) {
			error = e instanceof Error ? e.message : String(e);
			result = null;
		} finally {
			stopTimer();
			loading = false;
		}
	}
</script>

<main>
	<header>
		<div class="header-inner">
			<div>
				<h1>inku</h1>
				<p class="sub">視覚的な短歌を書く</p>
			</div>
			<button
				class="saijiki-toggle"
				aria-expanded={saijikiOpen}
				onclick={() => (saijikiOpen = !saijikiOpen)}
			>
				歳時記
			</button>
		</div>
	</header>

	<div class="model-row">
		<div class="model-group">
			<span class="model-label">解釈</span>
			<select
				value={stage1Provider}
				onchange={(e) => setStage1Provider((e.currentTarget as HTMLSelectElement).value as Provider)}
			>
				{#each PROVIDER_GROUPS as pg (pg.id)}
					<option value={pg.id}>{pg.label}</option>
				{/each}
			</select>
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
			<select
				value={stage2Provider}
				onchange={(e) => setStage2Provider((e.currentTarget as HTMLSelectElement).value as Provider)}
			>
				{#each PROVIDER_GROUPS as pg (pg.id)}
					<option value={pg.id}>{pg.label}</option>
				{/each}
			</select>
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

	<div class="row">
		<section class="input">
			<label for="input-ta">記述</label>
			<textarea
				id="input-ta"
				bind:this={textareaEl}
				bind:value={input}
				rows="8"
				spellcheck="false"
				placeholder="山の向こうに月が昇る"
			></textarea>
			<div class="submit-row">
				<button class="submit" onclick={submit} disabled={loading || !input.trim()}>
					{loading ? '演奏中…' : '演奏する'}
				</button>
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

			{#if result}
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
				<label for="canvas">演奏</label>
				{#if history.length > 0}
					<div class="nav" aria-label="履歴ナビゲーション">
						<button
							class="nav-btn"
							onclick={gotoPrev}
							disabled={cursor <= 0}
							aria-label="前の演奏"
						>◀</button>
						<span class="counter">{cursor + 1} / {history.length}</span>
						<button
							class="nav-btn"
							onclick={gotoNext}
							disabled={cursor >= history.length - 1}
							aria-label="次の演奏"
						>▶</button>
					</div>
				{/if}
			</div>
			<div id="canvas" class="canvas">
				{#if result}
					{@html result.svg}
				{:else}
					<div class="placeholder">（まだ演奏されていない）</div>
				{/if}
			</div>
			{#if result}
				<details>
					<summary>楽譜 (JSON Score)</summary>
					<pre>{JSON.stringify(result.score, null, 2)}</pre>
				</details>
				<details>
					<summary>プロンプト (デバッグ)</summary>
					{#if promptsData}
						<div class="prompt-section">
							<p class="prompt-label">Stage 1 システムプロンプト</p>
							<pre class="prompt-pre">{promptsData.stage1_system}</pre>
							<p class="prompt-label">Stage 1 ユーザー入力</p>
							<pre class="prompt-pre">{input}</pre>
							<p class="prompt-label">Stage 2 システムプロンプト</p>
							<pre class="prompt-pre">{promptsData.stage2_system}</pre>
							{#if ddl}
								<p class="prompt-label">Stage 2 ユーザー入力 (正規化DDL)</p>
								<pre class="prompt-pre">{ddl}</pre>
							{/if}
						</div>
					{:else}
						<p class="muted">読み込み中…</p>
					{/if}
				</details>
			{/if}
		</section>
	</div>

	{#if history.length > 1}
		<section class="history" aria-label="演奏履歴">
			<div class="history-head">
				<h2>履歴 <span class="muted">({history.length})</span></h2>
				<button class="clear-btn" onclick={clearHistory}>全て消す</button>
			</div>
			<div class="strip">
				{#each history as it, i (it.at)}
					<button
						class="thumb"
						class:current={i === cursor}
						onclick={() => loadIteration(i)}
						title={it.input}
					>
						<div class="thumb-svg">{@html it.svg}</div>
						<div class="thumb-label">
							{#if it.elapsed_ms && it.elapsed_ms > 0}
								{(it.elapsed_ms / 1000).toFixed(1)}s
							{:else}
								{i + 1}
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
			<button class="saijiki-close" onclick={() => (saijikiOpen = false)} aria-label="閉じる">
				×
			</button>
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

	header {
		margin-bottom: 1.5rem;
	}

	.header-inner {
		display: flex;
		justify-content: space-between;
		align-items: flex-end;
	}

	h1 {
		font-size: 2rem;
		margin: 0;
		letter-spacing: 0.2em;
	}

	.sub {
		color: #666;
		margin: 0.25rem 0 0;
	}

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

	.saijiki-toggle:hover {
		background: #111;
		color: #fff;
		border-color: #111;
	}

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

	.saijiki-head h2 {
		margin: 0;
		font-size: 1.3rem;
		letter-spacing: 0.1em;
	}

	.saijiki-head .en {
		font-size: 0.75rem;
		color: #888;
		font-weight: normal;
		letter-spacing: 0.05em;
	}

	.saijiki-close {
		background: transparent;
		border: none;
		font-size: 1.5rem;
		color: #666;
		cursor: pointer;
		line-height: 1;
		padding: 0 0.25rem;
	}

	.saijiki-hint {
		color: #888;
		font-size: 0.8rem;
		margin: 0 0 1rem;
	}

	.saijiki-cat {
		margin-bottom: 1.5rem;
	}

	.saijiki-cat h3 {
		margin: 0 0 0.5rem;
		font-size: 0.95rem;
		color: #333;
		font-weight: 600;
	}

	.saijiki-cat .en {
		font-size: 0.7rem;
		color: #aaa;
		font-weight: normal;
		margin-left: 0.25rem;
	}

	.chips {
		display: flex;
		flex-wrap: wrap;
		gap: 0.4rem;
	}

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

	.chip:hover {
		background: #111;
		color: #fff;
		border-color: #111;
	}

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

	.model-label {
		color: #888;
		min-width: 2.5rem;
	}

	.model-group select {
		font-family: inherit;
		font-size: 0.85rem;
		padding: 0.25rem 0.5rem;
		border: 1px solid #ccc;
		border-radius: 3px;
		background: #fff;
		color: #333;
	}

	.model-group select:first-of-type {
		color: #555;
	}

	.think-toggle {
		display: flex;
		align-items: center;
		gap: 0.35rem;
		font-size: 0.85rem;
		color: #666;
		cursor: pointer;
	}

	.thinking {
		margin-top: 1rem;
		font-size: 0.85rem;
		background: #f3efe6;
		border-left: 3px solid #c9a08a;
		border-radius: 0 3px 3px 0;
		padding: 0.5rem 0.75rem;
	}

	.thinking summary {
		cursor: pointer;
		color: #8a6f5a;
		font-style: italic;
	}

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

	.row {
		display: grid;
		grid-template-columns: 1fr 1fr;
		gap: 2rem;
	}

	label {
		display: block;
		font-size: 0.85rem;
		color: #666;
		margin-bottom: 0.5rem;
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

	.submit-row {
		display: flex;
		align-items: center;
		gap: 0.75rem;
		margin-top: 0.75rem;
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

	.elapsed {
		font-size: 0.8rem;
		color: #888;
		font-variant-numeric: tabular-nums;
	}

	.elapsed-live {
		color: #c9a08a;
	}

	.error {
		color: #a2342a;
		margin-top: 0.75rem;
	}

	.interpreted {
		margin-top: 1.5rem;
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

	.ddl-box {
		border-left: 3px solid #888;
		border-radius: 0 4px 4px 0;
	}

	.tok {
		transition: color 0.15s;
	}

	/* 墨の濃淡: Saijiki = 濃墨、地文 = 薄墨、感情語 = 滲む */
	.tok-saijiki {
		color: #111;
		font-weight: 500;
	}

	.tok-plain {
		color: #9a9a9a;
	}

	.tok-emotion {
		color: #c9a08a;
		font-style: italic;
		text-decoration: line-through;
		text-decoration-color: rgba(162, 52, 42, 0.4);
		text-decoration-thickness: 1px;
	}

	.output-head {
		display: flex;
		justify-content: space-between;
		align-items: baseline;
		margin-bottom: 0.5rem;
	}

	.output-head label {
		margin-bottom: 0;
	}

	.nav {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		font-size: 0.85rem;
	}

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

	.nav-btn:hover:not(:disabled) {
		background: #111;
		color: #fff;
		border-color: #111;
	}

	.nav-btn:disabled {
		opacity: 0.35;
		cursor: not-allowed;
	}

	.counter {
		color: #666;
		min-width: 3rem;
		text-align: center;
	}

	.history {
		margin-top: 2.5rem;
		border-top: 1px solid #ddd;
		padding-top: 1.5rem;
	}

	.history-head {
		display: flex;
		justify-content: space-between;
		align-items: center;
		margin-bottom: 0.75rem;
	}

	.history h2 {
		font-size: 1rem;
		font-weight: 600;
		color: #555;
		margin: 0;
	}

	.muted {
		color: #aaa;
		font-weight: normal;
		font-size: 0.85rem;
		margin-left: 0.25rem;
	}

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

	.clear-btn:hover {
		color: #a2342a;
		border-color: #a2342a;
	}

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

	.thumb.current {
		border-color: #111;
		box-shadow: 0 0 0 2px #11111133;
	}

	.thumb-svg {
		width: 96px;
		height: 96px;
		overflow: hidden;
	}

	.thumb-svg :global(svg) {
		width: 100%;
		height: 100%;
		display: block;
	}

	.thumb-label {
		padding: 0.2rem;
		font-size: 0.75rem;
		color: #888;
		text-align: center;
		border-top: 1px solid #eee;
	}

	.canvas {
		aspect-ratio: 1 / 1;
		border: 1px solid #ccc;
		border-radius: 4px;
		background: #fff;
		overflow: hidden;
	}

	.canvas :global(svg) {
		width: 100%;
		height: 100%;
		display: block;
	}

	.placeholder {
		height: 100%;
		display: flex;
		align-items: center;
		justify-content: center;
		color: #999;
	}

	details {
		margin-top: 1rem;
		font-size: 0.85rem;
	}

	pre {
		background: #fff;
		padding: 0.75rem;
		border-radius: 4px;
		border: 1px solid #ddd;
		overflow: auto;
		max-height: 300px;
	}

	.prompt-section {
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
	}

	.prompt-label {
		margin: 0.5rem 0 0.25rem;
		font-size: 0.8rem;
		font-weight: 600;
		color: #555;
	}

	.prompt-pre {
		background: #f8f6f0;
		padding: 0.75rem;
		border-radius: 4px;
		border: 1px solid #ddd;
		overflow: auto;
		max-height: 200px;
		white-space: pre-wrap;
		word-break: break-word;
		font-size: 0.78rem;
		line-height: 1.5;
		margin: 0;
	}

	@media (max-width: 720px) {
		.row {
			grid-template-columns: 1fr;
		}
	}
</style>

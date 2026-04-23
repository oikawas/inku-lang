<script lang="ts">
	import { SAIJIKI } from '$lib/saijiki';

	type Score = { instructions: unknown[] };

	type PaintResponse = {
		text: string;
		ddl: string;
		score: Score;
		svg: string;
	};

	type ComposeResponse = {
		score: Score;
		svg: string;
	};

	type Mode = 'free' | 'ddl';

	let mode = $state<Mode>('free');
	let input = $state('山の向こうに月が昇る');
	let loading = $state(false);
	let error = $state<string | null>(null);
	let ddl = $state<string | null>(null);
	let result = $state<PaintResponse | ComposeResponse | null>(null);
	let saijikiOpen = $state(false);
	let textareaEl = $state<HTMLTextAreaElement | null>(null);

	const placeholders: Record<Mode, string> = {
		free: '山の向こうに月が昇る',
		ddl: '中心に赤い円を置く。半径は画面の2割。'
	};

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

	function switchMode(next: Mode) {
		if (mode === next) return;
		mode = next;
		input = placeholders[next];
		ddl = null;
		result = null;
		error = null;
	}

	async function submit() {
		if (!input.trim()) return;
		loading = true;
		error = null;
		ddl = null;
		try {
			if (mode === 'free') {
				const r = await fetch('/api/paint', {
					method: 'POST',
					headers: { 'Content-Type': 'application/json' },
					body: JSON.stringify({ text: input })
				});
				if (!r.ok) {
					const d = await r.json().catch(() => ({}));
					throw new Error(d.detail ?? `HTTP ${r.status}`);
				}
				const data = (await r.json()) as PaintResponse;
				ddl = data.ddl;
				result = data;
			} else {
				const r = await fetch('/api/compose', {
					method: 'POST',
					headers: { 'Content-Type': 'application/json' },
					body: JSON.stringify({ ddl: input })
				});
				if (!r.ok) {
					const d = await r.json().catch(() => ({}));
					throw new Error(d.detail ?? `HTTP ${r.status}`);
				}
				result = (await r.json()) as ComposeResponse;
			}
		} catch (e) {
			error = e instanceof Error ? e.message : String(e);
			result = null;
		} finally {
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

	<div class="mode-switch" role="tablist" aria-label="入力モード">
		<button
			role="tab"
			aria-selected={mode === 'free'}
			class:active={mode === 'free'}
			onclick={() => switchMode('free')}
		>
			自由記述
		</button>
		<button
			role="tab"
			aria-selected={mode === 'ddl'}
			class:active={mode === 'ddl'}
			onclick={() => switchMode('ddl')}
		>
			正規化DDL
		</button>
	</div>

	<div class="row">
		<section class="input">
			<label for="input-ta">
				{mode === 'free' ? '記述 (自由)' : '正規化DDL'}
			</label>
			<textarea
				id="input-ta"
				bind:this={textareaEl}
				bind:value={input}
				rows="8"
				spellcheck="false"
				placeholder={placeholders[mode]}
			></textarea>
			<button class="submit" onclick={submit} disabled={loading || !input.trim()}>
				{loading ? '演奏中…' : '演奏する'}
			</button>
			{#if error}
				<p class="error">{error}</p>
			{/if}

			{#if mode === 'free' && ddl}
				<div class="interpreted">
					<label for="ddl-interpret">解釈 (正規化DDL)</label>
					<div id="ddl-interpret" class="ddl-box">{ddl}</div>
				</div>
			{/if}
		</section>

		<section class="output">
			<label for="canvas">演奏</label>
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
			{/if}
		</section>
	</div>
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

	.mode-switch {
		display: flex;
		gap: 0.25rem;
		margin-bottom: 1.5rem;
		border-bottom: 1px solid #ccc;
	}

	.mode-switch button {
		background: transparent;
		border: none;
		padding: 0.5rem 1rem;
		font-size: 0.95rem;
		cursor: pointer;
		color: #888;
		border-bottom: 2px solid transparent;
		margin-bottom: -1px;
		font-family: inherit;
	}

	.mode-switch button.active {
		color: #111;
		border-bottom-color: #111;
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

	button.submit {
		margin-top: 0.75rem;
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

	.error {
		color: #a2342a;
		margin-top: 0.75rem;
	}

	.interpreted {
		margin-top: 1.5rem;
	}

	.ddl-box {
		padding: 0.75rem;
		border-left: 3px solid #888;
		background: #fff;
		border-radius: 0 4px 4px 0;
		font-size: 0.95rem;
		line-height: 1.7;
		color: #333;
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

	@media (max-width: 720px) {
		.row {
			grid-template-columns: 1fr;
		}
	}
</style>

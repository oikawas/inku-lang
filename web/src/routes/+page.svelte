<script lang="ts">
	type ComposeResponse = {
		score: { instructions: unknown[] };
		svg: string;
	};

	let ddl = $state('中心に赤い円を置く。半径は画面の2割。');
	let loading = $state(false);
	let error = $state<string | null>(null);
	let result = $state<ComposeResponse | null>(null);

	async function submit() {
		if (!ddl.trim()) return;
		loading = true;
		error = null;
		try {
			const r = await fetch('/api/compose', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ ddl })
			});
			if (!r.ok) {
				const detail = await r.json().catch(() => ({}));
				throw new Error(detail.detail ?? `HTTP ${r.status}`);
			}
			result = await r.json();
		} catch (e) {
			error = e instanceof Error ? e.message : String(e);
			result = null;
		} finally {
			loading = false;
		}
	}
</script>

<main>
	<h1>inku</h1>
	<p class="sub">視覚的な短歌を書く</p>

	<div class="row">
		<section class="input">
			<label for="ddl">記述</label>
			<textarea id="ddl" bind:value={ddl} rows="10" spellcheck="false"></textarea>
			<button onclick={submit} disabled={loading || !ddl.trim()}>
				{loading ? '演奏中…' : '演奏する'}
			</button>
			{#if error}
				<p class="error">{error}</p>
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

	h1 {
		font-size: 2rem;
		margin: 0;
		letter-spacing: 0.2em;
	}

	.sub {
		color: #666;
		margin: 0.25rem 0 2rem;
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

	button {
		margin-top: 0.75rem;
		padding: 0.5rem 1.25rem;
		background: #111;
		color: #fff;
		border: none;
		border-radius: 4px;
		cursor: pointer;
		font-size: 0.95rem;
	}

	button:disabled {
		background: #999;
		cursor: not-allowed;
	}

	.error {
		color: #a2342a;
		margin-top: 0.75rem;
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

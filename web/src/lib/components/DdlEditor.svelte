<script lang="ts">
	import { t } from '$lib/i18n/index.svelte';
	import KiwiMascot from './KiwiMascot.svelte';

	type Props = {
		ddl: string;
		ddlHighlighted: string;
		ddlTextareaEl: HTMLTextAreaElement | null;
		ddlHighlightEl: HTMLDivElement | null;
		ddlFocused: boolean;
		reloading: boolean;
		reloadError: string | null;
		loading: boolean;
		showKiwi: boolean;
		onToggleSaijiki: () => void;
		onRememberSelection: () => void;
		onSyncHighlightScroll: () => void;
		onReplay: () => void | Promise<void>;
	};

	let {
		ddl = $bindable(''),
		ddlHighlighted,
		ddlTextareaEl = $bindable(null),
		ddlHighlightEl = $bindable(null),
		ddlFocused = $bindable(false),
		reloading,
		reloadError,
		loading,
		showKiwi,
		onToggleSaijiki,
		onRememberSelection,
		onSyncHighlightScroll,
		onReplay,
	}: Props = $props();
</script>

<section class="panel-section">
	<div class="section-head">
		<span class="section-label">{t().ddlLabel}</span>
		<div class="section-actions">
			<button class="ghost-btn" onclick={onToggleSaijiki}>{t().saijikiToggleBtn}</button>
		</div>
	</div>
	<div class="ddl-highlight-wrap">
		<div class="ddl-highlight" bind:this={ddlHighlightEl} aria-hidden="true">{@html ddlHighlighted}</div>
		<textarea
			class="ddl-edit-ta"
			bind:this={ddlTextareaEl}
			bind:value={ddl}
			rows="8"
			spellcheck="false"
			onclick={onRememberSelection}
			onfocus={() => { ddlFocused = true; onRememberSelection(); }}
			onblur={() => { onRememberSelection(); ddlFocused = false; }}
			oninput={() => { onRememberSelection(); onSyncHighlightScroll(); }}
			onkeyup={onRememberSelection}
			onmouseup={onRememberSelection}
			onselect={onRememberSelection}
			onscroll={onSyncHighlightScroll}
		></textarea>
	</div>

	{#if reloading}
		<div class="progress-wrap">
			<div class="progress-phases">
				<span class="phase-item phase-active"><span class="phase-dot"></span>{t().statsStruct}</span>
			</div>
			<div class="progress-right">
				<span class="progress-time">…</span>
			</div>
		</div>
		<div class="progress-bar-track" style="--progress-target: 55%">
			<div class="progress-bar-fill"></div>
			{#if showKiwi}
				<KiwiMascot />
			{/if}
		</div>
	{/if}
	{#if reloadError}<p class="error-text">{reloadError}</p>{/if}

	<button
		class="replay-btn"
		onclick={onReplay}
		disabled={reloading || !ddl || loading}
	>{t().replayFromDdlButton}</button>
</section>

<style>
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
		background: var(--panel);
		color: var(--fg2);
		font-size: 11px;
		cursor: pointer;
		font-family: inherit;
	}
	.ghost-btn:hover { background: var(--bg2); }
	.ddl-highlight-wrap {
		position: relative;
		width: 100%;
		border: 1px solid var(--accent); border-left: 3px solid var(--border2);
		border-radius: 0 var(--r) var(--r) 0;
		background: var(--panel);
		overflow: hidden;
	}
	.ddl-highlight,
	.ddl-edit-ta {
		width: 100%; padding: 9px 10px;
		box-sizing: border-box;
		margin: 0;
		font-family: inherit; font-size: 13px; font-weight: 400; font-style: normal; letter-spacing: 0;
		line-height: 1.75; resize: vertical; outline: none;
		min-height: 15.5em;
		white-space: pre-wrap; word-break: break-word;
		tab-size: 4;
		scrollbar-gutter: stable;
	}
	.ddl-highlight {
		position: absolute;
		inset: 0;
		z-index: 0;
		overflow: auto;
		color: var(--fg);
		pointer-events: none;
		scrollbar-width: none;
	}
	.ddl-highlight::-webkit-scrollbar { display: none; }
	.ddl-edit-ta {
		position: relative;
		z-index: 1;
		border: none;
		background: transparent;
		color: transparent;
		caret-color: transparent;
		overflow: auto;
	}
	.ddl-edit-ta::selection { background: rgba(44, 62, 145, 0.22); }
	.ddl-highlight :global(.ddl-token) {
		border-radius: 2px;
		font-weight: inherit;
	}
	.ddl-highlight :global(.ddl-custom-caret) {
		position: relative;
		display: inline-block;
		width: 0;
		height: 1em;
		vertical-align: text-bottom;
	}
	.ddl-highlight :global(.ddl-custom-caret)::after {
		content: '';
		position: absolute;
		left: 0;
		top: -0.18em;
		width: 3px;
		height: 1.45em;
		border-radius: 2px;
		background: var(--fg);
		animation: ddl-caret-blink 1s steps(2, start) infinite;
	}
	.ddl-highlight :global(.ddl-token-shape) { color: #2c5fb8; background: rgba(44, 95, 184, 0.08); }
	.ddl-highlight :global(.ddl-token-touch) { color: #7a5b2f; background: rgba(122, 91, 47, 0.10); }
	.ddl-highlight :global(.ddl-token-line) { color: #53606b; background: rgba(83, 96, 107, 0.10); }
	.ddl-highlight :global(.ddl-token-color) { color: #b12a6b; background: rgba(177, 42, 107, 0.09); }
	.ddl-highlight :global(.ddl-token-motion) { color: #197a74; background: rgba(25, 122, 116, 0.10); }
	.ddl-highlight :global(.ddl-token-place) { color: #6b4cb3; background: rgba(107, 76, 179, 0.09); }
	.ddl-highlight :global(.ddl-token-action) { color: #9a4a1d; background: rgba(154, 74, 29, 0.10); }
	.ddl-highlight :global(.ddl-token-angle) { color: #3d6f2c; background: rgba(61, 111, 44, 0.10); }
	.ddl-highlight :global(.ddl-token-ratio) { color: #9a3d3d; background: rgba(154, 61, 61, 0.09); }
	.ddl-highlight :global(.ddl-token-word) { color: #2c3e91; background: rgba(44, 62, 145, 0.08); }
	.ddl-highlight :global(.ddl-token-emotion) {
		color: #9b7a66;
		font-style: inherit;
	}
	.progress-wrap {
		display: flex; align-items: center; justify-content: space-between;
		padding: 8px 10px 6px;
		border: 1px solid var(--border2); border-radius: var(--r) var(--r) 0 0;
		background: var(--panel);
		margin-top: 8px;
	}
	.progress-phases { display: flex; align-items: center; gap: 4px; }
	.phase-item { font-size: 11px; color: var(--border2); display: flex; align-items: center; gap: 3px; }
	.phase-item.phase-active { color: var(--fg); font-weight: 500; }
	.phase-dot {
		display: inline-block; width: 6px; height: 6px; border-radius: 50%;
		background: var(--accent); flex-shrink: 0;
		animation: inkupulse 1s ease-in-out infinite;
	}
	.progress-right { display: flex; align-items: center; gap: 7px; }
	.progress-time { font-size: 11px; color: var(--fg3); font-variant-numeric: tabular-nums; }
	.progress-bar-track {
		position: relative;
		height: 32px; background: transparent;
		border-left: 1px solid var(--border2); border-right: 1px solid var(--border2);
		overflow: visible;
	}
	.progress-bar-track::before {
		content: "";
		position: absolute; top: 18px; left: 0; right: 0; height: 3px;
		background: var(--bg3);
	}
	.progress-bar-fill {
		position: absolute; top: 18px; left: 0; height: 3px;
		width: var(--progress-target, 50%);
		background: var(--accent); transition: width 0.3s ease;
	}
	.error-text { color: #a2342a; font-size: 12px; }
	.replay-btn {
		width: 100%; margin-top: 6px; padding: 10px;
		font-size: 14px; font-weight: 500; background: #e8f1fb; color: #234c78;
		border: 1px solid #9fb9d6; border-radius: var(--r);
		letter-spacing: 0.08em; cursor: pointer;
		display: flex; align-items: center; justify-content: center; gap: 6px;
		font-family: inherit; transition: background 0.15s, border-color 0.15s, color 0.15s;
	}
	.replay-btn:hover:not(:disabled) { background: #d7e8f8; border-color: #6f98c3; color: #173f68; }
	.replay-btn:disabled { background: var(--bg2); border-color: var(--border2); color: var(--fg3); cursor: not-allowed; }
	@keyframes ddl-caret-blink {
		50% { opacity: 0; }
	}
	@keyframes inkupulse {
		0%, 100% { opacity: 1; transform: scale(1); }
		50% { opacity: 0.4; transform: scale(0.7); }
	}
</style>

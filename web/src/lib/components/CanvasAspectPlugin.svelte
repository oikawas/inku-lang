<script lang="ts">
	import { getLang, t } from '$lib/i18n/index.svelte';
	import {
		CANVAS_ASPECT_OPTIONS,
		type CanvasAspectId,
	} from '$lib/plugins/system/canvas-aspect';

	type Props = {
		selected: CanvasAspectId;
		open: boolean;
		onToggle: () => void;
		onSelect: (id: CanvasAspectId) => void | Promise<void>;
	};

	let { selected, open = false, onToggle, onSelect }: Props = $props();

	const isJa = $derived(getLang() === 'ja');
</script>

<div class="canvas-aspect-plugin">
	<button
		type="button"
		class="ghost-btn aspect-trigger"
		onclick={(event) => {
			event.stopPropagation();
			onToggle();
		}}
		aria-haspopup="menu"
		aria-expanded={open}
	>
		<span>{t().canvasAspectButton}</span>
	</button>
	{#if open}
		<div class="aspect-menu" role="menu">
			<div class="aspect-menu-head">{t().canvasAspectTitle}</div>
			{#each CANVAS_ASPECT_OPTIONS as option (option.id)}
				<button
					type="button"
					class:selected={option.id === selected}
					role="menuitemradio"
					aria-checked={option.id === selected}
					onclick={() => onSelect(option.id)}
				>
					<span class="option-main">
						<span class="option-label">{option.label}</span>
						<span class="option-ratio">{option.ratio}</span>
					</span>
					<span class="option-meta">{option.category}</span>
					<span class="option-intent">{isJa ? option.intentJa : option.intentEn}</span>
				</button>
			{/each}
		</div>
	{/if}
</div>

<style>
	.canvas-aspect-plugin {
		position: relative;
		display: inline-flex;
	}
	.aspect-trigger { display: inline-flex; align-items: center; }
	.ghost-btn {
		padding: 4px 10px;
		border: 1px solid var(--border2);
		border-radius: var(--r);
		background: var(--panel);
		color: var(--fg2);
		font-size: 11px;
		cursor: pointer;
		font-family: inherit;
		white-space: nowrap;
	}
	.ghost-btn:hover { background: var(--bg2); }
	.aspect-menu {
		position: absolute;
		top: calc(100% + 6px);
		left: 0;
		z-index: 80;
		width: 310px;
		max-height: min(520px, 70vh);
		overflow: auto;
		border: 1px solid var(--border2);
		border-radius: var(--r-lg);
		background: var(--panel);
		box-shadow: 0 10px 32px rgba(0,0,0,0.18);
		padding: 6px;
	}
	.aspect-menu-head {
		padding: 6px 8px 8px;
		font-size: 11px;
		color: var(--fg3);
		border-bottom: 1px solid var(--border);
		margin-bottom: 4px;
	}
	.aspect-menu button {
		width: 100%;
		border: none;
		background: transparent;
		color: var(--fg);
		font-family: inherit;
		text-align: left;
		padding: 8px;
		border-radius: var(--r);
		cursor: pointer;
		display: grid;
		grid-template-columns: minmax(0, 1fr) auto;
		gap: 2px 10px;
	}
	.aspect-menu button:hover {
		background: var(--bg2);
	}
	.aspect-menu button.selected {
		background: var(--bg2);
		box-shadow: inset 3px 0 0 var(--fg2);
	}
	.option-main {
		min-width: 0;
		display: inline-flex;
		align-items: baseline;
		gap: 8px;
	}
	.option-label {
		font-size: 13px;
		font-weight: 500;
	}
	.option-ratio,
	.option-meta {
		font-size: 11px;
		color: var(--fg3);
		white-space: nowrap;
	}
	.option-intent {
		grid-column: 1 / -1;
		font-size: 11px;
		line-height: 1.35;
		color: var(--fg2);
	}
</style>

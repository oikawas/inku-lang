<script lang="ts">
	import { getLang, t } from '$lib/i18n/index.svelte';
	import { placeIn } from '$lib/place-in';
	import {
		type CanvasAspectOption,
		type CanvasAspectId,
	} from '$lib/plugins/system/canvas-aspect';

	type Props = {
		selected: CanvasAspectId;
		options: CanvasAspectOption[];
		open: boolean;
		showValue?: boolean;
		row?: boolean;
		onToggle: () => void;
		onSelect: (id: CanvasAspectId) => void | Promise<void>;
	};

	let { selected, options, open = false, showValue = false, row = false, onToggle, onSelect }: Props = $props();
	let trigger = $state<HTMLButtonElement | null>(null);
	function overlay(node: HTMLElement) {
		if (!row) return;
		const portal = placeIn(node, document.body);
		function position() {
			const rect = trigger?.getBoundingClientRect();
			if (!rect) return;
			node.style.top = `${rect.bottom + 6}px`;
			node.style.right = `${Math.max(8, window.innerWidth - rect.right)}px`;
			node.style.maxHeight = `${Math.max(0, Math.min(520, window.innerHeight - rect.bottom - 14))}px`;
		}
		position();
		window.addEventListener('resize', position);
		window.addEventListener('scroll', position, true);
		return { destroy() { window.removeEventListener('resize', position); window.removeEventListener('scroll', position, true); portal.destroy(); } };
	}

	const isJa = $derived(getLang() === 'ja');
	const selectedLabel = $derived(options.find((option) => option.id === selected)?.label ?? '');
</script>

<div class="canvas-aspect-plugin" class:row>
	{#if row}<span class="aspect-label">{t().canvasAspectButton}</span><span class="aspect-value">{selectedLabel}</span>{/if}
	<button
		bind:this={trigger}
		type="button"
		class="ghost-btn aspect-trigger"
		onclick={(event) => {
			event.stopPropagation();
			onToggle();
		}}
		aria-haspopup="menu"
		aria-expanded={open}
	>
		<span>{row ? t().editButton : t().canvasAspectButton}{#if showValue && !row}<span class="aspect-trigger-value">{isJa ? '：' : ': '}{selectedLabel}</span>{/if}</span>
	</button>
	{#if open}
		<div><div class="aspect-menu" class:overlay={row} role="menu" use:overlay>
			<div class="aspect-menu-head">{t().canvasAspectTitle}</div>
			{#each options as option (option.id)}
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
		</div></div>
	{/if}
</div>

<style>
	.canvas-aspect-plugin {
		position: relative;
		display: inline-flex;
	}
	.aspect-trigger { display: inline-flex; align-items: center; }
	.canvas-aspect-plugin.row { align-items: center; gap: 5px; }
	.aspect-label, .aspect-value { font-size: var(--ui-font-size-11); white-space: nowrap; }
	.aspect-label { color: var(--fg3); }
	.aspect-value { color: var(--fg2); max-width: 9em; overflow: hidden; text-overflow: ellipsis; }
	.aspect-trigger-value { color: var(--fg2); font-weight: 400; }
	.aspect-menu {
		position: absolute;
		top: calc(100% + 6px);
		left: 0;
		z-index: 80;
		width: min(310px, calc(100vw - 16px));
		max-height: min(520px, 70vh);
		overflow: auto;
		border: 1px solid var(--border2);
		border-radius: var(--r-lg);
		background: var(--panel);
		box-shadow: 0 10px 32px rgba(0,0,0,0.18);
		padding: 6px;
	}
	.aspect-menu.overlay { position: fixed; left: auto; z-index: 1100; }
	.aspect-menu-head {
		padding: 6px 8px 8px;
		font-size: var(--ui-font-size-11);
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
		font-size: var(--ui-font-size-13);
		font-weight: 500;
	}
	.option-ratio,
	.option-meta {
		font-size: var(--ui-font-size-11);
		color: var(--fg3);
		white-space: nowrap;
	}
	.option-intent {
		grid-column: 1 / -1;
		font-size: var(--ui-font-size-11);
		line-height: 1.35;
		color: var(--fg2);
	}
</style>

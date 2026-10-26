<!--
	The composition and laws inside read and draw: off (the default) or on.
	The same dropdown as RouteSelect, shown beside it only while the route is
	read and draw (2026-10-26, SPEC 12.6.7).
-->
<script lang="ts">
	import { COMPOSITION_MODES, compositionModeHint, compositionModeLabel, type CompositionMode } from '$lib/draw-route';

	type Props = {
		value: CompositionMode;
		isJapanese: boolean;
		disabled?: boolean;
		onSelect: (mode: CompositionMode) => void;
	};

	let { value, isJapanese, disabled = false, onSelect }: Props = $props();

	let open = $state(false);
	const title = $derived(isJapanese ? '構図と法則' : 'Composition and laws');

	function choose(mode: CompositionMode) {
		onSelect(mode);
		open = false;
	}
</script>

<div class="composition-plugin">
	<button
		type="button"
		class="ghost-btn composition-trigger"
		{disabled}
		aria-haspopup="menu"
		aria-expanded={open}
		onclick={(event) => { event.stopPropagation(); open = !open; }}
	>
		<span>{title}<span class="composition-trigger-value">{isJapanese ? '：' : ': '}{compositionModeLabel(value, isJapanese)}</span></span>
	</button>
	{#if open}
		<div class="composition-menu" role="menu">
			<div class="composition-menu-head">{title}</div>
			{#each COMPOSITION_MODES as mode (mode)}
				<button
					type="button"
					class:selected={mode === value}
					role="menuitemradio"
					aria-checked={mode === value}
					onclick={() => choose(mode)}
				>
					<span class="option-label">{compositionModeLabel(mode, isJapanese)}</span>
					<span class="option-intent">{compositionModeHint(mode, isJapanese)}</span>
				</button>
			{/each}
		</div>
	{/if}
</div>

<style>
	.composition-plugin { position: relative; display: inline-flex; }
	.composition-trigger { display: inline-flex; align-items: center; }
	.composition-trigger-value { color: var(--fg2); font-weight: 400; }
	.composition-menu {
		position: absolute;
		top: calc(100% + 6px);
		left: 0;
		z-index: 80;
		width: 280px;
		border: 1px solid var(--border2);
		border-radius: var(--r-lg, var(--r));
		background: var(--panel);
		box-shadow: 0 10px 32px rgba(0, 0, 0, 0.18);
		padding: 6px;
	}
	.composition-menu-head {
		padding: 6px 8px 8px;
		font-size: var(--ui-font-size-11);
		color: var(--fg3);
		border-bottom: 1px solid var(--border);
		margin-bottom: 4px;
	}
	.composition-menu button {
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
		gap: 2px;
	}
	.composition-menu button:hover { background: var(--bg2); }
	.composition-menu button.selected { background: var(--bg2); box-shadow: inset 3px 0 0 var(--fg2); }
	.option-label { font-size: var(--ui-font-size-13); font-weight: 500; }
	.option-intent { font-size: var(--ui-font-size-11); line-height: 1.35; color: var(--fg3); }
</style>

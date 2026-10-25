<!--
	How a description is drawn: the current stages (the default) or read and
	draw. The same dropdown as SketchSelect, beside it in the describe tab's
	condition rows, which the batch shares.
-->
<script lang="ts">
	import { DRAW_ROUTES, drawRouteHint, drawRouteLabel, type DrawRoute } from '$lib/draw-route';

	type Props = {
		value: DrawRoute;
		isJapanese: boolean;
		disabled?: boolean;
		onSelect: (route: DrawRoute) => void;
	};

	let { value, isJapanese, disabled = false, onSelect }: Props = $props();

	let open = $state(false);
	const title = $derived(isJapanese ? '描き方' : 'Drawing');

	function choose(route: DrawRoute) {
		onSelect(route);
		open = false;
	}
</script>

<div class="route-plugin">
	<button
		type="button"
		class="ghost-btn route-trigger"
		{disabled}
		aria-haspopup="menu"
		aria-expanded={open}
		onclick={(event) => { event.stopPropagation(); open = !open; }}
	>
		<span>{title}<span class="route-trigger-value">{isJapanese ? '：' : ': '}{drawRouteLabel(value, isJapanese)}</span></span>
	</button>
	{#if open}
		<div class="route-menu" role="menu">
			<div class="route-menu-head">{title}</div>
			{#each DRAW_ROUTES as route (route)}
				<button
					type="button"
					class:selected={route === value}
					role="menuitemradio"
					aria-checked={route === value}
					onclick={() => choose(route)}
				>
					<span class="option-label">{drawRouteLabel(route, isJapanese)}</span>
					<span class="option-intent">{drawRouteHint(route, isJapanese)}</span>
				</button>
			{/each}
		</div>
	{/if}
</div>

<style>
	.route-plugin { position: relative; display: inline-flex; }
	.route-trigger { display: inline-flex; align-items: center; }
	.route-trigger-value { color: var(--fg2); font-weight: 400; }
	.route-menu {
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
	.route-menu-head {
		padding: 6px 8px 8px;
		font-size: var(--ui-font-size-11);
		color: var(--fg3);
		border-bottom: 1px solid var(--border);
		margin-bottom: 4px;
	}
	.route-menu button {
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
	.route-menu button:hover { background: var(--bg2); }
	.route-menu button.selected { background: var(--bg2); box-shadow: inset 3px 0 0 var(--fg2); }
	.option-label { font-size: var(--ui-font-size-13); font-weight: 500; }
	.option-intent { font-size: var(--ui-font-size-11); line-height: 1.35; color: var(--fg3); }
</style>

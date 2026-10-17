<script lang="ts">
	import { t } from '$lib/i18n/index.svelte';
	import Tooltip from '$lib/components/Tooltip.svelte';

	let { viewMode = $bindable('2d') }: { viewMode?: '2d' | '3d' } = $props();
</script>

<Tooltip placement="top-left" text={viewMode === '2d' ? t().ddl3dTitle : t().ddl3dReturn}>
	<button
		type="button"
		class="canvas-mode-button"
		class:active={viewMode === '3d'}
		aria-label={t().ddl3dMode}
		aria-pressed={viewMode === '3d'}
		onclick={() => (viewMode = viewMode === '2d' ? '3d' : '2d')}
	>
		{viewMode === '2d' ? '3D' : '2D'}
	</button>
</Tooltip>

<style>
	.canvas-mode-button {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		min-width: 40px;
		min-height: 34px;
		padding: var(--btn-sm-padding);
		border: 1px solid var(--border2);
		border-radius: var(--btn-sm-radius);
		background: var(--floating-control-bg);
		color: var(--floating-control-fg);
		font: inherit;
		font-size: var(--btn-sm-font-size);
		font-weight: 600;
		box-shadow: 0 1px 6px rgba(0,0,0,0.1);
		cursor: pointer;
	}
	.canvas-mode-button:hover { background: var(--floating-control-hover); }
	.canvas-mode-button.active { background: var(--accent); color: var(--accent-fg); border-color: var(--accent); }
	.canvas-mode-button:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
</style>

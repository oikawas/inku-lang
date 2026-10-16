<script lang="ts">
	import { t } from '$lib/i18n/index.svelte';

	let { viewMode = $bindable('2d') }: { viewMode?: '2d' | '3d' } = $props();
</script>

<div class="canvas-mode-controls">
	<button
		type="button"
		class="mode-switch"
		role="switch"
		aria-label={t().ddl3dMode}
		aria-checked={viewMode === '3d'}
		onclick={() => (viewMode = viewMode === '2d' ? '3d' : '2d')}
	>
		<span class="mode-label" class:active={viewMode === '2d'} aria-hidden="true">2D</span>
		<span class="switch-track" class:active={viewMode === '3d'} aria-hidden="true"><span class="switch-thumb"></span></span>
		<span class="mode-label" class:active={viewMode === '3d'} aria-hidden="true">3D</span>
	</button>
</div>

<style>
	.canvas-mode-controls { display: flex; flex: none; align-items: center; padding: 4px 22px; background: var(--bg2); }
	.mode-switch {
		display: inline-flex;
		align-items: center;
		gap: 8px;
		padding: var(--btn-sm-padding);
		border: 0;
		border-radius: var(--btn-sm-radius);
		background: transparent;
		color: var(--fg2);
		font: inherit;
		font-size: var(--btn-sm-font-size);
		cursor: pointer;
	}
	.mode-switch:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
	.mode-label { min-width: 1.65em; text-align: center; }
	.mode-label.active { color: var(--fg); font-weight: 600; }
	.switch-track { position: relative; width: 36px; height: 20px; flex: none; border-radius: 999px; background: var(--border2); }
	.switch-thumb { position: absolute; top: 2px; left: 2px; width: 16px; height: 16px; border-radius: 50%; background: var(--bg); transition: transform 0.12s ease; }
	.switch-track.active { background: var(--accent); }
	.switch-track.active .switch-thumb { transform: translateX(16px); background: var(--accent-fg); }
	@container canvas-panel (max-width: 67.6923em) { .canvas-mode-controls { padding-inline: 12px; } }
	@media (prefers-reduced-motion: reduce) { .switch-thumb { transition: none; } }
</style>

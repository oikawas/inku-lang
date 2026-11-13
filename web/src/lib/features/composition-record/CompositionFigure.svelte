<script lang="ts">
	// A form's or a law's small figure (2026-11-13). The figures are the app's own
	// fixed drawings (figures.ts), never a work's drawing, so they are written
	// into the DOM directly. A key with no figure draws nothing.
	import { FIGURES, FIGURE_VIEW_BOX } from './figures';

	let { figure, size = 14 }: { figure: string | null | undefined; size?: number } = $props();
	const body = $derived(figure ? FIGURES[figure] ?? null : null);
</script>

{#if body}
	<svg class="composition-figure" viewBox={FIGURE_VIEW_BOX} width={size} height={size} aria-hidden="true" focusable="false">{@html body}</svg>
{/if}

<style>
	.composition-figure { flex: 0 0 auto; vertical-align: -0.2em; color: inherit; }
</style>

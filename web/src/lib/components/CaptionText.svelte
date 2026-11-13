<script lang="ts">
	import { captionParts, withHighlight } from '$lib/captionText';

	// `highlight` lights the words the thing pointed at quotes (step 1c).
	type Props = { text: string; highlight?: { start: number; end: number } | null };
	let { text, highlight = null }: Props = $props();
	const parts = $derived(withHighlight(captionParts(text), highlight));
</script>

{#each parts as part, index (index)}{#if part.italic}<em class:lit={part.lit}>{part.text}</em>{:else if part.lit}<mark class="lit">{part.text}</mark>{:else}{part.text}{/if}{/each}

<style>
	em { font-style: italic; }
	.lit { background: color-mix(in srgb, var(--accent) 28%, transparent); color: inherit; border-radius: 2px; }
</style>

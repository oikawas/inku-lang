<script lang="ts">
	import { captionParts } from '$lib/captionText';

	type Props = { text: string };
	let { text }: Props = $props();
	const parts = $derived(captionParts(text));
</script>

{#each parts as part, index (index)}{#if part.italic}<em>{part.text}</em>{:else}{part.text}{/if}{/each}

<style>
	em { font-style: italic; }
</style>

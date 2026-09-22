<script lang="ts">
	import '$lib/typography.css';
	import { textSizeSettings } from '$lib/features/appearance/text-size.svelte';

	let { children } = $props();

	$effect(() => {
		document.documentElement.style.setProperty('--ui-text-scale', String(textSizeSettings.scale));
	});
</script>

{@render children()}

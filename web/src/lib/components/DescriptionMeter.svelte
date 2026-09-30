<script lang="ts">
	/**
	 * The length of a description and the verse form it is nearest to, e.g.
	 * "文字数 17/17（俳句）". The description box and the "change the
	 * description" dialog both show it under their text, at the right.
	 */
	import { t } from '$lib/i18n/index.svelte';
	import { describeLength } from '$lib/verseForm';

	let { text }: { text: string } = $props();

	const meter = $derived(describeLength(text, t().code));
</script>

<div class="description-meter" class:soft-over={meter.over} aria-hidden="true">
	{meter.unit === 'words'
		? t().inputMeterWords(meter.count, meter.target)
		: t().inputMeterVerse(meter.count, meter.target, t().verseFormName(meter.form))}
</div>

<style>
	.description-meter {
		min-width: 54px;
		margin-left: auto;
		font-size: var(--ui-font-size-12);
		line-height: 1.5;
		font-variant-numeric: tabular-nums;
		text-align: right;
		color: var(--fg3);
	}
	.description-meter.soft-over { color: color-mix(in srgb, var(--fg) 78%, transparent); }
</style>

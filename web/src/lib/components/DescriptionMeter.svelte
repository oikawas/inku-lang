<script lang="ts">
	/**
	 * The length of a description and the verse form it is nearest to, e.g.
	 * "音数 17/17（俳句）" or "Lines 3/3 (haiku)". The description box and the
	 * "change the description" dialog both show it under their text, at the
	 * right.
	 *
	 * Japanese is counted in sounds by the Server. Until its first answer, or
	 * when it cannot answer, the meter counts characters; while the author
	 * types it keeps the last answer rather than falling back each keystroke.
	 */
	import { t } from '$lib/i18n/index.svelte';
	import { describeLength, readsAsJapanese, type MoraCount } from '$lib/verseForm';
	import { fetchMora } from '$lib/descriptionMora';

	let { text }: { text: string } = $props();

	// The Server is asked once the typing pauses.
	const ASK_AFTER_MS = 300;
	let mora = $state<MoraCount | null>(null);

	$effect(() => {
		const source = text;
		if (!readsAsJapanese(source, t().code)) {
			mora = null;
			return;
		}
		const controller = new AbortController();
		const timer = window.setTimeout(() => {
			fetchMora(source, controller.signal)
				.then((counted) => { if (!controller.signal.aborted) mora = counted; })
				.catch(() => { if (!controller.signal.aborted) mora = null; });
		}, ASK_AFTER_MS);
		return () => {
			window.clearTimeout(timer);
			controller.abort();
		};
	});

	const meter = $derived(describeLength(text, t().code, mora));
</script>

<div class="description-meter" class:soft-over={meter.over} aria-hidden="true">
	{meter.unit === 'lines'
		? t().inputMeterLines(meter.count, meter.target, t().englishFormName(meter.form))
		: meter.unit === 'mora'
			? t().inputMeterMora(meter.count, meter.target, t().verseFormName(meter.form), meter.approximate)
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

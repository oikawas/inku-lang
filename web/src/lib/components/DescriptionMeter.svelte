<script lang="ts">
	/**
	 * The length of a description and the verse form it is, e.g.
	 * "音数 17/17（俳句/川柳）", "Lines 3/3 (haiku)", or the count alone when
	 * it is no form. The description box and the "change the description"
	 * dialog both show it under their text, at the right.
	 *
	 * The Server counts Japanese sounds and English syllables. Until its first
	 * answer, or when it cannot answer, the page estimates; while the author
	 * types it keeps the last answer rather than falling back each keystroke.
	 * A language switched off in Settings is counted but not judged, and the
	 * Server is not asked.
	 */
	import { t } from '$lib/i18n/index.svelte';
	import { describeLength, readsAsJapanese, type MoraCount, type SyllableCount } from '$lib/verseForm';
	import { fetchMora, fetchSyllables, meterSwitches } from '$lib/descriptionMeter.svelte';

	let { text }: { text: string } = $props();

	// The Server is asked once the typing pauses.
	const ASK_AFTER_MS = 300;
	let mora = $state<MoraCount | null>(null);
	let syllables = $state<SyllableCount | null>(null);

	$effect(() => {
		const source = text;
		const japanese = readsAsJapanese(source, t().code);
		const judged = japanese ? meterSwitches.japanese : meterSwitches.english;
		if (!judged) return;
		const controller = new AbortController();
		const timer = window.setTimeout(() => {
			const asked = japanese ? fetchMora(source, controller.signal) : fetchSyllables(source, controller.signal);
			asked
				.then((counted) => {
					if (controller.signal.aborted) return;
					if (japanese) mora = counted as MoraCount | null;
					else syllables = counted as SyllableCount | null;
				})
				.catch(() => {
					if (controller.signal.aborted) return;
					if (japanese) mora = null;
					else syllables = null;
				});
		}, ASK_AFTER_MS);
		return () => {
			window.clearTimeout(timer);
			controller.abort();
		};
	});

	const meter = $derived(describeLength(text, t().code, meterSwitches, { mora, syllables }));
	const label = $derived.by(() => {
		const strings = t();
		if (meter.unit === 'lines') {
			return strings.inputMeterLines(meter.count, meter.form?.length ?? null, meter.form ? strings.englishFormName(meter.form.form) : null);
		}
		const form = meter.form ? strings.verseFormName(meter.form.form) : null;
		return meter.unit === 'mora'
			? strings.inputMeterMora(meter.count, meter.form?.length ?? null, form, meter.approximate)
			: strings.inputMeterVerse(meter.count, meter.form?.length ?? null, form);
	});
</script>

<div class="description-meter" aria-hidden="true">{label}</div>

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
</style>

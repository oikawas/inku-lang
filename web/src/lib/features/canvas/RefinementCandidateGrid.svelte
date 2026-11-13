<script module lang="ts">
	import type { CompositionSummary } from '$lib/features/composition-record/record';

	/** The work being refined, set beside a pressed option (2026-11-13). */
	export type RefinementTarget = {
		artworkUrl: string | null;
		aspectWidth: number;
		aspectHeight: number;
		/** Its composition record's summary; null where the refinement does not read the description again. */
		composition: CompositionSummary | null;
	};
</script>

<script lang="ts">
	import { t } from '$lib/i18n/index.svelte';
	import Tooltip from '$lib/components/Tooltip.svelte';
	import { svgImage } from '$lib/svgImage';
	import type { RefinementSession } from '$lib/features/canvas/refinement-session.svelte';
	import CompositionChips from '$lib/features/composition-record/CompositionChips.svelte';
	import { candidateComposition } from '$lib/features/composition-record/record';
	import { recompositionLines } from './recomposition';

	type Props = {
		isJapanese: boolean;
		refinementSession: RefinementSession;
		/** Save the chosen options, then leave; the rest are dropped. */
		onSaveAndClose: () => void | Promise<void>;
		/** Drop every unsaved option, then leave. */
		onDiscardAndClose: () => void | Promise<void>;
		/** The widest the grid goes; the color change shows a dozen options. */
		maxColumns?: number;
		/** What the empty grid says before the first options arrive. */
		placeholder?: string;
		target?: RefinementTarget | null;
	};

	let { isJapanese, refinementSession, onSaveAndClose, onDiscardAndClose, maxColumns = 2, placeholder, target = null }: Props = $props();
	// The pressed option sits beside the target, the same size, instead of alone.
	const pressed = $derived(refinementSession.previewId
		? refinementSession.candidates.find((candidate) => candidate.id === refinementSession.previewId) ?? null
		: null);
	const comparing = $derived(!!pressed && !!target);
	// Only the refinements that read the description again name each option's
	// composition; the others keep the parent's record, so every card would
	// repeat the target's.
	const named = $derived(!!target?.composition);
	const unnamed: CompositionSummary = { state: 'none', thesis: null, form: null, mainLaw: null, reason: null };
	const summaryOf = (result: { description_ddl?: unknown }): CompositionSummary => named ? candidateComposition(result) : unnamed;
</script>

	<div class="refine-workspace">
		<!-- Above the options: a dozen of them push anything below out of the dialog. -->
		{#if refinementSession.status}<div class="variation-grid-status">{refinementSession.status}</div>{/if}
		<section class="refine-action-section refine-candidates-section">
			{#if refinementSession.candidates.length > 0}
				<!-- Unsaved options keep the dialog open: these two are its only
				     ways out, so no unsaved work is left behind on another screen. -->
				<div class="refine-actions refine-save-actions">
					{#if refinementSession.previewId}
						<button class="refine-preview-back" type="button" onclick={() => refinementSession.preview(null)}>{t().refinePreviewBack}</button>
					{/if}
					<Tooltip placement="top-left" text={t().tooltipRefineDiscardAndClose}>
						<button class="refine-discard-btn" type="button" onclick={onDiscardAndClose} disabled={refinementSession.busy || refinementSession.gridBusy}>
							{t().refineDiscardAndClose}
						</button>
					</Tooltip>
					<Tooltip placement="top-left" text={t().tooltipVariationGridSaveSelected}>
						<button class="refine-save-btn" type="button" onclick={onSaveAndClose} disabled={refinementSession.busy || refinementSession.gridBusy || refinementSession.candidates.every((candidate) => !candidate.selected)}>
							{t().refineSaveAndClose}
						</button>
					</Tooltip>
				</div>
				{#if comparing && pressed && target}
					{@const option = summaryOf(pressed.result)}
					<!-- The target and the pressed option side by side, the same size, each with its record. -->
					<div class="compare-grid">
						<div class="compare-side">
							<div class="comparison-label">{t().refineCompareTarget}</div>
							<div class="compare-art" style="aspect-ratio: {target.aspectWidth} / {target.aspectHeight}">{#if target.artworkUrl}<img src={target.artworkUrl} alt="" />{/if}</div>
							{#if target.composition}
								<CompositionChips summary={target.composition} {isJapanese} />
								{#if target.composition.thesis}<p class="compare-thesis">{target.composition.thesis}</p>{/if}
								{#if target.composition.reason}<p class="compare-reason">{target.composition.reason}</p>{/if}
							{/if}
						</div>
						<div class="compare-side">
							<div class="comparison-label">{t().refineCompareOption(refinementSession.candidates.indexOf(pressed) + 1)}</div>
							<button class="compare-art compare-option" style="aspect-ratio: {target.aspectWidth} / {target.aspectHeight}" type="button" onclick={() => refinementSession.preview(null)}>
								<img use:svgImage={pressed.result.svg} alt="" />
							</button>
							{#each [pressed.label, ...recompositionLines(pressed.result.recomposition, t()), ...(pressed.details ?? [])].filter(Boolean) as line}
								<span class="compare-detail">{line}</span>
							{/each}
							<CompositionChips summary={option} target={target.composition} {isJapanese} />
							{#if option.thesis}<p class="compare-thesis">{option.thesis}</p>{/if}
							{#if option.reason}<p class="compare-reason">{option.reason}</p>{/if}
						</div>
					</div>
				{:else}
					{@const shown = refinementSession.candidates.filter((candidate) => !refinementSession.previewId || candidate.id === refinementSession.previewId)}
					<div class="variation-grid" style="--variation-cols: {Math.max(1, Math.min(maxColumns, shown.length))};">
						{#each shown as candidate (candidate.id)}
							{@const summary = summaryOf(candidate.result)}
							<div class="variation-card-wrap">
								<!-- Pressed, it sits beside the target; a second press returns to all of them. -->
								<button class="variation-card" class:selected={candidate.selected} class:saved={candidate.saved} onclick={() => refinementSession.preview(refinementSession.previewId === candidate.id ? null : candidate.id)} type="button">
									<span class="variation-card-art"><img use:svgImage={candidate.result.svg} alt="" /></span>
									<span class="variation-card-meta">
										<span class="cand-head"><span class="cand-no">{candidate.label}</span><CompositionChips {summary} target={target?.composition ?? null} {isJapanese} /></span>
										{#if summary.thesis}<span class="cand-thesis">{summary.thesis}</span>{/if}
										{#each recompositionLines(candidate.result.recomposition, t()) as line}
											<span class="recomposition-detail">{line}</span>
										{/each}
										{#each candidate.details ?? [] as line}
											<span class="recomposition-detail">{line}</span>
										{/each}
										<span>r {candidate.result.render_seed ?? "-"} / v {candidate.result.composition_seed ?? t().seedBaseLabel}{candidate.result.interpretation_seed ? ` / i ${candidate.result.interpretation_seed.slice(0, 8)}` : ""}</span>
									</span>
								</button>
							{#if refinementSession.gridIncludesReading}
								<div class="variation-ddl-popup">
									{#if summary.thesis}<div class="cand-popup-term">{t().compositionThesisLabel}</div><p class="cand-popup-text">{summary.thesis}</p>{/if}
									{#if summary.reason}<div class="cand-popup-term">{t().compositionReasonTerm}</div><p class="cand-popup-text">{summary.reason}</p>{/if}
									{#if summary.thesis || summary.reason}<div class="cand-popup-term">{t().compositionDdlTerm}</div>{/if}
									<pre class="cand-popup-ddl">{candidate.result.ddl}</pre>
								</div>
							{/if}
								<button
									class="variation-select"
									class:selected={candidate.selected}
									class:saved={candidate.saved}
								disabled={candidate.saved}
								title={candidate.saved ? (isJapanese ? '保存済み' : 'Saved') : undefined}
								aria-label={candidate.saved ? (isJapanese ? '保存済み' : 'Saved') : undefined}
								onclick={() => refinementSession.toggleCandidate(candidate.id)}
								type="button"
								>{candidate.saved ? "✔" : candidate.selected ? "✓" : "+"}</button>
							</div>
						{/each}
					</div>
				{/if}
			{:else}
				<div class="variation-grid-placeholder">
					<span>{placeholder ?? t().refineCandidatePlaceholder}</span>
				</div>
			{/if}
		</section>
	</div>

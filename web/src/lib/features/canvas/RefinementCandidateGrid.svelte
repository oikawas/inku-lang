<script lang="ts">
	import { t } from '$lib/i18n/index.svelte';
	import Tooltip from '$lib/components/Tooltip.svelte';
	import { svgImage } from '$lib/svgImage';
	import type { RefinementSession } from '$lib/features/canvas/refinement-session.svelte';

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
	};

	let { isJapanese, refinementSession, onSaveAndClose, onDiscardAndClose, maxColumns = 2, placeholder }: Props = $props();
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
				{@const shown = refinementSession.candidates.filter((candidate) => !refinementSession.previewId || candidate.id === refinementSession.previewId)}
				<div class="variation-grid" style="--variation-cols: {Math.max(1, Math.min(maxColumns, shown.length))};">
					{#each shown as candidate (candidate.id)}
						<div class="variation-card-wrap">
							<!-- Enlarged inside the dialog; a second press returns to all of them. -->
							<button class="variation-card" class:selected={candidate.selected} class:saved={candidate.saved} onclick={() => refinementSession.preview(refinementSession.previewId === candidate.id ? null : candidate.id)} type="button">
								<span class="variation-card-art"><img use:svgImage={candidate.result.svg} alt="" /></span>
								<span class="variation-card-meta">
									<span>{candidate.label}</span>
									<span>r {candidate.result.render_seed ?? "-"} / v {candidate.result.composition_seed ?? t().seedBaseLabel}{candidate.result.interpretation_seed ? ` / i ${candidate.result.interpretation_seed.slice(0, 8)}` : ""}</span>
								</span>
							</button>
						{#if refinementSession.gridIncludesReading}<pre class="variation-ddl-popup">{candidate.result.ddl}</pre>{/if}
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
			{:else}
				<div class="variation-grid-placeholder">
					<span>{placeholder ?? t().refineCandidatePlaceholder}</span>
				</div>
			{/if}
		</section>
	</div>

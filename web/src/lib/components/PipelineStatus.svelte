<script lang="ts">
	import { t } from '$lib/i18n/index.svelte';
	import type { PipelinePhase } from '$lib/features/pipeline/api';
	import { formatPipelineDiagnostic, type PipelineDiagnostic } from '$lib/features/pipeline/diagnostics';

	type Props = {
		patch: PipelinePhase | null;
		committedDdl: string;
		diagnostics: PipelineDiagnostic[];
		diagnosticsUnavailable: boolean;
		busy: boolean;
		reason: string | null;
		onApprove: () => void | Promise<void>;
		onDecline: () => void | Promise<void>;
	};

	let {
		patch,
		committedDdl,
		diagnostics,
		diagnosticsUnavailable,
		busy,
		reason,
		onApprove,
		onDecline,
	}: Props = $props();
</script>

{#if patch}
	<section class="pipeline-notice" aria-labelledby="pipeline-patch-title">
		<h3 id="pipeline-patch-title">{t().pipelinePatchTitle}</h3>
		<p>{t().pipelinePatchHint}</p>
		<div class="pipeline-comparison">
			<div><strong>{t().pipelineCommittedDdl}</strong><pre>{committedDdl}</pre></div>
			<div><strong>{t().pipelineProposedDdl}</strong><pre>{patch.candidate?.source ?? ''}</pre></div>
		</div>
		<div class="pipeline-actions">
			<button type="button" disabled={busy} onclick={onApprove}>{t().pipelineApprove}</button>
			<button type="button" disabled={busy} onclick={onDecline}>{t().pipelineDecline}</button>
		</div>
	</section>
{/if}

{#if diagnostics.length > 0}
	<details class="pipeline-notice">
		<summary>{t().pipelineDiagnostics}</summary>
		<ul class="pipeline-diagnostic-list">
			{#each diagnostics as diagnostic}
				<li>
					<p>{formatPipelineDiagnostic(diagnostic, t())}</p>
					<details>
						<summary>{t().pipelineDiagnosticDetails}</summary>
						<pre>{JSON.stringify(diagnostic.value, null, 2)}</pre>
					</details>
				</li>
			{/each}
		</ul>
	</details>
{/if}

{#if diagnosticsUnavailable}
	<p class="pipeline-attention" role="status">{t().pipelineDiagnosticsUnavailable}</p>
{/if}

{#if reason}
	<p class="pipeline-attention" role="status">{t().pipelineNeedsAttention} {t().pipelineAttentionReason(reason)}</p>
{/if}

<style>
	.pipeline-notice { margin-top: .75rem; padding: .75rem; border: 1px solid var(--border, #bbb); border-radius: .5rem; }
	.pipeline-notice h3 { margin: 0 0 .4rem; font-size: .95rem; }
	.pipeline-notice p { margin: .3rem 0 .7rem; }
	.pipeline-diagnostic-list { margin: .55rem 0 0; padding-left: 1.25rem; }
	.pipeline-diagnostic-list li + li { margin-top: .7rem; }
	.pipeline-diagnostic-list p { margin: 0 0 .25rem; }
	.pipeline-comparison { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: .6rem; }
	.pipeline-comparison pre, .pipeline-diagnostic-list pre { max-height: 15rem; overflow: auto; white-space: pre-wrap; overflow-wrap: anywhere; margin: .3rem 0; padding: .55rem; background: color-mix(in srgb, currentColor 6%, transparent); }
	.pipeline-actions { display: flex; gap: .5rem; margin-top: .6rem; }
	.pipeline-actions button { padding: .45rem .7rem; }
	.pipeline-attention { margin: .65rem 0 0; color: var(--danger, #a12d27); }
	@media (max-width: 40rem) { .pipeline-comparison { grid-template-columns: 1fr; } }
</style>

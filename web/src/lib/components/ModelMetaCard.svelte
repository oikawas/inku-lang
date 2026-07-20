<!--
	Shared model evaluation card (purposes / recommendation / speed / comment).
	This is the design used by the description-tab model selection; reused by the
	settings model picker and the model comparison dialog so all surfaces match.
	Display-only: the reveal (display:block on hover) is provided by the parent,
	which must be position:relative and target `:global(.model-hover-card)`.
-->
<script lang="ts">
	import type { ModelOption } from '$lib/models';
	import { modelPurposes, modelRecommendation, modelSpeed, modelComment, modelEolLabel } from '$lib/modelMeta';

	type Props = {
		model: ModelOption;
		isJapanese: boolean;
		extra?: string;
	};

	let { model, isJapanese, extra = '' }: Props = $props();
</script>

<span class="model-hover-card" role="tooltip">
	{#if model.eol}<span><strong>状態 / Status</strong>{modelEolLabel(model, isJapanese)}</span>{/if}
	<span><strong>用途 / Use</strong>{modelPurposes(model)}</span>
	<span><strong>オススメ度 / Recommendation</strong>{modelRecommendation(model)}</span>
	<span><strong>速度 / Speed</strong>{modelSpeed(model)}</span>
	<span><strong>評価 / Comment</strong>{modelComment(model, isJapanese)}</span>
	{#if extra}<span><strong>{isJapanese ? '状態 / Status' : 'Status'}</strong>{extra}</span>{/if}
</span>

<style>
	.model-hover-card {
		display: none;
		position: absolute;
		left: 0;
		top: calc(100% + 6px);
		z-index: 520;
		width: min(340px, 75vw);
		box-sizing: border-box;
		padding: 10px 12px;
		border: 1px solid #64748b;
		border-radius: var(--r);
		background: #111820;
		box-shadow: 0 8px 24px rgba(0, 0, 0, .32);
		color: #f8fafc;
		text-align: left;
		pointer-events: none;
		white-space: normal;
	}
	.model-hover-card > span { display: grid; gap: 2px; color: #f8fafc; font-size: 11px; line-height: 1.45; }
	.model-hover-card > span + span { margin-top: 6px; }
	.model-hover-card strong { color: #cbd5e1; font-size: 9px; font-weight: 500; letter-spacing: .05em; text-transform: uppercase; }
</style>

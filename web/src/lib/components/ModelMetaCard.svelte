<!--
	Shared model evaluation card (purposes / recommendation / cost / speed / comment).
	This is the design used by the description-tab model selection; reused by the
	settings model picker and the model comparison dialog so all surfaces match.
	Display-only: the parent decides when it shows (display:block on hover or
	focus, targeting `:global(.model-hover-card)`); the card places itself, fixed
	to the window beside the parent, so no scrolling list or dialog edge cuts it.
-->
<script lang="ts">
	import type { ModelOption } from '$lib/models';
	import { isModelUnselectable, modelRecommendation, modelStageRecommendations, modelSpeed, modelCost, modelComment, modelStatusLabel, type ModelPurpose } from '$lib/modelMeta';
	import { openFloatingCard } from '$lib/floatingCard';
	import ModelPurposeBadges from './ModelPurposeBadges.svelte';

	type Props = {
		model: ModelOption;
		isJapanese: boolean;
		extra?: string;
		purpose?: ModelPurpose;
	};

	let { model, isJapanese, extra = '', purpose = undefined }: Props = $props();

	// A model measured per stage shows both stages, whichever surface the card is on:
	// the two numbers are the measurement, and reading one of them means switching
	// tabs to find the other. The stage a surface is choosing for still decides the
	// order of the cards (sortModels) and what a click sets.
	const stages = $derived(modelStageRecommendations(model, purpose));

	let card = $state<HTMLSpanElement>();
	$effect(() => {
		const anchor = card?.parentElement;
		if (!card || !anchor) return;
		const shown = card;
		const open = () => openFloatingCard(shown, anchor);
		anchor.addEventListener('pointerenter', open);
		anchor.addEventListener('focusin', open);
		return () => {
			anchor.removeEventListener('pointerenter', open);
			anchor.removeEventListener('focusin', open);
		};
	});
</script>

<span class="model-hover-card" role="tooltip" bind:this={card}>
	{#if modelStatusLabel(model, isJapanese)}<span><strong>状態 / Status</strong><span class={isModelUnselectable(model) ? 'status-warning' : 'status-muted'}>{modelStatusLabel(model, isJapanese)}</span></span>{/if}
	<span><strong>用途 / Use</strong><ModelPurposeBadges {model} {isJapanese} /></span>
	{#if stages}
		<span><strong>オススメ度 / Stage 1</strong>{stages.stage1}</span>
		<span><strong>オススメ度 / Stage 2</strong>{stages.stage2}</span>
	{:else}
		<span><strong>オススメ度 / Recommendation</strong>{modelRecommendation(model, purpose)}</span>
	{/if}
	<span><strong>概算コスト / Est. cost</strong>{modelCost(model, isJapanese)}</span>
	<span><strong>速度 / Speed</strong>{modelSpeed(model, isJapanese)}</span>
	<span><strong>評価 / Comment</strong>{modelComment(model, isJapanese)}</span>
	{#if extra}<span><strong>状態 / Status</strong>{extra}</span>{/if}
</span>

<style>
	.model-hover-card {
		display: none;
		position: fixed;
		left: 0;
		top: 0;
		z-index: 520;
		width: min(340px, 75vw);
		box-sizing: border-box;
		padding: 10px 12px;
		border: 1px solid var(--tooltip-border);
		border-radius: var(--r);
		background: var(--tooltip-bg);
		box-shadow: var(--tooltip-shadow);
		color: var(--tooltip-fg);
		text-align: left;
		pointer-events: none;
		white-space: normal;
	}
	.model-hover-card > span { display: grid; gap: 2px; color: var(--tooltip-fg); font-size: var(--ui-font-size-11); line-height: 1.45; }
	.model-hover-card > span + span { margin-top: 6px; }
	.model-hover-card strong { color: var(--tooltip-muted); font-size: var(--ui-font-size-9); font-weight: 500; letter-spacing: .05em; text-transform: uppercase; }
	/* A label that keeps the model from publication is a warning; older and not measured stay muted. */
	.model-hover-card .status-warning { color: var(--danger); font-weight: 600; }
	.model-hover-card .status-muted { color: var(--tooltip-muted); }
</style>

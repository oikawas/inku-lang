<script lang="ts">
	import { tick } from 'svelte';
	import { t } from '$lib/i18n/index.svelte';
	import { pickerSelection, type ModelOption, type Provider, type ProviderGroup } from '$lib/models';
	import { modelRecommendation, modelRecommendationStars, modelSpeed, modelCost, modelComment, modelStatusLabel, modelStatusParts, isModelUnselectable, purposeUnsupported, sortModels, type ModelPurpose } from '$lib/modelMeta';
	import { openFloatingCard } from '$lib/floatingCard';
	import ModelPurposeBadges from './ModelPurposeBadges.svelte';

	type Props = {
		label: string;
		selectedModel: string;
		providerGroups: ProviderGroup[];
		purpose?: ModelPurpose;
		disabled?: boolean;
		onSelect: (provider: Provider, model: string) => void | Promise<void>;
	};

	let { label, selectedModel, providerGroups, purpose = 'llm', disabled = false, onSelect }: Props = $props();
	let open = $state(false);
	let selectionError = $state('');
	let launchButton = $state<HTMLButtonElement>();
	let pickerDialog = $state<HTMLDivElement>();
	let closeButton = $state<HTMLButtonElement>();

	const offer = $derived(pickerSelection(providerGroups, selectedModel));
	const configuredGroups = $derived(offer.groups);
	const selected = $derived(offer.selected);

	const isJapanese = $derived(t().closeLabel !== 'Close');

	async function choose(provider: Provider, model: string) {
		selectionError = '';
		try {
			await onSelect(provider, model);
		} catch (error) {
			selectionError = error instanceof Error && error.message ? error.message : t().modelSelectionFailed;
			return;
		}
		closePicker();
	}

	function openPicker() {
		selectionError = '';
		open = true;
		void tick().then(() => closeButton?.focus());
	}

	function closePicker() {
		open = false;
		void tick().then(() => launchButton?.focus());
	}

	function trapKeyboard(event: KeyboardEvent) {
		if (event.isComposing) return;
		if (event.key === 'Escape') {
			event.preventDefault();
			event.stopPropagation();
			closePicker();
			return;
		}
		if (event.key !== 'Tab' || !pickerDialog) return;
		const focusable = [...pickerDialog.querySelectorAll<HTMLElement>('button:not(:disabled), [href], input:not(:disabled), select:not(:disabled), textarea:not(:disabled), [tabindex]:not([tabindex="-1"])')];
		const first = focusable[0];
		const last = focusable.at(-1);
		if (!first || !last) return;
		if (event.shiftKey && document.activeElement === first) {
			event.preventDefault();
			last.focus();
		} else if (!event.shiftKey && document.activeElement === last) {
			event.preventDefault();
			first.focus();
		}
	}

	// Measured once shown rather than guessed: a guessed height let a taller card
	// run past the bottom of the window.
	function positionMeta(event: Event) {
		const btn = event.currentTarget as HTMLElement;
		const meta = btn.querySelector('.metadata') as HTMLElement | null;
		if (meta) openFloatingCard(meta, btn);
	}
</script>

<div class="context-model-picker">
	<span class="field-label">{label}</span>
	<button class="picker-launch" type="button" {disabled} bind:this={launchButton} onclick={openPicker}>
		<span><strong>{selected?.model.label ?? selectedModel}</strong>{#if selected}<small>{selected.group.id === 'chatgpt' ? t().chatgptPlanLabel : selected.group.label}</small>{:else if offer.notInList}<small class="not-in-list">{t().modelPickerNotInList}</small>{/if}</span>
		<span class="change-label">{t().modelSelectButton}</span>
	</button>
</div>

{#if open}
	<div class="picker-backdrop" role="presentation" onclick={closePicker}></div>
	<div class="picker-dialog" class:empty={configuredGroups.length === 0} role="dialog" aria-modal="true" aria-label={label} tabindex="-1" bind:this={pickerDialog} onkeydown={trapKeyboard}>
		<header><h2>{label}</h2><button type="button" bind:this={closeButton} aria-label={t().closeLabel} onclick={closePicker}>×</button></header>
		{#if selectionError}<p class="selection-error" role="alert">{selectionError}</p>{/if}
		<div class="picker-groups">
			{#each configuredGroups as group (group.id)}
				<section><h3>{group.id === 'chatgpt' ? t().chatgptPlanLabel : group.label}</h3><div class="model-grid">
					{#each sortModels(group.models, purpose) as model (model.id)}
						<button type="button" class:selected={selected?.group.id === group.id && selected?.model.id === model.id} class:eol={model.eol} class:unselectable={isModelUnselectable(model)} class:not-recommended={purposeUnsupported(model, purpose)} disabled={isModelUnselectable(model)} onpointerenter={positionMeta} onfocus={positionMeta} onclick={() => choose(group.id, model.id)}>
							<div class="model-button-heading">
								<strong>{model.label}</strong>
								<span class="model-recommendation" aria-label={`${t().settingsModelRecommendationFields[purpose === 'vision' ? 'recommendation_vision' : 'recommendation_llm']} ${modelRecommendation(model, purpose)}`}>{modelRecommendationStars(model, purpose)}</span>
							</div>
							{#if purposeUnsupported(model, purpose)}<small class="not-recommended-note">{t().modelNotRecommended}</small>{/if}
							{#if modelStatusLabel(model, isJapanese)}<small class="model-label-mark">{#each modelStatusParts(model, isJapanese) as part, partIndex (partIndex)}{#if partIndex > 0}{' · '}{/if}<span class:eol-mark={part.blocking}>{part.text}</span>{/each}</small>{/if}{#if model.notes}<small>{model.notes}</small>{/if}
							<span class="metadata" role="tooltip">
								{#if modelStatusLabel(model, isJapanese)}<span><b>状態 / Status</b><span class="status-muted">{#each modelStatusParts(model, isJapanese) as part, partIndex (partIndex)}{#if partIndex > 0}{' · '}{/if}<span class:status-warning={part.blocking}>{part.text}</span>{/each}</span></span>{/if}
								<span><b>用途 / Use</b><ModelPurposeBadges {model} {isJapanese} /></span>
								<span><b>オススメ度 / Recommendation</b>{modelRecommendation(model, purpose)}</span>
								<span><b>概算コスト / Est. cost</b>{modelCost(model, isJapanese)}</span>
								<span><b>速度 / Speed</b>{modelSpeed(model, isJapanese)}</span>
								<span><b>評価 / Comment</b>{modelComment(model, isJapanese)}</span>
							</span>
						</button>
					{/each}
				</div></section>
			{:else}
				<p class="picker-empty">{t().modelPickerEmpty}</p>
			{/each}
		</div>
	</div>
{/if}

<style>
	.model-grid button.unselectable { opacity: 0.55; cursor: not-allowed; }
	/* Strike through retired models only; a paid-tier model has not disappeared. */
	.model-grid button.eol strong { text-decoration: line-through; }
	/* Each label is its own span inside the card's muted small text (.model-grid > button > small
	   below); a label that keeps the model from publication outranks that rule in the warning colour. */
	.model-grid > button > small .eol-mark { color: var(--danger); font-weight: 600; }
	/* A label that leaves the model selectable (older model, not measured) is not a warning. */
	.model-label-mark { color: var(--fg3); }
	/* The hover card colours the labels the same way, in the tooltip's own palette. */
	.metadata .status-warning { color: var(--danger); font-weight: 600; }
	.metadata .status-muted { color: var(--tooltip-muted); }
	.context-model-picker { display: grid; gap: 4px; min-width: 0; }
	.field-label { color: var(--fg2); font-size: var(--ui-font-size-11); }
	.picker-launch { display: flex; align-items: center; justify-content: space-between; gap: 10px; width: 100%; min-width: 0; padding: 8px 10px; border: 1px solid var(--border2); border-radius: var(--r); background: var(--panel); color: var(--fg); text-align: left; cursor: pointer; font: inherit; }
	.picker-launch > span:first-child { display: grid; gap: 2px; min-width: 0; }
	.picker-launch strong { overflow-wrap: anywhere; font-size: var(--ui-font-size-12); font-weight: 500; }
	.picker-launch small { color: var(--fg3); font-size: var(--ui-font-size-10); }
	.picker-launch small.not-in-list { color: var(--danger); }
	.change-label { flex: 0 0 auto; color: var(--accent); font-size: var(--ui-font-size-10); }
	.picker-launch:disabled { opacity: .45; cursor: not-allowed; }
	.picker-backdrop { position: fixed; inset: 0; z-index: 1600; background: rgba(0,0,0,.28); backdrop-filter: blur(2px); }
	.picker-dialog { position: fixed; inset: 8vh max(5vw, calc((100vw - 900px)/2)); z-index: 1601; display: flex; flex-direction: column; overflow: hidden; border: 1px solid var(--border2); border-radius: 12px; background: var(--bg); box-shadow: 0 18px 55px rgba(0,0,0,.3); }
	/* Nothing to choose: one sentence, so the dialog is sized to it, not to a model grid. */
	.picker-dialog.empty { inset: auto; top: 50%; left: 50%; transform: translate(-50%, -50%); width: min(440px, calc(100vw - 32px)); }
	.picker-dialog header { display: flex; align-items: center; justify-content: space-between; padding: 13px 16px; border-bottom: 1px solid var(--border); }
	.picker-dialog h2 { margin: 0; font-size: var(--ui-font-size-15); font-weight: 400; }
	.picker-dialog header button { border: 0; background: none; color: var(--fg3); font-size: var(--ui-font-size-20); cursor: pointer; }
	.selection-error { margin: 12px 15px 0; color: var(--danger); font-size: var(--ui-font-size-12); }
	.picker-groups { display: grid; gap: 14px; padding: 15px; overflow: auto; }
	.picker-empty { margin: 0; color: var(--fg2); font-size: var(--ui-font-size-12); line-height: 1.6; }
	.picker-groups h3 { margin: 0 0 6px; color: var(--fg3); font-size: var(--ui-font-size-10); font-weight: 500; letter-spacing: .06em; }
	.model-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(190px, 1fr)); gap: 7px; }
	.model-grid > button { position: relative; display: grid; gap: 3px; min-width: 0; padding: 9px 10px; border: 1px solid var(--border2); border-radius: var(--r); background: var(--panel); color: var(--fg2); text-align: left; cursor: pointer; font: inherit; }
	.model-grid > button:hover { border-color: var(--accent); background: var(--bg2); }
	.model-grid > button.selected { border-color: var(--accent); box-shadow: inset 0 0 0 1px var(--accent); background: var(--accent-light); color: var(--fg); }
	/* Published for a purpose it did not answer when measured: choosable, framed in
	   red as not recommended (the author, 2026-10-26). */
	.model-grid > button.not-recommended,
	.model-grid > button.not-recommended:hover { border: 2px solid var(--danger); }
	.model-grid > button.not-recommended.selected { box-shadow: inset 0 0 0 1px var(--danger); }
	.model-grid > button > small.not-recommended-note { color: var(--danger); font-weight: 600; }
	.model-button-heading { display: flex; align-items: baseline; gap: 8px; width: 100%; min-width: 0; }
	.model-button-heading strong { flex: 1 1 auto; min-width: 0; font-size: var(--ui-font-size-12); font-weight: 500; overflow-wrap: anywhere; }
	.model-recommendation { flex: 0 0 auto; font-size: var(--ui-font-size-11); white-space: nowrap; }
	.model-grid > button > small { color: var(--fg3); font-size: var(--ui-font-size-10); }
	.metadata { display: none; position: fixed; left: 0; top: 0; z-index: 1610; width: min(340px, 75vw); box-sizing: border-box; padding: 10px 12px; border: 1px solid var(--tooltip-border); border-radius: var(--r); background: var(--tooltip-bg); box-shadow: var(--tooltip-shadow); pointer-events: none; }
	.model-grid > button:hover .metadata, .model-grid > button:focus-visible .metadata { display: grid; gap: 6px; }
	.metadata > span { display: grid; gap: 2px; color: var(--tooltip-fg); font-size: var(--ui-font-size-11); line-height: 1.4; }
	.metadata b { color: var(--tooltip-muted); font-size: var(--ui-font-size-9); font-weight: 500; letter-spacing: .04em; text-transform: uppercase; }
	@media (max-width: 640px) { .picker-dialog { inset: 4vh 3vw; } .model-grid { grid-template-columns: 1fr; } }
</style>

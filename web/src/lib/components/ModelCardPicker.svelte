<script lang="ts">
	import { t } from '$lib/i18n/index.svelte';
	import { qualifiedModelId, type ModelOption, type Provider, type ProviderGroup } from '$lib/models';
	import { modelPurposes, modelRecommendation, modelSpeed, modelComment, modelEolLabel } from '$lib/modelMeta';

	type Props = {
		label: string;
		selectedModel: string;
		providerGroups: ProviderGroup[];
		disabled?: boolean;
		onSelect: (provider: Provider, model: string) => void | Promise<void>;
	};

	let { label, selectedModel, providerGroups, disabled = false, onSelect }: Props = $props();
	let open = $state(false);

	const configuredGroups = $derived(providerGroups.filter((group) => group.models.length > 0));
	const selected = $derived.by(() => {
		for (const group of configuredGroups) {
			const model = group.models.find((item) => item.id === selectedModel || qualifiedModelId(group.id, item.id) === selectedModel);
			if (model) return { group, model };
		}
		return null;
	});

	const isJapanese = $derived(t().closeLabel !== 'Close');

	async function choose(provider: Provider, model: string) {
		await onSelect(provider, model);
		open = false;
	}

	function positionMeta(event: Event) {
		const btn = event.currentTarget as HTMLElement;
		const meta = btn.querySelector('.metadata') as HTMLElement | null;
		if (!meta) return;
		const b = btn.getBoundingClientRect();
		const mh = meta.offsetHeight || 170;
		const mw = meta.offsetWidth || Math.min(340, window.innerWidth * 0.75);
		const margin = 8;
		const spaceBelow = window.innerHeight - b.bottom;
		const openUp = spaceBelow < mh + margin && b.top > spaceBelow;
		let top = openUp ? b.top - mh - 5 : b.bottom + 5;
		top = Math.min(Math.max(margin, top), window.innerHeight - mh - margin);
		let left = Math.min(b.left, window.innerWidth - mw - margin);
		left = Math.max(margin, left);
		meta.style.top = `${top}px`;
		meta.style.left = `${left}px`;
	}
</script>

<div class="context-model-picker">
	<span class="field-label">{label}</span>
	<button class="picker-launch" type="button" {disabled} onclick={() => (open = true)}>
		<span><strong>{selected?.model.label ?? selectedModel}</strong>{#if selected}<small>{selected.group.label}</small>{/if}</span>
		<span class="change-label">{t().modelSelectButton}</span>
	</button>
</div>

{#if open}
	<div class="picker-backdrop" role="presentation" onclick={() => (open = false)}></div>
	<div class="picker-dialog" role="dialog" aria-modal="true" aria-label={label} tabindex="-1">
		<header><h2>{label}</h2><button type="button" onclick={() => (open = false)}>×</button></header>
		<div class="picker-groups">
			{#each configuredGroups as group (group.id)}
				<section><h3>{group.label}</h3><div class="model-grid">
					{#each group.models as model (model.id)}
						<button type="button" class:selected={selected?.group.id === group.id && selected?.model.id === model.id} class:eol={model.eol} disabled={model.eol} onpointerenter={positionMeta} onfocus={positionMeta} onclick={() => choose(group.id, model.id)}>
							<strong>{model.label}</strong>{#if model.eol}<small class="eol-mark">{modelEolLabel(model, isJapanese)}</small>{/if}{#if model.notes}<small>{model.notes}</small>{/if}
							<span class="metadata" role="tooltip">
								{#if model.eol}<span><b>{isJapanese ? '状態 / Status' : 'Status'}</b>{modelEolLabel(model, isJapanese)}</span>{/if}
								<span><b>用途 / Use</b>{modelPurposes(model)}</span>
								<span><b>オススメ度 / Recommendation</b>{modelRecommendation(model)}</span>
								<span><b>速度 / Speed</b>{modelSpeed(model)}</span>
								<span><b>評価 / Comment</b>{modelComment(model, isJapanese)}</span>
							</span>
						</button>
					{/each}
				</div></section>
			{/each}
		</div>
	</div>
{/if}

<style>
	.model-grid button.eol { opacity: 0.55; cursor: not-allowed; }
	.model-grid button.eol strong { text-decoration: line-through; }
	.eol-mark { color: #a2342a; font-weight: 600; }
	.context-model-picker { display: grid; gap: 4px; min-width: 0; }
	.field-label { color: var(--fg2); font-size: 11px; }
	.picker-launch { display: flex; align-items: center; justify-content: space-between; gap: 10px; width: 100%; min-width: 0; padding: 8px 10px; border: 1px solid var(--border2); border-radius: var(--r); background: var(--panel); color: var(--fg); text-align: left; cursor: pointer; font: inherit; }
	.picker-launch > span:first-child { display: grid; gap: 2px; min-width: 0; }
	.picker-launch strong { overflow-wrap: anywhere; font-size: 12px; font-weight: 500; }
	.picker-launch small { color: var(--fg3); font-size: 10px; }
	.change-label { flex: 0 0 auto; color: var(--accent); font-size: 10px; }
	.picker-launch:disabled { opacity: .45; cursor: not-allowed; }
	.picker-backdrop { position: fixed; inset: 0; z-index: 1600; background: rgba(0,0,0,.28); backdrop-filter: blur(2px); }
	.picker-dialog { position: fixed; inset: 8vh max(5vw, calc((100vw - 900px)/2)); z-index: 1601; display: flex; flex-direction: column; overflow: hidden; border: 1px solid var(--border2); border-radius: 12px; background: var(--bg); box-shadow: 0 18px 55px rgba(0,0,0,.3); }
	.picker-dialog header { display: flex; align-items: center; justify-content: space-between; padding: 13px 16px; border-bottom: 1px solid var(--border); }
	.picker-dialog h2 { margin: 0; font-size: 15px; font-weight: 400; }
	.picker-dialog header button { border: 0; background: none; color: var(--fg3); font-size: 20px; cursor: pointer; }
	.picker-groups { display: grid; gap: 14px; padding: 15px; overflow: auto; }
	.picker-groups h3 { margin: 0 0 6px; color: var(--fg3); font-size: 10px; font-weight: 500; letter-spacing: .06em; }
	.model-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(190px, 1fr)); gap: 7px; }
	.model-grid > button { position: relative; display: grid; gap: 3px; min-width: 0; padding: 9px 10px; border: 1px solid var(--border2); border-radius: var(--r); background: var(--panel); color: var(--fg2); text-align: left; cursor: pointer; font: inherit; }
	.model-grid > button:hover { border-color: var(--accent); background: var(--bg2); }
	.model-grid > button.selected { border-color: var(--accent); box-shadow: inset 0 0 0 1px var(--accent); background: var(--accent-light); color: var(--fg); }
	.model-grid > button > strong { font-size: 12px; font-weight: 500; overflow-wrap: anywhere; }
	.model-grid > button > small { color: var(--fg3); font-size: 10px; }
	.metadata { display: none; position: fixed; left: 0; top: 0; z-index: 1610; width: min(340px, 75vw); box-sizing: border-box; padding: 10px 12px; border: 1px solid #64748b; border-radius: var(--r); background: #111820; box-shadow: 0 8px 24px rgba(0,0,0,.32); pointer-events: none; }
	.model-grid > button:hover .metadata, .model-grid > button:focus-visible .metadata { display: grid; gap: 6px; }
	.metadata > span { display: grid; gap: 2px; color: #f8fafc; font-size: 11px; line-height: 1.4; }
	.metadata b { color: #cbd5e1; font-size: 9px; font-weight: 500; letter-spacing: .04em; text-transform: uppercase; }
	@media (max-width: 640px) { .picker-dialog { inset: 4vh 3vw; } .model-grid { grid-template-columns: 1fr; } }
</style>

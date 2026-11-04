<script lang="ts">
	import { t } from '$lib/i18n/index.svelte';
	import { untrack } from 'svelte';
	import { copyDrawDefaults, type DrawDefaults, type DrawTab } from '$lib/features/draw-options';
	import { loadModelReferences } from '$lib/modelReferences';
	import { modelDisplayName, qualifiedModelRef, splitModelReference, type Provider, type ProviderGroup } from '$lib/models';
	import ModelSelectionSettings from './ModelSelectionSettings.svelte';

	type Props = {
		defaults: DrawDefaults;
		catalogs: { id: string; name: string }[];
		canvases: { id: string; label: string }[];
		providerGroups: ProviderGroup[];
		visionProviderGroups: ProviderGroup[];
		onSave: (value: DrawDefaults) => Promise<void>;
	};
	let { defaults, catalogs, canvases, providerGroups, visionProviderGroups, onSave }: Props = $props();
	let draft = $state<DrawDefaults>(untrack(() => copyDrawDefaults(defaults)));
	let saving = $state(false);
	let failed = $state(false);
	let pickerTab = $state<DrawTab | null>(null);
	let pickerProvider = $state<Provider>('');
	let pickerModel = $state('');
	let includeThinking = $state(false);
	const tabs: DrawTab[] = ['describe', 'image', 'batch_text', 'batch_image'];
	async function save() {
		saving = true; failed = false;
		try { await onSave(copyDrawDefaults(draft)); }
		catch { failed = true; }
		finally { saving = false; }
	}
	async function chooseModel(tab: DrawTab) {
		const image = tab === 'image' || tab === 'batch_image';
		const ref = (image ? draft[tab].models.vision : draft[tab].models.stage1) ?? '';
		failed = false;
		try { await loadModelReferences([{ action: 'split_ref', ref }]); }
		catch { failed = true; return; }
		const parsed = splitModelReference(ref);
		pickerProvider = parsed.provider ?? '';
		pickerModel = parsed.model;
		pickerTab = tab;
	}
	async function confirmModel() {
		if (!pickerTab) return;
		try { await loadModelReferences([{ action: 'qualify_ref', provider: pickerProvider, ref: pickerModel }]); }
		catch { failed = true; return; }
		const ref = qualifiedModelRef(pickerProvider, pickerModel);
		if (!ref) return;
		if (pickerTab === 'image' || pickerTab === 'batch_image') draft[pickerTab].models.vision = ref;
		else draft[pickerTab].models.stage1 = draft[pickerTab].models.stage2 = ref;
		pickerTab = null;
	}
	function chooseCatalog(tab: DrawTab, selected: string) {
		draft[tab].catalog.mode = selected === 'auto' ? 'auto' : 'fixed';
		if (selected !== 'auto') draft[tab].catalog.id = selected;
	}
</script>

<section class="draw-defaults">
	<h3>{t().drawDefaultsTitle}</h3>
	{#each tabs as tab (tab)}
		{@const image = tab === 'image' || tab === 'batch_image'}
		<fieldset>
			<legend>{tab === 'describe' ? t().drawDefaultsDescribe : tab === 'image' ? t().drawDefaultsImage : tab === 'batch_text' ? t().drawDefaultsBatchText : t().drawDefaultsBatchImage}</legend>
			{#if !image}
			<label data-draw-option="route">{t().drawDefaultsRoute}<select bind:value={draft[tab].route}><option value="read_and_draw">{t().drawDefaultsRead}</option><option value="stages">{t().drawDefaultsStages}</option></select></label>
			<label data-draw-option="sketch">{t().sketchLabel}<select bind:value={draft[tab].sketch}><option value="off">{t().drawDefaultsOff}</option><option value="on">{t().drawDefaultsOn}</option></select></label>
			<label data-draw-option="composition">{t().drawDefaultsComposition}<select bind:value={draft[tab].composition}><option value="off">{t().drawDefaultsOff}</option><option value="on">{t().drawDefaultsOn}</option></select></label>
			<label data-draw-option="wild">{t().wildButton}<select bind:value={draft[tab].wild}><option value="off">{t().drawDefaultsOff}</option><option value="on">{t().drawDefaultsOn}</option></select></label>
			{/if}
			<label data-draw-option="catalog">{t().colorCatalogButton}<select value={draft[tab].catalog.mode === 'auto' ? 'auto' : draft[tab].catalog.id} onchange={(event) => chooseCatalog(tab, event.currentTarget.value)}><option value="auto">{t().colorCatalogAuto}</option>{#each catalogs as catalog (catalog.id)}<option value={catalog.id}>{catalog.name}</option>{/each}</select></label>
			<label data-draw-option="canvas_aspect">{t().drawDefaultsCanvas}<select bind:value={draft[tab].canvas_aspect}>{#if image}<option value="image">{t().imageCanvasAspect}</option>{/if}{#each canvases as canvas (canvas.id)}<option value={canvas.id}>{canvas.label}</option>{/each}</select></label>
			<div data-draw-option="models"><span>{image ? t().drawDefaultsVision : t().drawDefaultsModel}</span><button type="button" onclick={() => void chooseModel(tab)}>{modelDisplayName((image ? draft[tab].models.vision : draft[tab].models.stage1) ?? '', image ? visionProviderGroups : providerGroups)} · {t().modelSelectButton}</button></div>
		</fieldset>
	{/each}
	<button type="button" disabled={saving} onclick={save}>{t().drawDefaultsSave}</button>
	{#if failed}<p role="alert">{t().drawDefaultsSaveFailed}</p>{/if}
</section>

{#if pickerTab}
	<div class="picker-backdrop" role="presentation" onclick={() => (pickerTab = null)}></div>
	<div class="picker-dialog" role="dialog" aria-modal="true" aria-label={t().modelSelectButton}>
		<ModelSelectionSettings stage1Provider={pickerProvider} stage1Model={pickerModel} visionProvider={pickerProvider} visionModel={pickerModel}
			{providerGroups} {visionProviderGroups} allowVisionSelection={false} visionOnlySelection={pickerTab === 'image' || pickerTab === 'batch_image'} bind:includeThinking
			onSetStage1Provider={(v) => (pickerProvider = v)} onSetStage1Model={(v) => (pickerModel = v)} onSetStage2Provider={() => {}} onSetStage2Model={() => {}}
			onSetVisionProvider={(v) => (pickerProvider = v)} onSetVisionModel={(v) => (pickerModel = v)} onCancel={() => (pickerTab = null)} onConfirm={confirmModel} />
	</div>
{/if}

<style>
	.draw-defaults fieldset { display: grid; gap: .5rem; margin-block: 1rem; }
	.draw-defaults label { display: flex; justify-content: space-between; gap: 1rem; align-items: center; }
	.draw-defaults select { max-width: 65%; }
	.picker-backdrop { position: fixed; inset: 0; z-index: 1600; background: #0008; }
	.picker-dialog { position: fixed; inset: 8vh 8vw; z-index: 1601; display: flex; flex-direction: column; background: var(--bg); overflow: auto; }
</style>

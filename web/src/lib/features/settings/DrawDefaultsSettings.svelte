<script lang="ts">
	import { t } from '$lib/i18n/index.svelte';
	import { untrack } from 'svelte';
	import { copyDrawDefaults, isImageTab, type DrawDefaults, type DrawTab } from '$lib/features/draw-options';
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
	let saved = $state(false);
	let failed = $state(false);
	let pickerTab = $state<DrawTab | null>(null);
	let pickerProvider = $state<Provider>('');
	let pickerModel = $state('');
	let includeThinking = $state(false);
	const tabs: DrawTab[] = ['describe', 'image', 'batch_text', 'batch_image'];
	const tabName = (tab: DrawTab) => tab === 'describe' ? t().drawDefaultsDescribe : tab === 'image' ? t().drawDefaultsImage
		: tab === 'batch_text' ? t().drawDefaultsBatchText : t().drawDefaultsBatchImage;
	async function save() {
		saving = true; failed = false; saved = false;
		try { await onSave(copyDrawDefaults(draft)); saved = true; }
		catch { failed = true; }
		finally { saving = false; }
	}
	async function chooseModel(tab: DrawTab) {
		const ref = (isImageTab(tab) ? draft[tab].models.vision : draft[tab].models.stage1) ?? '';
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
		if (isImageTab(pickerTab)) draft[pickerTab].models.vision = ref;
		else draft[pickerTab].models.stage1 = draft[pickerTab].models.stage2 = ref;
		saved = false;
		pickerTab = null;
	}
	function chooseCatalog(tab: DrawTab, selected: string) {
		draft[tab].catalog.mode = selected === 'auto' ? 'auto' : 'fixed';
		if (selected !== 'auto') draft[tab].catalog.id = selected;
		saved = false;
	}
</script>

{#each tabs as tab (tab)}
	{@const image = isImageTab(tab)}
	<div class="popover-group draw-defaults-tab" data-draw-tab={tab}>
		<div class="popover-group-label">{tabName(tab)}</div>
		<div class="db-test-result">{tab === 'describe' ? t().drawDefaultsHintDescribe : tab === 'image' ? t().drawDefaultsHintImage
			: tab === 'batch_text' ? t().drawDefaultsHintBatchText : t().drawDefaultsHintBatchImage}</div>
		<div class="db-backup-grid" oninput={() => (saved = false)}>
			{#if !image}
			<label data-draw-option="route"><span>{t().drawDefaultsRoute}</span><select bind:value={draft[tab].route}><option value="read_and_draw">{t().drawDefaultsRead}</option><option value="stages">{t().drawDefaultsStages}</option></select></label>
			<label data-draw-option="sketch"><span>{t().sketchLabel}</span><select bind:value={draft[tab].sketch}><option value="off">{t().drawDefaultsOff}</option><option value="on">{t().drawDefaultsOn}</option></select></label>
			<label data-draw-option="composition"><span>{t().drawDefaultsComposition}</span><select bind:value={draft[tab].composition}><option value="off">{t().drawDefaultsOff}</option><option value="on">{t().drawDefaultsOn}</option></select></label>
			<label data-draw-option="wild"><span>{t().wildButton}</span><select bind:value={draft[tab].wild}><option value="off">{t().drawDefaultsOff}</option><option value="on">{t().drawDefaultsOn}</option></select></label>
			{/if}
			<label data-draw-option="catalog"><span>{t().colorCatalogButton}</span><select value={draft[tab].catalog.mode === 'auto' ? 'auto' : draft[tab].catalog.id} onchange={(event) => chooseCatalog(tab, event.currentTarget.value)}><option value="auto">{t().colorCatalogAuto}</option>{#each catalogs as catalog (catalog.id)}<option value={catalog.id}>{catalog.name}</option>{/each}</select></label>
			<label data-draw-option="canvas_aspect"><span>{t().drawDefaultsCanvas}</span><select bind:value={draft[tab].canvas_aspect}>{#if image}<option value="image">{t().imageCanvasAspect}</option>{/if}{#each canvases as canvas (canvas.id)}<option value={canvas.id}>{canvas.label}</option>{/each}</select></label>
			<div class="draw-defaults-model" data-draw-option="models">
				<span>{image ? t().drawDefaultsVision : t().drawDefaultsModel}</span>
				<div class="download-folder-row">
					<span class="download-folder-name">{modelDisplayName((image ? draft[tab].models.vision : draft[tab].models.stage1) ?? '', image ? visionProviderGroups : providerGroups)}</span>
					<button type="button" class="ghost-btn" onclick={() => void chooseModel(tab)}>{t().editButton}</button>
				</div>
			</div>
		</div>
	</div>
{/each}
<div class="settings-inline-actions">
	<button type="button" class="ghost-btn primary-inline" disabled={saving} onclick={save}>{t().drawDefaultsSave}</button>
	{#if saved}<div class="inline-message">{t().drawDefaultsSaved}</div>{/if}
	{#if failed}<div class="inline-message error-text" role="alert">{t().drawDefaultsSaveFailed}</div>{/if}
</div>

{#if pickerTab}
	<div class="picker-backdrop" role="presentation" onclick={() => (pickerTab = null)}></div>
	<div class="picker-dialog" role="dialog" aria-modal="true" aria-label={t().modelSelectButton}>
		<ModelSelectionSettings stage1Provider={pickerProvider} stage1Model={pickerModel} visionProvider={pickerProvider} visionModel={pickerModel}
			{providerGroups} {visionProviderGroups} allowVisionSelection={false} visionOnlySelection={isImageTab(pickerTab)} bind:includeThinking
			onSetStage1Provider={(v) => (pickerProvider = v)} onSetStage1Model={(v) => (pickerModel = v)} onSetStage2Provider={() => {}} onSetStage2Model={() => {}}
			onSetVisionProvider={(v) => (pickerProvider = v)} onSetVisionModel={(v) => (pickerModel = v)} onCancel={() => (pickerTab = null)} onConfirm={confirmModel} />
	</div>
{/if}

<style>
	.draw-defaults-model { display: flex; flex-direction: column; align-items: flex-start; gap: 6px; font-size: var(--ui-font-size-13); }
	.picker-backdrop { position: fixed; inset: 0; z-index: 1600; background: #0008; }
	.picker-dialog { position: fixed; inset: 8vh 8vw; z-index: 1601; display: flex; flex-direction: column; background: var(--bg); border: 1px solid var(--border); border-radius: var(--r); overflow: auto; }
</style>

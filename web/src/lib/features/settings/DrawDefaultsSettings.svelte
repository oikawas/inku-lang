<script lang="ts">
	import { t } from '$lib/i18n/index.svelte';
	import { untrack } from 'svelte';
	import { copyDrawDefaults, type DrawDefaults, type DrawTab } from '$lib/features/draw-options';

	type Props = {
		defaults: DrawDefaults;
		catalogs: { id: string; name: string }[];
		canvases: { id: string; label: string }[];
		onSave: (value: DrawDefaults) => Promise<void>;
	};
	let { defaults, catalogs, canvases, onSave }: Props = $props();
	let draft = $state<DrawDefaults>(untrack(() => copyDrawDefaults(defaults)));
	let saving = $state(false);
	let failed = $state(false);
	const tabs: DrawTab[] = ['describe', 'image', 'batch_text', 'batch_image'];
	async function save() {
		saving = true; failed = false;
		try { await onSave(copyDrawDefaults(draft)); }
		catch { failed = true; }
		finally { saving = false; }
	}
</script>

<section class="draw-defaults">
	<h3>{t().drawDefaultsTitle}</h3>
	{#each tabs as tab (tab)}
		{@const image = tab === 'image' || tab === 'batch_image'}
		<fieldset>
			<legend>{tab === 'describe' ? t().drawDefaultsDescribe : tab === 'image' ? t().drawDefaultsImage : tab === 'batch_text' ? t().drawDefaultsBatchText : t().drawDefaultsBatchImage}</legend>
			<label data-draw-option="route">{t().drawDefaultsRoute}<select bind:value={draft[tab].route}><option value="read_and_draw">{t().drawDefaultsRead}</option><option value="stages">{t().drawDefaultsStages}</option></select></label>
			<label data-draw-option="sketch">{t().sketchLabel}<select bind:value={draft[tab].sketch}><option value="off">{t().drawDefaultsOff}</option><option value="on">{t().drawDefaultsOn}</option></select></label>
			<label data-draw-option="composition">{t().drawDefaultsComposition}<select bind:value={draft[tab].composition}><option value="off">{t().drawDefaultsOff}</option><option value="on">{t().drawDefaultsOn}</option></select></label>
			<label data-draw-option="wild">{t().wildButton}<select bind:value={draft[tab].wild}><option value="off">{t().drawDefaultsOff}</option><option value="on">{t().drawDefaultsOn}</option></select></label>
			<label data-draw-option="catalog">{t().colorCatalogButton}<select bind:value={draft[tab].catalog.mode}><option value="auto">{t().colorCatalogAuto}</option><option value="fixed">{t().drawDefaultsFixed}</option></select></label>
			<label>{t().drawDefaultsCatalogId}<select bind:value={draft[tab].catalog.id}>{#each catalogs as catalog (catalog.id)}<option value={catalog.id}>{catalog.name}</option>{/each}</select></label>
			<label data-draw-option="canvas_aspect">{t().drawDefaultsCanvas}<select bind:value={draft[tab].canvas_aspect}>{#if image}<option value="image">{t().imageCanvasAspect}</option>{/if}{#each canvases as canvas (canvas.id)}<option value={canvas.id}>{canvas.label}</option>{/each}</select></label>
			{#if image}
				<label data-draw-option="models">{t().drawDefaultsVision}<input bind:value={draft[tab].models.vision} /></label>
			{:else}
				<label data-draw-option="models">{t().drawDefaultsModel}<input bind:value={draft[tab].models.stage1} onchange={() => (draft[tab].models.stage2 = draft[tab].models.stage1)} /></label>
			{/if}
		</fieldset>
	{/each}
	<button type="button" disabled={saving} onclick={save}>{t().drawDefaultsSave}</button>
	{#if failed}<p role="alert">{t().drawDefaultsSaveFailed}</p>{/if}
</section>

<style>
	.draw-defaults fieldset { display: grid; gap: .5rem; margin-block: 1rem; }
	.draw-defaults label { display: flex; justify-content: space-between; gap: 1rem; align-items: center; }
	.draw-defaults input, .draw-defaults select { max-width: 65%; }
</style>

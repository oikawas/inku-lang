<script lang="ts">
	import { t } from '$lib/i18n/index.svelte';
	let { model = $bindable(), label, disabled = false, onChoose }: {
		model: string; label: (model: string) => string; disabled?: boolean;
		onChoose: (model: string, accept: (model: string) => void) => void;
	} = $props();
	let value = $derived(label(model));
</script>

<div class="condition-selection">
	<span class="condition-inline-label">{t().modelButton}</span>
	<span class="condition-value" title={value}>{value}</span>
	<button type="button" class="ghost-btn condition-change" disabled={disabled}
		onclick={() => onChoose(model, (next) => { model = next; })}>{t().editButton}</button>
</div>

<style>
	.condition-selection { display: flex; align-items: center; gap: 8px; min-width: 0; }
	.condition-inline-label { flex: 0 0 auto; color: var(--fg3); font-size: var(--ui-font-size-11); line-height: 1.35; white-space: nowrap; }
	.condition-value { flex: 1 1 auto; min-width: 0; color: var(--fg); font-size: var(--ui-font-size-14); line-height: 1.35; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
	.condition-change { flex: none; white-space: nowrap; }
</style>

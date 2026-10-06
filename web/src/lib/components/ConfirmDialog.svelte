<script lang="ts">
	import { t } from '$lib/i18n/index.svelte';
	import { onMount } from 'svelte';

type ConfirmAction = {
	message: string;
	run: () => void;
	destructive?: boolean;
	runLabel?: string;
	secondaryLabel?: string;
	secondaryRun?: () => void;
	hideCancel?: boolean;
};

	type Props = {
		action: ConfirmAction;
		onCancel: () => void;
		onRun: () => void;
		focusOnOpen?: boolean;
	};

	let { action, onCancel, onRun, focusOnOpen = false }: Props = $props();
	let dialog = $state<HTMLDivElement>();
	onMount(() => { if (focusOnOpen) dialog?.querySelector<HTMLButtonElement>('button')?.focus(); });
	function handleKeydown(event: KeyboardEvent): void {
		if (!focusOnOpen || !dialog || event.isComposing) return;
		if (event.key === 'Escape') {
			event.preventDefault(); event.stopPropagation(); onCancel();
		} else if (event.key === 'Tab') {
			const controls = [...dialog.querySelectorAll<HTMLButtonElement>('button:not(:disabled)')];
			const first = controls[0], last = controls.at(-1);
			if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
			else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
		}
	}
</script>

<div class="confirm-layer">
	<div class="confirm-backdrop" role="button" tabindex="0" aria-label={t().confirmCancel} onclick={onCancel} onkeydown={(e) => { if (e.key === 'Enter' || e.key === ' ') onCancel(); }}></div>
	<div class="confirm-box" role="dialog" aria-modal="true" tabindex="-1" bind:this={dialog} onkeydown={handleKeydown}>
		<p>{action.message}</p>
		<div class="confirm-actions">
			{#if !action.hideCancel}
				<button class="ghost-btn" onclick={onCancel}>{t().confirmCancel}</button>
			{/if}
			<button class={action.destructive ? 'danger-btn' : 'confirm-btn'} onclick={onRun}>{action.runLabel ?? (action.destructive ? t().deleteButton : t().confirmRun)}</button>
			{#if action.secondaryRun}
				<button class="paint-action" onclick={() => { const run = action.secondaryRun; onCancel(); run?.(); }}>{action.secondaryLabel ?? t().confirmRun}</button>
			{/if}
		</div>
	</div>
</div>

<style>
	.confirm-layer {
		position: fixed; inset: 0; z-index: 5000;
		display: flex; align-items: center; justify-content: center;
	}
	.confirm-backdrop {
		position: absolute; inset: 0; background: rgba(0,0,0,0.3);
	}
	.confirm-box {
		position: relative; background: var(--panel); border-radius: var(--r-lg);
		padding: 22px 24px; box-shadow: 0 8px 32px rgba(0,0,0,0.18);
		min-width: 280px; text-align: center;
	}
	.confirm-box p { margin-bottom: 16px; font-size: var(--ui-font-size-13); color: var(--fg); }
	.confirm-actions { display: flex; gap: 8px; justify-content: center; }
	.danger-btn, .confirm-btn {
		padding: var(--btn-sm-padding); border: none; border-radius: var(--btn-sm-radius);
		font-size: var(--btn-sm-font-size); cursor: pointer; font-family: inherit;
	}
	/* The second action starts a drawing, so it wears the paint shell (no ▶ mark). */
	.paint-action {
		padding: var(--btn-sm-padding);
		border: 1px solid var(--action-bg);
		border-radius: var(--btn-sm-radius);
		background: var(--action-bg);
		color: var(--action-fg);
		font-size: var(--btn-sm-font-size);
		cursor: pointer;
		font-family: inherit;
	}
	.paint-action:hover { background: var(--action-hover); border-color: var(--action-hover); }
	.danger-btn { background: var(--danger-bg); color: var(--danger-fg); }
	.confirm-btn {
		background: var(--accent);
		color: var(--accent-fg);
		border: 1px solid color-mix(in srgb, var(--accent) 82%, #000);
	}
	.confirm-btn:hover {
		filter: brightness(0.96);
	}
</style>

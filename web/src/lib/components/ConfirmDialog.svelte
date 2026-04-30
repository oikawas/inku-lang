<script lang="ts">
	import { t } from '$lib/i18n/index.svelte';

	type ConfirmAction = {
		message: string;
		run: () => void;
		destructive?: boolean;
	};

	type Props = {
		action: ConfirmAction;
		onCancel: () => void;
		onRun: () => void;
	};

	let { action, onCancel, onRun }: Props = $props();
</script>

<div class="confirm-layer">
	<div class="confirm-backdrop" role="button" tabindex="0" aria-label={t().confirmCancel} onclick={onCancel} onkeydown={(e) => { if (e.key === 'Enter' || e.key === ' ') onCancel(); }}></div>
	<div class="confirm-box" role="dialog" aria-modal="true" tabindex="-1">
		<p>{action.message}</p>
		<div class="confirm-actions">
			<button class="ghost-btn" onclick={onCancel}>{t().confirmCancel}</button>
			<button class={action.destructive ? 'danger-btn' : 'confirm-btn'} onclick={onRun}>{action.destructive ? t().deleteButton : t().confirmRun}</button>
		</div>
	</div>
</div>

<style>
	.confirm-layer {
		position: fixed; inset: 0; z-index: 600;
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
	.confirm-box p { margin-bottom: 16px; font-size: 13px; color: var(--fg); }
	.confirm-actions { display: flex; gap: 8px; justify-content: center; }
	.ghost-btn {
		padding: 4px 10px;
		border: 1px solid var(--border2);
		border-radius: var(--r);
		background: var(--panel);
		color: var(--fg2);
		font-size: 11px;
		cursor: pointer;
		font-family: inherit;
	}
	.ghost-btn:hover { background: var(--bg2); }
	.danger-btn, .confirm-btn {
		padding: 4px 10px; border: none; border-radius: var(--r);
		color: #fff; font-size: 11px; cursor: pointer; font-family: inherit;
	}
	.danger-btn { background: #c0392b; }
	.confirm-btn { background: var(--fg); }
</style>

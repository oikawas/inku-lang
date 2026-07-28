<script lang="ts">
	type Props = {
		disabled?: boolean;
		/** The ▶ mark. Off for buttons that repeat a drawing rather than start one. */
		icon?: boolean;
		/** Full panel width (the main paint button) or shrink to the label. */
		block?: boolean;
		onclick: () => void | Promise<void>;
		children: import('svelte').Snippet;
	};

	let { disabled = false, icon = true, block = true, onclick, children }: Props = $props();
</script>

<button class="paint-btn" class:block {onclick} {disabled}>
	{#if icon}<span class="paint-icon" aria-hidden="true">▶</span>{/if}
	<span>{@render children()}</span>
</button>

<style>
	.paint-btn {
		padding: 9px;
		font-size: 14px;
		font-weight: 500;
		background: var(--action-bg);
		color: var(--action-fg);
		border: none;
		border-radius: var(--r);
		letter-spacing: 0.08em;
		cursor: pointer;
		display: flex;
		align-items: center;
		justify-content: center;
		gap: 8px;
		font-family: inherit;
		transition: background 0.15s;
	}
	.paint-btn.block {
		width: 100%;
		margin-top: 8px;
	}
	.paint-btn:hover:not(:disabled) { background: var(--action-hover); }
	.paint-btn:disabled {
		background: var(--action-disabled-bg);
		color: var(--action-disabled-fg);
		cursor: not-allowed;
	}
	.paint-icon {
		font-size: 12px;
		line-height: 1;
	}
</style>

<script lang="ts">
	type Props = {
		disabled?: boolean;
		onclick: () => void | Promise<void>;
		children: import('svelte').Snippet;
	};

	let { disabled = false, onclick, children }: Props = $props();
</script>

<button class="paint-btn" {onclick} {disabled}>
	<span class="paint-icon" aria-hidden="true">▶</span>
	<span>{@render children()}</span>
</button>

<style>
	.paint-btn {
		width: 100%;
		margin-top: 8px;
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

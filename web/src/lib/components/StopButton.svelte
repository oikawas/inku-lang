<script lang="ts">
	type Props = {
		onclick: () => void | Promise<void>;
		children: import('svelte').Snippet;
	};

	let { onclick, children }: Props = $props();
</script>

<button class="stop-btn" {onclick}>
	<span class="stop-dot" aria-hidden="true"></span>
	<span>{@render children()}</span>
</button>

<style>
	.stop-btn {
		--stop-border: rgba(154, 61, 61, 0.78);
		--stop-bg: rgba(154, 61, 61, 0.16);
		--stop-bg-hover: rgba(154, 61, 61, 0.24);
		--stop-bg-pulse: rgba(154, 61, 61, 0.30);
		--stop-fg: #7f241d;
		--stop-ring: rgba(154, 61, 61, 0.22);
		width: min(50%, 220px);
		min-width: 112px;
		flex: 0 0 min(50%, 220px);
		padding: 9px 12px;
		border: 1px solid var(--stop-border);
		border-radius: var(--r);
		background: var(--stop-bg);
		color: var(--stop-fg);
		font-family: inherit;
		font-size: 14px;
		font-weight: 500;
		letter-spacing: 0.08em;
		line-height: 1;
		cursor: pointer;
		display: inline-flex;
		align-items: center;
		justify-content: center;
		gap: 8px;
		box-shadow: 0 0 0 0 var(--stop-ring);
		animation: stopPulse 2.2s ease-in-out infinite;
	}
	:global(html[data-theme='dark']) .stop-btn {
		--stop-border: rgba(255, 130, 110, 0.88);
		--stop-bg: rgba(255, 112, 88, 0.20);
		--stop-bg-hover: rgba(255, 126, 104, 0.30);
		--stop-bg-pulse: rgba(255, 126, 104, 0.42);
		--stop-fg: #ffd6cc;
		--stop-ring: rgba(255, 126, 104, 0.28);
	}
	.stop-btn:hover {
		background: var(--stop-bg-hover);
		border-color: var(--stop-border);
	}
	.stop-dot {
		width: 8px;
		height: 8px;
		border-radius: 50%;
		background: currentColor;
		box-shadow: 0 0 0 3px var(--stop-ring);
	}
	@keyframes stopPulse {
		0%, 100% {
			background: var(--stop-bg);
			box-shadow: 0 0 0 0 color-mix(in srgb, var(--stop-ring) 40%, transparent);
			filter: saturate(1);
		}
		50% {
			background: var(--stop-bg-pulse);
			box-shadow: 0 0 0 5px var(--stop-ring);
			filter: saturate(1.28);
		}
	}
</style>

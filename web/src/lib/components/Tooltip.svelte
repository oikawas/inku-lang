<script lang="ts">
	type Props = {
		text: string;
		children: import('svelte').Snippet;
	};

	let { text, children }: Props = $props();
</script>

<span class="tooltip-wrap">
	{@render children()}
	<span class="tooltip-bubble" role="tooltip">{text}</span>
</span>

<style>
	.tooltip-wrap {
		position: relative;
		display: inline-flex;
		align-items: center;
		min-width: 0;
	}
	.tooltip-bubble {
		position: absolute;
		left: 50%;
		bottom: calc(100% + 8px);
		z-index: 900;
		max-width: min(260px, calc(100vw - 32px));
		width: max-content;
		padding: 6px 8px;
		border-radius: var(--r);
		background: var(--tooltip-bg);
		color: white;
		font-size: 11px;
		line-height: 1.45;
		font-weight: 400;
		letter-spacing: 0;
		text-align: left;
		white-space: normal;
		overflow-wrap: anywhere;
		box-shadow: 0 8px 24px rgba(0, 0, 0, 0.22);
		opacity: 0;
		pointer-events: none;
		transform: translate(-50%, 2px);
		transition: opacity 0.12s ease, transform 0.12s ease;
	}
	.tooltip-bubble::after {
		content: "";
		position: absolute;
		left: 50%;
		top: 100%;
		border: 5px solid transparent;
		border-top-color: var(--tooltip-bg);
		transform: translateX(-50%);
	}
	.tooltip-wrap:hover .tooltip-bubble,
	.tooltip-wrap:focus-within .tooltip-bubble {
		opacity: 1;
		transform: translate(-50%, 0);
	}
</style>

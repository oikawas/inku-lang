<script lang="ts">
	type Props = {
		text: string;
		placement?: 'top' | 'bottom' | 'left' | 'right';
		children: import('svelte').Snippet;
	};

	let { text, placement = 'top', children }: Props = $props();
</script>

<span class="tooltip-wrap">
	{@render children()}
	<span class="tooltip-bubble" class:bottom={placement === 'bottom'} class:left={placement === 'left'} class:right={placement === 'right'} role="tooltip">{text}</span>
</span>

<style>
	.tooltip-wrap {
		position: relative;
		display: inline-flex;
		align-items: center;
		min-width: 0;
	}
	.tooltip-wrap:hover,
	.tooltip-wrap:focus-within {
		z-index: 1010;
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

	.tooltip-bubble.bottom {
		bottom: auto;
		top: calc(100% + 8px);
		transform: translate(-50%, -2px);
	}
	.tooltip-bubble.bottom::after {
		top: auto;
		bottom: 100%;
		border-top-color: transparent;
		border-bottom-color: var(--tooltip-bg);
	}

	.tooltip-bubble.left {
		bottom: auto;
		left: auto;
		right: calc(100% + 8px);
		top: 50%;
		transform: translate(-2px, -50%);
	}
	.tooltip-bubble.left::after {
		top: 50%;
		left: 100%;
		bottom: auto;
		border-top-color: transparent;
		border-left-color: var(--tooltip-bg);
		transform: translateY(-50%);
	}

	.tooltip-bubble.right {
		bottom: auto;
		left: calc(100% + 8px);
		top: 50%;
		transform: translate(2px, -50%);
	}
	.tooltip-bubble.right::after {
		top: 50%;
		right: 100%;
		left: auto;
		bottom: auto;
		border-top-color: transparent;
		border-right-color: var(--tooltip-bg);
		transform: translateY(-50%);
	}

	.tooltip-wrap:hover .tooltip-bubble,
	.tooltip-wrap:focus-within .tooltip-bubble {
		opacity: 1;
	}
	.tooltip-wrap:hover .tooltip-bubble:not(.bottom):not(.left):not(.right),
	.tooltip-wrap:focus-within .tooltip-bubble:not(.bottom):not(.left):not(.right) {
		transform: translate(-50%, 0);
	}
	.tooltip-wrap:hover .tooltip-bubble.bottom,
	.tooltip-wrap:focus-within .tooltip-bubble.bottom {
		transform: translate(-50%, 0);
	}
	.tooltip-wrap:hover .tooltip-bubble.left,
	.tooltip-wrap:focus-within .tooltip-bubble.left {
		transform: translate(0, -50%);
	}
	.tooltip-wrap:hover .tooltip-bubble.right,
	.tooltip-wrap:focus-within .tooltip-bubble.right {
		transform: translate(0, -50%);
	}
</style>

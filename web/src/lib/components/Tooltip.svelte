<script lang="ts">
	type Props = {
		text: string;
		placement?: 'top' | 'bottom' | 'left' | 'right' | 'bottom-left' | 'bottom-right' | 'top-left' | 'top-right';
		wide?: boolean;
		disabled?: boolean;
		children: import('svelte').Snippet;
	};

	let { text, placement = 'top', wide = false, disabled = false, children }: Props = $props();
</script>

<span class="tooltip-wrap" class:disabled>
	{@render children()}
	<span
		class="tooltip-bubble"
		class:bottom={placement === 'bottom'}
		class:left={placement === 'left'}
		class:right={placement === 'right'}
		class:bottom-left={placement === 'bottom-left'}
		class:bottom-right={placement === 'bottom-right'}
		class:top-left={placement === 'top-left'}
		class:top-right={placement === 'top-right'}
		class:wide
		role="tooltip"
	>{text}</span>
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
	.tooltip-wrap.disabled {
		z-index: auto;
	}
	.tooltip-bubble {
		position: absolute;
		left: 50%;
		bottom: calc(100% + 8px);
		z-index: 900;
		max-width: min(260px, calc(100vw - 32px));
		width: max-content;
		padding: 6px 8px;
		border: 1px solid var(--tooltip-border);
		border-radius: var(--r);
		background: var(--tooltip-bg);
		color: var(--tooltip-fg);
		font-size: 11px;
		line-height: 1.45;
		font-weight: 400;
		letter-spacing: 0;
		text-align: left;
		white-space: normal;
		overflow-wrap: anywhere;
		box-shadow: var(--tooltip-shadow);
		opacity: 0;
		pointer-events: none;
		transform: translate(-50%, 2px);
		transition: opacity 0.12s ease, transform 0.12s ease;
	}
	.tooltip-bubble.wide {
		max-width: min(440px, calc(100vw - 48px));
		white-space: pre-line;
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

	/* bottom-left placement */
	.tooltip-bubble.bottom-left {
		bottom: auto;
		left: auto;
		right: 0;
		top: calc(100% + 8px);
		transform: translate(0, -2px);
	}
	.tooltip-bubble.bottom-left::after {
		top: auto;
		bottom: 100%;
		left: auto;
		right: 12px;
		border-top-color: transparent;
		border-bottom-color: var(--tooltip-bg);
		transform: none;
	}

	/* bottom-right placement */
	.tooltip-bubble.bottom-right {
		bottom: auto;
		left: 0;
		right: auto;
		top: calc(100% + 8px);
		transform: translate(0, -2px);
	}
	.tooltip-bubble.bottom-right::after {
		top: auto;
		bottom: 100%;
		left: 12px;
		right: auto;
		border-top-color: transparent;
		border-bottom-color: var(--tooltip-bg);
		transform: none;
	}

	/* top-left placement */
	.tooltip-bubble.top-left {
		bottom: calc(100% + 8px);
		left: auto;
		right: 0;
		top: auto;
		transform: translate(0, 2px);
	}
	.tooltip-bubble.top-left::after {
		top: 100%;
		bottom: auto;
		left: auto;
		right: 12px;
		border-bottom-color: transparent;
		border-top-color: var(--tooltip-bg);
		transform: none;
	}

	/* top-right placement */
	.tooltip-bubble.top-right {
		bottom: calc(100% + 8px);
		left: 0;
		right: auto;
		top: auto;
		transform: translate(0, 2px);
	}
	.tooltip-bubble.top-right::after {
		top: 100%;
		bottom: auto;
		left: 12px;
		right: auto;
		border-bottom-color: transparent;
		border-top-color: var(--tooltip-bg);
		transform: none;
	}

	.tooltip-wrap:hover .tooltip-bubble,
	.tooltip-wrap:focus-within .tooltip-bubble {
		opacity: 1;
	}
	.tooltip-wrap.disabled .tooltip-bubble {
		opacity: 0;
		visibility: hidden;
	}
	.tooltip-wrap:hover .tooltip-bubble:not(.bottom):not(.left):not(.right):not(.bottom-left):not(.bottom-right):not(.top-left):not(.top-right),
	.tooltip-wrap:focus-within .tooltip-bubble:not(.bottom):not(.left):not(.right):not(.bottom-left):not(.bottom-right):not(.top-left):not(.top-right) {
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
	.tooltip-wrap:hover .tooltip-bubble.bottom-left,
	.tooltip-wrap:focus-within .tooltip-bubble.bottom-left,
	.tooltip-wrap:hover .tooltip-bubble.bottom-right,
	.tooltip-wrap:focus-within .tooltip-bubble.bottom-right,
	.tooltip-wrap:hover .tooltip-bubble.top-left,
	.tooltip-wrap:focus-within .tooltip-bubble.top-left,
	.tooltip-wrap:hover .tooltip-bubble.top-right,
	.tooltip-wrap:focus-within .tooltip-bubble.top-right {
		transform: translate(0, 0);
	}
</style>

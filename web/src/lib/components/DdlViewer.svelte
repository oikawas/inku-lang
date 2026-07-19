<script lang="ts">
	import { highlightDDL } from '$lib/highlight';

	type Props = {
		ddl: string;
		label: string;
		saijikiLabel: string;
		onToggleSaijiki: () => void;
	};

	let { ddl, label, saijikiLabel, onToggleSaijiki }: Props = $props();
	const highlighted = $derived(highlightDDL(ddl));
</script>

<div class="ddl-viewer">
	<div class="ddl-viewer-head">
		<span class="ddl-viewer-label">{label}</span>
		<button class="ddl-viewer-btn" type="button" onclick={onToggleSaijiki}>{saijikiLabel}</button>
	</div>
	<div class="ddl-viewer-body ddl-highlight">{@html highlighted}</div>
</div>

<style>
	.ddl-viewer {
		display: flex;
		flex-direction: column;
		gap: 8px;
		min-width: 0;
	}
	.ddl-viewer-head {
		display: flex;
		align-items: center;
		gap: 8px;
	}
	.ddl-viewer-label {
		margin-right: auto;
		font-size: 12px;
		font-weight: 600;
		letter-spacing: 0.04em;
		color: var(--fg2);
	}
	.ddl-viewer-btn {
		padding: 4px 10px;
		border: 1px solid var(--border2);
		border-radius: var(--r);
		background: var(--panel);
		color: var(--fg2);
		font-size: 11px;
		cursor: pointer;
		font-family: inherit;
	}
	.ddl-viewer-btn:hover {
		background: var(--bg2);
	}
	.ddl-viewer-body {
		padding: 2px 0 2px 12px;
		border-left: 2px solid var(--border2);
		background: transparent;
		color: var(--fg);
		font-family: inherit;
		font-size: 13px;
		line-height: 1.78;
		white-space: pre-wrap;
		word-break: break-word;
		tab-size: 4;
		overflow-x: auto;
	}
	.ddl-highlight :global(.ddl-token) {
		border-radius: 2px;
		font-weight: inherit;
	}
	.ddl-highlight :global(.ddl-token-shape) { color: #2c5fb8; background: rgba(44, 95, 184, 0.08); }
	.ddl-highlight :global(.ddl-token-touch) { color: #7a5b2f; background: rgba(122, 91, 47, 0.10); }
	.ddl-highlight :global(.ddl-token-line) { color: #53606b; background: rgba(83, 96, 107, 0.10); }
	.ddl-highlight :global(.ddl-token-color) { color: #b12a6b; background: rgba(177, 42, 107, 0.09); }
	.ddl-highlight :global(.ddl-token-motion) { color: #197a74; background: rgba(25, 122, 116, 0.10); }
	.ddl-highlight :global(.ddl-token-place) { color: #6b4cb3; background: rgba(107, 76, 179, 0.09); }
	.ddl-highlight :global(.ddl-token-action) { color: #9a4a1d; background: rgba(154, 74, 29, 0.10); }
	.ddl-highlight :global(.ddl-token-angle) { color: #3d6f2c; background: rgba(61, 111, 44, 0.10); }
	.ddl-highlight :global(.ddl-token-ratio) { color: #9a3d3d; background: rgba(154, 61, 61, 0.09); }
	.ddl-highlight :global(.ddl-token-plugin) { color: #9f4b3b; background: rgba(185, 88, 69, 0.10); }
	.ddl-highlight :global(.ddl-token-word) { color: #2c3e91; background: rgba(44, 62, 145, 0.08); }
	.ddl-highlight :global(.ddl-token-emotion) { color: #9b7a66; font-style: inherit; }
	:global(html[data-theme='dark']) .ddl-highlight :global(.ddl-token-shape) { color: #9cc4ff; background: rgba(92, 143, 220, 0.26); }
	:global(html[data-theme='dark']) .ddl-highlight :global(.ddl-token-touch) { color: #e2bf82; background: rgba(188, 139, 62, 0.24); }
	:global(html[data-theme='dark']) .ddl-highlight :global(.ddl-token-line) { color: #c4ccd5; background: rgba(147, 160, 176, 0.22); }
	:global(html[data-theme='dark']) .ddl-highlight :global(.ddl-token-color) { color: #ff91c7; background: rgba(215, 80, 149, 0.24); }
	:global(html[data-theme='dark']) .ddl-highlight :global(.ddl-token-motion) { color: #7ce1d4; background: rgba(50, 157, 147, 0.24); }
	:global(html[data-theme='dark']) .ddl-highlight :global(.ddl-token-place) { color: #c2a9ff; background: rgba(133, 99, 214, 0.26); }
	:global(html[data-theme='dark']) .ddl-highlight :global(.ddl-token-action) { color: #f0aa73; background: rgba(197, 105, 45, 0.24); }
	:global(html[data-theme='dark']) .ddl-highlight :global(.ddl-token-angle) { color: #a7d88e; background: rgba(89, 142, 65, 0.25); }
	:global(html[data-theme='dark']) .ddl-highlight :global(.ddl-token-ratio) { color: #f0a0a0; background: rgba(196, 78, 78, 0.24); }
	:global(html[data-theme='dark']) .ddl-highlight :global(.ddl-token-word) { color: #b8c7ff; background: rgba(92, 111, 205, 0.26); }
	:global(html[data-theme='dark']) .ddl-highlight :global(.ddl-token-emotion) { color: #d8b8a6; }
</style>

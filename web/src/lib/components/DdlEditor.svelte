<script lang="ts">
	import { t } from '$lib/i18n/index.svelte';

	type Props = {
		ddl: string;
		ddlHighlighted: string;
		ddlTextareaEl: HTMLTextAreaElement | null;
		ddlHighlightEl: HTMLDivElement | null;
		ddlFocused: boolean;
		reloading: boolean;
		reloadError: string | null;
		loading: boolean;
		showBirds: boolean;
		onToggleSaijiki: () => void;
		onRememberSelection: () => void;
		onSyncHighlightScroll: () => void;
		onReplay: () => void | Promise<void>;
	};

	let {
		ddl = $bindable(''),
		ddlHighlighted,
		ddlTextareaEl = $bindable(null),
		ddlHighlightEl = $bindable(null),
		ddlFocused = $bindable(false),
		reloading,
		reloadError,
		loading,
		showBirds,
		onToggleSaijiki,
		onRememberSelection,
		onSyncHighlightScroll,
		onReplay,
	}: Props = $props();
</script>

<section class="panel-section">
	<div class="section-head">
		<span class="section-label">{t().ddlLabel}</span>
		<div class="section-actions">
			<button class="ghost-btn" onclick={onToggleSaijiki}>{t().saijikiToggleBtn}</button>
		</div>
	</div>
	<div class="ddl-highlight-wrap">
		<div class="ddl-highlight" bind:this={ddlHighlightEl} aria-hidden="true">{@html ddlHighlighted}</div>
		<textarea
			class="ddl-edit-ta"
			bind:this={ddlTextareaEl}
			bind:value={ddl}
			rows="4"
			spellcheck="false"
			onclick={onRememberSelection}
			onfocus={() => { ddlFocused = true; onRememberSelection(); }}
			onblur={() => { onRememberSelection(); ddlFocused = false; }}
			oninput={() => { onRememberSelection(); onSyncHighlightScroll(); }}
			onkeyup={onRememberSelection}
			onmouseup={onRememberSelection}
			onselect={onRememberSelection}
			onscroll={onSyncHighlightScroll}
		></textarea>
	</div>

	{#if reloading}
		<div class="progress-wrap">
			<div class="progress-phases">
				<span class="phase-item phase-active"><span class="phase-dot"></span>{t().statsStruct}</span>
			</div>
			<div class="progress-right">
				<span class="progress-time">…</span>
			</div>
		</div>
		<div class="progress-bar-track" style="--progress-target: 55%">
			<div class="progress-bar-fill"></div>
			{#if showBirds}
				<svg class="progress-bird" viewBox="0 0 52 44" aria-hidden="true">
					<g class="bird-peck">
						<ellipse class="bird-shadow" cx="26" cy="38" rx="12" ry="2.4" />
						<g class="bird-preen">
							<g class="bird-view bird-view-side">
								<path class="bird-tail" d="M33 25 Q43 24 47 19 Q44 29 34 30 Z" />
								<ellipse class="bird-body" cx="27" cy="25" rx="11" ry="8" />
								<path class="bird-wing" d="M24 23 Q31 15 37 24 Q31 30 25 29 Z" />
								<g class="bird-head">
									<circle class="bird-head-fill" cx="17" cy="19" r="5.8" />
									<path class="bird-beak" d="M11.5 19 L5 16.9 L5 21.1 Z" />
									<circle class="bird-eye" cx="15.4" cy="17.5" r="0.95" />
								</g>
							</g>
							<g class="bird-view bird-view-front">
								<ellipse class="bird-body" cx="26" cy="25.5" rx="9.2" ry="8.8" />
								<circle class="bird-head-fill" cx="26" cy="17" r="6.4" />
								<path class="bird-wing bird-wing-left" d="M18 24 Q13 25 11 30 Q18 31 22 27 Z" />
								<path class="bird-wing bird-wing-right" d="M34 24 Q39 25 41 30 Q34 31 30 27 Z" />
								<path class="bird-beak" d="M23 18.7 L26 22.4 L29 18.7 Z" />
								<circle class="bird-eye" cx="23.4" cy="16.3" r="0.9" />
								<circle class="bird-eye" cx="28.6" cy="16.3" r="0.9" />
							</g>
							<g class="bird-view bird-view-three">
								<path class="bird-tail" d="M33 25 Q41 23 44 18 Q43 27 35 30 Z" />
								<ellipse class="bird-body" cx="27" cy="25" rx="10" ry="8.5" />
								<path class="bird-wing" d="M24 23 Q30 17 36 24 Q31 29 25 29 Z" />
								<circle class="bird-head-fill" cx="20" cy="18" r="6.1" />
								<path class="bird-beak" d="M16 19 L9.8 17.2 L10.8 21.2 Z" />
								<circle class="bird-eye" cx="18.3" cy="16.5" r="0.95" />
							</g>
							<g class="bird-legs">
								<path class="bird-leg bird-leg-a" d="M22 32 L20 37" />
								<path class="bird-leg bird-leg-b" d="M30 32 L32 37" />
							</g>
						</g>
					</g>
				</svg>
			{/if}
		</div>
	{/if}
	{#if reloadError}<p class="error-text">{reloadError}</p>{/if}

	<button
		class="replay-btn"
		onclick={onReplay}
		disabled={reloading || !ddl || loading}
	>{t().replayFromDdlButton}</button>
</section>

<style>
	.panel-section { display: flex; flex-direction: column; gap: 6px; }
	.section-head {
		display: flex;
		justify-content: space-between;
		align-items: center;
	}
	.section-label {
		font-size: 10px; font-weight: 500; letter-spacing: 0.08em;
		color: var(--fg3); text-transform: uppercase;
	}
	.section-actions { display: flex; gap: 5px; }
	.ghost-btn {
		padding: 4px 10px;
		border: 1px solid var(--border2);
		border-radius: var(--r);
		background: #fff;
		color: var(--fg2);
		font-size: 11px;
		cursor: pointer;
		font-family: inherit;
	}
	.ghost-btn:hover { background: var(--bg2); }
	.ddl-highlight-wrap {
		position: relative;
		width: 100%;
		border: 1px solid var(--accent); border-left: 3px solid var(--border2);
		border-radius: 0 var(--r) var(--r) 0;
		background: #fff;
		overflow: hidden;
	}
	.ddl-highlight,
	.ddl-edit-ta {
		width: 100%; padding: 9px 10px;
		box-sizing: border-box;
		margin: 0;
		font-family: inherit; font-size: 13px; font-weight: 400; font-style: normal; letter-spacing: 0;
		line-height: 1.75; resize: vertical; outline: none;
		white-space: pre-wrap; word-break: break-word;
		tab-size: 4;
		scrollbar-gutter: stable;
	}
	.ddl-highlight {
		position: absolute;
		inset: 0;
		z-index: 0;
		overflow: auto;
		color: var(--fg);
		pointer-events: none;
		scrollbar-width: none;
	}
	.ddl-highlight::-webkit-scrollbar { display: none; }
	.ddl-edit-ta {
		position: relative;
		z-index: 1;
		border: none;
		background: transparent;
		color: transparent;
		caret-color: transparent;
		overflow: auto;
	}
	.ddl-edit-ta::selection { background: rgba(44, 62, 145, 0.22); }
	.ddl-highlight :global(.ddl-token) {
		border-radius: 2px;
		font-weight: inherit;
	}
	.ddl-highlight :global(.ddl-custom-caret) {
		position: relative;
		display: inline-block;
		width: 0;
		height: 1em;
		vertical-align: text-bottom;
	}
	.ddl-highlight :global(.ddl-custom-caret)::after {
		content: '';
		position: absolute;
		left: 0;
		top: -0.18em;
		width: 3px;
		height: 1.45em;
		border-radius: 2px;
		background: var(--fg);
		animation: ddl-caret-blink 1s steps(2, start) infinite;
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
	.ddl-highlight :global(.ddl-token-word) { color: #2c3e91; background: rgba(44, 62, 145, 0.08); }
	.ddl-highlight :global(.ddl-token-emotion) {
		color: #9b7a66;
		font-style: inherit;
	}
	.progress-wrap {
		display: flex; align-items: center; justify-content: space-between;
		padding: 8px 10px 6px;
		border: 1px solid var(--border2); border-radius: var(--r) var(--r) 0 0;
		background: #fff;
		margin-top: 8px;
	}
	.progress-phases { display: flex; align-items: center; gap: 4px; }
	.phase-item { font-size: 11px; color: var(--border2); display: flex; align-items: center; gap: 3px; }
	.phase-item.phase-active { color: var(--fg); font-weight: 500; }
	.phase-dot {
		display: inline-block; width: 6px; height: 6px; border-radius: 50%;
		background: var(--accent); flex-shrink: 0;
		animation: inkupulse 1s ease-in-out infinite;
	}
	.progress-right { display: flex; align-items: center; gap: 7px; }
	.progress-time { font-size: 11px; color: var(--fg3); font-variant-numeric: tabular-nums; }
	.progress-bar-track {
		position: relative;
		height: 32px; background: transparent;
		border-left: 1px solid var(--border2); border-right: 1px solid var(--border2);
		overflow: visible;
	}
	.progress-bar-track::before {
		content: "";
		position: absolute; top: 18px; left: 0; right: 0; height: 3px;
		background: var(--bg3);
	}
	.progress-bar-fill {
		position: absolute; top: 18px; left: 0; height: 3px;
		width: var(--progress-target, 50%);
		background: var(--accent); transition: width 0.3s ease;
	}
	.progress-bird {
		position: absolute;
		left: calc(var(--progress-target, 50%) - 26px);
		bottom: 8px;
		width: 52px;
		height: 44px;
		pointer-events: none;
		overflow: visible;
		filter: drop-shadow(0 2px 3px rgba(107, 123, 42, 0.18));
		animation: birdWalk 12s ease-in-out infinite;
	}
	.bird-peck { transform-origin: 22px 35px; animation: birdPeck 7.8s ease-in-out infinite; }
	.bird-preen { transform-origin: 28px 26px; animation: birdPreen 11.5s ease-in-out infinite; }
	.bird-shadow { fill: rgba(60, 55, 39, 0.18); }
	.bird-body, .bird-head-fill { fill: #7f8f35; }
	.bird-tail { fill: #536523; }
	.bird-view-side { transform-origin: 26px 25px; animation: birdSideView 12s ease-in-out infinite; }
	.bird-view-front { opacity: 0; transform-origin: 26px 25px; animation: birdFrontView 12s ease-in-out infinite; }
	.bird-view-three { opacity: 0; transform-origin: 26px 25px; animation: birdThreeQuarterView 12s ease-in-out infinite; }
	.bird-wing { fill: #a7b45a; transform-origin: 28px 25px; animation: birdWing 5.6s ease-in-out infinite; }
	.bird-wing-left, .bird-wing-right { animation: none; }
	.bird-head { transform-origin: 21px 25px; animation: birdHead 7.8s ease-in-out infinite; }
	.bird-beak { fill: #bd8f34; }
	.bird-eye { fill: #1f2114; }
	.bird-leg {
		fill: none;
		stroke: #7a5a18;
		stroke-width: 1.5;
		stroke-linecap: round;
		transform-origin: 26px 33px;
	}
	.bird-leg-a { animation: birdStepA 1.25s ease-in-out infinite; }
	.bird-leg-b { animation: birdStepB 1.25s ease-in-out infinite; }
	.error-text { color: #a2342a; font-size: 12px; }
	.replay-btn {
		width: 100%; margin-top: 6px; padding: 10px;
		font-size: 14px; font-weight: 500; background: #e8f1fb; color: #234c78;
		border: 1px solid #9fb9d6; border-radius: var(--r);
		letter-spacing: 0.08em; cursor: pointer;
		display: flex; align-items: center; justify-content: center; gap: 6px;
		font-family: inherit; transition: background 0.15s, border-color 0.15s, color 0.15s;
	}
	.replay-btn:hover:not(:disabled) { background: #d7e8f8; border-color: #6f98c3; color: #173f68; }
	.replay-btn:disabled { background: var(--bg2); border-color: var(--border2); color: var(--fg3); cursor: not-allowed; }
	@keyframes ddl-caret-blink {
		50% { opacity: 0; }
	}
	@keyframes inkupulse {
		0%, 100% { opacity: 1; transform: scale(1); }
		50% { opacity: 0.4; transform: scale(0.7); }
	}
	@keyframes birdWalk {
		0% { transform: translate(-28px, 0) scaleX(1); }
		9% { transform: translate(-14px, -1px) scaleX(1); }
		18% { transform: translate(-14px, 0) scaleX(1); }
		28% { transform: translate(12px, -1px) scaleX(1); }
		36% { transform: translate(12px, 0) scaleX(1); }
		44% { transform: translate(5px, 0) scaleX(1); }
		48% { transform: translate(2px, 0) scaleX(1); }
		52% { transform: translate(0, 0) scaleX(-1); }
		62% { transform: translate(-18px, -1px) scaleX(-1); }
		72% { transform: translate(-18px, 0) scaleX(-1); }
		82% { transform: translate(10px, -1px) scaleX(-1); }
		90% { transform: translate(10px, 0) scaleX(-1); }
		96% { transform: translate(-6px, 0) scaleX(-1); }
		100% { transform: translate(-28px, 0) scaleX(1); }
	}
	@keyframes birdSideView {
		0%, 40%, 56%, 94%, 100% { opacity: 1; transform: scaleX(1); }
		46%, 50%, 98% { opacity: 0; transform: scaleX(0.72); }
	}
	@keyframes birdFrontView {
		0%, 42%, 56%, 96%, 100% { opacity: 0; transform: scaleX(0.86); }
		47%, 50%, 53%, 98% { opacity: 1; transform: scaleX(1); }
	}
	@keyframes birdThreeQuarterView {
		0%, 39%, 57%, 93%, 100% { opacity: 0; transform: rotate(0deg); }
		43%, 55%, 95%, 99% { opacity: 0.92; transform: rotate(3deg); }
	}
	@keyframes birdWing {
		0%, 18%, 38%, 55%, 72%, 100% { transform: rotate(0deg) scaleY(1); }
		22%, 24%, 26% { transform: rotate(-28deg) scaleY(0.75); }
		29% { transform: rotate(8deg) scaleY(1.08); }
		78%, 80% { transform: rotate(-18deg) scaleY(0.82); }
		82% { transform: rotate(6deg) scaleY(1.06); }
	}
	@keyframes birdPeck {
		0%, 42%, 58%, 100% { transform: rotate(0deg) translateY(0); }
		46%, 50%, 54% { transform: rotate(-16deg) translateY(5px); }
		48%, 52%, 56% { transform: rotate(5deg) translateY(0); }
	}
	@keyframes birdPreen {
		0%, 62%, 78%, 100% { transform: rotate(0deg); }
		66%, 70%, 74% { transform: rotate(9deg) translateX(1px); }
		68%, 72% { transform: rotate(-5deg) translateX(-1px); }
	}
	@keyframes birdHead {
		0%, 42%, 58%, 62%, 100% { transform: rotate(0deg); }
		46%, 50%, 54% { transform: rotate(-22deg) translate(-1px, 4px); }
		66%, 70%, 74% { transform: rotate(18deg) translate(5px, 2px); }
	}
	@keyframes birdStepA {
		0%, 100% { transform: rotate(0deg); }
		45% { transform: rotate(14deg) translateX(1px); }
	}
	@keyframes birdStepB {
		0%, 100% { transform: rotate(0deg); }
		45% { transform: rotate(-14deg) translateX(-1px); }
	}
</style>

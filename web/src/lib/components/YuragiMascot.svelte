<!--
	Yuragi, the crab mascot. A 5x5 pixel crab that steps sideways, waves each claw
	on its own period, blinks and winks, and now and then blows a round of bubbles.
	Ported from no-git-sync/mascot/crab/crab07.html. Like IncuMascot the pixels use
	the inku standard palette and are identical in light and dark mode, so the
	component is theme-independent and sits on a transparent box. The one departure
	from the reference: the bubbles are grey rather than white, because white ones
	are invisible on light paper.
-->
<div class="yuragi-mascot-box" aria-hidden="true">
	<div class="mascot-wrapper">
		<div class="yuragi-mascot">
			<!-- Bubbles, blown in one grand round -->
			<div class="bubble" style="--tx: -25px; --s: 1.2; --delay: 0.0s;"></div>
			<div class="bubble" style="--tx:  15px; --s: 0.8; --delay: 0.2s;"></div>
			<div class="bubble" style="--tx: -10px; --s: 1.5; --delay: 0.4s;"></div>
			<div class="bubble" style="--tx:  30px; --s: 1.0; --delay: 0.6s;"></div>
			<div class="bubble" style="--tx:  -5px; --s: 1.8; --delay: 0.8s;"></div>
			<div class="bubble" style="--tx:  20px; --s: 0.7; --delay: 1.0s;"></div>
			<div class="bubble" style="--tx: -35px; --s: 1.1; --delay: 1.2s;"></div>
			<div class="bubble" style="--tx:  10px; --s: 1.4; --delay: 1.4s;"></div>

			<!-- Row 1: claws, each waving on its own period -->
			<div class="pixel red claw-left"></div>
			<div class="pixel"></div>
			<div class="pixel"></div>
			<div class="pixel"></div>
			<div class="pixel red claw-right"></div>

			<!-- Row 2: arms and eyes (the right eye also winks) -->
			<div class="pixel red"></div>
			<div class="pixel eye eye-left"></div>
			<div class="pixel red"></div>
			<div class="pixel eye eye-right"></div>
			<div class="pixel red"></div>

			<!-- Row 3: body, the centre pixel incubating -->
			<div class="pixel red leg" style="--delay: 0s;"></div>
			<div class="pixel red"></div>
			<div class="pixel red incubator"></div>
			<div class="pixel red"></div>
			<div class="pixel red leg" style="--delay: 0.3s;"></div>

			<!-- Row 4: lower legs -->
			<div class="pixel red leg" style="--delay: 0.1s;"></div>
			<div class="pixel"></div>
			<div class="pixel red leg" style="--delay: 0.2s;"></div>
			<div class="pixel"></div>
			<div class="pixel red leg" style="--delay: 0.4s;"></div>

			<!-- Row 5: empty -->
			<div class="pixel"></div>
			<div class="pixel"></div>
			<div class="pixel"></div>
			<div class="pixel"></div>
			<div class="pixel"></div>
		</div>
	</div>
</div>

<style>
	.yuragi-mascot-box {
		/* inku standard palette (render_color_map) */
		--inku-white: #ffffff;
		--inku-black: #111111;
		--inku-red: #a2342a;
		--inku-gray: #888888;
		--inku-ink-shade: #555555;
		position: relative;
		width: 32px;
		height: 32px;
		flex: 0 0 auto;
	}
	/*
		Same discipline as IncuMascot: the 92px grid is scaled to 33% (~30px) and
		transform: scale() does not shrink the layout box, so the wrapper is taken
		out of flow and centred while the box stays a real 32px.
	*/
	.mascot-wrapper {
		position: absolute;
		top: 50%;
		left: 50%;
		transform: translate(-50%, -50%) scale(0.33);
		width: 92px;
		height: 92px;
		display: flex;
		justify-content: center;
		align-items: center;
	}
	.yuragi-mascot {
		display: grid;
		grid-template-columns: repeat(5, 16px);
		grid-template-rows: repeat(5, 16px);
		gap: 3px;
		position: relative;
		animation: crab-step 1.5s infinite ease-in-out;
	}
	@keyframes crab-step {
		0%, 100% { transform: translateX(-4px) rotate(-3deg); }
		50% { transform: translateX(4px) rotate(3deg); }
	}
	.pixel {
		width: 16px;
		height: 16px;
		background-color: transparent;
		transform-origin: center;
	}
	.red { background-color: var(--inku-red); }
	.eye { background-color: var(--inku-white); }

	/* The left claw greets every 11s, the right one every 8s. */
	@keyframes claw-greet-left {
		0%, 85%, 100% { transform: scale(1) rotate(0deg); border-radius: 0; }
		87% { transform: scale(1.3) rotate(-45deg) translateY(-4px); border-radius: 50%; }
		89% { transform: scale(1.3) rotate(15deg) translateY(-4px); border-radius: 50%; }
		91% { transform: scale(1.3) rotate(-45deg) translateY(-4px); border-radius: 50%; }
		93% { transform: scale(1.3) rotate(15deg) translateY(-4px); border-radius: 50%; }
		95% { transform: scale(1) rotate(0deg); border-radius: 0; }
	}
	.claw-left {
		transform-origin: bottom right;
		animation: claw-greet-left 11s infinite ease-in-out;
	}
	@keyframes claw-greet-right {
		0%, 80%, 100% { transform: scale(1) rotate(0deg); border-radius: 0; }
		82% { transform: scale(1.3) rotate(45deg) translateY(-4px); border-radius: 50%; }
		84% { transform: scale(1.3) rotate(-15deg) translateY(-4px); border-radius: 50%; }
		86% { transform: scale(1.3) rotate(45deg) translateY(-4px); border-radius: 50%; }
		88% { transform: scale(1.3) rotate(-15deg) translateY(-4px); border-radius: 50%; }
		90% { transform: scale(1.3) rotate(45deg) translateY(-4px); border-radius: 50%; }
		92% { transform: scale(1) rotate(0deg); border-radius: 0; }
	}
	.claw-right {
		transform-origin: bottom left;
		animation: claw-greet-right 8s infinite ease-in-out;
	}
	@keyframes leg-tremble {
		0%, 100% { transform: translateY(0); }
		50% { transform: translateY(-3px); }
	}
	.leg {
		animation: leg-tremble 0.6s infinite ease-in-out;
		animation-delay: var(--delay, 0s);
	}
	@keyframes incubate-red {
		0%, 100% { background-color: var(--inku-red); }
		50% { background-color: var(--inku-ink-shade); }
	}
	.incubator {
		animation: incubate-red 4s infinite step-end;
	}
	@keyframes eye-blink-left {
		0%, 94%, 100% { background-color: var(--inku-white); }
		96%, 98% { background-color: var(--inku-black); }
	}
	@keyframes eye-blink-right {
		0%, 64%, 70%, 94%, 100% { background-color: var(--inku-white); }
		66%, 68% { background-color: var(--inku-black); } /* the wink */
		96%, 98% { background-color: var(--inku-black); } /* blinks with the left eye */
	}
	.eye-left { animation: eye-blink-left 7s infinite; }
	.eye-right { animation: eye-blink-right 7s infinite; }

	.bubble {
		position: absolute;
		top: 34px;
		left: calc(50% - 8px);
		width: 16px;
		height: 16px;
		background-color: var(--inku-gray);
		opacity: 0;
		pointer-events: none;
		animation: blow-grand-bubble 12s infinite ease-in;
		animation-delay: var(--delay, 0s);
	}
	@keyframes blow-grand-bubble {
		0%, 85%, 100% {
			transform: translate(0, 0) scale(0.2);
			border-radius: 0;
			opacity: 0;
		}
		87% {
			transform: translate(calc(var(--tx) * 0.2), -5px) scale(0.4);
			border-radius: 20%;
			opacity: 0.9;
		}
		92% {
			transform: translate(calc(var(--tx) * 0.7), -30px) scale(var(--s));
			border-radius: 50%;
			opacity: 0.6;
		}
		98% {
			transform: translate(var(--tx), -90px) scale(calc(var(--s) * 1.5));
			border-radius: 50%;
			opacity: 0;
		}
	}
	@media (prefers-reduced-motion: reduce) {
		.yuragi-mascot,
		.claw-left,
		.claw-right,
		.leg,
		.incubator,
		.eye-left,
		.eye-right { animation: none; }
		.bubble { animation: none; opacity: 0; }
	}
</style>

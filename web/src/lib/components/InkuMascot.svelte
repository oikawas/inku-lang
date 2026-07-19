<!--
	inku-lang cube mascot. A 5x5 pixel "cube" that orbits (mascot-spin) while each
	pixel does a vortex-breathe, with a few incubator pixels blinking between inku
	palette colours. Ported from no-git-sync/mascot/gemini15/18.html. The pixel
	colours are identical in light and dark mode (only the page paper differs in the
	reference), so this component is theme-independent and sits on a transparent box.
-->
<div class="inku-mascot-box" aria-hidden="true">
	<div class="mascot-wrapper">
		<div class="inku-mascot">
			<!-- Row 1 -->
			<div class="pixel empty" style="--x: -2; --y: -2; --delay:  0.0s;"></div>
			<div class="pixel empty" style="--x: -1; --y: -2; --delay: -0.2s;"></div>
			<div class="pixel top"   style="--x:  0; --y: -2; --delay: -0.4s;"></div>
			<div class="pixel empty" style="--x:  1; --y: -2; --delay: -0.2s;"></div>
			<div class="pixel empty" style="--x:  2; --y: -2; --delay:  0.0s;"></div>

			<!-- Row 2 -->
			<div class="pixel empty" style="--x: -2; --y: -1; --delay: -0.2s;"></div>
			<div class="pixel top"   style="--x: -1; --y: -1; --delay: -0.4s;"></div>
			<div class="pixel top incubator" style="--x: 0; --y: -1; --delay: -0.6s;"></div>
			<div class="pixel top"   style="--x:  1; --y: -1; --delay: -0.4s;"></div>
			<div class="pixel empty" style="--x:  2; --y: -1; --delay: -0.2s;"></div>

			<!-- Row 3 (center) -->
			<div class="pixel left"  style="--x: -2; --y:  0; --delay: -0.4s;"></div>
			<div class="pixel left"  style="--x: -1; --y:  0; --delay: -0.6s;"></div>
			<div class="pixel top"   style="--x:  0; --y:  0; --delay: -0.8s;"></div>
			<div class="pixel right" style="--x:  1; --y:  0; --delay: -0.6s;"></div>
			<div class="pixel right" style="--x:  2; --y:  0; --delay: -0.4s;"></div>

			<!-- Row 4 -->
			<div class="pixel empty"           style="--x: -2; --y:  1; --delay: -0.2s;"></div>
			<div class="pixel left"            style="--x: -1; --y:  1; --delay: -0.4s;"></div>
			<div class="pixel left incubator"  style="--x:  0; --y:  1; --delay: -0.6s;"></div>
			<div class="pixel right incubator" style="--x:  1; --y:  1; --delay: -0.4s;"></div>
			<div class="pixel right"           style="--x:  2; --y:  1; --delay: -0.2s;"></div>

			<!-- Row 5 -->
			<div class="pixel empty" style="--x: -2; --y:  2; --delay:  0.0s;"></div>
			<div class="pixel empty" style="--x: -1; --y:  2; --delay: -0.2s;"></div>
			<div class="pixel left"  style="--x:  0; --y:  2; --delay: -0.4s;"></div>
			<div class="pixel right" style="--x:  1; --y:  2; --delay: -0.2s;"></div>
			<div class="pixel empty" style="--x:  2; --y:  2; --delay:  0.0s;"></div>
		</div>
	</div>
</div>

<style>
	.inku-mascot-box {
		/* inku standard palette (render_color_map) */
		--inku-black: #111111;
		--inku-blue: #2c3e91;
		--inku-red: #a2342a;
		--inku-green: #2f6b3a;
		--inku-gray: #888888;
		--inku-ink-shade: #555555;
		position: relative;
		width: 32px;
		height: 32px;
		flex: 0 0 auto;
	}
	/*
		The 92px cube is scaled to 33% (~30px). transform: scale() does NOT shrink
		the layout box, so the wrapper is taken out of flow (absolute) and centered;
		the box itself stays a real 32px so it never leaks into the surrounding row.
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
	.inku-mascot {
		display: grid;
		grid-template-columns: repeat(5, 16px);
		grid-template-rows: repeat(5, 16px);
		gap: 3px;
		animation: mascot-spin 15s infinite linear;
	}
	@keyframes mascot-spin {
		0% { transform: rotate(0deg); }
		100% { transform: rotate(360deg); }
	}
	.pixel {
		width: 16px;
		height: 16px;
		background-color: transparent;
		transform-origin: calc(50% + var(--x) * -19px) calc(50% + var(--y) * -19px);
		animation: vortex-breathe 4s infinite;
		animation-delay: var(--delay, 0s);
	}
	.top { background-color: var(--inku-gray); }
	.left { background-color: var(--inku-black); }
	.right { background-color: var(--inku-blue); }
	@keyframes vortex-breathe {
		0%, 10% {
			transform: rotate(0deg) scale(1);
			border-radius: 0;
			animation-timing-function: cubic-bezier(0.7, 0, 1, 0.5);
		}
		40% {
			transform: rotate(180deg) scale(0.33);
			border-radius: 50%;
			animation-timing-function: linear;
		}
		60% {
			transform: rotate(180deg) scale(0.33);
			border-radius: 50%;
			animation-timing-function: cubic-bezier(0, 0.5, 0.3, 1);
		}
		90%, 100% {
			transform: rotate(360deg) scale(1);
			border-radius: 0;
		}
	}
	@keyframes incubate-left {
		0%, 100% { background-color: var(--inku-black); }
		50% { background-color: var(--inku-red); }
	}
	@keyframes incubate-right {
		0%, 100% { background-color: var(--inku-blue); }
		50% { background-color: var(--inku-green); }
	}
	@keyframes incubate-top {
		0%, 100% { background-color: var(--inku-gray); }
		50% { background-color: var(--inku-ink-shade); }
	}
	.pixel.left.incubator {
		animation: vortex-breathe 4s infinite, incubate-left 5s infinite step-end;
		animation-delay: var(--delay, 0s), 0s;
	}
	.pixel.right.incubator {
		animation: vortex-breathe 4s infinite, incubate-right 7s infinite step-end;
		animation-delay: var(--delay, 0s), 0s;
	}
	.pixel.top.incubator {
		animation: vortex-breathe 4s infinite, incubate-top 6s infinite step-end;
		animation-delay: var(--delay, 0s), 0s;
	}
	@media (prefers-reduced-motion: reduce) {
		.inku-mascot { animation: none; }
		.pixel, .pixel.left.incubator, .pixel.right.incubator, .pixel.top.incubator { animation: none; }
	}
</style>

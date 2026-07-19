<!--
	Crab mascot (batch runs). Temporarily not rendered — the cube InkuMascot
	replaces it for now. Preserved here as a self-contained component (parallel to
	KiwiMascot) so it can be re-enabled later. Extracted verbatim from BatchPanel.
-->
<svg class="batch-crab" viewBox="0 0 74 42" aria-hidden="true">
	<defs>
		<clipPath id="crab-visible-clip">
			<rect x="0" y="0" width="74" height="80">
				<animate
					attributeName="height"
					dur="12.5s"
					repeatCount="indefinite"
					values="80;80;35;35;80;80"
					keyTimes="0;0.56;0.62;0.76;0.84;1"
				/>
			</rect>
		</clipPath>
	</defs>
	<g class="crab-walk">
		<g class="crab-water crab-water-back">
			<ellipse cx="37" cy="35" rx="21" ry="3.8" />
			<path d="M15 35 Q21 32.5 27 35 T39 35 T51 35 T63 35" />
		</g>
		<g class="crab-bow">
			<g class="crab-bury" clip-path="url(#crab-visible-clip)">
				<path class="crab-leg leg-a" d="M23 28 L14 34 M28 29 L22 37 M46 29 L52 37 M51 28 L60 34" />
				<ellipse class="crab-body" cx="37" cy="24" rx="18" ry="11" />
				<path class="crab-shell" d="M23 23 Q37 9 51 23" />
				<g class="crab-claw claw-left">
					<path d="M21 23 C10 18 9 10 16 8" />
					<path class="claw-pincer" d="M15 8 C9 4 10 14 16 12 C21 16 22 6 15 8 Z" />
				</g>
				<g class="crab-claw claw-right">
					<path d="M53 23 C64 18 65 10 58 8" />
					<path class="claw-pincer" d="M59 8 C65 4 64 14 58 12 C53 16 52 6 59 8 Z" />
				</g>
				<g class="crab-eyes">
					<path d="M31 15 L29 8 M43 15 L45 8" />
					<circle class="eye-white" cx="29" cy="7" r="3.3" />
					<circle class="eye-white" cx="45" cy="7" r="3.3" />
					<circle class="eye-dot eye-left" cx="29" cy="7" r="1.2" />
					<circle class="eye-dot eye-right" cx="45" cy="7" r="1.2" />
				</g>
				<path class="crab-mouth" d="M33 25 Q37 28 41 25" />
			</g>
		</g>
		<g class="crab-bubbles">
			<circle class="bubble bubble-a" cx="49" cy="32" r="1.7" />
			<circle class="bubble bubble-b" cx="55" cy="31" r="1.2" />
			<circle class="bubble bubble-c" cx="44" cy="33" r="0.9" />
		</g>
		<g class="crab-water crab-water-front">
			<ellipse cx="37" cy="35" rx="23" ry="4.3" />
			<path d="M14 35 Q20 32 26 35 T38 35 T50 35 T62 35" />
		</g>
	</g>
</svg>

<style>
	.batch-crab {
		width: 46px;
		height: 28px;
		flex: 0 0 46px;
		overflow: visible;
	}
	.crab-water {
		opacity: 0;
		transform-origin: 37px 35px;
		animation: crabWater 12.5s ease-in-out infinite;
	}
	.crab-water ellipse {
		fill: rgba(77, 159, 190, 0.23);
	}
	.crab-water path {
		fill: none;
		stroke: rgba(66, 137, 171, 0.82);
		stroke-width: 1.6;
		stroke-linecap: round;
	}
	.crab-water-back {
		opacity: 0;
	}
	.crab-water-front {
		opacity: 0;
		animation-name: crabWaterFront;
	}
	.crab-walk {
		transform-origin: 37px 24px;
		animation: crabWalk 12s ease-in-out infinite;
	}
	.crab-bow {
		transform-origin: 37px 30px;
		animation: crabBow 14s ease-in-out infinite;
	}
	.crab-bury {
		transform-origin: 37px 34px;
		animation: crabBury 12.5s ease-in-out infinite;
	}
	.crab-body {
		fill: #c75b43;
		stroke: #7e2d24;
		stroke-width: 2;
	}
	.crab-shell,
	.crab-mouth {
		fill: none;
		stroke: #7e2d24;
		stroke-width: 1.8;
		stroke-linecap: round;
	}
	.crab-leg,
	.crab-claw path,
	.crab-eyes path {
		fill: none;
		stroke: #7e2d24;
		stroke-width: 2.4;
		stroke-linecap: round;
		stroke-linejoin: round;
	}
	.leg-a { animation: crabLegs 1.25s ease-in-out infinite; transform-origin: 37px 30px; }
	.crab-claw { transform-origin: 37px 24px; }
	.claw-left {
		animation: clawLeft 8s ease-in-out infinite;
		transform-origin: 18px 21px;
	}
	.claw-right {
		animation: clawRight 9s ease-in-out infinite;
		transform-origin: 56px 21px;
	}
	.claw-pincer {
		fill: #e07a52;
		stroke: #7e2d24;
		stroke-width: 1.8;
	}
	.eye-white {
		fill: var(--panel);
		stroke: #7e2d24;
		stroke-width: 1.5;
	}
	.eye-dot {
		fill: #20201f;
		animation: crabEyes 3.6s steps(1, end) infinite;
	}
	.eye-right { animation-delay: 0.12s; }
	.crab-bubbles {
		fill: none;
		stroke: #87bcd0;
		stroke-width: 1.3;
		opacity: 0;
		animation: crabBubbleGroup 12.5s ease-in-out infinite;
	}
	.bubble {
		transform-origin: 49px 35px;
		animation: crabBubble 12.5s ease-in-out infinite;
	}
	.bubble-b { animation-delay: 0.28s; }
	.bubble-c { animation-delay: 0.55s; }
	@keyframes crabWalk {
		0%, 100% { transform: translateX(-8px); }
		18% { transform: translateX(5px); }
		34% { transform: translateX(10px); }
		48% { transform: translateX(4px); }
		66% { transform: translateX(-7px); }
		84% { transform: translateX(-11px); }
	}
	@keyframes crabLegs {
		0%, 100% { transform: translateX(0); }
		50% { transform: translateX(1.6px); }
	}
	@keyframes clawLeft {
		0%, 18%, 46%, 66%, 100% { transform: rotate(0deg); }
		24%, 29% { transform: rotate(-18deg) translateY(-1px); }
		34% { transform: rotate(8deg); }
		52% { transform: rotate(-28deg) translateY(-2px); }
		56% { transform: rotate(14deg) translateY(1px); }
		60% { transform: rotate(-22deg) translateY(-1px); }
	}
	@keyframes clawRight {
		0%, 26%, 52%, 74%, 100% { transform: rotate(0deg); }
		34%, 40% { transform: rotate(20deg) translateY(-1px); }
		46% { transform: rotate(-8deg); }
		58% { transform: rotate(30deg) translateY(-2px); }
		62% { transform: rotate(-12deg) translateY(1px); }
		67% { transform: rotate(24deg) translateY(-1px); }
	}
	@keyframes crabEyes {
		0%, 100% { transform: translateX(0); }
		22% { transform: translateX(-1.3px); }
		44% { transform: translateX(1.3px); }
		68% { transform: translateY(1px); }
	}
	@keyframes crabBury {
		0%, 50%, 100% { transform: translateY(0); opacity: 1; }
		62%, 72% { transform: translateY(36px); opacity: 1; }
		82% { transform: translateY(6px); opacity: 1; }
	}
	@keyframes crabWater {
		0%, 56%, 88%, 100% { transform: scaleX(0.78); opacity: 0; }
		60% { transform: scaleX(1.02); opacity: 0.18; }
		66%, 78% { transform: scaleX(1.28); opacity: 0.62; }
		84% { transform: scaleX(1.00); opacity: 0.12; }
	}
	@keyframes crabWaterFront {
		0%, 56%, 88%, 100% { transform: scaleX(0.74); opacity: 0; }
		62% { transform: scaleX(1.14); opacity: 0.42; }
		68%, 78% { transform: scaleX(1.34); opacity: 0.76; }
		84% { transform: scaleX(1.04); opacity: 0.18; }
	}
	@keyframes crabBow {
		0%, 42%, 88%, 100% { transform: rotate(0deg); }
		48%, 56% { transform: rotate(7deg) translateY(2px); }
		62% { transform: rotate(-3deg); }
	}
	@keyframes crabBubbleGroup {
		0%, 58%, 88%, 100% { opacity: 0; }
		64%, 82% { opacity: 0.9; }
	}
	@keyframes crabBubble {
		0%, 58%, 88%, 100% { transform: translate(0, 0) scale(0.72); opacity: 0; }
		64% { transform: translate(0, 0) scale(0.82); opacity: 0.85; }
		74% { transform: translate(2px, -9px) scale(1.05); opacity: 0.58; }
		84% { transform: translate(4px, -18px) scale(1.24); opacity: 0; }
	}
</style>

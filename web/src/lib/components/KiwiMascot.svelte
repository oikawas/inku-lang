<svg class="progress-kiwi" viewBox="0 0 72 50" aria-hidden="true">
	<g class="kiwi-motion">
		<ellipse class="kiwi-shadow" cx="36" cy="43" rx="17" ry="2.7" />
		<g class="kiwi-dash">
			<g class="kiwi-ball">
				<ellipse class="kiwi-ball-body" cx="38" cy="32" rx="14.2" ry="10.4" />
				<ellipse class="kiwi-ball-belly" cx="35.5" cy="34" rx="8" ry="5.9" />
				<g class="kiwi-ball-head-group">
					<circle class="kiwi-ball-head" cx="27.5" cy="27.4" r="6.7" />
					<path class="kiwi-ball-neck" d="M31.5 30.4 C34.4 29.7 37.2 30.6 38.9 33.2 C36.1 35.1 32.5 34.3 30.7 31.8 Z" />
					<path class="kiwi-ball-beak" d="M22.5 28.2 C15.3 28 10.5 29.6 7 33 C13.6 33.8 18.5 32.3 24 29.5 Z" />
					<path class="kiwi-ball-eye-closed" d="M25.5 25.3 Q27 26.2 28.5 25.3" />
				</g>
			</g>

			<g class="kiwi-active">
				<g class="kiwi-view kiwi-view-side">
					<g class="kiwi-hip">
						<ellipse class="kiwi-body" cx="38" cy="28" rx="14.8" ry="10.6" />
						<ellipse class="kiwi-belly" cx="34" cy="30" rx="8.4" ry="6.8" />
						<path class="kiwi-tail" d="M50.5 25.7 C56 24 59.5 21.5 61.8 17.8 C61.1 25.1 56.5 30.7 51.4 31.8 Z" />
					</g>
					<g class="kiwi-neck">
						<path class="kiwi-neck-fill" d="M29.7 23.2 C26.6 22.8 24.1 24.4 23.1 27.7 C25.5 28.5 28.6 27.1 30.8 24.9 Z" />
						<g class="kiwi-head">
							<circle class="kiwi-head-fill" cx="25" cy="20.8" r="7.1" />
							<g class="kiwi-beak-wrap">
								<path class="kiwi-beak kiwi-beak-closed" d="M19.2 21.8 C11.4 21.5 6 23.6 2.8 27.5 C10.8 27.8 15.9 25.9 20.9 23.2 Z" />
								<g class="kiwi-beak-open">
									<path d="M19.3 21.1 C11.5 20.1 6.1 21.7 2.7 25.7 C10 26.1 15.4 24.6 20.4 22.4 Z" />
									<path d="M19.6 22.6 C12.4 23 7.3 25.2 4 29.2 C11.7 29.1 16.3 26.4 20.9 23.4 Z" />
								</g>
							</g>
							<circle class="kiwi-eye kiwi-eye-open" cx="23" cy="18.7" r="1.1" />
							<path class="kiwi-eye-closed" d="M21.7 18.7 Q23 19.5 24.3 18.7" />
							<g class="kiwi-sniff-marks">
								<path d="M2.1 22.5 C0.7 21.3 0.7 19.9 2.2 18.7" />
								<path d="M1.0 28.8 C-0.8 29.6 -1.0 31.2 0.8 32.4" />
							</g>
						</g>
					</g>
				</g>

				<g class="kiwi-legs">
					<path class="kiwi-leg kiwi-leg-root" d="M33.2 36.5 L31.4 41.2" />
					<g class="kiwi-leg-foot kiwi-leg-foot-a">
						<path class="kiwi-leg" d="M31.4 41.2 L26.8 44.8 M31.4 41.2 L31.9 45.8 M31.4 41.2 L34.4 44.7" />
					</g>
					<path class="kiwi-leg kiwi-leg-root" d="M41.1 36.4 L42.5 41.2" />
					<g class="kiwi-leg-foot kiwi-leg-foot-b">
						<path class="kiwi-leg" d="M42.5 41.2 L37.8 44.8 M42.5 41.2 L42.8 45.9 M42.5 41.2 L47.3 44.8" />
					</g>
				</g>
			</g>
		</g>
	</g>
</svg>

<style>
	.progress-kiwi {
		position: absolute;
		left: calc(var(--progress-target, 50%) - 36px);
		bottom: 5px;
		width: 72px;
		height: 50px;
		pointer-events: none;
		overflow: visible;
		filter: drop-shadow(0 2px 3px rgba(86, 68, 39, 0.18));
	}
	.kiwi-motion {
		transform-origin: 36px 32px;
		animation: kiwiWalk 28s ease-in-out infinite;
	}
	.kiwi-dash {
		transform-origin: 36px 32px;
		animation: kiwiDash 28s ease-in-out infinite;
	}
	.kiwi-active {
		transform-origin: 36px 31px;
		animation: kiwiActive 28s ease-in-out infinite;
	}
	.kiwi-view {
		transform-origin: 36px 30px;
		animation-duration: 28s;
		animation-timing-function: ease-in-out;
		animation-iteration-count: infinite;
	}
	.kiwi-view-side { animation-name: kiwiSideView; }
	.kiwi-hip {
		transform-origin: 46px 31px;
		animation: kiwiHipWiggle 28s ease-in-out infinite;
	}
	.kiwi-neck {
		transform-origin: 31px 27px;
		animation: kiwiNeck 13s ease-in-out infinite;
	}
	.kiwi-head {
		transform-origin: 25px 22px;
		animation: kiwiHead 13s ease-in-out infinite;
	}
	.kiwi-beak-wrap {
		transform-origin: 19px 22px;
		animation: kiwiBeakTap 13s ease-in-out infinite;
	}
	.kiwi-ball {
		opacity: 0;
		transform-origin: 36px 34px;
		animation: kiwiBall 28s ease-in-out infinite;
	}
	.kiwi-ball-head-group {
		transform-origin: 32px 32px;
		animation: kiwiBallHeadNod 28s ease-in-out infinite;
	}
	.kiwi-shadow { fill: rgba(57, 44, 25, 0.20); }
	.kiwi-body { fill: #8a6f46; }
	.kiwi-belly { fill: #b59664; opacity: 0.72; }
	.kiwi-head-fill, .kiwi-neck-fill { fill: #7f663f; }
	.kiwi-tail { fill: #5f4d32; }
	.kiwi-ball-body { fill: #7c633c; }
	.kiwi-ball-belly { fill: #b59664; opacity: 0.62; }
	.kiwi-ball-head, .kiwi-ball-neck { fill: #725a37; }
	.kiwi-beak, .kiwi-ball-beak, .kiwi-beak-open path {
		fill: #c19a53;
		stroke: #7d5d24;
		stroke-width: 0.8;
		stroke-linejoin: round;
	}
	.kiwi-beak-open {
		opacity: 0;
		transform-origin: 19px 22px;
		animation: kiwiOpenBeak 28s ease-in-out infinite;
	}
	.kiwi-eye, .kiwi-eye-open { fill: #1f1b14; animation: kiwiBlink 8.4s ease-in-out infinite; }
	.kiwi-eye-closed,
	.kiwi-ball-eye-closed {
		fill: none;
		stroke: #1f1b14;
		stroke-width: 1.2;
		stroke-linecap: round;
		opacity: 0;
		animation: kiwiClosedEye 8.4s ease-in-out infinite;
	}
	.kiwi-ball-eye-closed { opacity: 1; animation: none; }
	.kiwi-leg {
		fill: none;
		stroke: #7a5421;
		stroke-width: 1.45;
		stroke-linecap: round;
		stroke-linejoin: round;
	}
	.kiwi-leg-root { opacity: 0.96; }
	.kiwi-leg-foot-a {
		transform-origin: 31.4px 41.2px;
		animation: kiwiStepA 2.15s ease-in-out infinite;
	}
	.kiwi-leg-foot-b {
		transform-origin: 42.5px 41.2px;
		animation: kiwiStepB 2.15s ease-in-out infinite;
	}
	.kiwi-sniff-marks {
		fill: none;
		stroke: #9a7d48;
		stroke-width: 1;
		stroke-linecap: round;
		opacity: 0;
		animation: kiwiSniffMarks 13s ease-in-out infinite;
	}
	:global(html[data-theme='dark']) .kiwi-shadow { fill: rgba(0, 0, 0, 0.28); }
	:global(html[data-theme='dark']) .kiwi-body { fill: #9f8050; }
	:global(html[data-theme='dark']) .kiwi-head-fill,
	:global(html[data-theme='dark']) .kiwi-neck-fill { fill: #8f7247; }
	:global(html[data-theme='dark']) .kiwi-belly { fill: #c1a06b; opacity: 0.70; }
	:global(html[data-theme='dark']) .kiwi-ball-belly { fill: #c1a06b; opacity: 0.60; }
	:global(html[data-theme='dark']) .kiwi-ball-head,
	:global(html[data-theme='dark']) .kiwi-ball-neck { fill: #8f7247; }
	:global(html[data-theme='dark']) .kiwi-beak,
	:global(html[data-theme='dark']) .kiwi-ball-beak,
	:global(html[data-theme='dark']) .kiwi-beak-open path {
		fill: #d3aa5f;
		stroke: #9d7430;
	}
	@keyframes kiwiWalk {
		0% { transform: translate(-20px, 0) scaleX(1); }
		9% { transform: translate(-8px, -1px) scaleX(1); }
		17% { transform: translate(-8px, 0) scaleX(1); }
		28% { transform: translate(14px, -1px) scaleX(1); }
		38% { transform: translate(14px, 0) scaleX(1); }
		43% { transform: translate(8px, 0) scaleX(1); }
		52% { transform: translate(0, -1px) scaleX(1); }
		62% { transform: translate(-18px, 0) scaleX(1); }
		68% { transform: translate(-10px, 0) scaleX(1); }
		90% { transform: translate(-10px, 0) scaleX(1); }
		93% { transform: translate(-28px, -1px) scaleX(1); }
		96% { transform: translate(-46px, 0) scaleX(1); }
		98% { transform: translate(-24px, 0) scaleX(1); }
		100% { transform: translate(-20px, 0) scaleX(1); }
	}
	@keyframes kiwiSideView {
		0%, 100% { opacity: 1; transform: scaleX(1); }
	}
	@keyframes kiwiActive {
		0%, 66%, 91%, 100% { opacity: 1; }
		68%, 90% { opacity: 0; }
	}
	@keyframes kiwiNeck {
		0%, 15%, 36%, 43%, 60%, 100% { transform: rotate(0deg) translate(0, 0); }
		18%, 23%, 28%, 33% { transform: rotate(-10deg) translate(-1px, 3px); }
		20%, 25%, 30%, 35% { transform: rotate(4deg) translate(0, 0); }
		46%, 50%, 54%, 58% { transform: rotate(-4deg) translate(-1px, 1px); }
	}
	@keyframes kiwiHipWiggle {
		0%, 23%, 34%, 55%, 63%, 91%, 100% { transform: rotate(0deg) translate(0, 0) scaleX(1); }
		25%, 59%, 94% { transform: rotate(5deg) translate(1.8px, 0.3px) scaleX(1.03); }
		28%, 61%, 96% { transform: rotate(-4deg) translate(-1.2px, -0.2px) scaleX(0.98); }
		31%, 98% { transform: rotate(3deg) translate(1px, 0.2px) scaleX(1.02); }
	}
	@keyframes kiwiHead {
		0%, 15%, 36%, 43%, 60%, 100% { transform: rotate(0deg); }
		18%, 23%, 28%, 33% { transform: rotate(-9deg) translate(-1px, 1px); }
		20%, 25%, 30%, 35% { transform: rotate(7deg); }
		46%, 50%, 54%, 58% { transform: rotate(-5deg) translateX(-1px); }
		48%, 52%, 56% { transform: rotate(4deg) translateX(1px); }
	}
	@keyframes kiwiBeakTap {
		0%, 16%, 36%, 100% { transform: rotate(0deg); }
		19%, 24%, 29%, 34% { transform: rotate(-7deg) translateY(1px); }
		21%, 26%, 31% { transform: rotate(4deg); }
	}
	@keyframes kiwiSniffMarks {
		0%, 43%, 61%, 100% { opacity: 0; transform: translateX(0); }
		46%, 50%, 54%, 58% { opacity: 0.75; transform: translateX(-1px); }
	}
	@keyframes kiwiBall {
		0%, 66%, 91%, 100% { opacity: 0; transform: scale(0.88) translateY(1px); }
		68%, 90% { opacity: 1; transform: scale(1) translateY(0); }
	}
	@keyframes kiwiBallHeadNod {
		0%, 68%, 90%, 100% { transform: rotate(0deg) translate(0, 0); }
		71%, 78%, 85% { transform: rotate(-8deg) translate(-1px, 2px); }
		74%, 81%, 88% { transform: rotate(3deg) translate(0, 0); }
	}
	@keyframes kiwiDash {
		0%, 91%, 100% { transform: translateX(0) scaleX(1); }
		94% { transform: translateX(-20px) scaleX(1.24); }
		96% { transform: translateX(15px) scaleX(0.88); }
		98% { transform: translateX(-7px) scaleX(1.08); }
	}
	@keyframes kiwiOpenBeak {
		0%, 91%, 99%, 100% { opacity: 0; transform: scaleY(0.7); }
		94%, 96%, 98% { opacity: 1; transform: scaleY(1); }
	}
	@keyframes kiwiBlink {
		0%, 5%, 7%, 53%, 55%, 100% { opacity: 1; transform: scaleY(1); }
		6%, 54% { opacity: 0; transform: scaleY(0.05); }
	}
	@keyframes kiwiClosedEye {
		0%, 5%, 7%, 53%, 55%, 100% { opacity: 0; }
		6%, 54% { opacity: 1; }
	}
	@keyframes kiwiStepA {
		0%, 16%, 38%, 66%, 85%, 100% { transform: rotate(0deg); }
		8%, 29%, 60% { transform: rotate(30deg) translate(1px, -0.5px); }
		18%, 43% { transform: rotate(-22deg) translate(-1px, 0.6px); }
		23%, 52% { transform: rotate(-34deg) translate(-2px, 0.8px); }
		94% { transform: rotate(44deg) translate(1.6px, -0.8px); }
	}
	@keyframes kiwiStepB {
		0%, 16%, 38%, 66%, 85%, 100% { transform: rotate(0deg); }
		8%, 29%, 60% { transform: rotate(-22deg) translate(-0.8px, 0.4px); }
		18%, 43% { transform: rotate(24deg) translate(1px, -0.5px); }
		23%, 52% { transform: rotate(34deg) translate(2px, -0.7px); }
		95% { transform: rotate(-42deg) translate(-1.5px, 0.7px); }
	}
</style>

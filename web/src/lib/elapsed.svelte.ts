/**
 * Shared elapsed counter for running operations.
 *
 * Every "drawing in progress" indicator shows the same `elapsed N.Ns` reading,
 * so the tick interval and the reset semantics live here instead of being
 * re-implemented next to each operation.
 */
export type Elapsed = {
	readonly ms: number;
	start: () => void;
	stop: () => void;
};

const TICK_MS = 100;

export function createElapsed(): Elapsed {
	let ms = $state(0);
	let handle: ReturnType<typeof setInterval> | null = null;
	let startedAt = 0;

	function stop() {
		if (handle !== null) {
			clearInterval(handle);
			handle = null;
		}
	}

	return {
		get ms() {
			return ms;
		},
		start() {
			stop();
			startedAt = Date.now();
			ms = 0;
			handle = setInterval(() => {
				ms = Date.now() - startedAt;
			}, TICK_MS);
		},
		stop
	};
}

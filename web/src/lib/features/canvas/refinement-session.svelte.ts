import { createElapsed, type Elapsed } from '../../elapsed.svelte.ts';
import type { PaintResult } from '../run/current-work.ts';

export type RefineKind = 'touch' | 'layout' | 'reading' | 'color' | 'variation';
export type VariationAmplitude = 'small' | 'medium' | 'large';

export type VariationCandidate = {
	id: string;
	label: string;
	result: PaintResult & { ddl: string; thinking: string | null };
	selected: boolean;
	saved?: boolean;
};

/** One fan-out job is queued, drawing, or finished. */
export type VariationSlotState = 'waiting' | 'running' | 'done';

export type RefinementSession = {
	readonly busy: boolean;
	readonly candidates: readonly VariationCandidate[];
	readonly gridBusy: boolean;
	readonly gridCanAbort: boolean;
	readonly gridIncludesReading: boolean;
	readonly gridTaskLabel: string;
	readonly gridDone: number;
	readonly gridTotal: number;
	readonly gridSlots: VariationSlotState[];
	readonly gridSlotLabels: string[];
	readonly status: string | null;
	readonly elapsedMs: number;
	readonly tokensIn: number | null;
	readonly tokensOut: number | null;
	abort(): void;
	toggleCandidate(id: string): void;
};

type GridStart = {
	includesReading: boolean;
	taskLabel: string;
	count: number;
};

type ResetOptions = {
	preserveCandidates?: boolean;
};

const addTokenCount = (total: number | null, delta: number | null | undefined): number | null => {
	if (delta === null || delta === undefined) return total;
	return (total ?? 0) + delta;
};

/** Route-instance owner for refinement progress, cancellation, and selection. */
export class RefinementSessionState implements RefinementSession {
	busy = $state(false);
	candidates = $state<VariationCandidate[]>([]);
	gridBusy = $state(false);
	gridCanAbort = $state(false);
	gridIncludesReading = $state(false);
	gridTaskLabel = $state('');
	// Fan-out jobs finish out of order, so progress counts completed jobs
	// instead of treating one slot as the current position.
	gridDone = $state(0);
	gridTotal = $state(0);
	// Parallel arrays preserve one visible lane and label per candidate.
	gridSlots = $state<VariationSlotState[]>([]);
	gridSlotLabels = $state<string[]>([]);
	status = $state<string | null>(null);
	tokensIn = $state<number | null>(null);
	tokensOut = $state<number | null>(null);

	private activeController: AbortController | null = null;
	private readonly elapsed: Elapsed;

	constructor(elapsed: Elapsed = createElapsed()) {
		this.elapsed = elapsed;
	}

	get elapsedMs(): number {
		return this.elapsed.ms;
	}

	beginSingle(): void {
		this.busy = true;
		this.tokensIn = null;
		this.tokensOut = null;
		this.elapsed.start();
	}

	finishSingle(): void {
		this.busy = false;
		this.elapsed.stop();
	}

	beginGrid(input: GridStart): AbortController {
		const controller = new AbortController();
		this.activeController = controller;
		this.gridBusy = true;
		this.gridCanAbort = false;
		this.tokensIn = null;
		this.tokensOut = null;
		this.elapsed.start();
		this.gridIncludesReading = input.includesReading;
		this.gridTaskLabel = input.taskLabel;
		this.status = null;
		this.gridDone = 0;
		this.gridTotal = input.count;
		// Seat every lane before seed or catalog allocation so progress exists
		// for the whole operation, not only after its first request starts.
		this.gridSlotLabels = Array.from({ length: input.count }, () => '');
		this.gridSlots = Array.from({ length: input.count }, () => 'waiting');
		return controller;
	}

	isActive(controller: AbortController): boolean {
		return this.activeController === controller;
	}

	enableAbort(controller: AbortController): boolean {
		if (!this.isActive(controller) || !this.gridBusy) return false;
		this.gridCanAbort = true;
		return true;
	}

	setPlans(controller: AbortController, labels: string[]): boolean {
		if (!this.isActive(controller)) return false;
		this.gridSlotLabels = [...labels];
		this.gridSlots = labels.map(() => 'waiting');
		return true;
	}

	seatSlot(controller: AbortController, index: number, state: VariationSlotState): boolean {
		if (!this.isActive(controller)) return false;
		this.gridSlots = this.gridSlots.map((current, candidateIndex) => (
			candidateIndex === index ? state : current
		));
		return true;
	}

	finishSlot(controller: AbortController, index: number): boolean {
		if (!this.seatSlot(controller, index, 'done')) return false;
		this.gridDone += 1;
		return true;
	}

	commitCandidates(controller: AbortController, candidates: VariationCandidate[]): boolean {
		if (!this.isActive(controller)) return false;
		this.candidates = candidates;
		return true;
	}

	addTokens(controller: AbortController, tokensIn: number | null, tokensOut: number | null): boolean {
		if (!this.isActive(controller)) return false;
		this.tokensIn = addTokenCount(this.tokensIn, tokensIn);
		this.tokensOut = addTokenCount(this.tokensOut, tokensOut);
		return true;
	}

	failGrid(controller: AbortController, message: string): boolean {
		if (!this.isActive(controller)) return false;
		this.status = message;
		return true;
	}

	finishGrid(controller: AbortController): boolean {
		// A completion from an invalidated target must not unlock or overwrite
		// the session that replaced it.
		if (!this.isActive(controller)) return false;
		this.activeController = null;
		this.gridBusy = false;
		this.gridCanAbort = false;
		this.elapsed.stop();
		return true;
	}

	abort(): void {
		this.activeController?.abort();
	}

	setStatus(message: string | null): void {
		this.status = message;
	}

	reset(options: ResetOptions = {}): void {
		if (options.preserveCandidates) return;
		// Target changes invalidate the controller before clearing projections;
		// late slot or completion callbacks then fail the identity checks above.
		this.activeController?.abort();
		this.activeController = null;
		this.gridBusy = false;
		this.gridCanAbort = false;
		this.candidates = [];
		this.gridIncludesReading = false;
		this.gridTaskLabel = '';
		this.gridDone = 0;
		this.gridTotal = 0;
		this.gridSlots = [];
		this.gridSlotLabels = [];
		this.status = null;
	}

	toggleCandidate(id: string): void {
		this.candidates = this.candidates.map((candidate) => candidate.id === id
			? { ...candidate, selected: !candidate.selected }
			: candidate);
	}

	beginSave(): void {
		// Candidate saving reuses the grid lock so no new fan-out starts while
		// the selected set is being projected into history one item at a time.
		this.gridBusy = true;
		this.status = null;
	}

	markSaved(id: string): void {
		this.candidates = this.candidates.map((candidate) => candidate.id === id
			? { ...candidate, saved: true, selected: false }
			: candidate);
	}

	finishSave(): void {
		this.gridBusy = false;
	}
}

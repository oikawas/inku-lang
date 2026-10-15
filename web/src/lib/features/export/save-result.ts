import type { SaveOutcome } from './save-target';

/** One export may save several contact-sheet pages and their notes. */
export type ExportSaveResult = SaveOutcome | readonly SaveOutcome[] | void;
export type ExportSaveActionResult = ExportSaveResult | Promise<ExportSaveResult>;

/** A later file failed after earlier files had already been saved. */
export class ExportSaveError extends Error {
	readonly outcomes: readonly SaveOutcome[];

	constructor(cause: unknown, outcomes: readonly SaveOutcome[]) {
		super(cause instanceof Error ? cause.message : String(cause), { cause });
		this.outcomes = [...outcomes];
	}
}

export function exportSaveFailure(cause: unknown): { error: string; fallbackReason: 'denied' | 'failed' | null } {
	return {
		error: cause instanceof Error ? cause.message : String(cause),
		fallbackReason: cause instanceof ExportSaveError ? exportFallbackReason(cause.outcomes) : null,
	};
}

export function exportFallbackReason(result: ExportSaveResult): 'denied' | 'failed' | null {
	const outcomes: readonly SaveOutcome[] = !result ? [] : Array.isArray(result) ? result : [result as SaveOutcome];
	// Keep a write failure visible even if another file only lacked permission.
	for (const reason of ['failed', 'denied'] as const) {
		if (outcomes.some((outcome) => outcome.kind === 'browser' && outcome.reason === reason)) return reason;
	}
	return null;
}

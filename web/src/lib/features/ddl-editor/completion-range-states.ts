import type { ApiFetch } from '../../transport/api-fetch';
import type { LangPack } from '../../i18n/types';

export type CompletionRangeState = {
	utf16_start: number;
	utf16_end: number;
	state: 'completed' | 'numbers_changed' | 'words_changed';
};
export type CompletionRangeWork = { history_id: string } | { execution_id: string };

export function completionWordsHint(ranges: readonly CompletionRangeState[], strings: LangPack): string | null {
	const count = ranges.filter((range) => range.state === 'words_changed').length;
	return count ? strings.ddlCompletionWordsHint(count) : null;
}

/** Each editor owns its request; an old response cannot label a newer draft. */
export class CompletionRangeStatesQuery {
	private generation = 0;
	private controller: AbortController | null = null;
	cancel(): void {
		this.generation++;
		this.controller?.abort();
		this.controller = null;
	}
	async load(apiFetch: ApiFetch, work: CompletionRangeWork, source: string, publish: (ranges: CompletionRangeState[]) => void): Promise<void> {
		this.cancel();
		const generation = this.generation;
		const controller = this.controller = new AbortController();
		try {
			const response = await apiFetch('/api/pipeline/completion-range-states', {
				method: 'POST', headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ ...work, source }), signal: controller.signal,
			});
			if (!response.ok) return;
			const result = await response.json() as { schema?: string; ranges?: CompletionRangeState[] };
			if (generation === this.generation && result.schema === 'inku.completion-range-states.v1' && Array.isArray(result.ranges)) publish(result.ranges);
		} catch {
			// Editing stays available when the optional record cannot be read.
		} finally {
			if (this.controller === controller) this.controller = null;
		}
	}
}

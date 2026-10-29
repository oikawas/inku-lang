import type { ApiFetch } from '../../transport/api-fetch';
import type { CompletionRangeWork } from './completion-range-states';

export type PluginCall = {
	start_byte: number; end_byte: number; start_utf16: number; end_utf16: number;
	text: string; spelling: 'braced' | 'legacy'; status: string;
	qualified_name?: string; suggestion?: string | null; candidates?: string[] | null;
};

/** An answer only applies to the exact source that was sent. */
export class PluginCallsQuery {
	private generation = 0;
	private controller: AbortController | null = null;
	cancel(): void { this.generation++; this.controller?.abort(); this.controller = null; }
	async load(fetch: ApiFetch, work: CompletionRangeWork | null, source: string, language: 'ja' | 'en', publish: (calls: PluginCall[]) => void): Promise<void> {
		this.cancel();
		const generation = this.generation, controller = this.controller = new AbortController();
		try {
			const response = await fetch('/api/pipeline/plugin-calls', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ...work, source, language }), signal: controller.signal });
			if (!response.ok) return;
			const result = await response.json() as { schema?: string; calls?: PluginCall[] };
			if (generation === this.generation && result.schema === 'inku.plugin-calls.v1' && Array.isArray(result.calls)) publish(result.calls);
		} catch { /* Editing remains available if inspection fails. */ }
		finally { if (this.controller === controller) this.controller = null; }
	}
}

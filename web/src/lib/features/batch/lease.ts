import type { ApiFetch } from '../../transport/api-fetch.ts';
import type { BatchRunConditions } from './resume.ts';

export type BatchLeaseRecord = {
	run_id: string; kind: 'web' | 'cli' | 'image'; total: number; completed: number;
	state: 'running' | 'uncertain' | 'lease_expired' | 'interrupted' | 'stopped' | 'completed';
	prompt: string; conditions: BatchRunConditions; updated_at: number;
};

/** A lease fences a resumed client against late heartbeats from an older one. */
export async function startBatchLease(apiFetch: ApiFetch, runId: string, prompt: string,
	conditions: BatchRunConditions | Record<string, unknown>, total: number, completed: () => number, lost: () => void,
	kind: 'web' | 'image' = 'web'): Promise<{
	lease: string;
	refresh: () => Promise<void>;
	finish: (state: 'completed' | 'stopped' | 'interrupted') => Promise<void>;
} | null> {
	const response = await apiFetch('/api/pipeline/batches', { method: 'POST', headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify({ run_id: runId, kind, prompt, conditions, total }) });
	if (response.status === 404) return null; // Older Server, whose history-based resume remains available.
	if (!response.ok) throw new Error(`Batch lease: HTTP ${response.status}`);
	const data = await response.json() as { lease?: unknown };
	if (typeof data.lease !== 'string') throw new Error('Batch lease response is invalid');
	const lease = data.lease;
	let ended = false;
	let pending = false;
	const update = async (state: 'running' | 'completed' | 'stopped' | 'interrupted') => {
		const result = await apiFetch(`/api/pipeline/batches/${encodeURIComponent(runId)}/heartbeat`, {
			method: 'POST', headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({ lease, state, completed: completed() })
		});
		if (result.status === 409 && !ended) lost();
		if (!result.ok) throw new Error(`Batch heartbeat: HTTP ${result.status}`);
	};
	const timer = setInterval(() => {
		if (ended || pending) return;
		pending = true;
		void update('running').catch(() => undefined).finally(() => { pending = false; });
	}, 15_000);
	return { lease, refresh: () => update('running'), finish: async (state) => {
		ended = true;
		clearInterval(timer);
		await update(state);
	} };
}

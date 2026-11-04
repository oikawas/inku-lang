// These are browser-local presentation choices. The Server lease is untouched.
const KEY = 'inku.batch.dismissedRuns.v1';
const memory = new Set<string>();

function stored(): string[] {
	try {
		const value: unknown = JSON.parse(localStorage.getItem(KEY) ?? '[]');
		return Array.isArray(value) ? value.filter((id): id is string => typeof id === 'string') : [];
	} catch { return []; }
}

export function dismissBatchRun(id: string | null | undefined): void {
	if (!id) return;
	memory.add(id);
	try { localStorage.setItem(KEY, JSON.stringify([...new Set([...stored(), ...memory])])); }
	catch { /* Storage can be unavailable; keep the choice for this page. */ }
}

export function isBatchRunDismissed(id: string | null | undefined): boolean {
	return !!id && (memory.has(id) || stored().includes(id));
}

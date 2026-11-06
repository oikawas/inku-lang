export function ddlWorkKey<T extends { history_id?: string | null }>(historyId: string | null | undefined, result: T | null): string | T | null {
	return historyId ?? result?.history_id ?? result;
}

export function historyListDescription(text: string, limit = 20): string {
	const description = text.replace(/^\s*#\d+\s*/, '').trim();
	return Array.from(description).slice(0, limit).join('');
}

export function formatHistoryMinute(at: number, locale: string, timeZone?: string): string {
	return new Date(at).toLocaleString(locale, {
		year: 'numeric',
		month: '2-digit',
		day: '2-digit',
		hour: '2-digit',
		minute: '2-digit',
		...(timeZone ? { timeZone } : {})
	});
}

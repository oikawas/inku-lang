import type { LangPack } from '../../i18n/types.ts';

export function batchClockTime(milliseconds: number): string {
	const total = Math.max(0, Math.floor(milliseconds / 1000));
	const seconds = String(total % 60).padStart(2, '0');
	const minutes = Math.floor(total / 60);
	if (total < 3600) return `${minutes}:${seconds}`;
	return `${Math.floor(minutes / 60)}:${String(minutes % 60).padStart(2, '0')}:${seconds}`;
}

export function batchElapsedTime(milliseconds: number, strings: LangPack): string {
	const total = Math.max(0, Math.floor(milliseconds / 1000));
	const seconds = String(total % 60).padStart(2, '0');
	const minutes = Math.floor(total / 60);
	if (total < 60) return strings.elapsedSeconds(String(total));
	if (total < 3600) return strings.elapsedMinutes(String(minutes), seconds);
	return strings.elapsedHours(String(Math.floor(minutes / 60)), String(minutes % 60).padStart(2, '0'), seconds);
}

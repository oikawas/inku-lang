/** A missing Score and an older Score without a recorded version are distinct. */
export function scoreVersionDisplay(score: { version?: string | null } | null | undefined, notRecorded: string): string {
	if (score == null) return '-';
	return typeof score.version === 'string' ? score.version : notRecorded;
}

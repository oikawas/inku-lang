// Chunk titles (DDL 27), the rule of the shared core's `chunk_title.rs`: a
// line that is only a bracketed name, 「灯台」 or "lighthouse" (or
// “lighthouse”), names the chunk of sentences after it. A title draws nothing,
// so a DDL view shows it as a heading and colours no word in it, and the
// language of a DDL is read without it.

const TITLE_BRACKETS: ReadonlyArray<readonly [string, string]> = [
	['「', '」'],
	['"', '"'],
	['“', '”']
];

/** The name a line gives when the whole line, without the spaces around it,
    is a title (empty for a title that ends a chunk); null for any other line.
    A name leaves out its own pair's characters only. */
export function ddlTitleName(line: string): string | null {
	const trimmed = line.trim();
	for (const [open, close] of TITLE_BRACKETS) {
		if (trimmed.length < open.length + close.length || !trimmed.startsWith(open) || !trimmed.endsWith(close)) continue;
		const inner = trimmed.slice(open.length, trimmed.length - close.length);
		if (!inner.includes(open) && !inner.includes(close) && !inner.includes('\n')) return inner.trim();
	}
	return null;
}

/** Where each title line stands in `text`, without its line break. */
export function ddlTitleLineSpans(text: string): Array<{ start: number; end: number }> {
	const spans: Array<{ start: number; end: number }> = [];
	let start = 0;
	for (const line of text.split('\n')) {
		const content = line.endsWith('\r') ? line.slice(0, -1) : line;
		if (ddlTitleName(content) !== null) spans.push({ start, end: start + content.length });
		start += line.length + 1;
	}
	return spans;
}

/** `text` without its title lines. */
export function withoutDdlTitleLines(text: string): string {
	return text.split('\n').filter((line) => ddlTitleName(line) === null).join('\n');
}

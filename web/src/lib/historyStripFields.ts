/**
 * Which facts the history strip prints under each thumbnail.
 *
 * The strip used to print the generation and the Stage 1 model, fixed, with no
 * way to ask for anything else. Four facts are on offer now and at most three
 * are shown, in a smaller type (v2.15.62; two before): the tile is only a
 * thumbnail wide, and a fourth line would push the picture out of the strip.
 *
 * None is a real answer -- a reader who wants only the pictures gets only the
 * pictures -- so an empty list is a choice and is stored as one. That is why
 * the normaliser tells an absent value (no column, an old account, a broken
 * payload) apart from an empty list: the first takes the default, the second
 * does not. Reading both through one falsy test would make "show nothing"
 * impossible to save.
 *
 * Plain .ts (no runes), so the rules are testable without the compiler -- the
 * same split $lib/uiMode.ts uses.
 */

export const HISTORY_STRIP_FIELDS = ['generation', 'model', 'engine_version', 'bytes'] as const;

export type HistoryStripField = (typeof HISTORY_STRIP_FIELDS)[number];

export function formatHistoryStripEngineVersion(value: string | null | undefined, notRecorded: string): string {
	const version = String(value ?? '').trim();
	if (!version) return notRecorded;
	return `Ver.${version.replace(/^Ver\.\s*/i, '')}`;
}

const STRIP_MODEL_WORDS: Readonly<Record<string, string>> = {
	gpt: 'GPT', oss: 'oss', sol: 'So', luna: 'Lu', astra: 'As', terra: 'Te',
	claude: 'Cl', sonnet: 'So', opus: 'Op', haiku: 'Ha', fable: 'Fa',
	gemini: 'Ge', gemma: 'Gm', flash: 'Fl', lite: 'L', pro: 'Pr', mini: 'Mi', nano: 'Na', turbo: 'T',
	llama: 'Ll', qwen: 'Qw', deepseek: 'DS', minimax: 'MM', kimi: 'Ki',
	mistral: 'Mi', ministral: 'Min', mixtral: 'Mx', nemotron: 'Nem', granite: 'Gr',
	large: 'Lg', medium: 'Md', small: 'Sm', super: 'Su', ultra: 'Ul',
	instruct: 'I', it: 'I', vision: 'V', reasoning: 'R', thinking: 'Th',
	preview: 'Pv', latest: 'Lt', code: 'Cd', coder: 'Cdr',
	a: 'A', b: 'B', e: 'E'
};

/** Compact recognizable tokens, keeping numeric versions, sizes and variants. */
export function abbreviateStripModel(owner: string, name: string): string {
	const provider = /ollama.*cloud/i.test(owner) ? 'Oc' : owner.trim().slice(0, 2);
	let model = name.trim().replace(/^.*\//, '')
		.replace(/^(?:anthropic|google|meta|mistral\s+ai)\s+/i, '')
		.replace(/\s*\([\d.]+\s*[GM]B\)\s*$/i, '')
		.replace(/\bdeepseek[-\s]+v(?=\d)/i, 'deepseek-')
		.replace(/\bq(\d+)[_-]k[_-]([a-z])\b/gi, (_, bits, suffix) => `Q${bits}K${suffix.toUpperCase()}`);
	// The provider already identifies these brands; Gemma still needs its name.
	if (/^claude\b/i.test(owner)) model = model.replace(/^claude[\s-]+/i, '');
	if (/^gemini\b/i.test(owner)) model = model.replace(/^gemini[\s-]+/i, '');
	const tokens = model.split(/[\s:_-]+/).filter(Boolean)
		.map((token) => token.replace(/[a-z]+/gi, (word) => STRIP_MODEL_WORDS[word.toLowerCase()] ?? word));
	// Without a separator, version 4 + size 31B would read as version 431B.
	const compact = tokens.reduce((text, token, index) =>
		text + (index > 0 && /\d$/.test(tokens[index - 1]) && /^\d/.test(token) ? '·' : '') + token, '');
	return [provider, compact].filter(Boolean).join(' ');
}

/** At most three facts at once; unusually long model names can still wrap. */
export const HISTORY_STRIP_FIELD_LIMIT = 3;

/** What the strip printed before it could be asked, so nobody's strip moves. */
export const DEFAULT_HISTORY_STRIP_FIELDS: HistoryStripField[] = ['generation', 'model'];

function isField(value: unknown): value is HistoryStripField {
	return typeof value === 'string' && (HISTORY_STRIP_FIELDS as readonly string[]).includes(value);
}

/**
 * The stored value as a list this page can print.
 *
 * Anything that is not an array is an absence and takes the default. An array
 * is taken at its word: unknown names drop out, repeats collapse, and what is
 * left is put back into the order the four are declared in, so the strip reads
 * the same whichever order they were ticked.
 */
export function normalizeHistoryStripFields(value: unknown): HistoryStripField[] {
	if (!Array.isArray(value)) return [...DEFAULT_HISTORY_STRIP_FIELDS];
	const chosen = new Set(value.filter(isField));
	return HISTORY_STRIP_FIELDS.filter((field) => chosen.has(field)).slice(0, HISTORY_STRIP_FIELD_LIMIT);
}

/** Whether a box that is not ticked can still be ticked. */
export function canAddHistoryStripField(current: readonly HistoryStripField[]): boolean {
	return current.length < HISTORY_STRIP_FIELD_LIMIT;
}

/**
 * The list after one box is clicked.
 *
 * Unticking always works. Ticking is refused once three are on -- the boxes are
 * disabled at that point, so this is the second half of the same rule rather
 * than a different one, and refusing is what keeps the reader's two choices
 * where they put them instead of silently evicting one.
 */
export function toggleHistoryStripField(
	current: readonly HistoryStripField[],
	field: HistoryStripField
): HistoryStripField[] {
	if (current.includes(field)) return current.filter((item) => item !== field);
	if (!canAddHistoryStripField(current)) return [...current];
	return normalizeHistoryStripFields([...current, field]);
}

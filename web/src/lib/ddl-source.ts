/** The portable persistence contract's fixed Unicode White_Space set. */
const BODY_CHARACTER = /[^\u0009-\u000d\u0020\u0085\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]/;

/** Test for a body without changing the source that display and replay use. */
export function hasDdlBody(value: string | null | undefined): boolean {
	return typeof value === 'string' && BODY_CHARACTER.test(value);
}

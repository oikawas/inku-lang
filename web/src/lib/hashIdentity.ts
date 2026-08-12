/**
 * How a stored hash is read apart, out where a test can drive it.
 *
 * The server stores an identity as `<scheme>:<digest>` -- `dh1:` for a
 * description (identity.py), `rh2:`/`rh3:` for a render (db.py). The scheme is
 * not decoration: it is one of the fields that goes *into* the digest
 * (`{"version": "rh3", …}`), so two schemes can never produce the same digest
 * for the same work, and the digest alone is unique across all of them.
 *
 * That is why the scheme is treated here as a property of the value rather than
 * as part of it. Nothing in the product takes a prefixed string as input: the
 * only lookup is the four-character suffix search (db.py `_is_render_hash_
 * suffix_search`), and the short form the server publishes is `render_hash[-4:]`,
 * which carries no scheme either. A prefixed string pasted anywhere in the app
 * matches nothing.
 *
 * Before this module each surface decided for itself whether to strip the
 * prefix, and they disagreed three ways: the lineage row was labelled with a
 * scheme name frozen at `rh2` while showing an `rh3` value, and two copy
 * buttons handed over the prefix while the badge beside them did not.
 */

export type HashIdentity = {
	/** The scheme the value names, or null when it carries none. */
	scheme: string | null;
	/** The digest on its own. Never null: a value with no scheme is all digest. */
	digest: string;
};

/**
 * Split a stored hash. Returns null for an absent value, so a caller can tell
 * "no hash" from "a hash with no scheme" -- the second is a real state, held by
 * works saved before the schemes were written down.
 *
 * Split on the first colon only, with indexOf rather than String.split: a digest
 * is hex today, but a scheme that ever put a colon in its payload would be
 * silently truncated by a plain split.
 */
export function splitHashIdentity(value: string | null | undefined): HashIdentity | null {
	if (!value) return null;
	const at = value.indexOf(':');
	if (at < 0) return { scheme: null, digest: value };
	return { scheme: value.slice(0, at), digest: value.slice(at + 1) };
}

/** The digest to hand over -- what a copy button puts on the clipboard. */
export function hashDigest(value: string | null | undefined): string {
	return splitHashIdentity(value)?.digest ?? '';
}

/**
 * What to label the row with: the scheme the value actually names, never a
 * constant. `fallback` is used when the value has no scheme or is absent, which
 * is why it is the family name (`dh`, `rh`) rather than a scheme that would be a
 * claim about how the value was made.
 */
export function hashSchemeLabel(value: string | null | undefined, fallback: string): string {
	return splitHashIdentity(value)?.scheme ?? fallback;
}

/**
 * A row named by its family with the scheme in tow -- "render hash (rh3)".
 *
 * For the surfaces whose rows are named in words rather than by the scheme
 * itself. The scheme still appears exactly once per row, and never inside the
 * value: what is shown in the cell is what the copy button hands over.
 */
export function hashRowLabel(family: string, value: string | null | undefined): string {
	const scheme = splitHashIdentity(value)?.scheme;
	return scheme ? `${family} (${scheme})` : family;
}

/** The digest, shortened for a detail row. The whole value is what gets copied. */
export function shortHashDigest(value: string | null | undefined, length = 12): string {
	const digest = hashDigest(value);
	return digest ? `${digest.slice(0, length)}…` : '—';
}

// The socket the share-target flag will plug into.
//
// A work can carry two marks today -- `starred` and `for_revision`, both
// columns on `history`. A third was asked for: "this work may be shared", the
// flag that lets a group of works be named by a condition instead of one ACL
// row at a time. That flag does not exist. It is ledger I-191, it reaches
// server, web and cli, and I-191 still holds two undecided questions: who sees
// a work once the flag is up, and what happens to visibility reached through
// the lineage (only `history` can carry the column at all).
//
// So this file is the receiving end and nothing more. The canvas offers the
// mark the moment a work arrives carrying the field and a handler is wired;
// until then it offers nothing, because a mark that cannot be saved tells the
// reader the opposite of the truth -- it says the work is marked when nothing
// recorded it.
//
// What decides is the presence of the field, not its value. An absent field is
// a server that does not know the flag; `false` is a server that knows it and
// says this work is not marked. Reading `!item.for_share` for both would hide
// the mark on precisely the works that are allowed to carry it.

/** The parts of a work this decision reads. */
export type ShareTargetWork = { id?: string; for_share?: boolean } | null | undefined;

export type ShareTargetState = {
	/** Whether the flag exists at all -- see the note above. */
	supported: boolean;
	/** Whether this work is marked. Meaningless while `supported` is false. */
	marked: boolean;
	/** Whether the mark can be pressed: an unsaved work has nothing to mark. */
	pressable: boolean;
};

export function shareTargetOf(work: ShareTargetWork): ShareTargetState {
	const supported = typeof work?.for_share === 'boolean';
	return {
		supported,
		marked: work?.for_share === true,
		pressable: supported && !!work?.id
	};
}

// The group-sharing mark (ledger I-191) is separate from per-work ACL grants. The canvas
// offers it only when a saved work carries the field and a handler is wired.
// Field presence matters: an absent value is an older response without this
// capability; false means the server supports it and the work is closed.

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

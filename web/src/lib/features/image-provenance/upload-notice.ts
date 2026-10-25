/**
 * The warning before painting from a picture (author, 2026-10-25): the picture
 * goes to the chosen model's provider, so it is said once after each sign-in,
 * before the first picture is painted. An administrator turns it off for
 * everyone in Settings > Other (server); the page reads the switch from
 * /api/client-config.
 *
 * "Once after each sign-in" is kept in this browser per account: the mark is
 * set when the author goes on past the warning and cleared by a sign-in, so a
 * reload of a signed-in page does not ask again.
 */

const ACK_PREFIX = 'inku.imageUploadNotice.ack.';

type StorageLike = Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>;

function storage(): StorageLike | null {
	try {
		return typeof localStorage === 'undefined' ? null : localStorage;
	} catch {
		return null;
	}
}

export function imageUploadNoticeEnabled(value: unknown): boolean {
	if (!value || typeof value !== 'object') return true;
	const enabled = (value as { enabled?: unknown }).enabled;
	return typeof enabled === 'boolean' ? enabled : true;
}

// Read only when a picture is about to be painted, so a plain value is enough.
// On until the Server says otherwise: a failed read errs toward warning.
let noticeEnabled = true;

/** The Server's switch, from /api/client-config or an administrator's save in this tab. */
export function applyImageUploadNotice(value: unknown): void {
	noticeEnabled = imageUploadNoticeEnabled(value);
}

export function uploadNoticeDue(userId: string, store: StorageLike | null = storage()): boolean {
	return noticeEnabled && !uploadNoticeAcknowledged(userId, store);
}

export function uploadNoticeAcknowledged(userId: string, store: StorageLike | null = storage()): boolean {
	try {
		return store?.getItem(ACK_PREFIX + userId) === '1';
	} catch {
		return false;
	}
}

export function acknowledgeUploadNotice(userId: string, store: StorageLike | null = storage()): void {
	try {
		store?.setItem(ACK_PREFIX + userId, '1');
	} catch {
		// Without storage the warning is shown again next time, which is the safe side.
	}
}

/** A sign-in starts over: the next picture is warned about again. */
export function forgetUploadNotice(userId: string, store: StorageLike | null = storage()): void {
	try {
		store?.removeItem(ACK_PREFIX + userId);
	} catch {
		// Nothing was kept, so nothing is left to forget.
	}
}

// What the page makes of its start-up session check.
//
// Only the server saying so means signed out. A proxy's 502 or an API that
// is restarting used to show the sign-in form, which a single-user install
// has no password for; those now wait for the server instead.
export type StartupAnswer = 'signed-in' | 'signed-out' | 'unreachable';

/** `status` is null when the request itself failed. */
export function startupAnswer(status: number | null): StartupAnswer {
	if (status === null) return 'unreachable';
	if (status === 401 || status === 403) return 'signed-out';
	return status >= 200 && status < 300 ? 'signed-in' : 'unreachable';
}

import type { ApiFetch } from '../../transport/api-fetch';

export type ChatGPTProfile = { id: string; label: string; email: string; state: string; generation: number; scopes: string[] };
export type ChatGPTState = { available: boolean; reason: string | null; self_hosted: boolean; active_profile_id: string | null; profiles: ChatGPTProfile[]; pending_registrations?: { id: string; client_id: string }[] };

// What the settings show is the shared core's answer (Sign in with ChatGPT step 2,
// 2026-11-14): this screen keeps only the words and the windows. There is one
// connection, with the one action of its state (the author, 2026-11-14).
export type ChatGPTViewAction = { action: string; enabled: boolean; confirm?: boolean };
export type ChatGPTView = {
	status: string | null;
	label: string | null;
	primary: ChatGPTViewAction | null;
	attempt_actions: ChatGPTViewAction[];
	sign_out: ChatGPTViewAction | null;
	notice: string | null;
	manage_usage: { url: string } | null;
	guide: boolean;
};
export type ChatGPTViewInput = {
	connection: ChatGPTState | null;
	attempt: { active: boolean; can_reopen: boolean; helper: boolean };
	busy: boolean;
	code: string | null;
	last_operation: 'sign_out' | null;
	revocation_confirmed: boolean | null;
};

/** The core's sign-in deadline in the Server's /authorize answer, in milliseconds. */
function deadlineMs(answer: { deadline_seconds?: unknown }): number {
	if (typeof answer.deadline_seconds !== 'number' || !(answer.deadline_seconds > 0)) throw new Error('chatgpt_operation_failed');
	return answer.deadline_seconds * 1000;
}

async function helperBrowser(): Promise<'brave' | 'chrome'> {
	const brave = typeof navigator === 'undefined' ? undefined : (navigator as Navigator & { brave?: { isBrave: () => Promise<boolean> } }).brave;
	if (brave && typeof brave.isBrave === 'function') {
		try { return await brave.isBrave() ? 'brave' : 'chrome'; }
		catch { throw new Error('chatgpt_browser_unavailable'); }
	}
	return 'chrome';
}

export function createChatGPTSettings(deps: {
	apiFetch: ApiFetch;
	owner: () => string | undefined;
	available: () => boolean;
	invalidate: () => void;
	changed: () => void | Promise<void>;
	language?: () => string;
}) {
	let state = $state<ChatGPTState | null>(null);
	let code = $state<string | null>(null);
	let busy = $state(false);
	let authorizationUrl = $state<string | null>(null);
	let helperUrl = $state<string | null>(null);
	let boundOwner = $state<string | undefined>();
	let lastOperation = $state<'sign_out' | null>(null);
	let revocationConfirmed = $state<boolean | null>(null);
	let attemptId: string | null = null;
	let timer: ReturnType<typeof setTimeout> | null = null;
	let epoch = 0;
	let abort: AbortController | null = null;
	let helperBefore: ChatGPTState | null = null;
	let helperChecking = false;
	let catalogFailure = false;
	let finishingAuthorization = false;

	function stop() {
		epoch++;
		abort?.abort();
		if (timer) clearTimeout(timer);
		timer = null;
		attemptId = null;
		authorizationUrl = null;
		helperUrl = null;
		helperBefore = null;
		busy = false;
	}

	function reset() { stop(); state = null; code = null; lastOperation = null; revocationConfirmed = null; catalogFailure = false; boundOwner = undefined; }
	const current = (owner: string | undefined, stamp: number) => Boolean(owner && owner === deps.owner() && stamp === epoch && deps.available());
	const visible = () => boundOwner === deps.owner() && deps.available();
	const kept = () => (state?.profiles.find((profile) => profile.id === state?.active_profile_id) ?? state?.profiles[0])?.id;

	async function call(path: string, body?: unknown) {
		const response = await deps.apiFetch('/api/me/chatgpt' + path, {
			cache: 'no-store', signal: abort?.signal,
			...(body !== undefined ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) } : {})
		});
		const value = await response.json();
		if (!response.ok) throw new Error(typeof value?.detail?.code === 'string' ? value.detail.code : 'chatgpt_operation_failed');
		return value;
	}

	async function refresh(owner: string, stamp: number, preserveCode: string | null = null,
		operation: { name: 'sign_out'; revocationConfirmed: boolean } | null = null) {
		const value = await call('');
		if (!current(owner, stamp)) return;
		state = value; code = preserveCode ?? value.reason;
		lastOperation = operation?.name ?? null; revocationConfirmed = operation?.revocationConfirmed ?? null;
	}

	async function load() {
		const owner = deps.owner();
		if (!owner || !deps.available()) { reset(); return; }
		if (finishingAuthorization && owner === boundOwner) return;
		if (helperUrl && owner === boundOwner) { await recheck(); return; }
		if (owner !== boundOwner) { catalogFailure = false; code = null; }
		await cancel();
		boundOwner = owner;
		const stamp = epoch;
		abort = new AbortController();
		try {
			await refresh(owner, stamp, catalogFailure ? code : null);
		} catch (error) {
			if (current(owner, stamp)) code = error instanceof Error ? error.message : 'chatgpt_operation_failed';
		}
	}

	async function refreshAfterLogin(owner: string, stamp: number) {
		deps.invalidate();
		catalogFailure = false;
		finishingAuthorization = true;
		try {
			const response = await deps.apiFetch('/api/me/chatgpt/models/refresh', { method: 'POST', cache: 'no-store', signal: abort?.signal });
			if (!response.ok) {
				const value = await response.json().catch(() => ({}));
				if (current(owner, stamp)) { code = typeof value?.detail?.code === 'string' ? value.detail.code : 'chatgpt_transport_unavailable'; catalogFailure = true; }
			}
		} catch {
			if (current(owner, stamp)) { code = 'chatgpt_transport_unavailable'; catalogFailure = true; }
		} finally {
			try { if (current(owner, stamp)) await deps.changed(); }
			finally { finishingAuthorization = false; }
		}
	}

	async function mutate(path: string, operation: 'sign_out' | null = null) {
		stop(); deps.invalidate();
		catalogFailure = false;
		const stamp = epoch, owner = deps.owner();
		if (!owner || !deps.available()) return;
		if (owner !== boundOwner) state = null;
		boundOwner = owner;
		abort = new AbortController(); busy = true; code = null; lastOperation = null; revocationConfirmed = null;
		try {
			const result = await call(path, {});
			if (!current(owner, stamp)) return;
			// The core says whether an unconfirmed revocation is reported (sign_in_connection_view).
			await refresh(owner, stamp, null, operation && result.status === 'signed_out'
				? { name: operation, revocationConfirmed: result.revocation_confirmed !== false } : null);
			if (current(owner, stamp)) await deps.changed();
		} catch (error) {
			if (current(owner, stamp)) code = error instanceof Error ? error.message : 'chatgpt_operation_failed';
		} finally { if (current(owner, stamp)) busy = false; }
	}

	async function poll(owner: string, stamp: number, deadline: number) {
		if (!attemptId || !current(owner, stamp)) return;
		try {
			const result = await call('/attempts/' + encodeURIComponent(attemptId));
			if (!current(owner, stamp)) return;
			if (result.status === 'pending' && Date.now() < deadline) {
				timer = setTimeout(() => void poll(owner, stamp, deadline), 1000); return;
			}
			attemptId = null; authorizationUrl = null; busy = false;
			await refresh(owner, stamp, result.status === 'pending' ? 'chatgpt_cancelled' : result.code);
			if (current(owner, stamp) && result.status === 'completed' && state?.active_profile_id === result.profile_id) {
				await refreshAfterLogin(owner, stamp);
			} else if (current(owner, stamp)) await deps.changed();
		} catch (error) { if (current(owner, stamp)) { code = error instanceof Error ? error.message : 'chatgpt_operation_failed'; stop(); } }
	}

	// The server signs in the host's one registration again; `newRegistration` replaces it
	// after the account changed (the core's `new_sign_in`).
	async function authorize(consent = false, newRegistration = false) {
		await cancel();
		catalogFailure = false;
		const stamp = epoch, owner = deps.owner();
		if (!owner || !deps.available()) return;
		if (owner !== boundOwner) state = null;
		boundOwner = owner;
		abort = new AbortController(); busy = true; code = null; lastOperation = null; revocationConfirmed = null;
		try {
			if (!state) {
				await refresh(owner, stamp);
				if (!current(owner, stamp)) return;
			}
			const language = deps.language?.() === 'en' ? 'en' : 'ja';
			const result = await call('/authorize', { consent, new_registration: newRegistration, language });
			if (!current(owner, stamp)) return;
			if (result.action === 'local_helper') {
				if (result.helper_target !== undefined && result.helper_target !== 'container') throw new Error('chatgpt_operation_failed');
				// How long to wait is the core's sign-in deadline, which the Server answers.
				const wait = deadlineMs(result);
				const identifier = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
				if (!identifier.test(owner)) throw new Error('chatgpt_owner_not_allowed');
				const url = new URL('inku-chatgpt://connect');
				url.searchParams.set('owner_id', owner);
				url.searchParams.set('consent', consent ? '1' : '0');
				if (newRegistration) url.searchParams.set('new_registration', '1');
				url.searchParams.set('browser', await helperBrowser());
				url.searchParams.set('language', language);
				if (result.helper_target === 'container') url.searchParams.set('target', 'container');
				if (!current(owner, stamp)) return;
				helperUrl = url.href;
				helperBefore = state;
				code = 'chatgpt_helper_requested'; busy = false;
				window.location.assign(url.href);
				const deadline = Date.now() + wait;
				const watch = async () => {
					if (!current(owner, stamp) || !helperUrl || Date.now() >= deadline) return;
					await recheck();
					if (current(owner, stamp) && helperUrl) timer = setTimeout(() => void watch(), 1000);
				};
				timer = setTimeout(() => void watch(), 1000);
				return;
			}
			// A sign-in again carries the kept id token as `id_token_hint` (OpenAI's advice, the
			// author 2026-11-14); the URL is opened, never logged or stored.
			// The URL is opened only at the core's authorization endpoint, which the Server answers.
			const url = new URL(result.authorization_url);
			if (typeof result.authorization_endpoint !== 'string' || url.origin + url.pathname !== result.authorization_endpoint) throw new Error('chatgpt_operation_failed');
			authorizationUrl = url.href; attemptId = result.attempt_id;
			window.open(url.href, '_blank', 'noopener,noreferrer');
			timer = setTimeout(() => void poll(owner, stamp, Date.now() + deadlineMs(result)), 1000);
		} catch (error) { if (current(owner, stamp)) { code = error instanceof Error ? error.message : 'chatgpt_operation_failed'; busy = false; } }
	}

	// The Mac helper finishes outside this page, so re-read the state when the author comes back,
	// keeping the helper link and its message.
	async function recheck() {
		const owner = deps.owner();
		if (!helperUrl || busy || helperChecking || !owner || owner !== boundOwner || !deps.available()) return;
		const stamp = epoch, before = JSON.stringify(state);
		helperChecking = true;
		try {
			await refresh(owner, stamp, code);
			if (!current(owner, stamp)) return;
			const active = state?.profiles.find((profile) => profile.id === state?.active_profile_id);
			const previous = helperBefore?.profiles.find((profile) => profile.id === active?.id);
			if (active?.state === 'connected' && (!previous || active.generation !== previous.generation)) {
				helperBefore = null; code = null;
				if (timer) clearTimeout(timer);
				timer = null;
				await refreshAfterLogin(owner, stamp);
				if (current(owner, stamp)) helperUrl = null;
			} else if (JSON.stringify(state) !== before) await deps.changed();
		} catch { /* Opening the screen again reads the state and reports errors. */ }
		finally { helperChecking = false; }
	}

	async function cancel() {
		const pending = attemptId;
		const owner = boundOwner;
		stop();
		if (pending && owner === deps.owner() && deps.available()) {
			try { await call('/attempts/' + encodeURIComponent(pending) + '/cancel', {}); } catch { /* The server also expires attempts. */ }
		}
	}

	return {
		get state() { return visible() ? state : null; }, get code() { return visible() ? code : null; }, get busy() { return visible() && busy; },
		get authorizationUrl() { return visible() ? authorizationUrl : null; },
		get helperUrl() { return visible() ? helperUrl : null; },
		get finishingAuthorization() { return visible() && finishingAuthorization; },
		// The state the shared core's view is asked for; the screen asks again whenever it changes.
		get viewInput(): ChatGPTViewInput {
			const shown = visible();
			return {
				connection: shown ? state : null,
				attempt: { active: shown && Boolean(authorizationUrl || helperUrl), can_reopen: shown && Boolean(authorizationUrl), helper: shown && Boolean(helperUrl) },
				busy: shown && busy, code: shown ? code : null,
				last_operation: shown ? lastOperation : null, revocation_confirmed: shown ? revocationConfirmed : null
			};
		},
		async view(input: ChatGPTViewInput): Promise<ChatGPTView> {
			const response = await deps.apiFetch('/api/me/chatgpt/view', {
				method: 'POST', cache: 'no-store', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(input)
			});
			const value = await response.json();
			if (!response.ok) throw new Error(typeof value?.detail?.code === 'string' ? value.detail.code : 'chatgpt_operation_failed');
			return value as ChatGPTView;
		},
		load, reset, stop, cancel, authorize, recheck,
		// The one registration the server keeps (the active one, or the only one).
		signOut: () => mutate('/profiles/' + encodeURIComponent(kept() ?? '') + '/sign-out', 'sign_out'),
		retry: () => mutate('/profiles/' + encodeURIComponent(kept() ?? '') + '/retry')
	};
}

export type ChatGPTSettingsController = ReturnType<typeof createChatGPTSettings>;

import type { ApiFetch } from '../../transport/api-fetch';

export type ChatGPTProfile = { id: string; label: string; email: string; state: string; generation: number; scopes: string[] };
export type ChatGPTState = { available: boolean; reason: string | null; self_hosted: boolean; active_profile_id: string | null; profiles: ChatGPTProfile[]; pending_registrations?: { id: string; client_id: string }[] };

export function createChatGPTSettings(deps: {
	apiFetch: ApiFetch;
	owner: () => string | undefined;
	available: () => boolean;
	invalidate: () => void;
	changed: () => void | Promise<void>;
}) {
	let state = $state<ChatGPTState | null>(null);
	let code = $state<string | null>(null);
	let busy = $state(false);
	let authorizationUrl = $state<string | null>(null);
	let helperUrl = $state<string | null>(null);
	let boundOwner = $state<string | undefined>();
	let attemptId: string | null = null;
	let timer: ReturnType<typeof setTimeout> | null = null;
	let epoch = 0;
	let abort: AbortController | null = null;

	function stop() {
		epoch++;
		abort?.abort();
		if (timer) clearTimeout(timer);
		timer = null;
		attemptId = null;
		authorizationUrl = null;
		helperUrl = null;
		busy = false;
	}

	function reset() { stop(); state = null; code = null; boundOwner = undefined; }
	const current = (owner: string | undefined, stamp: number) => Boolean(owner && owner === deps.owner() && stamp === epoch && deps.available());
	const visible = () => boundOwner === deps.owner() && deps.available();

	async function call(path: string, body?: unknown) {
		const response = await deps.apiFetch('/api/me/chatgpt' + path, {
			cache: 'no-store', signal: abort?.signal,
			...(body !== undefined ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) } : {})
		});
		const value = await response.json();
		if (!response.ok) throw new Error(typeof value?.detail?.code === 'string' ? value.detail.code : 'chatgpt_operation_failed');
		return value;
	}

	async function refresh(owner: string, stamp: number, preserveCode: string | null = null) {
		const value = await call('');
		if (!current(owner, stamp)) return;
		state = value; code = preserveCode ?? value.reason;
	}

	async function load() {
		const owner = deps.owner();
		if (!owner || !deps.available()) { reset(); return; }
		await cancel();
		boundOwner = owner;
		const stamp = epoch;
		abort = new AbortController();
		try {
			await refresh(owner, stamp);
		} catch (error) {
			if (current(owner, stamp)) code = error instanceof Error ? error.message : 'chatgpt_operation_failed';
		}
	}

	async function mutate(path: string) {
		stop(); deps.invalidate();
		const stamp = epoch, owner = deps.owner();
		if (!owner || !deps.available()) return;
		boundOwner = owner;
		abort = new AbortController(); busy = true; code = null;
		try {
			const result = await call(path, {});
			if (!current(owner, stamp)) return;
			await refresh(owner, stamp, result.status === 'signed_out' && !result.revocation_confirmed ? 'chatgpt_revocation_unconfirmed' : null);
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
			if (current(owner, stamp)) await deps.changed();
		} catch (error) { if (current(owner, stamp)) { code = error instanceof Error ? error.message : 'chatgpt_operation_failed'; stop(); } }
	}

	async function authorize(profileId?: string, consent = false) {
		await cancel();
		const stamp = epoch, owner = deps.owner();
		if (!owner || !deps.available()) return;
		boundOwner = owner;
		abort = new AbortController(); busy = true; code = null;
		try {
			const result = await call('/authorize', { profile_id: profileId ?? null, consent });
			if (!current(owner, stamp)) return;
			if (result.action === 'local_helper') {
				const identifier = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
				if (!identifier.test(owner) || (profileId && !identifier.test(profileId))) throw new Error('chatgpt_owner_not_allowed');
				const url = new URL('inku-chatgpt://connect');
				url.searchParams.set('owner_id', owner);
				url.searchParams.set('consent', consent ? '1' : '0');
				if (profileId) url.searchParams.set('profile_id', profileId);
				helperUrl = url.href;
				code = 'chatgpt_helper_requested'; busy = false;
				window.location.assign(url.href);
				return;
			}
			const url = new URL(result.authorization_url);
			if (url.origin !== 'https://auth.openai.com' || url.pathname !== '/api/accounts/authorize' || url.searchParams.has('id_token_hint')) throw new Error('chatgpt_operation_failed');
			authorizationUrl = url.href; attemptId = result.attempt_id;
			window.open(url.href, '_blank', 'noopener,noreferrer');
			timer = setTimeout(() => void poll(owner, stamp, Date.now() + 300_000), 1000);
		} catch (error) { if (current(owner, stamp)) { code = error instanceof Error ? error.message : 'chatgpt_operation_failed'; busy = false; } }
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
		load, reset, stop, cancel, authorize,
		select: (id: string) => mutate('/profiles/' + encodeURIComponent(id) + '/select'),
		signOut: (id: string) => mutate('/profiles/' + encodeURIComponent(id) + '/sign-out'),
		retry: (id: string) => mutate('/profiles/' + encodeURIComponent(id) + '/retry'),
		refreshModels: () => mutate('/models/refresh')
	};
}

export type ChatGPTSettingsController = ReturnType<typeof createChatGPTSettings>;

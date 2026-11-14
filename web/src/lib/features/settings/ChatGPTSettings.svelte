<script lang="ts">
	import { onDestroy, onMount } from 'svelte';
	import { t } from '$lib/i18n/index.svelte';
	import type { ChatGPTSettingsController, ChatGPTView, ChatGPTViewAction } from './chatgpt.svelte';
	// `initialView` is an answer already in hand, for a server render, where no effect runs.
	let { connection, onOpenModelSettings, initialView = null }: {
		connection: Pick<ChatGPTSettingsController, 'state' | 'busy' | 'viewInput' | 'view' | 'load' | 'cancel' | 'recheck' | 'authorize'
			| 'select' | 'signOut' | 'remove' | 'retry' | 'authorizationUrl' | 'helperUrl' | 'finishingAuthorization'>;
		onOpenModelSettings: () => void; initialView?: ChatGPTView | null;
	} = $props();

	// The status line, which actions show and whether they can be pressed, each profile's
	// status and the guide come from the shared core (Sign in with ChatGPT step 2,
	// 2026-11-14). Until the answer matches the current state, nothing can be pressed.
	const inputKey = $derived(JSON.stringify(connection.viewInput));
	// svelte-ignore state_referenced_locally
	let view = $state<ChatGPTView | null>(initialView);
	// svelte-ignore state_referenced_locally
	let viewKey = $state(initialView ? inputKey : '');
	let asked = '';
	$effect(() => {
		const key = inputKey, input = JSON.parse(key);
		asked = key;
		void connection.view(input).then((answer) => { if (asked === key) { view = answer; viewKey = key; } }).catch(() => {});
	});
	const fresh = $derived(view !== null && viewKey === inputKey);
	const top = (name: string) => view?.actions.find((item) => item.action === name);
	const can = (item: ChatGPTViewAction | undefined) => fresh && item?.enabled === true;
	const actionOf = (actions: ChatGPTViewAction[], name: string) => actions.find((item) => item.action === name);

	// An action the core marks `confirm` (sign out, delete) asks first, in two steps.
	let confirming = $state<{ profile: string; action: 'sign_out' | 'delete' } | null>(null);
	function press(profile: string, item: ChatGPTViewAction) {
		if (item.confirm && (item.action === 'sign_out' || item.action === 'delete')) { confirming = { profile, action: item.action }; return; }
		run(profile, item.action);
	}
	function run(profile: string, action: string) {
		if (action === 'select') void connection.select(profile);
		else if (action === 'reauthenticate') void connection.authorize(profile);
		else if (action === 'grant_plan') void connection.authorize(profile, true);
		else if (action === 'retry') void connection.retry(profile);
		else if (action === 'sign_out') void connection.signOut(profile);
		else if (action === 'delete') void connection.remove(profile);
	}
	const PROFILE_LABELS: Record<string, () => string> = {
		select: () => t().chatgptSelect, reauthenticate: () => t().chatgptReconnect, grant_plan: () => t().chatgptGrantPlan,
		retry: () => t().chatgptRetry, sign_out: () => t().chatgptSignOut, delete: () => t().chatgptDelete
	};

	const recheck = () => { if (document.visibilityState === 'visible') void connection.recheck(); };
	onMount(() => {
		void connection.load();
		window.addEventListener('focus', recheck);
		document.addEventListener('visibilitychange', recheck);
		return () => { window.removeEventListener('focus', recheck); document.removeEventListener('visibilitychange', recheck); };
	});
	onDestroy(() => { if (!connection.helperUrl && !connection.finishingAuthorization) void connection.cancel(); });
</script>

<section class="chatgpt-connection" aria-busy={connection.busy}>
	<p>{t().chatgptPlanNotice}</p>
	{#if connection.state?.self_hosted}<p>{t().chatgptLocalHelperHint}</p>{/if}
	{#if view?.status}<p role="status">{t().chatgptStatus(view.status)}</p>{/if}
	<div class="actions">
		{#if top('sign_in')}<button class="ghost-btn" disabled={!can(top('sign_in'))} onclick={() => void connection.authorize()}>{connection.state?.self_hosted ? t().chatgptConnectHelper : t().chatgptSignIn}</button>{/if}
		{#if top('check_connection')}<button class="ghost-btn" disabled={!can(top('check_connection'))} onclick={() => void connection.load()}>{t().chatgptCheckConnection}</button>{/if}
		{#if top('manage_usage')}<a href={top('manage_usage')?.url} target="_blank" rel="noopener noreferrer">{t().chatgptManageUsage}</a>{/if}
	</div>
	{#if top('reopen_sign_in') && connection.authorizationUrl}
		<a href={connection.authorizationUrl} target="_blank" rel="noopener noreferrer">{t().chatgptReopenSignIn}</a>
	{/if}
	{#if top('cancel')}<button class="ghost-btn" disabled={!can(top('cancel'))} onclick={() => void connection.cancel()}>{t().pipelineCancel}</button>{/if}
	{#if top('reopen_helper') && connection.helperUrl}
		<a href={connection.helperUrl}>{t().chatgptReopenHelper}</a>
	{/if}
	{#each view?.pending ?? [] as pending (pending.id)}
		<button class="ghost-btn" disabled={!can(actionOf(pending.actions, 'reconnect'))} onclick={() => void connection.authorize(pending.id)}>{t().chatgptReconnect} ({pending.client_id})</button>
	{/each}
	{#each view?.profiles ?? [] as profile (profile.id)}
		<section class="profile">
			<p><strong>{profile.label}</strong> {profile.active ? t().chatgptActive : ''}</p>
			<p>{t().chatgptStatus(profile.status)}</p>
			<div class="actions">
				{#each profile.actions as item (item.action)}
					{#if !(confirming?.profile === profile.id && confirming.action === item.action)}
						<button class="ghost-btn" disabled={!can(item)} onclick={() => press(profile.id, item)}>{PROFILE_LABELS[item.action]?.() ?? item.action}</button>
					{/if}
				{/each}
			</div>
			{#if confirming?.profile === profile.id}
				{@const action = confirming.action}
				<div class="actions" role="group" aria-label={action === 'delete' ? t().chatgptDelete : t().chatgptSignOut}>
					<span>{action === 'delete' ? t().chatgptDeleteConfirmText : t().chatgptSignOutConfirmText}</span>
					<button class="ghost-btn danger" disabled={!can(actionOf(profile.actions, action))} onclick={() => { confirming = null; run(profile.id, action); }}>{action === 'delete' ? t().chatgptDeleteConfirm : t().chatgptSignOutConfirm}</button>
					<button class="ghost-btn" onclick={() => { confirming = null; }}>{t().chatgptDeleteCancel}</button>
				</div>
			{/if}
		</section>
	{/each}
	{#if view?.guide}
		<p role="status">{t().chatgptModelSettingsGuide}</p>
		<button class="ghost-btn" onclick={onOpenModelSettings}>{t().chatgptOpenModelSettings}</button>
	{/if}
</section>

<style>
	.chatgpt-connection { display: grid; gap: 1rem; }
	.actions { display: flex; flex-wrap: wrap; align-items: center; gap: .5rem; }
	.profile { border-top: 1px solid var(--border); padding-top: .75rem; }
	.danger { color: var(--danger); border-color: color-mix(in srgb, var(--danger) 48%, var(--border2)); }
</style>

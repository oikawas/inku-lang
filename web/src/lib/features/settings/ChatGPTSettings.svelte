<script lang="ts">
	import { onDestroy, onMount } from 'svelte';
	import { t } from '$lib/i18n/index.svelte';
	import type { ChatGPTSettingsController, ChatGPTView, ChatGPTViewAction } from './chatgpt.svelte';
	// `initialView` is an answer already in hand, for a server render, where no effect runs.
	let { connection, onOpenModelSettings, initialView = null }: {
		connection: Pick<ChatGPTSettingsController, 'state' | 'busy' | 'viewInput' | 'view' | 'load' | 'cancel' | 'recheck' | 'authorize'
			| 'signOut' | 'retry' | 'authorizationUrl' | 'helperUrl' | 'finishingAuthorization'>;
		onOpenModelSettings: () => void; initialView?: ChatGPTView | null;
	} = $props();

	// One connection, with the one action of its state (the author, 2026-11-14). The status
	// line, that action, sign-out and the notice are the shared core's answer, asked again
	// from the current state each time, so nothing of an earlier operation lingers. Until the
	// answer matches the current state, nothing can be pressed.
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
	const can = (item: ChatGPTViewAction | null | undefined) => fresh && item?.enabled === true;
	const attemptAction = (name: string) => view?.attempt_actions.find((item) => item.action === name);

	function primaryLabel(action: string): string {
		if (action === 'grant_plan') return t().chatgptGrantPlan;
		if (action === 'retry') return t().chatgptRetry;
		if (action === 'new_sign_in') return t().chatgptNewSignIn;
		return connection.state?.self_hosted ? t().chatgptConnectHelper : t().chatgptSignIn;
	}
	function runPrimary(action: string) {
		if (action === 'retry') void connection.retry();
		else void connection.authorize(action === 'grant_plan', action === 'new_sign_in');
	}

	// Sign-out stands apart and asks first.
	let confirming = $state(false);

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
	{#if view?.label}<p><strong>{view.label}</strong></p>{/if}
	<div class="actions">
		{#if view?.primary}
			{@const primary = view.primary}
			<button class="ghost-btn" disabled={!can(primary)} onclick={() => runPrimary(primary.action)}>{primaryLabel(primary.action)}</button>
		{/if}
		{#if attemptAction('reopen_sign_in') && connection.authorizationUrl}
			<a href={connection.authorizationUrl} target="_blank" rel="noopener noreferrer">{t().chatgptReopenSignIn}</a>
		{/if}
		{#if attemptAction('cancel')}<button class="ghost-btn" disabled={!can(attemptAction('cancel'))} onclick={() => void connection.cancel()}>{t().pipelineCancel}</button>{/if}
		{#if attemptAction('reopen_helper') && connection.helperUrl}
			<a href={connection.helperUrl}>{t().chatgptReopenHelper}</a>
		{/if}
		{#if view?.manage_usage}<a href={view.manage_usage.url} target="_blank" rel="noopener noreferrer">{t().chatgptManageUsage}</a>{/if}
	</div>
	{#if view?.guide}
		<p>{t().chatgptModelSettingsGuide}</p>
		<div class="actions"><button class="ghost-btn" onclick={onOpenModelSettings}>{t().chatgptOpenModelSettings}</button></div>
	{/if}
	{#if view?.sign_out || view?.notice}
		<section class="sign-out">
			{#if view?.sign_out}
				{@const signOut = view.sign_out}
				{#if confirming}
					<div class="actions" role="group" aria-label={t().chatgptSignOut}>
						<span>{t().chatgptSignOutConfirmText}</span>
						<button class="ghost-btn danger" disabled={!can(signOut)} onclick={() => { confirming = false; void connection.signOut(); }}>{t().chatgptSignOutConfirm}</button>
						<button class="ghost-btn" onclick={() => { confirming = false; }}>{t().chatgptSignOutCancel}</button>
					</div>
				{:else}
					<div class="actions"><button class="ghost-btn danger" disabled={!can(signOut)} onclick={() => { if (signOut.confirm) confirming = true; else void connection.signOut(); }}>{t().chatgptSignOut}</button></div>
				{/if}
			{/if}
			{#if view?.notice}<p class="notice">{t().chatgptStatus(view.notice)}</p>{/if}
		</section>
	{/if}
</section>

<style>
	.chatgpt-connection { display: grid; gap: 1rem; }
	.actions { display: flex; flex-wrap: wrap; align-items: center; gap: .5rem; }
	.sign-out { display: grid; gap: .5rem; border-top: 1px solid var(--border); padding-top: .75rem; margin-top: .5rem; }
	.notice { color: var(--fg2); font-size: .9em; }
	.danger { color: var(--danger); border-color: color-mix(in srgb, var(--danger) 48%, var(--border2)); }
</style>

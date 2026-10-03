<script lang="ts">
	import { onDestroy, onMount } from 'svelte';
	import { t } from '$lib/i18n/index.svelte';
	import type { ChatGPTSettingsController } from './chatgpt.svelte';
	let { connection }: { connection: ChatGPTSettingsController } = $props();
	onMount(() => { void connection.load(); });
	onDestroy(() => { void connection.cancel(); });
</script>

<section class="chatgpt-connection">
	<p>{t().chatgptPlanNotice}</p>
	{#if connection.state?.self_hosted}<p>{t().chatgptLocalHelperHint}</p>{/if}
	{#if connection.code}<p role="status">{t().chatgptStatus(connection.code)}</p>{/if}
	<div class="actions">
		<button class="ghost-btn" disabled={connection.busy} onclick={() => void connection.authorize()}>{t().chatgptContinue}</button>
		<button class="ghost-btn" disabled={connection.busy} onclick={() => void connection.load()}>{t().chatgptCheckConnection}</button>
		<a href="https://chatgpt.com/settings/usage" target="_blank" rel="noopener noreferrer">{t().chatgptManageUsage}</a>
	</div>
	{#if connection.authorizationUrl}
		<a href={connection.authorizationUrl} target="_blank" rel="noopener noreferrer">{t().chatgptContinue}</a>
		<button class="ghost-btn" onclick={() => void connection.cancel()}>{t().pipelineCancel}</button>
	{/if}
	{#if connection.helperUrl}
		<a href={connection.helperUrl}>{t().chatgptContinue}</a>
	{/if}
	{#each connection.state?.pending_registrations ?? [] as pending (pending.id)}
		<button class="ghost-btn" disabled={connection.busy} onclick={() => void connection.authorize(pending.id)}>{t().chatgptReconnect} ({pending.client_id})</button>
	{/each}
	{#each connection.state?.profiles ?? [] as profile (profile.id)}
		<section class="profile">
			<p><strong>{profile.label}</strong> {profile.id === connection.state?.active_profile_id ? t().chatgptActive : ''}</p>
			<p>{t().chatgptStatus(profile.state === 'connected' && !profile.scopes.includes('chatgpt.tokens.use.direct') ? 'chatgpt_scope_required' : 'chatgpt_' + profile.state)}</p>
			<div class="actions">
				<button class="ghost-btn" disabled={connection.busy} onclick={() => void connection.select(profile.id)}>{t().chatgptSelect}</button>
				<button class="ghost-btn" disabled={connection.busy} onclick={() => void connection.authorize(profile.id)}>{t().chatgptReconnect}</button>
				{#if !profile.scopes.includes('chatgpt.tokens.use.direct')}
					<button class="ghost-btn" disabled={connection.busy} onclick={() => void connection.authorize(profile.id, true)}>{t().chatgptGrantPlan}</button>
				{/if}
				{#if profile.state === 'quota'}<button class="ghost-btn" disabled={connection.busy} onclick={() => void connection.retry(profile.id)}>{t().chatgptRetry}</button>{/if}
				<button class="ghost-btn" disabled={connection.busy} onclick={() => void connection.signOut(profile.id)}>{t().chatgptSignOut}</button>
			</div>
		</section>
	{/each}
	<button class="ghost-btn" disabled={connection.busy || !connection.state?.active_profile_id} onclick={() => void connection.refreshModels()}>{t().chatgptRefreshModels}</button>
</section>

<style>
	.chatgpt-connection { display: grid; gap: 1rem; }
	.actions { display: flex; flex-wrap: wrap; align-items: center; gap: .5rem; }
	.profile { border-top: 1px solid var(--border); padding-top: .75rem; }
</style>

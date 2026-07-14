<script lang="ts">
	import { onMount } from 'svelte';
	import { t } from '$lib/i18n/index.svelte';

	type UnreadWord = { word: string; frequency: number; first_at: number; last_at: number; contexts: string[]; user_count?: number };
	type Scope = 'mine' | 'all';

	let { isAdmin = false }: { isAdmin?: boolean } = $props();
	let scope = $state<Scope>('mine');
	let items = $state<UnreadWord[]>([]);
	let loading = $state(false);
	let error = $state<string | null>(null);
	let requestId = 0;

	function formatTimestamp(ms: number): string { return ms ? new Date(ms).toLocaleString() : '-'; }

	async function load(nextScope: Scope = scope): Promise<void> {
		const normalizedScope: Scope = isAdmin && nextScope === 'all' ? 'all' : 'mine';
		scope = normalizedScope;
		const currentRequest = ++requestId;
		loading = true;
		error = null;
		try {
			const path = normalizedScope === 'all' ? '/api/admin/unread-words?limit=2000' : '/api/feedback/unread-words?limit=500';
			const response = await fetch(path, { cache: 'no-store', credentials: 'same-origin' });
			if (!response.ok) throw new Error(`HTTP ${response.status}`);
			const data = await response.json();
			if (currentRequest === requestId) items = Array.isArray(data) ? data : [];
		} catch (cause) {
			if (currentRequest === requestId) {
				items = [];
				error = cause instanceof Error ? cause.message : String(cause);
			}
		} finally {
			if (currentRequest === requestId) loading = false;
		}
	}

	onMount(() => { void load(); });
</script>

<div class="popover-group unread-ledger">
	<div class="unread-head">
		<div>
			<div class="popover-group-label">{t().settingsUnreadWordsTitle}</div>
			<div class="unread-note">{t().settingsUnreadWordsDescription}</div>
		</div>
		<div class="unread-actions">
			{#if isAdmin}
				<div class="scope-toggle" aria-label={t().settingsUnreadWordsScope}>
					<button type="button" class:active={scope === 'mine'} onclick={() => void load('mine')}>{t().settingsUnreadWordsMine}</button>
					<button type="button" class:active={scope === 'all'} onclick={() => void load('all')}>{t().settingsUnreadWordsAll}</button>
				</div>
			{/if}
			<button type="button" class="ghost-btn" onclick={() => void load()} disabled={loading}>{t().settingsUnreadWordsReload}</button>
		</div>
	</div>

	{#if loading}
		<div class="inline-message">{t().settingsLoading}</div>
	{:else if error}
		<div class="inline-message error">{t().settingsUnreadWordsLoadFailed}: {error}</div>
	{:else if items.length === 0}
		<div class="inline-message">{t().settingsUnreadWordsEmpty}</div>
	{:else}
		<div class="unread-count">{t().settingsUnreadWordsCount(items.length)}</div>
		<div class="unread-table-wrap">
			<table>
				<thead><tr>
					<th>{t().settingsUnreadWordsWord}</th>
					<th class="numeric">{t().settingsUnreadWordsFrequency}</th>
					{#if scope === 'all'}<th class="numeric">{t().settingsUnreadWordsUsers}</th>{/if}
					<th>{t().settingsUnreadWordsLastSeen}</th>
					<th>{t().settingsUnreadWordsContexts}</th>
				</tr></thead>
				<tbody>
					{#each items as item (item.word)}
						<tr>
							<td class="word">{item.word}</td>
							<td class="numeric">{item.frequency}</td>
							{#if scope === 'all'}<td class="numeric">{item.user_count ?? 0}</td>{/if}
							<td class="timestamp" title={`${t().settingsUnreadWordsFirstSeen}: ${formatTimestamp(item.first_at)}`}>{formatTimestamp(item.last_at)}</td>
							<td class="contexts">
								{#each item.contexts ?? [] as context}<div title={context}>{context}</div>{/each}
							</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</div>
	{/if}
</div>

<style>
	.unread-ledger { min-height: 260px; }
	.unread-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; margin-bottom: 12px; }
	.popover-group-label { font-size: 10px; color: var(--fg3); text-transform: uppercase; letter-spacing: 0.08em; font-weight: 500; margin-bottom: 7px; }
	.unread-note { color: var(--fg2); font-size: 12px; line-height: 1.55; }
	.unread-actions { display: flex; align-items: center; gap: 8px; flex: 0 0 auto; }
	.scope-toggle { display: inline-flex; border: 1px solid var(--border2); border-radius: var(--r); overflow: hidden; }
	.scope-toggle button { border: 0; border-right: 1px solid var(--border2); padding: 5px 9px; background: var(--panel); color: var(--fg2); cursor: pointer; font: inherit; font-size: 12px; }
	.scope-toggle button:last-child { border-right: 0; }
	.scope-toggle button.active { background: var(--accent); color: var(--bg); }
	.ghost-btn { border: 1px solid var(--border2); border-radius: var(--r); padding: 5px 9px; background: var(--panel); color: var(--fg2); cursor: pointer; font: inherit; font-size: 12px; }
	.ghost-btn:disabled { opacity: 0.55; cursor: default; }
	.inline-message { color: var(--fg2); font-size: 12px; padding: 12px 0; }
	.inline-message.error { color: var(--danger, #b33); }
	.unread-count { color: var(--fg3); font-size: 11px; margin-bottom: 6px; text-align: right; }
	.unread-table-wrap { overflow: auto; max-height: 55vh; border: 1px solid var(--border); border-radius: var(--r); }
	table { width: 100%; border-collapse: collapse; font-size: 12px; }
	th, td { padding: 7px 8px; border-bottom: 1px solid var(--border); text-align: left; vertical-align: top; }
	th { position: sticky; top: 0; z-index: 1; background: var(--bg); color: var(--fg3); font-weight: 500; white-space: nowrap; }
	tbody tr:last-child td { border-bottom: 0; }
	.numeric { text-align: right; font-variant-numeric: tabular-nums; }
	.word { color: var(--fg); font-weight: 600; max-width: 150px; overflow-wrap: anywhere; }
	.timestamp { color: var(--fg2); white-space: nowrap; }
	.contexts { min-width: 260px; color: var(--fg2); }
	.contexts div { max-width: 440px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
	.contexts div + div { margin-top: 4px; }
	@media (max-width: 720px) { .unread-head { flex-direction: column; } .unread-actions { width: 100%; justify-content: space-between; } .timestamp { white-space: normal; min-width: 130px; } }
</style>

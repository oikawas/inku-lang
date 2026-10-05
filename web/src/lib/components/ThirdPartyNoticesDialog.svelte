<script lang="ts">
	import { onMount } from 'svelte';
	import { t } from '$lib/i18n/index.svelte';
	import { NOTICE_GROUPS, type NoticeGroup, type NoticeState } from '$lib/third-party-notices';

	let { state, onSelect, onReload, onRetryText, onClose }: {
		state: NoticeState;
		onSelect: (id: string) => void;
		onReload: () => void;
		onRetryText: () => void;
		onClose: () => void;
	} = $props();
	let dialog: HTMLElement;
	let closeButton: HTMLButtonElement;
	const selected = $derived(state.components.find((item) => item.id === state.selectedId));
	const groupTitle = (group: NoticeGroup) => ({
		inku: 'inku', web: t().noticesGroupWeb, server: t().noticesGroupServer,
		resources: t().noticesGroupResources, rust: t().noticesGroupRust,
	})[group];

	onMount(() => closeButton.focus());
	function keydown(event: KeyboardEvent) {
		if (event.key === 'Escape') {
			event.preventDefault();
			event.stopPropagation();
			onClose();
		} else if (event.key === 'Tab') {
			const targets = Array.from(dialog.querySelectorAll<HTMLElement>('button:not(:disabled), a[href], textarea:not(:disabled)'));
			const first = targets[0], last = targets[targets.length - 1];
			if (event.shiftKey && (document.activeElement === first || document.activeElement === dialog)) {
				event.preventDefault(); last?.focus();
			} else if (!event.shiftKey && document.activeElement === last) {
				event.preventDefault(); first?.focus();
			}
		}
	}
</script>

<div class="notices-backdrop" onclick={onClose} aria-hidden="true"></div>
<div class="notices-dialog" role="dialog" aria-modal="true" aria-labelledby="notices-title"
	bind:this={dialog} tabindex="-1" onkeydown={keydown}>
	<header>
		<h2 id="notices-title">{t().noticesTitle}</h2>
		<button type="button" class="ghost-btn" bind:this={closeButton} onclick={onClose}>{t().appInfoClose}</button>
	</header>
	{#if state.failedGroups.length}
		<div class="catalog-error" role="status">
			<span>{t().noticesCatalogFailed(state.failedGroups.map(groupTitle).join(' / '))}</span>
			<button type="button" class="ghost-btn" onclick={onReload} disabled={state.loading}>{t().noticesRetry}</button>
		</div>
	{/if}
	{#if state.loading}
		<p class="status" role="status">{t().noticesLoading}</p>
	{:else}
		<div class="notices-columns">
			<nav aria-label={t().noticesList}>
				{#each NOTICE_GROUPS as group}
					{@const items = state.components.filter((item) => item.group === group)}
					{#if items.length}
						<h3>{groupTitle(group)}</h3>
						<ul>
							{#each items as item (item.id)}
								<li><button type="button" class:selected={state.selectedId === item.id}
									aria-pressed={state.selectedId === item.id} onclick={() => onSelect(item.id)}>
									<span class="name">{item.name}</span>
									<span class="summary">{[item.version, item.license].filter(Boolean).join(' · ')}</span>
								</button></li>
							{/each}
						</ul>
					{/if}
				{/each}
			</nav>
			<div class="notice-detail">
				{#if selected}
					<h3>{selected.name}{selected.version ? ` ${selected.version}` : ''}</h3>
					<dl>
						{#if selected.license}<div><dt>{t().appInfoLicenseTitle}</dt><dd>{selected.license}</dd></div>{/if}
						<div><dt>{t().noticesSource}</dt><dd><a href={selected.source} target="_blank" rel="noopener noreferrer">{selected.source}</a></dd></div>
					</dl>
					{#if state.textLoading}
						<p class="status" role="status">{t().noticesLoading}</p>
					{:else if state.textFailed}
						<div class="status" role="status">
							<p>{t().noticesTextFailed}</p>
							<button type="button" class="ghost-btn" onclick={onRetryText}>{t().noticesRetry}</button>
						</div>
					{:else}
						<textarea class="notice-text" readonly aria-label={t().noticesText} value={state.text}></textarea>
					{/if}
				{:else}
					<p class="status">{t().noticesSelect}</p>
				{/if}
			</div>
		</div>
	{/if}
</div>

<style>
	.notices-backdrop { position: fixed; inset: 0; z-index: 710; background: rgba(0, 0, 0, 0.25); }
	.notices-dialog { position: fixed; top: 50%; left: 50%; transform: translate(-50%, -50%); z-index: 711;
		width: min(960px, calc(100vw - 32px)); height: min(640px, calc(100dvh - 32px));
		display: flex; flex-direction: column; overflow: hidden; background: var(--panel2); color: var(--fg);
		border: 1px solid var(--border); border-radius: var(--r-lg); box-shadow: 0 18px 56px rgba(0, 0, 0, 0.24); }
	header { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 12px 16px; border-bottom: 1px solid var(--border); }
	h2 { margin: 0; font-size: var(--ui-font-size-14); font-weight: 500; }
	button:disabled { opacity: 0.5; cursor: default; }
	button:focus-visible, a:focus-visible, .notice-text:focus-visible { outline: 2px solid var(--accent); outline-offset: -2px; }
	.catalog-error { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 8px 16px;
		font-size: var(--ui-font-size-12); border-bottom: 1px solid var(--border); color: var(--fg2); }
	.notices-columns { flex: 1; display: grid; grid-template-columns: 260px minmax(0, 1fr); min-height: 0; }
	nav { overflow: auto; border-right: 1px solid var(--border); padding: 12px 8px; }
	nav h3 { margin: 12px 8px 6px; font-size: var(--ui-font-size-11); font-weight: 500; color: var(--fg3); }
	nav h3:first-child { margin-top: 0; }
	ul { margin: 0; padding: 0; list-style: none; }
	li button { display: flex; flex-direction: column; width: 100%; text-align: left; gap: 3px; padding: 8px;
		font-family: inherit; color: var(--fg); background: transparent; border: 1px solid transparent; border-radius: var(--r); cursor: pointer; }
	li button:hover { background: var(--panel); }
	li button.selected { border-color: var(--accent); background: var(--panel); }
	.name { font-size: var(--ui-font-size-12); overflow-wrap: anywhere; }
	.summary { font-size: var(--ui-font-size-10); color: var(--fg3); overflow-wrap: anywhere; }
	.notice-detail { display: flex; flex-direction: column; gap: 8px; padding: 16px; min-width: 0; min-height: 0; }
	.notice-detail h3 { margin: 0; font-size: var(--ui-font-size-14); font-weight: 500; overflow-wrap: anywhere; }
	dl { margin: 0; font-size: var(--ui-font-size-12); line-height: 1.6; }
	dl div { display: grid; grid-template-columns: auto minmax(0, 1fr); gap: 12px; }
	dt { color: var(--fg3); }
	dd { margin: 0; overflow-wrap: anywhere; }
	a { color: var(--accent); }
	.notice-text { flex: 1; overflow: auto; min-height: 0; width: 100%; box-sizing: border-box; resize: none;
		padding: 10px; border: 1px solid var(--border); background: var(--panel); color: var(--fg);
		font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
		font-size: var(--ui-font-size-11); line-height: 1.65; white-space: pre-wrap; overflow-wrap: anywhere; user-select: text; }
	.status { margin: auto; padding: 16px; color: var(--fg2); font-size: var(--ui-font-size-12); }
	.status p { margin-top: 0; }
	@media (max-width: 640px) {
		.notices-columns { grid-template-columns: minmax(0, 1fr); grid-template-rows: minmax(100px, 26%) minmax(0, 1fr); }
		nav { border-right: 0; border-bottom: 1px solid var(--border); }
		.notice-detail { padding: 12px; }
	}
</style>

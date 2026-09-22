<script module lang="ts">
	export type WorkAction = 'adjust' | 'description' | 'instructions' | 'sketch-grain' | 'models' | 'autonomous';

	let lastWorkActionTrigger: HTMLButtonElement | null = null;

	export function restoreWorkActionFocus(): boolean {
		if (!lastWorkActionTrigger?.isConnected) return false;
		lastWorkActionTrigger.focus();
		return true;
	}
</script>

<script lang="ts">
	import { tick } from 'svelte';
	import { t } from '$lib/i18n/index.svelte';
	import type { LineageNode } from '$lib/features/history/types';

	type Props = {
		node: LineageNode | null;
		isJapanese: boolean;
		variant: 'card' | 'header';
		open: boolean;
		available?: boolean;
		unavailableReason?: string;
		onRequestOpen?: () => void | Promise<void>;
		onOpenChange: (open: boolean) => void;
		onAction: (action: WorkAction, node: LineageNode) => void | Promise<void>;
	};

	let { node, isJapanese, variant, open, available = undefined, unavailableReason, onRequestOpen, onOpenChange, onAction }: Props = $props();
	let triggerEl = $state<HTMLButtonElement | null>(null);
	let menuEl = $state<HTMLDivElement | null>(null);
	let wrapperEl = $state<HTMLDivElement | null>(null);
	$effect(() => {
		if (open && node) void tick().then(() => menuEl?.querySelector<HTMLButtonElement>('button')?.focus());
	});

	const ddlOrigin = $derived(node?.history?.display_label === 'DDL');
	const enabled = $derived(available ?? (!!node?.history?.id && !node?.history?.trashed));

	function toggle(event: MouseEvent): void {
		event.stopPropagation();
		if (!enabled) return;
		if (!open && onRequestOpen) {
			void onRequestOpen();
			return;
		}
		onOpenChange(!open);
	}

	function select(action: WorkAction, event: MouseEvent): void {
		event.stopPropagation();
		if (!node) return;
		lastWorkActionTrigger = triggerEl;
		triggerEl?.focus();
		onOpenChange(false);
		void onAction(action, node);
	}

	function closeAndRestoreFocus(): void {
		if (!open) return;
		lastWorkActionTrigger = triggerEl;
		onOpenChange(false);
		void tick().then(() => restoreWorkActionFocus());
	}

	function onWindowKeydown(event: KeyboardEvent): void {
		if (event.key !== 'Escape' || !open) return;
		event.preventDefault();
		event.stopPropagation();
		closeAndRestoreFocus();
	}

	function onMenuKeydown(event: KeyboardEvent): void {
		if (event.key === 'Escape') { onWindowKeydown(event); return; }
		if (!['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) return;
		const buttons = [...(menuEl?.querySelectorAll<HTMLButtonElement>('button') ?? [])];
		if (!buttons.length) return;
		event.preventDefault();
		event.stopPropagation();
		const current = buttons.indexOf(document.activeElement as HTMLButtonElement);
		const next = event.key === 'Home' ? 0 : event.key === 'End' ? buttons.length - 1
			: (current + (event.key === 'ArrowDown' ? 1 : -1) + buttons.length) % buttons.length;
		buttons[next]?.focus();
	}
</script>

<svelte:window onkeydown={onWindowKeydown} onclick={(event) => {
	if (open && event.target instanceof Node && !wrapperEl?.contains(event.target)) onOpenChange(false);
}} />

<div bind:this={wrapperEl} data-lang={isJapanese ? 'ja' : 'en'} class:card={variant === 'card'} class:header={variant === 'header'} class="work-action-menu">
	<button
		bind:this={triggerEl}
		type="button"
		class="work-action-trigger"
		class:open
		disabled={!enabled}
		aria-haspopup="menu"
		aria-expanded={open}
		aria-label={t().workActionOpenMenu}
		title={!enabled ? unavailableReason : undefined}
		onclick={toggle}
	>
		{#if variant === 'card'}
			<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="1"></circle><circle cx="19" cy="12" r="1"></circle><circle cx="5" cy="12" r="1"></circle></svg>
		{:else}
			<span>{t().workActionRefine}</span><span aria-hidden="true">▾</span>
		{/if}
	</button>
	{#if open && node}
		<div bind:this={menuEl} class="work-action-dropdown" role="menu" tabindex="-1" onkeydown={onMenuKeydown}>
			<div class="work-action-title">
				{t().workActionMenuTitle}
				{#if ddlOrigin}<span class="work-action-origin">{t().workActionDdlOrigin}</span>{/if}
			</div>
			<button type="button" role="menuitem" onclick={(event) => select('adjust', event)}>{t().workActionAdjust}</button>
			{#if !ddlOrigin}
				<button type="button" role="menuitem" onclick={(event) => select('description', event)}>{t().workActionDescription}</button>
			{/if}
			<button type="button" role="menuitem" onclick={(event) => select('instructions', event)}>{t().workActionInstructions}</button>
			{#if !ddlOrigin}
				<button type="button" role="menuitem" onclick={(event) => select('sketch-grain', event)}>{t().workActionSketchGrain}</button>
				<button type="button" role="menuitem" onclick={(event) => select('models', event)}>{t().workActionModels}</button>
			{/if}
			<button type="button" role="menuitem" onclick={(event) => select('autonomous', event)}>{t().workActionAutonomous}</button>
		</div>
	{/if}
</div>

<style>
	.work-action-menu { position: relative; display: inline-flex; }
	.work-action-menu.card { position: absolute; top: 6px; right: 6px; z-index: 3; }
	.work-action-trigger { border: 1px solid var(--border2); background: var(--panel); color: var(--fg); font: inherit; cursor: pointer; }
	.work-action-trigger:disabled { cursor: default; opacity: .55; }
	.work-action-menu.card .work-action-trigger { display: grid; place-items: center; width: 28px; height: 28px; border: 0; padding: 0; border-radius: var(--btn-sm-radius); background: color-mix(in srgb, var(--panel) 88%, transparent); color: var(--fg2); }
	.work-action-menu.card .work-action-trigger:hover:not(:disabled) { background: var(--bg2); color: var(--fg); }
	.work-action-menu.header .work-action-trigger { display: inline-flex; align-items: center; gap: 5px; border-radius: var(--btn-sm-radius); padding: var(--btn-sm-padding); font-size: var(--btn-sm-font-size); font-weight: 600; white-space: nowrap; }
	.work-action-menu.header .work-action-trigger:hover:not(:disabled), .work-action-menu.header .work-action-trigger.open { border-color: var(--accent); background: var(--accent-light); }
	.work-action-dropdown { position: absolute; z-index: 100; min-width: 210px; border: 1px solid var(--border2); border-radius: 6px; padding: 0 0 4px; overflow: hidden; background: var(--panel); box-shadow: 0 6px 20px rgba(0, 0, 0, 0.35); display: flex; flex-direction: column; }
	.work-action-menu.card .work-action-dropdown { top: 27px; right: 0; }
	.work-action-menu.header .work-action-dropdown { top: calc(100% + 6px); right: 0; }
	.work-action-dropdown button { border: 0; background: transparent; color: var(--fg); padding: 6px 13px; font: inherit; font-size: 12px; line-height: 1.35; text-align: left; cursor: pointer; width: 100%; box-sizing: border-box; }
	.work-action-dropdown button:hover { background: var(--bg2); }
	.work-action-title { margin-bottom: 4px; padding: 7px 13px; border-bottom: 1px solid var(--accent); background: color-mix(in srgb, var(--accent) 14%, var(--panel)); color: var(--fg); font-size: 12px; font-weight: 700; letter-spacing: 0.08em; }
	.work-action-origin { display: block; margin-top: 2px; color: var(--fg2); font-size: 12px; font-weight: 500; letter-spacing: 0.02em; }
</style>

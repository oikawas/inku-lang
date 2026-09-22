<script lang="ts">
	import { tick } from 'svelte';
	import { t } from '$lib/i18n/index.svelte';
	import AnimationExportModal from '$lib/components/AnimationExportModal.svelte';
	import type { ExportTemplate } from '$lib/exportTemplates';
	import type { AnimationExportSettings } from '$lib/animationExport';
	import type { SheetVariant } from '$lib/contactSheet';
	import { svgImage } from '$lib/svgImage';
	import type { SvgProfile } from '$lib/features/export/download';
	import {
		snapshotSavedWorkExport,
		type SavedWorkExportScope,
		type SavedWorkExportSnapshot,
	} from '$lib/features/export/saved-work';

	export type SavedWorkExportMenuProps = {
		scope: SavedWorkExportScope | null;
		animationSettings: AnimationExportSettings;
		pngTemplates?: ExportTemplate[];
		variant?: 'canvas' | 'panel';
		onDownloadSVG?: (profile: SvgProfile, snapshot: SavedWorkExportSnapshot) => void | Promise<void>;
		onDownloadPNG?: (height: number, snapshot: SavedWorkExportSnapshot) => void | Promise<void>;
		onDownloadCard?: (historyId: string, snapshot: SavedWorkExportSnapshot) => void | Promise<void>;
		onDownloadAnimation: (snapshot: SavedWorkExportSnapshot, settings: AnimationExportSettings, directory?: FileSystemDirectoryHandle) => void | Promise<void>;
		onDownloadContactSheet: (snapshot: SavedWorkExportSnapshot, variant: SheetVariant) => void | Promise<void>;
		onValidateSnapshot: (snapshot: SavedWorkExportSnapshot) => boolean | Promise<boolean>;
	};

	let {
		scope,
		animationSettings,
		pngTemplates = [],
		variant = 'panel',
		onDownloadSVG,
		onDownloadPNG,
		onDownloadCard,
		onDownloadAnimation,
		onDownloadContactSheet,
		onValidateSnapshot,
	}: SavedWorkExportMenuProps = $props();

	let open = $state(false);
	let animationOpen = $state(false);
	let snapshot = $state<SavedWorkExportSnapshot | null>(null);
	let busy = $state(false);
	let error = $state<string | null>(null);
	let wrapperEl = $state<HTMLDivElement | null>(null);
	let menuEl = $state<HTMLDivElement | null>(null);
	let triggerEl = $state<HTMLButtonElement | null>(null);
	const single = $derived((snapshot?.ids.length ?? 0) === 1);
	const transition = $derived((snapshot?.ids.length ?? 0) > 1);

	function scopeLabel(target: SavedWorkExportSnapshot): string {
		if (target.description) return target.description;
		if (target.kind === 'current') return t().savedWorkExportCurrentScope;
		if (target.kind === 'lineage-path') return t().savedWorkExportLineagePathScope(target.ids.length);
		return t().savedWorkExportSelectionScope(target.ids.length);
	}

	function openMenu(event: MouseEvent): void {
		event.stopPropagation();
		if (open) {
			open = false;
			return;
		}
		const next = snapshotSavedWorkExport(scope);
		if (!next) {
			error = t().savedWorkExportUnavailable;
			return;
		}
		error = null;
		snapshot = next;
		open = true;
		void tick().then(() => menuEl?.querySelector<HTMLButtonElement>('button:not(:disabled)')?.focus());
	}

	function onMenuKeydown(event: KeyboardEvent): void {
		if (event.key === 'Escape') {
			event.preventDefault();
			event.stopPropagation();
			if (!busy) { open = false; triggerEl?.focus(); }
			return;
		}
		if (!['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) return;
		const buttons = [...(menuEl?.querySelectorAll<HTMLButtonElement>('button:not(:disabled)') ?? [])];
		if (!buttons.length) return;
		event.preventDefault();
		event.stopPropagation();
		const current = buttons.indexOf(document.activeElement as HTMLButtonElement);
		const next = event.key === 'Home' ? 0 : event.key === 'End' ? buttons.length - 1
			: (current + (event.key === 'ArrowDown' ? 1 : -1) + buttons.length) % buttons.length;
		buttons[next]?.focus();
	}

	async function run(action: (target: SavedWorkExportSnapshot) => void | Promise<void>): Promise<boolean> {
		const target = snapshot;
		if (!target || busy) return false;
		busy = true;
		error = null;
		try {
			if (!(await onValidateSnapshot(target))) {
				error = t().savedWorkExportUnavailable;
				return false;
			}
			await action(target);
			open = false;
			return true;
		} catch (cause) {
			error = cause instanceof Error ? cause.message : String(cause);
			return false;
		} finally {
			busy = false;
		}
	}

	async function saveAnimation(settings: AnimationExportSettings, directory?: FileSystemDirectoryHandle): Promise<void> {
		const target = snapshot;
		if (!target || busy) throw new Error(t().savedWorkExportUnavailable);
		busy = true;
		error = null;
		try {
			if (!(await onValidateSnapshot(target))) throw new Error(t().savedWorkExportUnavailable);
			await onDownloadAnimation(target, settings, directory);
			open = false;
		} catch (cause) {
			error = cause instanceof Error ? cause.message : String(cause);
			throw cause;
		} finally {
			busy = false;
		}
	}

	function openAnimation(): void {
		if (!snapshot || busy) return;
		animationOpen = true;
	}
</script>

<svelte:window onclick={(event) => {
	if (open && !busy && !animationOpen && event.target instanceof Node && !wrapperEl?.contains(event.target)) open = false;
}} />

<div bind:this={wrapperEl} class:canvas={variant === 'canvas'} class="saved-work-export">
	<button
		bind:this={triggerEl}
		type="button"
		class="saved-work-export-trigger"
		disabled={!scope || busy}
		aria-haspopup="menu"
		aria-expanded={open}
		aria-label={t().exportLabel}
		title={t().exportLabel}
		onclick={openMenu}
	>
		<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3v11m0 0 4-4m-4 4-4-4M5 18h14" /></svg>
		{#if variant === 'panel'}<span>{t().exportLabel} ▾</span>{/if}
	</button>
	{#if open && snapshot}
		<div bind:this={menuEl} class="saved-work-export-menu" role="menu" tabindex="-1" onkeydown={onMenuKeydown}>
			<div class="saved-work-export-scope">
				<strong>{scopeLabel(snapshot)}</strong>
				{#if transition && snapshot.kind !== 'lineage-path'}<span>{t().savedWorkExportOldestFirst}</span>{/if}
			</div>
			{#if single}
				{@const target = snapshot.works[0]}
				<div class="saved-work-export-target">
					{#if target.preview}<img use:svgImage={target.preview} alt="" />{/if}
					<code title={target.id}>{target.id.slice(0, 8)}</code>
					<span title={target.description || scopeLabel(snapshot)}>{target.description || scopeLabel(snapshot)}</span>
				</div>
			{/if}
			{#if single && onDownloadSVG && onDownloadPNG}
				<div class="saved-work-export-group">
					<div class="saved-work-export-heading">SVG</div>
					<button type="button" role="menuitem" disabled={busy} onclick={() => void run((target) => onDownloadSVG?.('display', target))}>{t().svgExportDisplayName}</button>
					<button type="button" role="menuitem" disabled={busy} onclick={() => void run((target) => onDownloadSVG?.('editable', target))}>{t().svgExportEditableName}</button>
					<button type="button" role="menuitem" disabled={busy} onclick={() => void run((target) => onDownloadSVG?.('compat', target))}>{t().svgExportCompatName}</button>
				</div>
				<div class="saved-work-export-group">
					<div class="saved-work-export-heading">PNG</div>
					{#each pngTemplates as template (template.id)}
						<button type="button" role="menuitem" disabled={busy} onclick={() => void run((target) => onDownloadPNG?.(template.y_px, target))}>{template.name}</button>
					{/each}
				</div>
				{#if onDownloadCard}
					<div class="saved-work-export-group">
						<button type="button" role="menuitem" disabled={busy} onclick={() => void run((target) => onDownloadCard?.(target.ids[0], target))}>{t().historyCardExport}</button>
					</div>
				{/if}
			{/if}
			<div class="saved-work-export-group">
				<button type="button" role="menuitem" disabled={busy} onclick={openAnimation}>{single ? t().savedWorkExportLayerAnimation : t().savedWorkExportTransitionAnimation}</button>
				{#if transition}
					<button type="button" role="menuitem" disabled={busy} onclick={() => void run((target) => onDownloadContactSheet(target, 'review'))}>{t().savedWorkExportContactSheet}</button>
					<button type="button" role="menuitem" disabled={busy} onclick={() => void run((target) => onDownloadContactSheet(target, 'ai'))}>{t().savedWorkExportAiContactSheet}</button>
				{/if}
			</div>
			{#if error}<p class="saved-work-export-error" role="alert">{error}</p>{/if}
		</div>
	{/if}
</div>

{#if animationOpen && snapshot}
	<AnimationExportModal
		initialSettings={animationSettings}
		count={snapshot.ids.length}
		mode={single ? 'layer' : 'transition'}
		scopeDescription={scopeLabel(snapshot)}
		onSave={saveAnimation}
		onClose={() => (animationOpen = false)}
	/>
{/if}

<style>
	.saved-work-export { position: relative; display: inline-flex; }
	.saved-work-export-trigger { display: inline-flex; align-items: center; gap: 5px; border: 1px solid var(--border2); border-radius: var(--btn-sm-radius); padding: var(--btn-sm-padding); background: var(--panel); color: var(--fg); cursor: pointer; font: inherit; font-size: var(--btn-sm-font-size); white-space: nowrap; }
	.saved-work-export-trigger svg { width: 16px; height: 16px; fill: none; stroke: currentColor; stroke-width: 2; stroke-linecap: round; stroke-linejoin: round; display: block; }
	.saved-work-export.canvas .saved-work-export-trigger { width: 34px; height: 34px; border-radius: 999px; padding: 0; background: var(--floating-control-bg); color: var(--floating-control-fg); box-shadow: 0 1px 6px rgba(0, 0, 0, 0.1); display: inline-flex; align-items: center; justify-content: center; }
	.saved-work-export-trigger:hover:not(:disabled) { background: var(--floating-control-hover); }
	.saved-work-export-trigger:disabled { opacity: .55; cursor: default; }
	.saved-work-export-menu { position: absolute; right: 0; z-index: 110; width: min(280px, calc(100vw - 32px)); max-height: min(520px, calc(100dvh - 160px)); overflow-y: auto; border: 1px solid var(--border2); border-radius: var(--r-lg); background: var(--panel); box-shadow: 0 4px 18px rgba(0, 0, 0, .18); }
	.saved-work-export.canvas .saved-work-export-menu { right: 0; bottom: calc(100% + 6px); }
	.saved-work-export:not(.canvas) .saved-work-export-menu { top: calc(100% + 6px); }
	.saved-work-export-scope { display: grid; gap: 2px; padding: 8px 12px; border-bottom: 1px solid var(--border); color: var(--fg2); font-size: 12px; }
	.saved-work-export-scope strong { color: var(--fg); font-size: 12px; }
	.saved-work-export-target { display: flex; align-items: center; gap: 8px; padding: 8px 12px; border-bottom: 1px solid var(--border); color: var(--fg2); font-size: 12px; line-height: 1.5; }
	.saved-work-export-target span { display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 3; line-clamp: 3; overflow: hidden; overflow-wrap: anywhere; }
	.saved-work-export-target code { flex: 0 0 auto; font-size: 12px; }
	.saved-work-export-target img { width: 34px; height: 34px; flex: 0 0 auto; object-fit: contain; border: 1px solid var(--border); background: var(--canvas-paper); }
	.saved-work-export-group + .saved-work-export-group { border-top: 1px solid var(--border); }
	.saved-work-export-heading { padding: 7px 12px 2px; color: var(--fg2); font-size: 12px; font-weight: 700; letter-spacing: .08em; }
	.saved-work-export-group button { display: block; width: 100%; border: 0; padding: 7px 12px; background: transparent; color: var(--fg); cursor: pointer; font: inherit; font-size: 12px; text-align: left; }
	.saved-work-export-group button:hover:not(:disabled) { background: var(--bg); }
	.saved-work-export-group button:disabled { opacity: .55; cursor: default; }
	.saved-work-export-error { margin: 0; padding: 8px 12px; border-top: 1px solid var(--border); color: var(--danger); font-size: 12px; }
</style>

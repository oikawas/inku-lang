<script lang="ts">
	import { t } from '$lib/i18n/index.svelte';
	import type { SettingsStatus } from './state.svelte';

	type ServerRuntimeStatus = Pick<SettingsStatus, 'output_save' | 'render_concurrency'>;

	type Props = {
		status: ServerRuntimeStatus | null;
		statusError: string | null;
		loading: boolean;
		outputSaveStatus: string | null;
		renderConcurrencyStatus: string | null;
		isAdmin: boolean;
		onReload: () => void;
		onUpdateOutputSave: (enabled: boolean, outputDir: string, pngSize: number) => void | Promise<void>;
		onUpdateRenderConcurrency: (serverLimit: number, clientLimit: number) => void | Promise<void>;
	};

	let {
		status,
		statusError,
		loading,
		outputSaveStatus,
		renderConcurrencyStatus,
		isAdmin,
		onReload,
		onUpdateOutputSave,
		onUpdateRenderConcurrency
	}: Props = $props();
</script>

<div class="popover-group">
	<div class="popover-group-label">{t().settingsOutputSaveTitle}</div>
	{#if loading}
		<div class="inline-message">{t().settingsLoading}</div>
	{:else if status}
		<label class="setting-toggle">
			<input
				type="checkbox"
				checked={status.output_save.enabled}
				onchange={(e) => onUpdateOutputSave((e.currentTarget as HTMLInputElement).checked, status.output_save.output_dir ?? '', status.output_save.png_size ?? 2160)}
			/>
			<span>{t().settingsOutputSaveEnabled}</span>
		</label>
		<label class="server-path-row">
			<span>{t().settingsOutputSaveDir}</span>
			<div class="server-path-input-row">
				<input
					value={status.output_save.output_dir}
					placeholder={t().settingsOutputSaveDirPlaceholder}
					onchange={(e) => onUpdateOutputSave(status.output_save.enabled ?? true, (e.currentTarget as HTMLInputElement).value, status.output_save.png_size ?? 2160)}
				/>
				<button class="ghost-btn primary-inline" onclick={() => onUpdateOutputSave(status.output_save.enabled ?? true, status.output_save.output_dir ?? '', status.output_save.png_size ?? 2160)}>{t().profileSaveButton}</button>
			</div>
		</label>
		<label class="server-path-row compact-control">
			<span>{t().settingsOutputSavePngSize}</span>
			<select
				value={String(status.output_save.png_size)}
				onchange={(e) => onUpdateOutputSave(status.output_save.enabled ?? true, status.output_save.output_dir ?? '', Number((e.currentTarget as HTMLSelectElement).value))}
			>
				<option value="1080">1080px</option>
				<option value="2160">2160px</option>
			</select>
		</label>
		<div class="settings-readonly-grid compact">
			<span class="nowrap-label">
				{t().settingsOutputSaveWorkers}
				<span class="info-dot" aria-label={t().settingsOutputSaveWorkersHelp}>
					i
					<span class="info-tooltip">{t().settingsOutputSaveWorkersHelp}</span>
				</span>
			</span><strong>{status.output_save.workers} / {status.output_save.queue_limit}</strong>
			<span>{t().settingsOutputSaveStats}</span><strong>{status.output_save.submitted} / {status.output_save.completed} / {status.output_save.failed} / {status.output_save.skipped}</strong>
		</div>
		<div class="db-test-result">{t().settingsOutputSaveNoteLabel}: {t().settingsOutputSaveNote}</div>
		{#if outputSaveStatus}
			<div class="inline-message">{outputSaveStatus}</div>
		{/if}
	{:else}
		<div class="inline-message">{statusError ?? t().settingsLoadFailed}</div>
	{/if}
</div>
<div class="popover-group">
	<div class="popover-group-label">{t().settingsRenderConcurrencyTitle}</div>
	{#if loading}
		<div class="inline-message">{t().settingsLoading}</div>
	{:else if status}
		<label class="server-path-row compact-control">
			<span>
				{t().settingsRenderConcurrencyServer}
				<span class="info-dot" aria-label={t().settingsRenderConcurrencyServerHelp}>
					i
					<span class="info-tooltip">{t().settingsRenderConcurrencyServerHelp}</span>
				</span>
			</span>
			<input
				type="number"
				min={status.render_concurrency.min_limit}
				max={status.render_concurrency.max_limit}
				value={status.render_concurrency.server_limit}
				onchange={(e) => onUpdateRenderConcurrency(Number((e.currentTarget as HTMLInputElement).value), status.render_concurrency.client_limit ?? 4)}
			/>
		</label>
		<label class="server-path-row compact-control">
			<span>
				{t().settingsRenderConcurrencyClient}
				<span class="info-dot" aria-label={t().settingsRenderConcurrencyClientHelp}>
					i
					<span class="info-tooltip">{t().settingsRenderConcurrencyClientHelp}</span>
				</span>
			</span>
			<input
				type="number"
				min={status.render_concurrency.min_limit}
				max={status.render_concurrency.max_limit}
				value={status.render_concurrency.client_limit}
				onchange={(e) => onUpdateRenderConcurrency(status.render_concurrency.server_limit ?? 2, Number((e.currentTarget as HTMLInputElement).value))}
			/>
		</label>
		<div class="db-test-result">{t().settingsRenderConcurrencyRange(status.render_concurrency.min_limit, status.render_concurrency.max_limit)}</div>
		{#if renderConcurrencyStatus}
			<div class="inline-message">{renderConcurrencyStatus}</div>
		{/if}
	{:else}
		<div class="inline-message">{statusError ?? t().settingsLoadFailed}</div>
	{/if}
</div>
<div class="settings-inline-actions">
	<button class="ghost-btn" onclick={onReload} disabled={loading || !isAdmin}>{t().settingsReloadSettings}</button>
</div>

<style>
	.popover-group {
		border: 1px solid var(--border);
		border-radius: var(--r);
		padding: 12px;
		background: var(--panel);
	}
	.popover-group-label {
		font-size: 10px;
		color: var(--fg3);
		text-transform: uppercase;
		letter-spacing: 0.08em;
		font-weight: 500;
		margin-bottom: 7px;
	}
	.setting-toggle {
		display: flex;
		align-items: center;
		gap: 8px;
		font-size: 12px;
		color: var(--fg2);
		cursor: pointer;
	}
	.server-path-row {
		display: flex;
		flex-direction: column;
		gap: 5px;
		margin-top: 10px;
		color: var(--fg3);
		font-size: 10px;
		text-transform: uppercase;
		letter-spacing: 0.06em;
	}
	.server-path-input-row { display: flex; gap: 8px; }
	.server-path-input-row input {
		flex: 1;
		min-width: 0;
		padding: 5px 7px;
		border: 1px solid var(--border2);
		border-radius: var(--r);
		background: var(--panel);
		color: var(--fg);
		font-size: 12px;
		font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
	}
	.server-path-row.compact-control { width: max-content; }
	.server-path-row select {
		min-width: 110px;
		padding: 5px 7px;
		border: 1px solid var(--border2);
		border-radius: var(--r);
		background: var(--panel);
		color: var(--fg);
		font-size: 12px;
		font-family: inherit;
	}
	.info-dot {
		position: relative;
		display: inline-flex;
		align-items: center;
		justify-content: center;
		width: 14px;
		height: 14px;
		margin-left: 5px;
		border: 1px solid var(--border2);
		border-radius: 50%;
		color: var(--fg3);
		font-size: 10px;
		line-height: 1;
		text-transform: none;
		letter-spacing: 0;
		cursor: help;
	}
	.info-tooltip {
		position: absolute;
		left: 50%;
		bottom: calc(100% + 8px);
		z-index: 20;
		width: min(260px, 70vw);
		transform: translateX(-50%);
		padding: 7px 9px;
		border-radius: var(--r);
		background: var(--tooltip-bg);
		color: var(--tooltip-fg);
		font-size: 11px;
		line-height: 1.5;
		text-align: left;
		white-space: normal;
		text-transform: none;
		letter-spacing: 0;
		opacity: 0;
		pointer-events: none;
	}
	.info-dot:hover .info-tooltip,
	.info-dot:focus .info-tooltip { opacity: 1; }
	.settings-readonly-grid {
		display: grid;
		grid-template-columns: max-content minmax(0, 1fr);
		gap: 7px 12px;
		align-items: baseline;
		margin-bottom: 9px;
		font-size: 12px;
	}
	.settings-readonly-grid span { color: var(--fg3); }
	.settings-readonly-grid .nowrap-label { white-space: nowrap; }
	.settings-readonly-grid strong { color: var(--fg); font-weight: 500; min-width: 0; word-break: break-word; }
	.settings-readonly-grid.compact { margin-top: 10px; margin-bottom: 0; }
	.settings-inline-actions { display: flex; align-items: center; gap: 10px; }
	.db-test-result { color: var(--fg2); font-size: 12px; }
	.inline-message {
		padding: 7px 9px;
		border: 1px solid var(--border);
		border-radius: var(--r);
		background: var(--panel);
		color: var(--fg2);
		font-size: 12px;
	}
	.primary-inline {
		border-color: var(--accent);
		background: var(--accent-light);
		color: var(--accent);
	}
</style>

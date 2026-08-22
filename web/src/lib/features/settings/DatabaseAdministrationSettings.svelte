<script lang="ts">
	import { t } from '$lib/i18n/index.svelte';
	import NumberStepper from '$lib/components/NumberStepper.svelte';
	import type { SettingsStatus } from './state.svelte';

	type DatabaseStatus = Pick<SettingsStatus, 'database' | 'db_backup'>;

	type Props = {
		status: DatabaseStatus | null;
		statusError: string | null;
		loading: boolean;
		backupStatus: string | null;
		isAdmin: boolean;
		onReload: () => void | Promise<void>;
		onUpdateBackupSettings: (intervalDays: number, maxGenerations: number, backupHour: number, backupMinute: number) => void | Promise<void>;
		onRunBackupNow: () => void | Promise<void>;
	};

	let {
		status,
		statusError,
		loading,
		backupStatus,
		isAdmin,
		onReload,
		onUpdateBackupSettings,
		onRunBackupNow
	}: Props = $props();

	function formatBytes(bytes: number | null | undefined): string {
		if (bytes == null) return '-';
		if (bytes < 1024) return `${bytes} B`;
		const units = ['KB', 'MB', 'GB', 'TB'];
		let value = bytes / 1024;
		let unit = units[0];
		for (let i = 1; i < units.length && value >= 1024; i += 1) {
			value /= 1024;
			unit = units[i];
		}
		return `${value.toFixed(value >= 10 ? 1 : 2)} ${unit}`;
	}

	function formatTimestamp(ms: number): string {
		if (!ms) return '-';
		return new Date(ms).toLocaleString();
	}

	// What the current settings will ask of the disk: the automatic copies are
	// pruned to max_generations, so that is the ceiling. Manual copies are never
	// pruned and are therefore not something the settings can predict.
	const dbBackupEstimatedBytes = $derived(
		status ? (status.database.file_size_bytes ?? 0) * status.db_backup.max_generations : 0
	);

	function saveDbBackupSettings(patch: { intervalDays?: number; maxGenerations?: number; hour?: number; minute?: number }): void {
		const current = status?.db_backup;
		void onUpdateBackupSettings(
			patch.intervalDays ?? current?.interval_days ?? 7,
			patch.maxGenerations ?? current?.max_generations ?? 4,
			patch.hour ?? current?.backup_hour ?? 3,
			patch.minute ?? current?.backup_minute ?? 0
		);
	}
</script>

<div class="database-administration-settings">
	<div class="popover-group">
		<div class="popover-group-label">{t().settingsCurrentDb}</div>
		{#if loading}
			<div class="inline-message">{t().settingsLoading}</div>
		{:else if status}
			<div class="settings-readonly-grid">
				<span>Backend</span><strong>{status.database.backend}</strong>
				<span>Driver</span><strong>{status.database.driver}</strong>
				<span>URL</span><code>{status.database.url}</code>
				<span>Database</span><strong>{status.database.database ?? '-'}</strong>
				<span>Default</span><strong>{status.database.is_default ? t().settingsYes : t().settingsNo}</strong>
				<span>{t().settingsDbFileSize}</span><strong>{formatBytes(status.database.file_size_bytes)}</strong>
			</div>
			<div class="db-test-result">{status.database.note}</div>
		{:else}
			<div class="inline-message">{statusError ?? t().settingsLoadFailed}</div>
		{/if}
	</div>
	<div class="popover-group">
		<div class="popover-group-label">{t().settingsDbBackupTitle}</div>
		{#if loading}
			<div class="inline-message">{t().settingsLoading}</div>
		{:else if status}
			{#if !status.db_backup.supported}
				<div class="inline-message">{t().settingsDbBackupUnsupported}</div>
			{/if}
			<div class="db-backup-grid">
				<div class="db-backup-field">
					<span>{t().settingsDbBackupInterval}</span>
					<NumberStepper
						label={t().settingsDbBackupInterval}
						min={1}
						max={365}
						value={status.db_backup.interval_days}
						disabled={!status.db_backup.supported}
						onChange={(value) => saveDbBackupSettings({ intervalDays: value })}
					/>
				</div>
				<div class="db-backup-field">
					<span>{t().settingsDbBackupMaxGenerations}</span>
					<NumberStepper
						label={t().settingsDbBackupMaxGenerations}
						min={1}
						max={100}
						value={status.db_backup.max_generations}
						disabled={!status.db_backup.supported}
						onChange={(value) => saveDbBackupSettings({ maxGenerations: value })}
					/>
				</div>
				<div class="db-backup-field db-backup-time">
					<span>{t().settingsDbBackupTime}</span>
					<div class="db-backup-time-fields">
						<NumberStepper
							min={0}
							max={23}
							label={t().settingsDbBackupTimeHourLabel}
							value={status.db_backup.backup_hour}
							disabled={!status.db_backup.supported}
							onChange={(value) => saveDbBackupSettings({ hour: value })}
						/>
						<span class="db-backup-time-unit">{t().settingsDbBackupTimeHourUnit}</span>
						<NumberStepper
							min={0}
							max={59}
							label={t().settingsDbBackupTimeMinuteLabel}
							value={status.db_backup.backup_minute}
							disabled={!status.db_backup.supported}
							onChange={(value) => saveDbBackupSettings({ minute: value })}
						/>
						<span class="db-backup-time-unit">{t().settingsDbBackupTimeMinuteUnit}</span>
					</div>
				</div>
			</div>
			<div class="db-backup-hint">{t().settingsDbBackupTimeHint}</div>
			<div class="settings-readonly-grid compact">
				<span>{t().settingsDbBackupLastAuto}</span><strong>{formatTimestamp(status.db_backup.last_auto_backup_at)}</strong>
				<span>{t().settingsDbBackupNextAuto}</span><strong>{formatTimestamp(status.db_backup.next_auto_backup_at)}</strong>
				<span>{t().settingsDbBackupEstimatedDisk}</span><strong title={t().settingsDbBackupEstimatedDiskHint}>{formatBytes(dbBackupEstimatedBytes)}</strong>
				<span>Directory</span><code>{status.db_backup.backup_dir}</code>
				<span>Saved</span><strong>{t().settingsDbBackupStoredCounts(status.db_backup.auto_count, status.db_backup.manual_count)}</strong>
			</div>
			<div class="popover-group-label db-backup-list-label">{t().settingsDbBackupListTitle}</div>
			{#if status.db_backup.backups.length === 0}
				<div class="inline-message">{t().settingsDbBackupListEmpty}</div>
			{:else}
				<div class="db-backup-list-wrap">
					<table class="db-backup-list">
						<thead>
							<tr>
								<th>{t().settingsDbBackupListGeneration}</th>
								<th>{t().settingsDbBackupListKind}</th>
								<th>{t().settingsDbBackupListAt}</th>
								<th>{t().settingsDbBackupListSize}</th>
							</tr>
						</thead>
						<tbody>
							{#each status.db_backup.backups as entry (entry.name)}
								<tr>
									<td class="db-backup-generation">{entry.generation ?? '—'}</td>
									<td>{entry.kind === 'auto' ? t().settingsDbBackupKindAuto : t().settingsDbBackupKindManual}</td>
									<td>{formatTimestamp(entry.at)}</td>
									<td class="db-backup-size">{formatBytes(entry.size_bytes)}</td>
								</tr>
							{/each}
						</tbody>
					</table>
				</div>
				<div class="db-backup-hint">
					{t().settingsDbBackupListTotal(status.db_backup.backups_total_count, formatBytes(status.db_backup.backups_total_size_bytes))}
					{#if status.db_backup.backups_total_count > status.db_backup.backups.length}
						{t().settingsDbBackupListTruncated(status.db_backup.backups.length)}
					{/if}
				</div>
			{/if}
			{#if backupStatus}
				<div class="inline-message">{backupStatus}</div>
			{/if}
		{:else}
			<div class="inline-message">{statusError ?? t().settingsLoadFailed}</div>
		{/if}
	</div>
	<div class="settings-inline-actions">
		<button class="ghost-btn" onclick={onReload} disabled={loading || !isAdmin}>{t().settingsReload}</button>
		<button class="ghost-btn primary-inline" onclick={onRunBackupNow} disabled={loading || !isAdmin || !status?.db_backup.supported}>{t().settingsDbBackupRunNow}</button>
	</div>
</div>

<style>
	.database-administration-settings {
		display: flex;
		flex-direction: column;
		gap: 10px;
	}
	.popover-group {
		border: 1px solid var(--border);
		border-radius: var(--r);
		padding: 12px;
		background: var(--panel);
	}
	.popover-group-label {
		font-size: 10px; color: var(--fg3); text-transform: uppercase; letter-spacing: 0.08em;
		font-weight: 500; margin-bottom: 7px;
	}
	.inline-message {
		padding: 7px 9px;
		border: 1px solid var(--border);
		border-radius: var(--r);
		background: var(--panel);
		color: var(--fg2);
		font-size: 12px;
	}
	.db-test-result { color: var(--fg2); font-size: 12px; }
	.settings-readonly-grid {
		display: grid;
		grid-template-columns: max-content minmax(0, 1fr);
		gap: 7px 12px;
		align-items: baseline;
		margin-bottom: 9px;
		font-size: 12px;
	}
	.settings-readonly-grid span { color: var(--fg3); }
	.settings-readonly-grid strong { color: var(--fg); font-weight: 500; min-width: 0; word-break: break-word; }
	.settings-readonly-grid code {
		min-width: 0;
		padding: 2px 4px;
		border-radius: var(--r);
		background: var(--bg);
		color: var(--fg2);
		font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
		font-size: 11px;
		word-break: break-all;
	}
	.settings-readonly-grid.compact {
		margin-top: 10px;
		margin-bottom: 0;
	}
	.db-backup-grid {
		display: grid;
		/* The time takes two number fields, so it claims two of these tracks. */
		grid-template-columns: repeat(auto-fit, minmax(96px, 1fr));
		gap: 10px;
		margin-top: 10px;
	}
	.db-backup-field {
		display: flex;
		flex-direction: column;
		gap: 4px;
		color: var(--fg3);
		font-size: 10px;
		text-transform: uppercase;
		letter-spacing: 0.06em;
	}
	.db-backup-time { grid-column: span 2; }
	.db-backup-time-fields {
		display: flex;
		align-items: center;
		gap: 4px;
		min-width: 0;
	}
	.db-backup-time-fields :global(.number-stepper) { flex: 1 1 0; }
	.db-backup-time-unit {
		flex: 0 0 auto;
		color: var(--fg2);
		font-size: 11px;
		letter-spacing: 0;
		text-transform: none;
	}
	.db-backup-hint {
		margin-top: 6px;
		color: var(--fg3);
		font-size: 10px;
		line-height: 1.5;
	}
	.db-backup-list-label {
		margin-top: 14px;
	}
	.db-backup-list-wrap {
		margin-top: 6px;
		max-height: 190px;
		overflow: auto;
		border: 1px solid var(--border);
		border-radius: var(--r);
	}
	.db-backup-list {
		width: 100%;
		border-collapse: collapse;
		font-size: 11px;
		font-variant-numeric: tabular-nums;
	}
	.db-backup-list th {
		position: sticky;
		top: 0;
		z-index: 1;
		padding: 5px 8px;
		background: var(--panel2);
		border-bottom: 1px solid var(--border);
		color: var(--fg3);
		font-weight: 500;
		text-align: left;
		white-space: nowrap;
	}
	.db-backup-list td {
		padding: 4px 8px;
		border-bottom: 1px solid var(--border);
		color: var(--fg2);
		white-space: nowrap;
	}
	.db-backup-list tr:last-child td { border-bottom: none; }
	.db-backup-generation,
	.db-backup-size { text-align: right; }
	.settings-inline-actions { display: flex; align-items: center; gap: 10px; }
	.primary-inline {
		border-color: var(--accent);
		background: var(--accent-light);
		color: var(--accent);
	}
</style>

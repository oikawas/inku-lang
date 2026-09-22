<script lang="ts">
	import { t } from '$lib/i18n/index.svelte';
	import NumberStepper from '$lib/components/NumberStepper.svelte';
	import Tooltip from '$lib/components/Tooltip.svelte';
	import { formatGroupedNumber } from '$lib/groupedNumber';
	import { markWeight } from '$lib/markWeight';
	import type { SettingsStatus } from './state.svelte';

	type RenderLimitsStatus = SettingsStatus['render_limits'];

	type Props = {
		status: RenderLimitsStatus | null;
		statusError: string | null;
		loading: boolean;
		saveStatus: string | null;
		isAdmin: boolean;
		onReload: () => void;
		onUpdate: (patch: Record<string, number> | null) => Promise<RenderLimitsStatus | null>;
	};

	let {
		status,
		statusError,
		loading,
		saveStatus,
		isAdmin,
		onReload,
		onUpdate
	}: Props = $props();
	let draft = $state<Record<string, number>>({});
	let saved = $state<Record<string, number>>({});
	let normalizedFields = $state<string[]>([]);
	let saving = $state(false);
	const changedFields = $derived(
		Object.keys(saved).filter((field) => draft[field] !== saved[field])
	);
	const hasChanges = $derived(changedFields.length > 0);

	$effect(() => {
		if (!status || saving || hasChanges) return;
		saved = { ...status.limits };
		draft = { ...status.limits };
	});

	// The nine limits are addressed by their server-side field names. The label,
	// the hint and the group heading all come from i18n by that name, so the
	// panel does not carry a second, drifting copy of the vocabulary.
	function renderLimitLabel(field: string): string {
		const labels = t().settingsRenderLimitLabels as Record<string, string>;
		return labels[field] ?? field;
	}

	function renderLimitHint(field: string): string {
		const hints = t().settingsRenderLimitHints as Record<string, string>;
		return hints[field] ?? '';
	}

	function renderLimitGroupLabel(group: string): string {
		const groups = t().settingsRenderLimitGroups as Record<string, string>;
		return groups[group] ?? group;
	}

	function renderLimitGroupSummary(group: string): string {
		const summaries = t().settingsRenderLimitGroupSummaries as Record<string, string>;
		return summaries[group] ?? '';
	}

	function renderLimitUnit(field: string): string {
		const units = t().settingsRenderLimitUnits as Record<string, string>;
		return t().settingsRenderLimitsUnit(units[field] ?? '');
	}

	// The families answer to different authorities -- the machine, the eye, and a
	// typing guard -- and nothing on the row says so. The heading carries the
	// reason; the per-field line under each stepper stays what that one field does.
	function renderLimitGroupTooltip(group: string): string {
		const tips = t().settingsRenderLimitGroupTooltips as Record<string, string>;
		return tips[group] ?? '';
	}

	function restoreDefaults(): void {
		if (!status || saving) return;
		draft = { ...status.defaults };
		normalizedFields = [];
	}

	function discardChanges(): void {
		draft = { ...saved };
		normalizedFields = [];
	}

	async function saveChanges(): Promise<void> {
		if (!status || !isAdmin || saving || !hasChanges) return;
		const submitted = { ...draft };
		const patch = Object.fromEntries(
			changedFields.map((field) => [field, submitted[field]])
		);
		saving = true;
		try {
			const next = await onUpdate(patch);
			if (!next) return;
			normalizedFields = Object.keys(next.limits).filter(
				(field) => submitted[field] !== next.limits[field]
			);
			saved = { ...next.limits };
			draft = { ...next.limits };
		} finally {
			saving = false;
		}
	}
</script>

<div class="popover-group">
	<div class="popover-group-label">{t().settingsRenderLimitsTitle}</div>
	{#if loading}
		<div class="inline-message">{t().settingsLoading}</div>
	{:else if status}
		<div class="db-test-result">{t().settingsRenderLimitsIntro}</div>
		{#each Object.entries(status.groups) as [groupName, fields]}
			<div class="limits-group">
				<div class="limits-group-label">
					<span>{renderLimitGroupLabel(groupName)}</span>
					{#if renderLimitGroupTooltip(groupName)}
						<Tooltip placement="bottom-right" wide text={renderLimitGroupTooltip(groupName)}>
							<span class="settings-info-mark" aria-hidden="true">i</span>
						</Tooltip>
					{/if}
				</div>
				{#if renderLimitGroupSummary(groupName)}
					<p class="limits-group-summary">{renderLimitGroupSummary(groupName)}</p>
				{/if}
				<div class="limits-grid">
					{#each fields as field}
						<!-- A div, not a label: the stepper's first labelable child is a
						     button, so a wrapping label would target that instead of the
						     field. The stepper carries its own aria-label. -->
						<div class="limits-field">
							<span>{renderLimitLabel(field)}</span>
							<div class="limits-field-facts">
								<span>{t().settingsRenderLimitsCurrent}: {formatGroupedNumber(saved[field] ?? status.limits[field], 1)}</span>
								<span>{t().settingsRenderLimitsDefault}: {formatGroupedNumber(status.defaults[field], 1)}</span>
								<span>{renderLimitUnit(field)}</span>
							</div>
							<NumberStepper
								label={renderLimitLabel(field)}
								min={1}
								max={status.absolute_max}
								value={draft[field] ?? status.limits[field]}
								disabled={!isAdmin || saving}
								onChange={(value) => {
									draft = { ...draft, [field]: value };
									normalizedFields = [];
								}}
							/>
							<small>{renderLimitHint(field)}</small>
							<!-- The Svelte const directive may only be the immediate child of a block,
							     so the costs guard hosts it rather than the field div. Both conditions
							     carry weight: an older server sends no costs at all, and eight of the
							     nine fields govern no megabytes even when it does. -->
							{#if status.bytes_per_mark}
								{@const weight = markWeight(
									field,
									draft[field] ?? status.limits[field],
									status.bytes_per_mark
								)}
								{#if weight}
									<small class="limits-weight"
										>{t().settingsRenderLimitsWeight(weight.low, weight.high)}</small
									>
								{/if}
							{/if}
						</div>
					{/each}
				</div>
			</div>
		{/each}
		<div class="db-test-result">{t().settingsRenderLimitsRounding}</div>
		<div class="limits-footer">
		{#if normalizedFields.length}
			<div class="inline-message limits-normalized">
				{t().settingsRenderLimitsNormalized(normalizedFields.map(renderLimitLabel).join(', '))}
			</div>
		{/if}
		{#if saveStatus && !(hasChanges && saveStatus === t().settingsRenderLimitsSaved)}
			<div class="inline-message">{saveStatus}</div>
		{/if}
		<div class="settings-inline-actions">
			<button class="ghost-btn" onclick={onReload} disabled={loading || saving || hasChanges || !isAdmin}>{t().settingsReloadSettings}</button>
			<button class="ghost-btn" onclick={restoreDefaults} disabled={saving || !isAdmin}>{t().settingsRenderLimitsReset}</button>
			{#if hasChanges}
				<span class="limits-change-count">{t().settingsRenderLimitsChanges(changedFields.length)}</span>
				<button class="ghost-btn" onclick={discardChanges} disabled={saving}>{t().settingsRenderLimitsCancel}</button>
				<button class="limits-save" onclick={saveChanges} disabled={saving || !isAdmin}>
					{saving ? t().settingsRenderLimitsSaving : t().settingsRenderLimitsSave}
				</button>
			{/if}
		</div>
		</div>
	{:else}
		<div class="inline-message">{statusError ?? t().settingsLoadFailed}</div>
	{/if}
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
	.settings-info-mark {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		width: 13px;
		height: 13px;
		border: 1px solid var(--border2);
		border-radius: 50%;
		color: var(--fg3);
		font-size: 9px;
		font-weight: 600;
		text-transform: none;
		letter-spacing: 0;
	}
	.db-test-result { color: var(--fg2); font-size: 12px; }
	.inline-message {
		padding: 7px 9px;
		border: 1px solid var(--border);
		border-radius: var(--r);
		background: var(--panel);
		color: var(--fg2);
		font-size: 12px;
	}
	.limits-footer {
		position: sticky;
		bottom: 0;
		z-index: 1;
		margin-top: 12px;
		padding: 10px 0;
		border-top: 1px solid var(--border);
		background: var(--panel);
	}
	.settings-inline-actions {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 10px;
		margin-top: 8px;
	}
	.limits-group { margin: 16px 0; padding: 14px; border: 1px solid var(--border); border-radius: var(--r); }
	.limits-group-label {
		font-size: var(--btn-sm-font-size);
		color: var(--fg2);
		font-weight: 600;
		margin-bottom: 6px;
		display: flex;
		align-items: center;
		gap: 6px;
	}
	.limits-group-summary {
		margin: 0 0 8px;
		color: var(--fg2);
		font-size: 12px;
		line-height: 1.4;
	}
	.limits-grid {
		display: grid;
		/* The hint sets the card width, not the control: the stepper is fixed
		   below and every hint is a sentence. */
		grid-template-columns: repeat(auto-fit, minmax(min(100%, 220px), 1fr));
		gap: 14px 16px;
	}
	.limits-field {
		display: flex;
		flex-direction: column;
		gap: 4px;
		min-width: 0;
		font-size: 12px;
	}
	.limits-field > span { color: var(--fg); font-weight: 500; }
	.limits-field > small { color: var(--fg3); font-size: 12px; line-height: 1.5; }
	.limits-field-facts {
		display: flex;
		flex-wrap: wrap;
		gap: 3px 8px;
		color: var(--fg3);
		font-size: 12px;
		font-variant-numeric: tabular-nums;
	}
	.limits-field-facts > span { color: inherit; font-weight: 400; }
	/* The conversion answers a different question from the hint above it -- what
	   this number costs, rather than what it governs -- so it is set apart
	   rather than reading as a second sentence of the same line. */
	.limits-field > small.limits-weight { color: var(--fg2); }
	.limits-normalized { margin-top: 8px; }
	.limits-change-count { color: var(--fg2); font-size: 12px; }
	.limits-save {
		padding: var(--btn-sm-padding);
		border: 1px solid var(--action-bg);
		border-radius: var(--btn-sm-radius);
		background: var(--action-bg);
		color: var(--action-fg);
		font: inherit;
		font-size: var(--btn-sm-font-size);
		cursor: pointer;
	}
	.limits-save:hover:not(:disabled) { background: var(--action-hover); }
	.limits-save:disabled { opacity: 0.5; cursor: default; }
</style>

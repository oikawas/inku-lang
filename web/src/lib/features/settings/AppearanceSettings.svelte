<script lang="ts">
	import { t } from '$lib/i18n/index.svelte';
	import { getMascot, setMascot } from '$lib/mascot.svelte';
	import Tooltip from '$lib/components/Tooltip.svelte';
	import NumberStepper from '$lib/components/NumberStepper.svelte';
	import { batchSettings, BATCH_RETRY_MAX, BATCH_RETRY_MIN } from '$lib/features/batch/settings.svelte';
	import { UI_VISIBILITY_KEYS, type UiCustomVisibility, type UiMode, type UiVisibilityKey } from '$lib/uiMode';
	import { canAddHistoryStripField, HISTORY_STRIP_FIELDS, type HistoryStripField } from '$lib/historyStripFields';
	import './appearance-settings.css';

	type Props = {
		uiMode: UiMode;
		uiCustom: UiCustomVisibility;
		uiModeSaving: boolean;
		uiModeSaveError: boolean;
		historyStripFields: HistoryStripField[];
		historyStripFieldsSaving: boolean;
		historyStripFieldsSaveError: boolean;
		autoRepairEnabled: boolean;
		onToggleHistoryStripField: (field: HistoryStripField) => void;
		onSetUiMode: (mode: UiMode) => void | Promise<void>;
		onSetUiCustomItem: (key: UiVisibilityKey, visible: boolean) => void;
	};

	let {
		uiMode, uiCustom, uiModeSaving, uiModeSaveError,
		historyStripFields, historyStripFieldsSaving, historyStripFieldsSaveError,
		autoRepairEnabled = $bindable(true), onToggleHistoryStripField,
		onSetUiMode, onSetUiCustomItem
	}: Props = $props();
</script>

			<div class="popover-group">
				<div class="popover-group-label">{t().settingsBatchRetryLabel}</div>
				<div class="db-test-result">{t().settingsBatchRetryDescription}</div>
				<div class="batch-retry-field">
					<span>{t().settingsBatchRetryCount}</span>
					<NumberStepper
						label={t().settingsBatchRetryCount}
						min={BATCH_RETRY_MIN}
						max={BATCH_RETRY_MAX}
						value={batchSettings.maxRetries}
						onChange={(value) => batchSettings.setMaxRetries(value)}
					/>
				</div>
			</div>
			<div class="popover-group ui-mode-settings">
				<div class="popover-group-label">{t().uiModeLabel}</div>
				<div class="db-test-result">{t().uiModeDescription}</div>
				<div class="settings-radio-set ui-mode-options">
					<label class="setting-toggle">
						<input type="radio" name="ui-mode" value="simple" checked={uiMode === 'simple'} disabled={uiModeSaving} onchange={() => onSetUiMode('simple')} />
						<span><strong>{t().uiModeSimple}</strong><small>{t().uiModeSimpleDescription}</small></span>
					</label>
					<label class="setting-toggle">
						<input type="radio" name="ui-mode" value="custom" checked={uiMode === 'custom'} disabled={uiModeSaving} onchange={() => onSetUiMode('custom')} />
						<span><strong>{t().uiModeCustom}</strong><small>{t().uiModeCustomDescription}</small></span>
					</label>
					<label class="setting-toggle">
						<input type="radio" name="ui-mode" value="full" checked={uiMode === 'full'} disabled={uiModeSaving} onchange={() => onSetUiMode('full')} />
						<span><strong>{t().uiModeFull}</strong><small>{t().uiModeFullDescription}</small></span>
					</label>
				</div>
				{#if uiMode === 'custom'}
					<div class="settings-radio-title">{t().uiModeCustomItems}</div>
					<div class="ui-custom-grid">
						{#each UI_VISIBILITY_KEYS as key (key)}
							<label class="setting-toggle">
								<input type="checkbox" checked={uiCustom[key] === true} disabled={uiModeSaving} onchange={(event) => onSetUiCustomItem(key, event.currentTarget.checked)} />
								<span>{key === 'input_modes' ? t().uiModeInputModes : key === 'drawing_settings' ? t().uiModeDrawingSettings : key === 'ddl_tools' ? t().uiModeDdlTools : key === 'detail_status' ? t().uiModeDetailStatus : key === 'work_tools' ? t().uiModeWorkTools : key === 'history' ? t().uiModeHistory : t().uiModeAuxiliary}</span>
							</label>
						{/each}
					</div>
					<div class="settings-inline-actions"><button class="ghost-btn" disabled={uiModeSaving} onclick={() => onSetUiMode('simple')}>{t().uiModeResetSimple}</button></div>
				{/if}
				<div class="db-test-result">{t().uiModeAlwaysVisible}</div>
				{#if uiModeSaving}<div class="inline-message">{t().uiModeSaving}</div>{/if}
				{#if uiModeSaveError}<div class="inline-message error-text">{t().uiModeSaveFailed}</div>{/if}
			</div>
			<!-- Two at most, and the unticked boxes go disabled at that point
			     rather than the third click evicting an earlier choice. -->
			<div class="popover-group history-strip-fields">
				<div class="popover-group-label">{t().historyStripFieldsLabel}</div>
				<div class="db-test-result">{t().historyStripFieldsDescription}</div>
				<div class="ui-custom-grid">
					{#each HISTORY_STRIP_FIELDS as field (field)}
						{@const checked = historyStripFields.includes(field)}
						<label class="setting-toggle" class:unavailable={!checked && !canAddHistoryStripField(historyStripFields)}>
							<input
								type="checkbox"
								{checked}
								disabled={historyStripFieldsSaving || (!checked && !canAddHistoryStripField(historyStripFields))}
								onchange={() => onToggleHistoryStripField(field)}
							/>
							<span>{field === 'generation' ? t().historyStripFieldGeneration : field === 'model' ? t().historyStripFieldModel : field === 'engine_version' ? t().historyStripFieldEngineVersion : t().historyStripFieldBytes}</span>
						</label>
					{/each}
				</div>
				{#if historyStripFieldsSaving}<div class="inline-message">{t().uiModeSaving}</div>{/if}
				{#if historyStripFieldsSaveError}<div class="inline-message error-text">{t().historyStripFieldsSaveFailed}</div>{/if}
			</div>
			<div class="popover-group">
				<div class="popover-group-label">{t().settingsMascotLabel}</div>
				<div class="settings-radio-set">
					<label class="setting-toggle">
						<input
							type="radio"
							name="mascot-kind"
							value="incu"
							checked={getMascot() === 'incu'}
							onchange={() => setMascot('incu')}
						/>
						<span>{t().settingsMascotIncu}</span>
					</label>
					<label class="setting-toggle">
						<input
							type="radio"
							name="mascot-kind"
							value="yuragi"
							checked={getMascot() === 'yuragi'}
							onchange={() => setMascot('yuragi')}
						/>
						<span>{t().settingsMascotYuragi}</span>
					</label>
				</div>
			</div>
			<div class="popover-group">
				<div class="popover-group-label generation-label">
					<span>{t().settingsGenerationLabel}</span>
					<Tooltip placement="bottom-right" wide text={t().tooltipDdlAutoRepairDetails}>
						<span class="settings-info-mark" aria-hidden="true">i</span>
					</Tooltip>
				</div>
				<label class="setting-toggle" title={t().tooltipDdlAutoRepair}>
					<input type="checkbox" bind:checked={autoRepairEnabled} />
					<span>{t().ddlAutoRepairLabel}</span>
				</label>
			</div>

<script lang="ts">
	import { t } from '$lib/i18n/index.svelte';
	import NumberStepper from '$lib/components/NumberStepper.svelte';
	import { exportSettings } from '$lib/features/export/settings.svelte';
	import {
		CLIPBOARD_HEIGHT_MAX,
		CLIPBOARD_HEIGHT_MIN,
		clampClipboardHeight,
		type ClipboardExportFormat
	} from '$lib/clipboardExport';
	import './export-settings.css';

	function setFormat(format: ClipboardExportFormat): void {
		exportSettings.clipboard = { ...exportSettings.clipboard, format };
	}

	function setHeight(height: number): void {
		exportSettings.clipboard = { ...exportSettings.clipboard, height: clampClipboardHeight(height) };
	}
</script>

<div class="popover-group export-pane">
	<div class="popover-group-label">{t().clipboardFormatLabel}</div>
	<div class="settings-radio-set" role="group" aria-label={t().clipboardFormatLabel}>
		<label class="setting-toggle">
			<input type="radio" name="clipboard-format" value="image" checked={exportSettings.clipboard.format === 'image'} onchange={() => setFormat('image')} />
			<span>{t().clipboardFormatImage}</span>
		</label>
		<label class="setting-toggle">
			<input type="radio" name="clipboard-format" value="card" checked={exportSettings.clipboard.format === 'card'} onchange={() => setFormat('card')} />
			<span>{t().clipboardFormatCard}</span>
		</label>
	</div>
	{#if exportSettings.clipboard.format === 'card'}
		<div class="export-scope-note">{t().clipboardFormatCardNote}</div>
	{/if}
</div>
<div class="popover-group export-pane">
	<div class="popover-group-label">{t().clipboardHeightLabel}</div>
	<div class="db-test-result">{t().clipboardHeightDescription}</div>
	<NumberStepper
		label={t().clipboardHeightLabel}
		min={CLIPBOARD_HEIGHT_MIN}
		max={CLIPBOARD_HEIGHT_MAX}
		step={64}
		value={exportSettings.clipboard.height}
		onChange={setHeight}
	/>
</div>

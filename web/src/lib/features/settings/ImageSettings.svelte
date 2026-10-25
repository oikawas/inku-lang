<script lang="ts">
	import { t } from '$lib/i18n/index.svelte';
	import { imageProvenanceSettings } from '$lib/features/image-provenance/settings.svelte';
	import './export-settings.css';

	function setIncludeFileName(includeFileName: boolean): void {
		imageProvenanceSettings.options = { ...imageProvenanceSettings.options, includeFileName };
	}

	function setIncludeExif(includeExif: boolean): void {
		imageProvenanceSettings.options = { ...imageProvenanceSettings.options, includeExif };
	}
</script>

<div class="popover-group export-pane">
	<div class="popover-group-label">{t().imageProvenanceLabel}</div>
	<div class="db-test-result">{t().settingsImageProvenanceDescription}</div>
	<label class="setting-toggle">
		<input type="checkbox" checked={imageProvenanceSettings.options.includeFileName} onchange={(event) => setIncludeFileName(event.currentTarget.checked)} />
		<span>{t().settingsImageProvenanceFileName}</span>
	</label>
	<label class="setting-toggle">
		<input type="checkbox" checked={imageProvenanceSettings.options.includeExif} onchange={(event) => setIncludeExif(event.currentTarget.checked)} />
		<span>{t().settingsImageProvenanceExif}</span>
	</label>
	<div class="export-scope-note">{t().settingsImageProvenanceExifNote}</div>
</div>

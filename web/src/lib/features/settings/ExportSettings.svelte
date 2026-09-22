<script lang="ts">
	import { t } from '$lib/i18n/index.svelte';
	import { downloadFolderSettings } from '$lib/features/export/download-folder.svelte';
	import AnimationExportFields from '$lib/features/export/AnimationExportFields.svelte';
	import type { ExportTemplate } from '$lib/exportTemplates';
	import type { AnimationExportSettings } from '$lib/animationExport';
	import type { CardExportSettings } from '$lib/cardExport';
	import './export-settings.css';

	type Props = {
		pngAlphaWhite: boolean;
		exportTemplates: ExportTemplate[];
		exportTemplateStatus: string | null;
		animationExportSettings: AnimationExportSettings;
		cardExportSettings: CardExportSettings;
		onChooseDownloadFolder: () => void | Promise<void>;
		onClearDownloadFolder: () => void | Promise<void>;
		onAddExportTemplate: () => void | Promise<void>;
		onUpdateExportTemplate: (id: string, patch: Partial<ExportTemplate>) => void | Promise<void>;
		onRemoveExportTemplate: (id: string) => void | Promise<void>;
	};

	let {
		pngAlphaWhite = $bindable(), exportTemplates, exportTemplateStatus,
		animationExportSettings = $bindable(), cardExportSettings = $bindable(),
		onChooseDownloadFolder, onClearDownloadFolder, onAddExportTemplate,
		onUpdateExportTemplate, onRemoveExportTemplate
	}: Props = $props();
</script>

			<!-- Chromium only: showDirectoryPicker does not exist in Firefox or
			     Safari, and a setting that is visible but cannot work is worse than
			     no setting, so the whole group is withheld rather than disabled. -->
			{#if downloadFolderSettings.supported}
				<div class="popover-group">
					<div class="popover-group-label">{t().settingsDownloadFolderLabel}</div>
					<div class="db-test-result">{t().settingsDownloadFolderDescription}</div>
					<div class="db-test-result">{t().settingsDownloadFolderBrowserOnly}</div>
					<div class="download-folder-row">
						<span class="download-folder-name">
							{#if downloadFolderSettings.enabled && downloadFolderSettings.name}
								{t().settingsDownloadFolderCurrent(downloadFolderSettings.name)}
							{:else}
								{t().settingsDownloadFolderNone}
							{/if}
						</span>
						<button class="ghost-btn" onclick={onChooseDownloadFolder}>{t().settingsDownloadFolderChoose}</button>
						{#if downloadFolderSettings.enabled}
							<button class="ghost-btn" onclick={onClearDownloadFolder}>{t().settingsDownloadFolderClear}</button>
						{/if}
					</div>
					{#if downloadFolderSettings.needsPicking}
						<div class="inline-message">{t().settingsDownloadFolderNeedsPicking}</div>
					{/if}
				</div>
			{/if}
			<div class="popover-group">
				<div class="popover-group-label">{t().settingsExportTemplatesTitle}</div>
				<div class="db-test-result">{t().settingsExportTemplatesDescription}</div>
				{#if exportTemplateStatus}
					<div class="inline-message">{exportTemplateStatus}</div>
				{/if}
				<div class="export-template-table">
					<div class="export-template-head">
						<span>{t().settingsExportTemplateName}</span>
						<span>{t().settingsExportTemplateDescription}</span>
						<span>{t().settingsExportTemplateHeight}</span>
						<span></span>
					</div>
					<div class="export-template-list">
						{#each exportTemplates as template (template.id)}
							<div class="export-template-row">
								<input
									value={template.name}
									aria-label={t().settingsExportTemplateName}
									onchange={(e) => onUpdateExportTemplate(template.id, { name: (e.currentTarget as HTMLInputElement).value })}
								/>
								<input
									value={template.description}
									aria-label={t().settingsExportTemplateDescription}
									onchange={(e) => onUpdateExportTemplate(template.id, { description: (e.currentTarget as HTMLInputElement).value })}
								/>
								<input
									value={template.y_px}
									type="number"
									min="64"
									max="12000"
									step="1"
									aria-label={t().settingsExportTemplateHeight}
									onchange={(e) => onUpdateExportTemplate(template.id, { y_px: Number((e.currentTarget as HTMLInputElement).value) })}
								/>
								<button class="ghost-btn" onclick={() => onRemoveExportTemplate(template.id)}>{t().settingsExportTemplateDelete}</button>
							</div>
						{/each}
					</div>
				</div>
				<div class="settings-inline-actions">
					<button class="ghost-btn primary-inline" onclick={onAddExportTemplate}>{t().settingsExportTemplateAdd}</button>
				</div>
			</div>
			<div class="popover-group">
				<div class="popover-group-label">{t().settingsAnimationExportTitle}</div>
				<div class="db-test-result">{t().settingsAnimationExportDescription}</div>
				<AnimationExportFields bind:settings={animationExportSettings} />
			</div>
			<div class="popover-group">
				<div class="popover-group-label">{t().settingsCardExportTitle}</div>
				<div class="db-test-result">{t().settingsCardExportDescription}</div>
				<div class="animation-settings-grid">
					<label>
						<span>{t().settingsCardLayout}</span>
						<select value={cardExportSettings.layout} onchange={(event) => (cardExportSettings = { ...cardExportSettings, layout: event.currentTarget.value as CardExportSettings["layout"] })}>
							<option value="square">{t().cardLayoutSquare}</option>
							<option value="portrait">{t().cardLayoutPortrait}</option>
						</select>
					</label>
					<label class="setting-toggle">
						<input type="checkbox" checked={cardExportSettings.seal} onchange={(event) => (cardExportSettings = { ...cardExportSettings, seal: event.currentTarget.checked })} />
						<span>{t().settingsCardSeal}</span>
					</label>
				</div>
			</div>
			<div class="popover-group">
				<div class="popover-group-label">{t().settingsExportLabel}</div>
				<label class="setting-toggle">
					<input type="checkbox" bind:checked={pngAlphaWhite} />
					<span>{t().settingsPngAlpha}</span>
				</label>
			</div>

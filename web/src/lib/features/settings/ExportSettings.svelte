<script lang="ts">
	import { t } from '$lib/i18n/index.svelte';
	import { downloadFolderSettings } from '$lib/features/export/download-folder.svelte';
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
				<div class="settings-inline-actions">
					<button class="ghost-btn primary-inline" onclick={onAddExportTemplate}>{t().settingsExportTemplateAdd}</button>
				</div>
			</div>
			<div class="popover-group">
				<div class="popover-group-label">{t().settingsAnimationExportTitle}</div>
				<div class="db-test-result">{t().settingsAnimationExportDescription}</div>
				<div class="animation-settings-grid">
					<label>
						<span>{t().settingsAnimationFormat}</span>
						<select value={animationExportSettings.format} onchange={(event) => (animationExportSettings = { ...animationExportSettings, format: event.currentTarget.value as AnimationExportSettings["format"] })}>
							<option value="apng">{t().animationFormatApng}</option>
							<option value="gif">{t().animationFormatGif}</option>
						</select>
					</label>
					<label>
						<span>{t().settingsAnimationPattern}</span>
						<select value={animationExportSettings.pattern} onchange={(event) => (animationExportSettings = { ...animationExportSettings, pattern: event.currentTarget.value as AnimationExportSettings["pattern"] })}>
							<option value="cut">{t().animationPatternCut}</option>
							<option value="crossfade">{t().animationPatternCrossfade}</option>
							<option value="fade_white">{t().animationPatternFadeWhite}</option>
							<option value="slide">{t().animationPatternSlide}</option>
						</select>
					</label>
					<label>
						<span>{t().settingsAnimationHold}</span>
						<input type="number" min="0.1" max="30" step="0.1" value={animationExportSettings.holdSeconds} onchange={(event) => (animationExportSettings = { ...animationExportSettings, holdSeconds: Math.max(0.1, Math.min(30, Number(event.currentTarget.value) || 1)) })} />
						<small>{t().settingsAnimationHoldHint}</small>
					</label>
					<label>
						<span>{t().settingsAnimationResolution}</span>
						<select value={animationExportSettings.resolution} onchange={(event) => (animationExportSettings = { ...animationExportSettings, resolution: event.currentTarget.value as AnimationExportSettings["resolution"] })}>
							<option value="150">{t().animationResolution150}</option>
							<option value="300">{t().animationResolution300}</option>
							<option value="500">{t().animationResolution500}</option>
							<option value="1k">{t().animationResolution1k}</option>
							<option value="4k">{t().animationResolution4k}</option>
							<option value="8k">{t().animationResolution8k}</option>
							<option value="custom">{t().animationResolutionCustom}</option>
						</select>
						{#if animationExportSettings.resolution === "custom"}
							<input
								type="number"
								min="64"
								max="12000"
								step="1"
								value={animationExportSettings.customHeight}
								aria-label={t().animationCustomHeight}
								onchange={(event) => (animationExportSettings = { ...animationExportSettings, customHeight: Math.max(64, Math.min(12000, Math.round(Number(event.currentTarget.value) || 720))) })}
							/>
							<small>{t().animationCustomHeight}</small>
						{/if}
					</label>
				</div>
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

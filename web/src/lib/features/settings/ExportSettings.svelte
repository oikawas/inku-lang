<script lang="ts">
	import { t } from '$lib/i18n/index.svelte';
	import { downloadFolderSettings } from '$lib/features/export/download-folder.svelte';
	import AnimationExportFields from '$lib/features/export/AnimationExportFields.svelte';
	import type { ExportTemplate } from '$lib/exportTemplates';
	import type { AnimationExportSettings } from '$lib/animationExport';
	import type { CardExportSettings } from '$lib/cardExport';
	import './export-settings.css';

	type ExportSection = 'destination' | 'png' | 'animation' | 'card';
	type TemplateDraft = Pick<ExportTemplate, 'name' | 'description' | 'y_px'>;

	type Props = {
		pngAlphaWhite: boolean;
		exportTemplates: ExportTemplate[];
		exportTemplateStatus: string | null;
		animationExportSettings: AnimationExportSettings;
		cardExportSettings: CardExportSettings;
		onChooseDownloadFolder: () => void | Promise<void>;
		onClearDownloadFolder: () => void | Promise<void>;
		onAddExportTemplate: () => boolean | Promise<boolean>;
		onUpdateExportTemplate: (id: string, patch: Partial<ExportTemplate>) => boolean | Promise<boolean>;
		onRemoveExportTemplate: (id: string) => boolean | Promise<boolean>;
	};

	let {
		pngAlphaWhite = $bindable(), exportTemplates, exportTemplateStatus,
		animationExportSettings = $bindable(), cardExportSettings = $bindable(),
		onChooseDownloadFolder, onClearDownloadFolder, onAddExportTemplate,
		onUpdateExportTemplate, onRemoveExportTemplate
	}: Props = $props();

	let activeSection = $state<ExportSection>('destination');
	let animationMode = $state<'layer' | 'transition'>('layer');
	let templateDrafts = $state<Record<string, Partial<TemplateDraft>>>({});
	let templatesSaving = $state(false);

	function draftFor(template: ExportTemplate): TemplateDraft {
		return { ...template, ...templateDrafts[template.id] };
	}

	function updateTemplateDraft(template: ExportTemplate, patch: Partial<TemplateDraft>): void {
		templateDrafts = {
			...templateDrafts,
			[template.id]: { ...templateDrafts[template.id], ...patch }
		};
	}

	function resetTemplateDraft(id: string): void {
		const { [id]: _discarded, ...remaining } = templateDrafts;
		templateDrafts = remaining;
	}

	function templateValidation(template: ExportTemplate): string | null {
		const draft = draftFor(template);
		if (!draft.name.trim()) return t().settingsExportTemplateNameRequired;
		if (!Number.isInteger(draft.y_px) || draft.y_px < 64 || draft.y_px > 12000) {
			return t().settingsExportTemplateHeightRange;
		}
		return null;
	}

	function templateIsDirty(template: ExportTemplate): boolean {
		const draft = draftFor(template);
		return draft.name !== template.name || draft.description !== template.description || draft.y_px !== template.y_px;
	}

	async function saveTemplate(template: ExportTemplate): Promise<void> {
		if (!templateIsDirty(template) || templateValidation(template)) return;
		await writeTemplates(async () => {
			const saved = await onUpdateExportTemplate(template.id, draftFor(template));
			if (saved) resetTemplateDraft(template.id);
			return saved;
		});
	}

	// Each operation writes the complete list, so only one may be in flight.
	async function writeTemplates(write: () => boolean | Promise<boolean>): Promise<void> {
		if (templatesSaving) return;
		templatesSaving = true;
		try {
			await write();
		} finally {
			templatesSaving = false;
		}
	}
</script>

			<nav class="export-section-tabs" aria-label={t().settingsExportLabel}>
				<button type="button" aria-pressed={activeSection === 'destination'} class:active={activeSection === 'destination'} onclick={() => (activeSection = 'destination')}>{t().settingsExportNavDestination}</button>
				<button type="button" aria-pressed={activeSection === 'png'} class:active={activeSection === 'png'} onclick={() => (activeSection = 'png')}>{t().settingsExportNavPng}</button>
				<button type="button" aria-pressed={activeSection === 'animation'} class:active={activeSection === 'animation'} onclick={() => (activeSection = 'animation')}>{t().settingsExportNavAnimation}</button>
				<button type="button" aria-pressed={activeSection === 'card'} class:active={activeSection === 'card'} onclick={() => (activeSection = 'card')}>{t().settingsExportNavCard}</button>
			</nav>

			{#if activeSection === 'destination'}
				<div class="popover-group">
					<div class="popover-group-label">{t().settingsDownloadFolderLabel}</div>
					<div class="db-test-result">{t().settingsDownloadFolderDescription}</div>
					<div class="export-scope-note">{t().settingsExportBrowserScope}</div>
					{#if downloadFolderSettings.supported}
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
					{:else}
						<div class="inline-message">{t().settingsDownloadFolderUnavailable}</div>
					{/if}
				</div>
			{/if}
			{#if activeSection === 'png'}
			<div class="popover-group export-pane">
				<div class="popover-group-label">{t().settingsExportTemplatesTitle}</div>
				<div class="db-test-result">{t().settingsExportTemplatesDescription}</div>
				<div class="export-scope-note">{t().settingsExportAccountScope}</div>
				{#if exportTemplateStatus}
					<div class="inline-message">{exportTemplateStatus}</div>
				{/if}
				<div class="export-template-table">
					<div class="export-template-list">
						{#each exportTemplates as template (template.id)}
							{@const draft = draftFor(template)}
							{@const validation = templateValidation(template)}
							<div class="export-template-row">
								<label><span>{t().settingsExportTemplateName}</span>
								<input
									disabled={templatesSaving}
									value={draft.name}
									aria-label={t().settingsExportTemplateName}
									oninput={(e) => updateTemplateDraft(template, { name: (e.currentTarget as HTMLInputElement).value })}
								/>
								</label>
								<label><span>{t().settingsExportTemplateDescription}</span>
								<input
									disabled={templatesSaving}
									value={draft.description}
									aria-label={t().settingsExportTemplateDescription}
									oninput={(e) => updateTemplateDraft(template, { description: (e.currentTarget as HTMLInputElement).value })}
								/>
								</label>
								<label><span>{t().settingsExportTemplateHeight}</span>
								<input
									disabled={templatesSaving}
									value={draft.y_px}
									type="number"
									min="64"
									max="12000"
									step="1"
									aria-label={t().settingsExportTemplateHeight}
									oninput={(e) => updateTemplateDraft(template, { y_px: Number((e.currentTarget as HTMLInputElement).value) })}
								/>
								</label>
								<div class="export-template-actions">
									{#if templateIsDirty(template)}
										<button class="ghost-btn primary-inline" disabled={Boolean(validation) || templatesSaving} onclick={() => void saveTemplate(template)}>{t().settingsExportTemplateSave}</button>
										<button class="ghost-btn" disabled={templatesSaving} onclick={() => resetTemplateDraft(template.id)}>{t().settingsExportTemplateReset}</button>
									{:else}
										<button class="ghost-btn" disabled={templatesSaving} onclick={() => writeTemplates(() => onRemoveExportTemplate(template.id))}>{t().settingsExportTemplateDelete}</button>
									{/if}
								</div>
								{#if templateIsDirty(template)}
									<div class="export-template-state" class:invalid={Boolean(validation)}>{validation ?? t().settingsExportTemplateUnsaved}</div>
								{/if}
							</div>
						{/each}
					</div>
				</div>
				<div class="settings-inline-actions">
					<button class="ghost-btn primary-inline" disabled={templatesSaving} onclick={() => writeTemplates(onAddExportTemplate)}>{t().settingsExportTemplateAdd}</button>
				</div>
				<div class="export-subgroup">
					<div class="popover-group-label">{t().settingsExportLabel}</div>
					<div class="export-scope-note">{t().settingsExportDefaultScope}</div>
					<label class="setting-toggle">
						<input type="checkbox" bind:checked={pngAlphaWhite} />
						<span>{t().settingsPngAlpha}</span>
					</label>
				</div>
			</div>
			{/if}
			{#if activeSection === 'animation'}
			<div class="popover-group export-pane">
				<div class="popover-group-label">{t().settingsAnimationExportTitle}</div>
				<div class="db-test-result">{t().settingsAnimationExportDescription}</div>
				<div class="export-scope-note">{t().settingsExportDefaultScope}</div>
				<div class="export-section-tabs">
					<button type="button" aria-pressed={animationMode === 'layer'} class:active={animationMode === 'layer'} onclick={() => (animationMode = 'layer')}>{t().settingsExportAnimationLayer}</button>
					<button type="button" aria-pressed={animationMode === 'transition'} class:active={animationMode === 'transition'} onclick={() => (animationMode = 'transition')}>{t().settingsExportAnimationTransition}</button>
				</div>
				<AnimationExportFields bind:settings={animationExportSettings} mode={animationMode} />
			</div>
			{/if}
			{#if activeSection === 'card'}
			<div class="popover-group export-pane">
				<div class="popover-group-label">{t().settingsCardExportTitle}</div>
				<div class="db-test-result">{t().settingsCardExportDescription}</div>
				<div class="export-scope-note">{t().settingsExportDefaultScope}</div>
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
			{/if}

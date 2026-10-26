<script lang="ts">
	import { t } from '$lib/i18n/index.svelte';
	import type { PluginPackageProblem, PluginPackageReport } from './server-administration.svelte';
	import { pluginProblemMessage } from './plugin-package-problems';

	// Adding a plugin is one file: choosing it checks it at once, and the
	// result says word by word what the Saijiki will show or what is wrong
	// and where. Only a package that passed every check can be added.
	type Props = {
		isAdmin: boolean;
		onCheck: (document: string) => Promise<PluginPackageReport | null>;
		onInstall: (document: string, replace: boolean) => Promise<PluginPackageReport | true | null>;
	};

	let { isAdmin, onCheck, onInstall }: Props = $props();

	let fileInput = $state<HTMLInputElement | null>(null);
	let fileName = $state('');
	let documentText = $state('');
	let report = $state<PluginPackageReport | null>(null);
	let busy = $state(false);
	let installed = $state('');
	const isJapanese = $derived(t().code === 'ja');

	async function chooseFile(event: Event): Promise<void> {
		const input = event.currentTarget as HTMLInputElement;
		const file = input.files?.[0];
		input.value = '';
		if (!file) return;
		fileName = file.name;
		installed = '';
		report = null;
		busy = true;
		documentText = await file.text();
		report = await onCheck(documentText);
		busy = false;
	}

	async function install(): Promise<void> {
		if (!report?.ok || busy) return;
		busy = true;
		const result = await onInstall(documentText, report.exists === true);
		busy = false;
		if (result === true) {
			installed = report.id ?? '';
			report = null;
			documentText = '';
			fileName = '';
		} else if (result) {
			report = result;
		}
	}

	function cancel(): void {
		report = null;
		documentText = '';
		fileName = '';
	}

	function describe(problem: PluginPackageProblem): string {
		const message = pluginProblemMessage(problem.code, isJapanese);
		return problem.detail ? `${message}（${problem.detail}）` : message;
	}
</script>

<div class="plugin-installer">
	<div class="plugin-installer-head">
		<button class="ghost-btn" type="button" onclick={() => fileInput?.click()} disabled={!isAdmin || busy}>{t().settingsUserPluginsAddTitle}</button>
		<input bind:this={fileInput} class="plugin-installer-file" type="file" accept=".json,application/json" onchange={chooseFile} />
		<span class="plugin-use-hint">{t().settingsUserPluginsAddDescription}</span>
	</div>
	{#if busy && !report}
		<div class="inline-message">{t().settingsPluginPackageChecking}（{fileName}）</div>
	{/if}
	{#if installed}
		<div class="inline-message">{t().settingsPluginPackageInstalled.replace('{id}', installed)}</div>
	{/if}
	{#if report}
		<div class="plugin-check" class:plugin-check-failed={!report.ok}>
			<div class="system-plugin-title-row">
				<div class="system-plugin-title">{report.id ?? fileName}</div>
				{#if report.version}<span class="plugin-version-pill">v{report.version}</span>{/if}
				<span class="plugin-use-mark" class:not-drawn={!report.ok}>{report.ok ? t().settingsPluginPackageCheckPassed : t().settingsPluginPackageCheckFailed}</span>
			</div>
			{#if (isJapanese ? report.description_ja : report.description_en)}<div class="system-plugin-desc">{isJapanese ? report.description_ja : report.description_en}</div>{/if}
			{#if report.problems.length}
				<ul class="plugin-problems">
					{#each report.problems as problem (problem.path + problem.code)}
						<li><code>{problem.path || fileName}</code> {describe(problem)}</li>
					{/each}
				</ul>
			{/if}
			{#if report.words.length}
				<ul class="plugin-word-list">
					{#each report.words as word (word.qualified_name)}
						<li class="plugin-word">
							{#if word.preview_png}<img class="plugin-word-preview" src={word.preview_png} alt="" />{:else}<span class="plugin-word-preview" aria-hidden="true"></span>{/if}
							<div class="plugin-word-text">
								<strong>{word.qualified_name}</strong>
								{#if word.aliases.length}<small>{word.aliases.join(', ')}</small>{/if}
								<span>{t().saijikiPreviewExampleLabel}{isJapanese ? word.example_ja : word.example_en}</span>
								<span>{isJapanese ? word.summary_ja : word.summary_en}</span>
								{#if word.problems.length}
									<ul class="plugin-problems">
										{#each word.problems as problem (problem.path + problem.code)}
											<li><code>{problem.path}</code> {describe(problem)}</li>
										{/each}
									</ul>
								{/if}
							</div>
						</li>
					{/each}
				</ul>
			{/if}
			<div class="settings-inline-actions">
				{#if report.ok}
					<button class="ghost-btn" type="button" onclick={() => void install()} disabled={!isAdmin || busy}>{report.exists ? t().settingsPluginPackageReplace : t().settingsPluginPackageInstall}</button>
				{/if}
				<button class="ghost-btn" type="button" onclick={() => fileInput?.click()} disabled={!isAdmin || busy}>{t().settingsPluginPackageChooseAgain}</button>
				<button class="ghost-btn" type="button" onclick={cancel} disabled={busy}>{t().confirmCancel}</button>
			</div>
			{#if report.ok && report.exists}<div class="plugin-use-hint">{t().settingsPluginPackageReplaceHint}</div>{/if}
		</div>
	{/if}
</div>

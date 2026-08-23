import { composeFallbackValue } from '../../composeFallback.ts';
import { DEFAULT_DEMO_SETTINGS, type DemoSettings } from '../../demo.ts';
import { qualifiedModelId, splitModelRef, type ProviderGroup } from '../../models.ts';
import type { CanvasAspectId } from '../../plugins/system/canvas-aspect/index.ts';
import type { ApiFetch } from '../../transport/api-fetch.ts';
import type {
	CurrentWorkResult,
	InstructionLang,
	PaintOptions,
} from '../run/current-work.ts';

type DemoSavedWork = {
	id: string;
	at: number;
	render_hash?: string | null;
	render_hash_short?: string | null;
};

export type DemoStateDependencies = {
	apiFetch: ApiFetch;
	signedIn: () => boolean;
	instructionLang: () => InstructionLang;
	uiLang: () => string;
	describeApiError: (detail: unknown, status: number) => string;
	now?: () => number;
	sleep?: (ms: number) => Promise<void>;
	warn?: (message: string, cause: unknown) => void;
};

export type DemoRunOptions<TResult extends CurrentWorkResult> = {
	canvasAspectId: () => CanvasAspectId;
	renderOverrides: () => PaintOptions['renderOverrides'];
	paintInstruction: (prompt: string, options: PaintOptions) => Promise<TResult>;
	onLatestResult: (result: TResult, prompt: string) => void;
	onRunFinished: () => void;
	refreshAfterServerSave: () => Promise<void>;
	refreshAfterRun: () => Promise<void>;
};

export type DemoSaveOptions<TResult extends CurrentWorkResult> = {
	stage1Model: string;
	stage2Model: string;
	effectiveCatalogId: string;
	canvasAspectId: CanvasAspectId;
	instructionLang: InstructionLang;
	uiLang: string;
	savedStatus: string;
	onSaved: (result: TResult) => void;
	refreshHistory: () => Promise<void>;
};

/**
 * Route-instance owner for Demo settings, repetition, and the current result.
 *
 * The route lends it one-work painting and focused projection callbacks. A
 * private identity guards every write after awaited instruction or paint work,
 * so a stopped request cannot replace the next run or its Canvas projection.
 */
export class DemoState<TResult extends CurrentWorkResult = CurrentWorkResult> {
	settings = $state<DemoSettings>({ ...DEFAULT_DEMO_SETTINGS });
	settingsLoaded = $state(false);
	generatedPrompt = $state('');
	generatedDdl = $state<string | null>(null);
	running = $state(false);
	timedOut = $state(false);
	error = $state<string | null>(null);
	saveStatus = $state<string | null>(null);
	savingCurrent = $state(false);
	currentSaved = $state(false);
	waitingSeconds = $state<number | null>(null);
	currentStartedAt: number | null = null;
	currentLiveMs = $state<number | null>(null);
	currentElapsedMs = $state<number | null>(null);
	currentTokensIn = $state<number | null>(null);
	currentTokensOut = $state<number | null>(null);
	totalElapsedMs = $state(0);
	totalTokensIn = $state(0);
	totalTokensOut = $state(0);
	renderCount = $state(0);
	latestResult = $state<TResult | null>(null);

	private readonly deps: DemoStateDependencies;
	private runIdentity = 0;
	private activeRefreshAfterRun: (() => Promise<void>) | null = null;

	constructor(deps: DemoStateDependencies) {
		this.deps = deps;
	}

	get canSaveCurrent(): boolean {
		return this.latestResult !== null
			&& this.generatedPrompt.length > 0
			&& this.generatedDdl !== null
			&& !this.currentSaved;
	}

	normalizeSettings(settings: DemoSettings): DemoSettings {
		// Older rows kept the provider inside prompt_model. Normalize that legacy
		// representation at the same boundary as current server responses.
		const prompt = splitModelRef(settings.prompt_model || DEFAULT_DEMO_SETTINGS.prompt_model);
		return {
			save_db: !!settings.save_db,
			save_files: !!settings.save_files,
			prompt_provider: prompt.provider ?? settings.prompt_provider ?? DEFAULT_DEMO_SETTINGS.prompt_provider,
			prompt_model: prompt.model,
			seed_phrase: settings.seed_phrase.trim() || DEFAULT_DEMO_SETTINGS.seed_phrase,
			interval_seconds: Math.max(1, Math.min(3600, Math.round(settings.interval_seconds || 30))),
			timeout_seconds: Math.max(60, Math.min(86400, Math.round(settings.timeout_seconds || 3600))),
		};
	}

	async loadSettings(): Promise<void> {
		if (!this.deps.signedIn()) {
			this.resetForSignedOut();
			return;
		}
		try {
			const response = await this.deps.apiFetch('/api/auth/me/demo-settings', { cache: 'no-store' });
			if (!response.ok) throw new Error(`HTTP ${response.status}`);
			this.settings = this.normalizeSettings(await response.json() as DemoSettings);
			this.settingsLoaded = true;
		} catch (cause) {
			this.resetForSignedOut();
			this.warn('failed to load demo settings', cause);
		}
	}

	async saveSettings(settings: DemoSettings): Promise<void> {
		const next = this.normalizeSettings(settings);
		this.settings = next;
		if (!this.deps.signedIn() || !this.settingsLoaded) return;
		try {
			const response = await this.deps.apiFetch('/api/auth/me/demo-settings', {
				method: 'PUT',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify(next),
			});
			if (!response.ok) throw new Error(`HTTP ${response.status}`);
			this.settings = this.normalizeSettings(await response.json() as DemoSettings);
		} catch (cause) {
			this.warn('failed to save demo settings', cause);
		}
	}

	reconcilePromptModel(groups: ProviderGroup[], catalogLoaded: boolean): void {
		if (!catalogLoaded || !this.settingsLoaded) return;
		const configured = groups.some((group) =>
			group.id === this.settings.prompt_provider
			&& group.models.some((model) => model.id === this.settings.prompt_model)
		);
		if (configured) return;
		const fallbackGroup = groups.find((group) => group.models.length > 0);
		const fallbackModel = fallbackGroup?.models[0]?.id;
		if (!fallbackGroup || !fallbackModel) return;
		void this.saveSettings({
			...this.settings,
			prompt_provider: fallbackGroup.id,
			prompt_model: fallbackModel,
		});
	}

	resetForSignedOut(): void {
		this.settings = { ...DEFAULT_DEMO_SETTINGS };
		this.settingsLoaded = false;
	}

	updateLiveTime(now = this.now()): void {
		if (this.currentStartedAt !== null) this.currentLiveMs = now - this.currentStartedAt;
	}

	clearInput(): void {
		this.generatedPrompt = '';
		this.generatedDdl = null;
		this.error = null;
		this.saveStatus = null;
		this.currentSaved = false;
		this.latestResult = null;
	}

	async start(options: DemoRunOptions<TResult>): Promise<void> {
		const runId = ++this.runIdentity;
		this.activeRefreshAfterRun = options.refreshAfterRun;
		this.resetRunProjection();
		this.running = true;
		const timeoutAt = this.now() + this.normalizeSettings(this.settings).timeout_seconds * 1000;

		while (this.isCurrent(runId) && this.now() < timeoutAt) {
			const startedAt = this.now();
			this.currentStartedAt = startedAt;
			this.currentLiveMs = 0;
			this.currentElapsedMs = null;
			this.currentTokensIn = null;
			this.currentTokensOut = null;
			this.waitingSeconds = null;
			try {
				const settings = this.normalizeSettings(this.settings);
				await this.saveSettings(settings);
				if (!this.isCurrent(runId)) break;
				const prompt = await this.generateInstruction(settings);
				if (!this.isCurrent(runId)) break;
				this.generatedPrompt = prompt;

				const result = await options.paintInstruction(prompt, {
					saveHistory: settings.save_db,
					saveArtifacts: settings.save_files,
					countGeneration: false,
					historyInput: `[demo] ${prompt}`,
					sourceText: prompt,
					displayLabel: '[demo]',
					canvasAspectId: options.canvasAspectId(),
					renderOverrides: options.renderOverrides(),
				});
				if (!this.isCurrent(runId)) break;

				this.adoptResult(result);
				options.onLatestResult(result, prompt);
				if (settings.save_db) {
					await options.refreshAfterServerSave();
					if (!this.isCurrent(runId)) break;
				}
				if (this.now() >= timeoutAt) break;

				const intervalRemainingMs = settings.interval_seconds * 1000 - (this.now() - startedAt);
				const timeoutRemainingMs = timeoutAt - this.now();
				const remainingMs = Math.max(0, Math.min(intervalRemainingMs, timeoutRemainingMs));
				const waitingForNextRender = intervalRemainingMs <= timeoutRemainingMs;
				for (let left = Math.ceil(remainingMs / 1000); left > 0 && this.isCurrent(runId); left -= 1) {
					this.waitingSeconds = waitingForNextRender ? left : null;
					await this.sleep(Math.min(1000, remainingMs));
				}
			} catch (cause) {
				if (!this.isCurrent(runId)) break;
				this.currentStartedAt = null;
				this.error = cause instanceof Error ? cause.message : String(cause);
				const retryDelayMs = Math.min(1000, Math.max(0, timeoutAt - this.now()));
				if (retryDelayMs > 0) await this.sleep(retryDelayMs);
			}
		}

		if (!this.isCurrent(runId)) return;
		await options.refreshAfterRun();
		if (!this.isCurrent(runId)) return;
		this.activeRefreshAfterRun = null;
		this.timedOut = this.now() >= timeoutAt;
		this.currentStartedAt = null;
		this.waitingSeconds = null;
		this.running = false;
		options.onRunFinished();
	}

	stop(): void {
		this.runIdentity += 1;
		const refreshAfterRun = this.activeRefreshAfterRun;
		this.activeRefreshAfterRun = null;
		this.running = false;
		this.timedOut = false;
		this.currentStartedAt = null;
		this.currentLiveMs = null;
		this.waitingSeconds = null;
		if (refreshAfterRun) void refreshAfterRun();
	}

	async saveCurrent(options: DemoSaveOptions<TResult>): Promise<void> {
		const current = this.latestResult;
		if (!current || !this.canSaveCurrent || this.savingCurrent) return;
		this.savingCurrent = true;
		this.saveStatus = null;
		try {
			const response = await this.deps.apiFetch('/api/history', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({
					input: `[demo] ${this.generatedPrompt}`,
					source_text: this.generatedPrompt,
					display_label: '[demo]',
					ddl: this.generatedDdl,
					score: current.score,
					at: this.now(),
					elapsed_ms: current.elapsed_total_ms ?? 0,
					stage1_model: current.stage1_model ?? options.stage1Model,
					stage2_model: current.stage2_model ?? options.stage2Model,
					tokens_in: (current.tokens_in_stage1 ?? 0) + (current.tokens_in_stage2 ?? 0) || null,
					tokens_out: (current.tokens_out_stage1 ?? 0) + (current.tokens_out_stage2 ?? 0) || null,
					catalog_id: current.render_color_catalog_id
						?? (options.effectiveCatalogId !== 'default' ? options.effectiveCatalogId : null),
					save_artifacts: this.settings.save_files,
					canvas_aspect: options.canvasAspectId,
					instruction_lang_requested: current.instruction_lang_requested ?? options.instructionLang,
					instruction_lang_resolved: current.instruction_lang_resolved ?? null,
					ui_lang: current.ui_lang ?? options.uiLang,
					// This owner is the second /api/history sender. Preserve the prose and
					// layer state so a Demo work does not appear to have skipped sketching.
					sketch_text: current.sketch_text ?? null,
					sketch_grain: current.sketch_grain ?? null,
					...(current.sketch_state ? { sketch_state: current.sketch_state } : {}),
					// The paint response always tells this sender how composition settled.
					// Persist it so the saved row is not mistaken for a pre-field work.
					compose_fallback: composeFallbackValue(current),
				}),
			});
			if (!response.ok) {
				const data = await response.json().catch(() => ({})) as { detail?: unknown };
				throw new Error(this.deps.describeApiError(data.detail, response.status));
			}
			const saved = await response.json() as DemoSavedWork;
			const updated = {
				...current,
				history_id: saved.id,
				history_at: saved.at,
				render_hash: saved.render_hash,
				render_hash_short: saved.render_hash_short,
			} as TResult;
			this.latestResult = updated;
			this.currentSaved = true;
			this.saveStatus = options.savedStatus;
			options.onSaved(updated);
			await options.refreshHistory();
		} catch (cause) {
			this.error = cause instanceof Error ? cause.message : String(cause);
		} finally {
			this.savingCurrent = false;
		}
	}

	private resetRunProjection(): void {
		this.generatedPrompt = '';
		this.generatedDdl = null;
		this.error = null;
		this.timedOut = false;
		this.saveStatus = null;
		this.currentSaved = false;
		this.waitingSeconds = null;
		this.currentStartedAt = null;
		this.currentLiveMs = null;
		this.currentElapsedMs = null;
		this.currentTokensIn = null;
		this.currentTokensOut = null;
		this.totalElapsedMs = 0;
		this.totalTokensIn = 0;
		this.totalTokensOut = 0;
		this.renderCount = 0;
		this.latestResult = null;
	}

	private adoptResult(result: TResult): void {
		const tokensIn = (result.tokens_in_stage1 ?? 0) + (result.tokens_in_stage2 ?? 0);
		const tokensOut = (result.tokens_out_stage1 ?? 0) + (result.tokens_out_stage2 ?? 0);
		this.generatedDdl = result.ddl;
		this.currentSaved = !!result.history_id;
		this.saveStatus = null;
		this.currentElapsedMs = result.elapsed_total_ms;
		this.currentLiveMs = result.elapsed_total_ms;
		this.currentStartedAt = null;
		this.currentTokensIn = tokensIn;
		this.currentTokensOut = tokensOut;
		this.totalElapsedMs += result.elapsed_total_ms;
		this.totalTokensIn += tokensIn;
		this.totalTokensOut += tokensOut;
		this.renderCount += 1;
		this.latestResult = result;
	}

	private async generateInstruction(settings: DemoSettings): Promise<string> {
		const response = await this.deps.apiFetch('/api/demo/instruction', {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({
				seed_phrase: settings.seed_phrase,
				model: qualifiedModelId(settings.prompt_provider, settings.prompt_model),
				instruction_lang: this.deps.instructionLang(),
				ui_lang: this.deps.uiLang(),
			}),
		});
		if (!response.ok) {
			const data = await response.json().catch(() => ({})) as { detail?: unknown };
			throw new Error(this.deps.describeApiError(data.detail, response.status));
		}
		const data = await response.json() as { instruction: string };
		return data.instruction;
	}

	private isCurrent(runId: number): boolean {
		return this.runIdentity === runId && this.running;
	}

	private now(): number {
		return this.deps.now?.() ?? Date.now();
	}

	private sleep(ms: number): Promise<void> {
		return this.deps.sleep?.(ms) ?? new Promise((resolve) => setTimeout(resolve, ms));
	}

	private warn(message: string, cause: unknown): void {
		(this.deps.warn ?? console.warn)(message, cause);
	}
}

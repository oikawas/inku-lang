import {
	PipelineApi,
	PipelineApiError,
	type PipelineOptions,
	type PipelineView,
} from './api';

type ViewObserver = (view: PipelineView | null) => void;
type Pause = (milliseconds: number) => Promise<void>;

/**
 * Own one browser tab's view of a server-owned pipeline execution.
 *
 * The server snapshot and its revision remain authoritative. The controller
 * only polls saved state, forwards author commands, and asks for performance
 * once a completed delivery is ready. It never retries provider effects.
 */
export class PipelineController {
	private view: PipelineView | null = null;
	private legacyHistoryId: string | null = null;
	private linkedHistoryId: string | null = null;
	private historySelection: Promise<boolean> | null = null;
	private requestOrdinal = 0;
	private readonly api: PipelineApi;
	private readonly options: () => PipelineOptions;
	private readonly observe: ViewObserver;
	private readonly pause: Pause;

	constructor(
		api: PipelineApi,
		options: () => PipelineOptions,
		observe: ViewObserver,
		pause: Pause = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds)),
	) {
		this.api = api;
		this.options = options;
		this.observe = observe;
		this.pause = pause;
	}

	get current(): PipelineView | null {
		return this.view;
	}

	adopt(view: PipelineView): void {
		this.requestOrdinal += 1;
		this.historySelection = null;
		this.legacyHistoryId = null;
		this.linkedHistoryId = null;
		this.setView(view);
	}

	markLegacy(historyId: string): void {
		this.requestOrdinal += 1;
		this.historySelection = null;
		this.linkedHistoryId = null;
		this.legacyHistoryId = historyId;
		this.setView(null);
	}

	markLinkedHistory(historyId: string): void {
		this.requestOrdinal += 1;
		this.historySelection = null;
		this.legacyHistoryId = null;
		this.linkedHistoryId = historyId;
		this.setView(null);
	}

	selectHistory(historyId: string, linkedVariationId?: string | null, signal?: AbortSignal): Promise<boolean> {
		const ordinal = ++this.requestOrdinal;
		this.legacyHistoryId = null;
		this.linkedHistoryId = null;
		this.setView(null);
		const selection = this.resolveHistorySelection(ordinal, historyId, linkedVariationId, signal);
		this.historySelection = selection;
		// A normal history load intentionally does not block painting the saved
		// work on screen. Keep its failure observed until an authoring caller
		// awaits the same selection below.
		void selection.catch(() => undefined);
		return selection;
	}

	private async resolveHistorySelection(
		ordinal: number,
		historyId: string,
		linkedVariationId?: string | null,
		signal?: AbortSignal,
	): Promise<boolean> {
		if (linkedVariationId) {
			if (ordinal !== this.requestOrdinal) return false;
			this.linkedHistoryId = historyId;
			return true;
		}
		try {
			await this.api.historyLink(historyId, signal);
			if (ordinal !== this.requestOrdinal) return false;
			this.linkedHistoryId = historyId;
			return true;
		} catch (cause) {
			if (ordinal !== this.requestOrdinal) return false;
			if (cause instanceof PipelineApiError && cause.status === 404) {
				this.legacyHistoryId = historyId;
				return true;
			}
			throw cause;
		}
	}

	clear(): void {
		this.requestOrdinal += 1;
		this.historySelection = null;
		this.legacyHistoryId = null;
		this.linkedHistoryId = null;
		this.setView(null);
	}

	async fromDescription(description: string, override: PipelineOptions = {}, signal?: AbortSignal): Promise<PipelineView> {
		const authoringOrdinal = await this.awaitHistorySelection(signal);
		const active = this.view;
		const legacy = this.legacyHistoryId;
		const linked = this.linkedHistoryId;
		const options = { ...this.options(), ...override };
		this.assertAuthoringStillCurrent(authoringOrdinal, signal);
		return this.run(() => {
			if (linked) return this.api.forkHistory(linked, 'description', description, options, signal);
			if (legacy) return this.api.forkLegacy(legacy, 'description', description, options, signal);
			if (!active) return this.api.start('description', description, options, signal);
			return this.api.forkDescription(active, description, options, signal);
		});
	}

	async fromDdl(source: string, override: PipelineOptions = {}, signal?: AbortSignal): Promise<PipelineView> {
		const authoringOrdinal = await this.awaitHistorySelection(signal);
		const active = this.view;
		const legacy = this.legacyHistoryId;
		const linked = this.linkedHistoryId;
		const options = { ...this.options(), ...override };
		this.assertAuthoringStillCurrent(authoringOrdinal, signal);
		return this.run(() => {
			if (linked) return this.api.forkHistory(linked, 'direct_ddl', source, options, signal);
			if (legacy) return this.api.forkLegacy(legacy, 'direct_ddl', source, options, signal);
			if (!active) return this.api.start('direct_ddl', source, options, signal);
			return this.api.authorDdl(active, source, options, signal);
		});
	}

	async forkDescription(signal?: AbortSignal): Promise<PipelineView> {
		const active = this.requiredView();
		return this.run(() => this.api.forkDescription(active, active.description, this.options(), signal));
	}

	async approvePatch(signal?: AbortSignal): Promise<PipelineView> {
		const active = this.requiredView();
		const proposalDigest = active.phase.tag === 'awaiting_patch_approval'
			? active.phase.proposal_digest
			: undefined;
		if (!proposalDigest) throw new Error('patch_proposal_missing');
		return this.run(() => this.api.command(active, {
			tag: 'approve_patch',
			expected_revision: active.authority.revision,
			proposal_digest: proposalDigest,
		}, signal));
	}

	async declinePatch(signal?: AbortSignal): Promise<PipelineView> {
		const active = this.requiredView();
		const proposalDigest = active.phase.tag === 'awaiting_patch_approval'
			? active.phase.proposal_digest
			: undefined;
		if (!proposalDigest) throw new Error('patch_proposal_missing');
		return this.run(() => this.api.command(active, {
			tag: 'decline_patch',
			proposal_digest: proposalDigest,
		}, signal), false);
	}

	async reload(signal?: AbortSignal): Promise<PipelineView> {
		const active = this.requiredView();
		return this.run(() => this.api.load(active.variation_id, signal));
	}

	async loadVariation(variationId: string, signal?: AbortSignal): Promise<PipelineView> {
		this.legacyHistoryId = null;
		return this.run(() => this.api.load(variationId, signal), false);
	}

	async cancel(): Promise<void> {
		const active = this.view;
		if (!active) return;
		this.requestOrdinal += 1;
		const next = await this.api.command(active, { tag: 'cancel' });
		this.legacyHistoryId = null;
		this.setView(next);
	}

	private requiredView(): PipelineView {
		if (!this.view) throw new Error('pipeline_execution_missing');
		return this.view;
	}

	private async awaitHistorySelection(signal?: AbortSignal): Promise<number> {
		const ordinal = this.requestOrdinal;
		signal?.throwIfAborted();
		const selection = this.historySelection;
		if (!selection) return ordinal;
		const selected = await selection;
		signal?.throwIfAborted();
		if (!selected || selection !== this.historySelection || ordinal !== this.requestOrdinal) {
			throw new Error('pipeline_history_selection_superseded');
		}
		return ordinal;
	}

	private assertAuthoringStillCurrent(ordinal: number, signal?: AbortSignal): void {
		signal?.throwIfAborted();
		if (ordinal !== this.requestOrdinal) throw new Error('pipeline_history_selection_superseded');
	}

	private setView(view: PipelineView | null): void {
		this.view = view;
		this.observe(view);
	}

	private async run(start: () => Promise<PipelineView>, autoPerform = true): Promise<PipelineView> {
		const ordinal = ++this.requestOrdinal;
		let next = await start();
		if (ordinal !== this.requestOrdinal) return next;
		this.historySelection = null;
		this.legacyHistoryId = null;
		this.linkedHistoryId = null;
		this.setView(next);
		while (next.busy) {
			await this.pause(250);
			if (ordinal !== this.requestOrdinal) return next;
			next = await this.api.load(next.variation_id);
			if (ordinal !== this.requestOrdinal) return next;
			this.setView(next);
		}
		if (
			autoPerform
			&& next.delivery?.score
			&& !next.result
			&& next.phase.tag !== 'awaiting_patch_approval'
		) {
			next = await this.api.command(next, { tag: 'perform' });
			if (ordinal !== this.requestOrdinal) return next;
			this.setView(next);
			while (next.busy) {
				await this.pause(250);
				if (ordinal !== this.requestOrdinal) return next;
				next = await this.api.load(next.variation_id);
				if (ordinal !== this.requestOrdinal) return next;
				this.setView(next);
			}
		}
		return next;
	}
}

import {
	PipelineApi,
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
		this.legacyHistoryId = null;
		this.linkedHistoryId = null;
		this.setView(view);
	}

	markLegacy(historyId: string): void {
		this.requestOrdinal += 1;
		this.linkedHistoryId = null;
		this.legacyHistoryId = historyId;
		this.setView(null);
	}

	markLinkedHistory(historyId: string): void {
		this.requestOrdinal += 1;
		this.legacyHistoryId = null;
		this.linkedHistoryId = historyId;
		this.setView(null);
	}

	clear(): void {
		this.requestOrdinal += 1;
		this.legacyHistoryId = null;
		this.linkedHistoryId = null;
		this.setView(null);
	}

	async fromDescription(description: string, override: PipelineOptions = {}, signal?: AbortSignal): Promise<PipelineView> {
		const active = this.view;
		const legacy = this.legacyHistoryId;
		const linked = this.linkedHistoryId;
		const options = { ...this.options(), ...override };
		return this.run(() => {
			if (linked) return this.api.forkHistory(linked, 'description', description, options, signal);
			if (legacy) return this.api.forkLegacy(legacy, 'description', description, options, signal);
			if (!active) return this.api.start('description', description, options, signal);
			return this.api.forkDescription(active, description, options, signal);
		});
	}

	async fromDdl(source: string, override: PipelineOptions = {}, signal?: AbortSignal): Promise<PipelineView> {
		const active = this.view;
		const legacy = this.legacyHistoryId;
		const linked = this.linkedHistoryId;
		const options = { ...this.options(), ...override };
		return this.run(() => {
			if (linked) return this.api.forkHistory(linked, 'direct_ddl', source, options, signal);
			if (legacy) return this.api.forkLegacy(legacy, 'direct_ddl', source, options, signal);
			if (!active) return this.api.start('direct_ddl', source, options, signal);
			return this.api.command(active, {
				tag: 'commit_user_ddl',
				expected_revision: active.authority.revision,
				source,
			}, signal);
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

	private setView(view: PipelineView | null): void {
		this.view = view;
		this.observe(view);
	}

	private async run(start: () => Promise<PipelineView>, autoPerform = true): Promise<PipelineView> {
		const ordinal = ++this.requestOrdinal;
		let next = await start();
		if (ordinal !== this.requestOrdinal) return next;
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

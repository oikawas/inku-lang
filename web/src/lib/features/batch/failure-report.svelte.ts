// The failure report of the last batch run, kept across reloads so the user can
// still read it after closing the tab.  Key, caps, compaction, parser and state
// stay together -- see features/color-catalog/settings.svelte.ts for why.
import { registerPersistedSetting } from '$lib/features/persisted-settings';
import type { BatchRunConditions } from './resume.ts';

const BATCH_FAILURE_REPORT_KEY = 'inku-batch-failure-report';
const BATCH_FAILURE_REPORT_MAX_ITEMS = 100;
const BATCH_FAILURE_REPORT_MAX_TEXT = 300;

export type BatchFailure = {
	line: number;
	input: string;
	message: string;
};

export type BatchFailureReport = {
	success: number;
	total: number;
	failures: BatchFailure[];
	/** Full source and failed line identities survive the display compaction. */
	retry?: {
		prompt: string;
		runId: string;
		conditions: BatchRunConditions;
		failedLines: number[];
		pendingLines: number[];
	};
};

function compact(report: BatchFailureReport): BatchFailureReport {
	return {
		success: report.success,
		total: report.total,
		failures: report.failures.slice(0, BATCH_FAILURE_REPORT_MAX_ITEMS).map((failure) => ({
			line: failure.line,
			input: failure.input.slice(0, BATCH_FAILURE_REPORT_MAX_TEXT),
			message: failure.message.slice(0, BATCH_FAILURE_REPORT_MAX_TEXT),
		})),
		...(report.retry ? { retry: report.retry } : {}),
	};
}

class BatchFailureReportStore {
	report = $state<BatchFailureReport | null>(null);

	set = (report: BatchFailureReport | null) => {
		const compactReport = report ? compact(report) : null;
		this.report = compactReport;
		try {
			if (compactReport) localStorage.setItem(BATCH_FAILURE_REPORT_KEY, JSON.stringify(compactReport));
			else localStorage.removeItem(BATCH_FAILURE_REPORT_KEY);
		} catch {
			try { localStorage.removeItem(BATCH_FAILURE_REPORT_KEY); } catch {
				/* nothing left to do: the stored report may be stale */
			}
		}
	};

	// Unlike the other settings this one catches on its own: it always did, and
	// a truncated report must not abort the surrounding load block.
	load = () => {
		this.set(this.read());
	};

	private read = (): BatchFailureReport | null => {
		try {
			const raw = localStorage.getItem(BATCH_FAILURE_REPORT_KEY);
			if (!raw) return null;
			const report = JSON.parse(raw) as Partial<BatchFailureReport>;
			if (
				typeof report.success !== 'number' ||
				typeof report.total !== 'number' ||
				!Array.isArray(report.failures)
			) return null;
			const failures = report.failures
				.filter((failure): failure is BatchFailure =>
					typeof failure?.line === 'number' &&
					typeof failure.input === 'string' &&
					typeof failure.message === 'string'
				);
			if (failures.length === 0) return null;
			// Older reports have only compact display text. Do not mistake that
			// truncated text for a complete description when retrying a work.
			const retry = report.retry;
			const validRetry = retry && typeof retry.prompt === 'string' && typeof retry.runId === 'string'
				&& retry.conditions && typeof retry.conditions === 'object'
				&& (['stage1Model', 'stage2Model', 'catalogId', 'catalogMode', 'sketchGrain', 'canvasAspectId'] as const)
					.every((key) => retry.conditions[key] === null || typeof retry.conditions[key] === 'string')
				&& (retry.conditions.wild === null || typeof retry.conditions.wild === 'boolean')
				&& Array.isArray(retry.failedLines) && retry.failedLines.every((line) => Number.isInteger(line) && line > 0)
				&& Array.isArray(retry.pendingLines) && retry.pendingLines.every((line) => Number.isInteger(line) && line > 0)
				&& retry.failedLines.every((line) => retry.pendingLines.includes(line));
			return compact({ success: report.success, total: report.total, failures,
				...(validRetry ? { retry } : {}) });
		} catch {
			return null;
		}
	};
}

export const batchFailureReportStore = new BatchFailureReportStore();

// Restored at start-up with every other persisted setting.
registerPersistedSetting({ id: 'batch-failure-report', load: batchFailureReportStore.load });

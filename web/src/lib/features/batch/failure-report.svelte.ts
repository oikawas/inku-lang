// The failure report of the last batch run, kept across reloads so the user can
// still read it after closing the tab.  Key, caps, compaction, parser and state
// stay together -- see features/color-catalog/settings.svelte.ts for why.
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
			return compact({ success: report.success, total: report.total, failures });
		} catch {
			return null;
		}
	};
}

export const batchFailureReportStore = new BatchFailureReportStore();

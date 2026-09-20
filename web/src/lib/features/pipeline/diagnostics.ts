import type { LangPack } from '../../i18n/types.ts';

export type PipelineDiagnosticChannel = 'upstream' | 'downstream' | 'resource' | 'relation' | 'render' | 'catalog';

export type PipelineDiagnostic = {
	channel: PipelineDiagnosticChannel;
	value: unknown;
};

export type PipelineHistoryDiagnostics = {
	upstream_diagnostics: unknown[];
	downstream_diagnostics: unknown[];
	resource_omissions: unknown[];
	relation_omissions: unknown[];
	render_diagnostics: Record<string, unknown> | null;
	resource_execution: Record<string, unknown> | null;
};

type JsonObject = Record<string, unknown>;

function object(value: unknown): JsonObject | null {
	return value !== null && typeof value === 'object' && !Array.isArray(value)
		? value as JsonObject
		: null;
}

function kind(value: unknown): string | null {
	if (typeof value === 'string') return value;
	const item = object(value);
	return typeof item?.kind === 'string' ? item.kind : null;
}

function reasonOf(value: JsonObject): string {
	const cause = object(value.cause);
	for (const candidate of [value.reason, value.failure, cause?.reason, cause?.failure, value.issue_kind]) {
		if (typeof candidate === 'string') return candidate;
		const tagged = kind(candidate);
		if (tagged) return tagged;
	}
	return 'diagnostic';
}

function budgetReason(value: JsonObject, strings: LangPack): string | null {
	const cause = object(value.cause);
	const reason = object(cause?.reason ?? value.reason ?? value.failure);
	if (kind(reason) !== 'budget_exceeded') return null;
	const detail = object(reason?.value);
	if (
		typeof detail?.dimension !== 'string'
		|| typeof detail.required !== 'number'
		|| typeof detail.maximum !== 'number'
	) return null;
	return strings.pipelineDiagnosticBudgetExceeded(
		strings.pipelineDiagnosticPart(detail.dimension),
		detail.required,
		detail.maximum,
	);
}

function firstIndex(value: unknown): { kind: string; index: number } | null {
	const item = object(value);
	if (!item) return null;
	for (const [field, label] of [
		['source_instruction_index', 'source_instruction'],
		['instruction_index', 'instruction'],
		['target_instruction_index', 'target_instruction'],
		['anchor_index', 'anchor'],
		['target_anchor_index', 'target_anchor'],
		['placement_group_index', 'placement_group'],
		['group_index', 'group'],
	] as const) {
		if (typeof item[field] === 'number') return { kind: label, index: item[field] };
	}
	for (const child of [item.owner, item.value, item.unit, item.disposition]) {
		const found = firstIndex(child);
		if (found) return found;
	}
	return null;
}

function sourceSpan(value: JsonObject): { start: number; end: number } | null {
	const direct = object(value.span);
	if (typeof direct?.start_byte === 'number' && typeof direct.end_byte === 'number') {
		return { start: direct.start_byte, end: direct.end_byte };
	}
	const owner = object(value.owner);
	const spans = owner?.spans;
	if (Array.isArray(spans)) {
		const first = object(spans[0]);
		if (typeof first?.start_byte === 'number' && typeof first.end_byte === 'number') {
			return { start: first.start_byte, end: first.end_byte };
		}
	}
	return null;
}

function omittedUnit(value: JsonObject, channel: PipelineDiagnosticChannel): { kind: string; index?: number } | null {
	const disposition = object(value.disposition);
	const dispositionKind = kind(value.disposition);
	const isOmitted = channel === 'resource'
		|| channel === 'relation'
		|| value.disposition === 'omitted'
		|| dispositionKind === 'omitted'
		|| dispositionKind === 'relation_omitted';
	if (!isOmitted) return null;
	const unit = disposition?.unit ?? value.owner ?? value;
	const indexed = firstIndex(unit);
	return {
		kind: kind(unit) ?? indexed?.kind ?? 'part',
		...(indexed ? { index: indexed.index } : {}),
	};
}

export function formatPipelineDiagnostic(
	diagnostic: PipelineDiagnostic,
	strings: LangPack,
): string {
	const value = object(diagnostic.value);
	if (!value) return strings.pipelineDiagnosticUnknown;
	if (diagnostic.channel === 'catalog') {
		const name = typeof value.qualified_name === 'string' ? `${value.qualified_name}: ` : '';
		return name + strings.pipelineDiagnosticReason(reasonOf(value));
	}
	const parts: string[] = [];
	const span = sourceSpan(value);
	const owner = firstIndex(value.owner ?? value);
	if (span) {
		parts.push(strings.pipelineDiagnosticSourceRange(span.start, span.end));
	} else if (owner) {
		parts.push(strings.pipelineDiagnosticOwner(strings.pipelineDiagnosticPart(owner.kind), owner.index + 1));
	}
	parts.push(budgetReason(value, strings) ?? strings.pipelineDiagnosticReason(reasonOf(value)));
	const partial = object(value.partial_execution);
	if (typeof partial?.requested_count === 'number' && typeof partial.executed_count === 'number') {
		parts.push(strings.pipelineDiagnosticPartialExecution(partial.requested_count, partial.executed_count));
		parts.push(strings.pipelineDiagnosticContinued);
	} else {
		const omitted = omittedUnit(value, diagnostic.channel);
		if (!omitted) return parts.join(' ');
		parts.push(strings.pipelineDiagnosticOmitted(strings.pipelineDiagnosticPart(omitted.kind), omitted.index === undefined ? null : omitted.index + 1));
		parts.push(strings.pipelineDiagnosticContinued);
	}
	return parts.join(' ');
}

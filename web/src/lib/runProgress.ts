import type { LangPack } from './i18n/types.ts';
import type { PaintProgressEvent } from './paintStream.ts';
import { runningStageLabel, type ProviderAttemptCount } from './paintStream.ts';

export function stageName(action: string, s: LangPack): string {
	const names: Record<string, string> = {
		select_description_catalog: s.runStageCatalog, read_description: s.runStageReading,
		compose_description: s.runStageComposition, write_description_ddl: s.runStageWriting,
		review_description_ddl: s.runStageReview, choose_colors: s.runStageColors,
		choose_laws: s.runStageLaws, generate_normalized_ddl: s.runStageInterpret,
		generate_sketch: s.runStageSketch, read_composition: s.runStageCompositionReading,
		complete_visible_ddl_holes: s.runStageCompletion, select_image_catalog: s.runStageImageCatalog,
		write_image_ddl: s.runStageImageWriting, review_image_ddl: s.runStageImageReview
	};
	return names[action] ?? action;
}

export function localWork(action: string, s: LangPack): string {
	if (action === 'draw_image_review') return s.runLocalReview;
	if (action === 'commit_visible_normalized_ddl' || action === 'save') return s.runLocalSave;
	return s.runLocalRender;
}

export function currentWork(
	current: PaintProgressEvent['run_progress']['current'],
	label: string,
	attempt: ProviderAttemptCount | null,
	s: LangPack
): string {
	if (!current) return label;
	if (current.kind === 'local') return localWork(current.action, s);
	const matchingAttempt = attempt?.action === current.action ? attempt : null;
	return runningStageLabel(`${stageName(current.action, s)}…`, {
		attempt: matchingAttempt?.attempt ?? 1,
		max_attempts: matchingAttempt?.max_attempts ?? 1,
		asked_again: matchingAttempt?.asked_again,
		action: current.action
	}, s);
}

/** How a finished stage names its main law (2026-11-13: by name from the composition names table); without one, the code. */
export type LawNamer = { law: (code: string) => string; colorLaw: (code: string) => string };

export function finishedText(item: PaintProgressEvent['run_progress']['finished'][number], s: LangPack, names?: LawNamer): string {
	const stage = stageName(item.action, s);
	if (item.outcome === 'fallback') return s.runFinishedFallback(stage);
	if (item.outcome === 'retried') return s.runFinishedRetried(stage);
	const facts = item.facts;
	if (item.action === 'read_description') return Number(facts.dropped_items) > 0
		? s.runFinishedReadingDropped(String(facts.dropped_items)) : s.runFinishedReading;
	if (item.action === 'compose_description' && facts.things != null && facts.main_law != null)
		return s.runFinishedComposition(String(facts.things), names ? names.law(String(facts.main_law)) : String(facts.main_law));
	if (item.action === 'write_description_ddl' || item.action === 'write_image_ddl') return s.runFinishedWriting;
	if (item.action === 'review_description_ddl' || item.action === 'review_image_ddl') return s.runFinishedReview;
	if (facts.catalog_id != null) return s.runFinishedCatalog(stage, String(facts.catalog_id));
	if (facts.main_law != null) {
		const code = String(facts.main_law);
		const named = !names ? code : item.action === 'choose_colors' ? names.colorLaw(code) : names.law(code);
		return s.runFinishedLaw(stage, named);
	}
	return s.runFinishedReady(stage);
}

export function tokenCount(value: number | null): string {
	return value === null ? '−' : value.toLocaleString('en-US');
}

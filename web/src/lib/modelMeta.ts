// Single source for formatting model evaluation metadata (purposes,
// recommendation, speed, comment). All model-picker surfaces read from here so
// the values and formatting stay consistent. The underlying data lives on
// ModelOption (server model catalog, editable via settings).
import type { ModelOption } from './models';

export function modelPurposes(model: ModelOption): string {
	return (model.purposes ?? ['llm']).map((purpose) => (purpose === 'vision' ? 'Vision' : 'LLM')).join(' / ');
}

export type ModelPurpose = 'llm' | 'vision';

// Which stage is choosing the model. 'both' assigns one model to both stages.
export type ModelStage = 'stage1' | 'stage2' | 'both';

// v1.98: Recommendations are measured per purpose because LLM evaluation uses
// three successful runs, schema validity, and correction frequency, while Vision
// uses visual-feature recall. Calls without purpose use the model's highest score.
//
// stage narrows the LLM score further. Models measured end to end (all NVIDIA
// and Ollama Cloud models) fall back to recommendation_llm, so a stage argument
// does not change their result. 'both' takes the lower stage score because a
// model assigned to both stages is limited by its weaker one. Using max would
// let qwen3.5:4b's Stage 1 result hide its 32% Stage 2 coverage and appear as ★5.
function stageLevel(model: ModelOption, llm: number, stage?: ModelStage): number {
	const s1 = model.recommendation_stage1;
	const s2 = model.recommendation_stage2;
	if (stage === 'stage1') return Number(s1 ?? llm);
	if (stage === 'stage2') return Number(s2 ?? llm);
	if (stage === 'both') {
		const measured = [s1, s2].filter((value): value is number => typeof value === 'number');
		return measured.length > 0 ? Math.min(...measured) : llm;
	}
	return llm;
}

export function modelRecommendationLevel(
	model: ModelOption,
	purpose?: ModelPurpose,
	stage?: ModelStage
): number {
	const llm = Number(model.recommendation_llm ?? model.recommendation_level ?? 0);
	const vision = Number(model.recommendation_vision ?? model.recommendation_level ?? 0);
	const purposes = model.purposes ?? ['llm'];
	const forLlm = stageLevel(model, llm, stage);
	const raw =
		purpose === 'llm' ? forLlm
		: purpose === 'vision' ? vision
		: Math.max(purposes.includes('llm') ? forLlm : 0, purposes.includes('vision') ? vision : 0);
	return Math.max(0, Math.min(5, Number.isFinite(raw) ? raw : 0));
}

export function modelRecommendation(
	model: ModelOption,
	purpose?: ModelPurpose,
	stage?: ModelStage
): string {
	const level = modelRecommendationLevel(model, purpose, stage);
	return level > 0 ? `${'★'.repeat(level)}${'☆'.repeat(5 - level)} (${level}/5)` : '—';
}

/**
 * The two stage rows for the hover card, or null when one row is the honest shape.
 *
 * A model measured end to end has one number and both stages read it, so splitting
 * it would print the same stars twice and imply a measurement nobody took. Only a
 * model carrying at least one stage key is split. Vision is never split — the stage
 * keys narrow the LLM level and say nothing about reading an image.
 *
 * Returning strings rather than levels keeps the card free of formatting decisions,
 * and keeps this decidable without rendering a component.
 */
export function modelStageRecommendations(
	model: ModelOption,
	purpose?: ModelPurpose
): { stage1: string; stage2: string } | null {
	if (purpose === 'vision') return null;
	const staged =
		typeof model.recommendation_stage1 === 'number' || typeof model.recommendation_stage2 === 'number';
	if (!staged) return null;
	return {
		stage1: modelRecommendation(model, 'llm', 'stage1'),
		stage2: modelRecommendation(model, 'llm', 'stage2')
	};
}

// Listing order: retired models last, then highest recommendation first. Fetch
// controls rebuild arrays in provider order, so catalog order cannot preserve it.
export function sortModels(models: ModelOption[], purpose?: ModelPurpose, stage?: ModelStage): ModelOption[] {
	return [...models].sort((a, b) => {
		const unselectable = Number(isModelUnselectable(a)) - Number(isModelUnselectable(b));
		if (unselectable !== 0) return unselectable;
		const level = modelRecommendationLevel(b, purpose, stage) - modelRecommendationLevel(a, purpose, stage);
		if (level !== 0) return level;
		return (a.label || a.id).localeCompare(b.label || b.id);
	});
}

export function modelSpeed(model: ModelOption): string {
	return model.speed_label || '—';
}

export function modelComment(model: ModelOption, isJapanese: boolean): string {
	return isJapanese ? (model.comment_ja || model.comment_en || '—') : (model.comment_en || model.comment_ja || '—');
}

export function modelEolLabel(model: ModelOption, isJapanese: boolean): string | null {
	if (!model.eol) return null;
	const date = model.eol_date ? ` (${model.eol_date})` : '';
	return isJapanese ? `提供終了${date}` : `End of life${date}`;
}

// Two conditions make a listed model unselectable: retirement (EOL) and a paid
// tier requirement. Disabling and sorting share this predicate.
export function isModelUnselectable(model: ModelOption): boolean {
	return !!model.eol || !!model.requires_subscription;
}

export function modelStatusLabel(model: ModelOption, isJapanese: boolean): string | null {
	const eol = modelEolLabel(model, isJapanese);
	if (eol) return eol;
	if (model.requires_subscription) return isJapanese ? '有料プラン限定' : 'Paid plan only';
	return null;
}

// Single source for formatting model evaluation metadata (purposes,
// recommendation, cost, speed, comment). All model-picker surfaces read from here so
// the values and formatting stay consistent. The underlying data lives on
// ModelOption (server model catalog, editable via settings).
import type { ModelOption } from './models';

export type ModelPurpose = 'llm' | 'vision';

// Both purposes are always listed, so the card says what a model cannot be chosen
// for as well as what it can (the author, 2026-10-13). Whether it can is the
// model's purposes, which the measurements set: a model whose drawings failed is
// not offered as an LLM, and one whose Vision answers could not be confirmed is
// not offered for Vision.
export function modelPurposeBadges(model: ModelOption): { purpose: ModelPurpose; label: string; selectable: boolean }[] {
	const purposes = model.purposes ?? ['llm'];
	return (['llm', 'vision'] as const).map((purpose) => ({
		purpose,
		label: purpose === 'vision' ? 'Vision' : 'LLM',
		selectable: purposes.includes(purpose) && !purposeUnsupported(model, purpose)
	}));
}

// A purpose the benchmark found the model does not answer (no drawing, or no
// Vision answer). Model administration cannot switch it on.
export function purposeUnsupported(model: ModelOption, purpose: ModelPurpose): boolean {
	return (model.unsupported_purposes ?? []).includes(purpose);
}

// Measured to answer neither purpose: there is nothing to choose it for.
function answersNothing(model: ModelOption): boolean {
	return purposeUnsupported(model, 'llm') && purposeUnsupported(model, 'vision');
}

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

// The card prints three tiers (the author, 2026-10-13). The stored levels keep
// their five steps -- the measurements were scored on them and they still order
// the cards -- and read as 4-5 recommended, 3 standard, 1-2 modest.
export function recommendationTier(level: number): number {
	return level >= 4 ? 3 : level >= 3 ? 2 : level >= 1 ? 1 : 0;
}

export function modelRecommendation(
	model: ModelOption,
	purpose?: ModelPurpose,
	stage?: ModelStage
): string {
	const tier = recommendationTier(modelRecommendationLevel(model, purpose, stage));
	return tier > 0 ? `${'★'.repeat(tier)}${'☆'.repeat(3 - tier)} (${tier}/3)` : '—';
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

// "LLM … / Vision …" for whichever of the two was measured, or null for neither.
function perPurpose(
	llm: number | undefined,
	vision: number | undefined,
	format: (value: number, purpose: ModelPurpose) => string
): string | null {
	const parts = [
		...(typeof llm === 'number' ? [`LLM ${format(llm, 'llm')}`] : []),
		...(typeof vision === 'number' ? [`Vision ${format(vision, 'vision')}`] : [])
	];
	return parts.length > 0 ? parts.join(' / ') : null;
}

// The measured means are a reference, not a promise: one sample of six
// descriptions and two images, on one day. A model measured only the old way
// keeps its label.
export function modelSpeed(model: ModelOption, isJapanese: boolean): string {
	const seconds = (value: number) => (value < 100 ? value.toFixed(1) : String(Math.round(value)));
	const means = perPurpose(model.speed_llm_seconds, model.speed_vision_seconds, (value) =>
		isJapanese ? `平均 ${seconds(value)}秒` : `mean ${seconds(value)} s`);
	if (means) return isJapanese ? `${means}（参考値）` : `${means} (reference)`;
	return model.speed_label || '—';
}

// Approximate USD for one drawing (every generation request it made) and for one
// Vision image. A free model costs $0, which is shown rather than left out.
export function modelCost(model: ModelOption, isJapanese: boolean): string {
	const usd = (value: number) => (value === 0 ? '$0' : value < 0.0001 ? '<$0.0001' : `$${Number(value.toPrecision(2))}`);
	const unit = (purpose: ModelPurpose) =>
		purpose === 'llm' ? (isJapanese ? '（描画1回）' : ' per drawing') : (isJapanese ? '（画像1枚）' : ' per picture');
	return perPurpose(model.cost_usd_llm, model.cost_usd_vision, (value, purpose) => `${usd(value)}${unit(purpose)}`) ?? '—';
}

export function modelComment(model: ModelOption, isJapanese: boolean): string {
	return isJapanese ? (model.comment_ja || model.comment_en || '—') : (model.comment_en || model.comment_ja || '—');
}

export function modelEolLabel(model: ModelOption, isJapanese: boolean): string | null {
	if (!model.eol) return null;
	const date = model.eol_date ? ` (${model.eol_date})` : '';
	return isJapanese ? `提供終了${date}` : `End of life${date}`;
}

// Four conditions make a listed model unselectable: retirement (EOL), a paid
// tier requirement, being a kind inku does not support, and a measurement in
// which it answered neither purpose. Disabling and sorting share this predicate.
export function isModelUnselectable(model: ModelOption): boolean {
	return !!model.eol || !!model.requires_subscription || !!model.not_supported || answersNothing(model);
}

export function modelStatusLabel(model: ModelOption, isJapanese: boolean): string | null {
	const eol = modelEolLabel(model, isJapanese);
	if (eol) return eol;
	if (model.not_supported) return isJapanese ? 'ノンサポート' : 'Not supported';
	if (model.requires_subscription) return isJapanese ? '有料プラン限定' : 'Paid plan only';
	if (answersNothing(model)) return isJapanese ? '計測で応答なし' : 'No response when measured';
	return null;
}

// Where model administration files a model that cannot be published (the
// author, 2026-10-13): each kind is folded away at the bottom of the list,
// closed at first. Paid-plan models stayed in the list until a measurement
// found twelve Ollama Cloud models this account cannot call; they now have the
// first fold (the author, 2026-10-13), and a plan that reaches one clears its
// mark on the next fetch. Older models can still be published; they are folded
// above the others (the author, 2026-10-13: the OpenAI API up to GPT-5.4), and
// only when nothing else keeps them from publication.
export type ModelFold = 'legacy' | 'subscription' | 'no_response' | 'not_supported' | 'eol';
export const MODEL_FOLDS: ModelFold[] = ['legacy', 'subscription', 'no_response', 'not_supported', 'eol'];

export function modelFold(model: ModelOption): ModelFold | null {
	if (model.eol) return 'eol';
	if (model.not_supported) return 'not_supported';
	if (model.requires_subscription) return 'subscription';
	if (answersNothing(model)) return 'no_response';
	if (model.legacy) return 'legacy';
	return null;
}

export function modelFoldTitle(fold: ModelFold, count: number, isJapanese: boolean): string {
	const [ja, en] = {
		legacy: ['旧モデル', 'Older models'],
		subscription: ['有料プラン限定', 'Paid plan only'],
		no_response: ['計測で応答なし', 'No response when measured'],
		not_supported: ['ノンサポート', 'Not supported'],
		eol: ['提供終了', 'End of life']
	}[fold];
	return isJapanese ? `${ja}（${count}）` : `${en} (${count})`;
}

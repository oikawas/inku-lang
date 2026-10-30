// Single source for formatting model evaluation metadata (purposes,
// recommendation, cost, speed, comment). All model-picker surfaces read from here so
// the values and formatting stay consistent. The underlying data lives on
// ModelOption (server model catalog, editable via settings).
import type { ModelLabel, ModelOption } from './models';

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
// Vision answer). It can be chosen, but the system does not recommend it: every
// control that chooses it is framed in red (the author, 2026-10-26).
export function purposeUnsupported(model: ModelOption, purpose: ModelPurpose): boolean {
	return model.selection?.unsupported[purpose] ?? false;
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
export function modelRecommendationLevel(
	model: ModelOption,
	purpose?: ModelPurpose,
	stage?: ModelStage
): number {
	return model.selection?.levels[purpose ?? 'none'][stage ?? 'none'] ?? 0;
}

// The card prints three tiers (the author, 2026-10-13). The stored levels keep
// their five steps -- the measurements were scored on them and they still order
// the cards -- and read as 4-5 recommended, 3 standard, 1-2 modest.
export function recommendationTier(level: number): number {
	return level >= 4 ? 3 : level >= 3 ? 2 : level >= 1 ? 1 : 0;
}

export function modelRecommendationStars(
	model: ModelOption,
	purpose?: ModelPurpose,
	stage?: ModelStage
): string {
	const tier = recommendationTier(modelRecommendationLevel(model, purpose, stage));
	return tier > 0 ? `${'★'.repeat(tier)}${'☆'.repeat(3 - tier)}` : '—';
}

export function modelRecommendation(
	model: ModelOption,
	purpose?: ModelPurpose,
	stage?: ModelStage
): string {
	const tier = recommendationTier(modelRecommendationLevel(model, purpose, stage));
	return tier > 0 ? `${modelRecommendationStars(model, purpose, stage)} (${tier}/3)` : '—';
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

// The Server returns a core-generated key for each purpose and stage.
export function sortModels(models: ModelOption[], purpose?: ModelPurpose, stage?: ModelStage): ModelOption[] {
	return [...models].sort((a, b) => {
		const left = a.selection?.sort_keys[purpose ?? 'none'][stage ?? 'none'];
		const right = b.selection?.sort_keys[purpose ?? 'none'][stage ?? 'none'];
		if (left === undefined || right === undefined) return 0;
		return left < right ? -1 : left > right ? 1 : 0;
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

// The label table of the core model catalog (the author,
// 2026-10-13), in fold order: what each label is called and whether a model carrying it
// can be published. It arrives with every model list as `model_labels`, and every listed
// model carries its `labels` and the `fold` it is filed in, worked out by the Server. The
// Web only reads them, so a new label or fold needs no change here.
let labelTable: ModelLabel[] = [];

export function setModelLabelTable(labels: ModelLabel[] | undefined): void {
	if (Array.isArray(labels) && labels.length > 0) labelTable = labels;
}

export function modelLabelTable(): ModelLabel[] {
	return labelTable;
}

function labelText(id: string, isJapanese: boolean): string {
	const label = labelTable.find((entry) => entry.id === id);
	return label ? (isJapanese ? label.ja : label.en) : id;
}

// A placeholder has no core decision yet; allow it until the API answers.
export function isModelUnselectable(model: ModelOption): boolean {
	return model.selection?.unselectable ?? false;
}

// Every label of the model, in the table's order, each with whether it keeps the model
// from publication: a row paints those in the warning colour and leaves the others
// (older model, not measured) muted. The end of life carries its date. No response
// when measured can be published since 2026-10-26, as not recommended, and keeps
// the warning colour.
export type ModelStatusPart = { text: string; blocking: boolean };

export function modelStatusParts(model: ModelOption, isJapanese: boolean): ModelStatusPart[] {
	return (model.labels ?? []).map((id) => ({
		text: id === 'eol' && model.eol_date ? `${labelText(id, isJapanese)} (${model.eol_date})` : labelText(id, isJapanese),
		blocking: id === 'no_response' || labelTable.find((entry) => entry.id === id)?.publishable === false
	}));
}

export function modelStatusLabel(model: ModelOption, isJapanese: boolean): string | null {
	const parts = modelStatusParts(model, isJapanese);
	return parts.length === 0 ? null : parts.map((part) => part.text).join(' · ');
}

// Model administration files each model into the fold of its last label, below the
// list and closed at first; a model with no label stays in the list.
export type ModelFold = string;

export function modelFolds(): ModelFold[] {
	return labelTable.map((label) => label.id);
}

export function modelFold(model: ModelOption): ModelFold | null {
	return model.fold ?? null;
}

export function modelFoldTitle(fold: ModelFold, count: number, isJapanese: boolean): string {
	return isJapanese ? `${labelText(fold, true)}（${count}）` : `${labelText(fold, false)} (${count})`;
}

// Single source for formatting model evaluation metadata (purposes,
// recommendation, speed, comment). All model-picker surfaces read from here so
// the values and formatting stay consistent. The underlying data lives on
// ModelOption (server model catalog, editable via settings).
import type { ModelOption } from './models';

export function modelPurposes(model: ModelOption): string {
	return (model.purposes ?? ['llm']).map((purpose) => (purpose === 'vision' ? 'Vision' : 'LLM')).join(' / ');
}

export type ModelPurpose = 'llm' | 'vision';

// どの段のために選んでいるか。'both' は 1 つのモデルを両方の段へ充てる場合。
export type ModelStage = 'stage1' | 'stage2' | 'both';

// v1.98: 推奨度は用途ごとに測る。LLM は「3 回成功したか・スキーマを壊さないか・補正発火が
// 少ないか」、Vision は画像特徴の再現率で決まり、同じ尺度に乗らないため。
// purpose を渡さない呼び出しは、そのモデルが持つ最も高い推奨度を見る。
//
// stage は LLM の値をさらに狭める。段ごとの値を持たないモデル (通しで測った NVIDIA と
// Ollama Cloud の全部) は recommendation_llm へ落ちるので、段を渡しても答えは変わらない。
// 'both' は 2 つの低い方を採る — 両方の段をこなす必要があるモデルは、苦手な段のほうで
// 律速される。ここを max にすると、第一段階の推奨 (qwen3.5:4b) が第二段階の被覆 32% を
// 隠して★5 に見える。
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

// 一覧の並び。提供終了を末尾へ送り、その中で推奨度の高い順に見せる。取得ボタンは提供元の
// 順序で配列を作り直すため、カタログの配列順では順序を維持できない (v1.98)。
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

// 選べない理由は 2 つある。退役 (EOL) と、有料プラン限定。どちらも一覧には残す
// ので、無効化と並べ替えは 1 つの述語を通す。
export function isModelUnselectable(model: ModelOption): boolean {
	return !!model.eol || !!model.requires_subscription;
}

export function modelStatusLabel(model: ModelOption, isJapanese: boolean): string | null {
	const eol = modelEolLabel(model, isJapanese);
	if (eol) return eol;
	if (model.requires_subscription) return isJapanese ? '有料プラン限定' : 'Paid plan only';
	return null;
}

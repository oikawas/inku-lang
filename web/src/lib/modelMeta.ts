// Single source for formatting model evaluation metadata (purposes,
// recommendation, speed, comment). All model-picker surfaces read from here so
// the values and formatting stay consistent. The underlying data lives on
// ModelOption (server model catalog, editable via settings).
import type { ModelOption } from './models';

export function modelPurposes(model: ModelOption): string {
	return (model.purposes ?? ['llm']).map((purpose) => (purpose === 'vision' ? 'Vision' : 'LLM')).join(' / ');
}

export type ModelPurpose = 'llm' | 'vision';

// v1.98: 推奨度は用途ごとに測る。LLM は「3 回成功したか・スキーマを壊さないか・補正発火が
// 少ないか」、Vision は画像特徴の再現率で決まり、同じ尺度に乗らないため。
// purpose を渡さない呼び出しは、そのモデルが持つ最も高い推奨度を見る。
export function modelRecommendationLevel(model: ModelOption, purpose?: ModelPurpose): number {
	const llm = Number(model.recommendation_llm ?? model.recommendation_level ?? 0);
	const vision = Number(model.recommendation_vision ?? model.recommendation_level ?? 0);
	const purposes = model.purposes ?? ['llm'];
	const raw =
		purpose === 'llm' ? llm
		: purpose === 'vision' ? vision
		: Math.max(purposes.includes('llm') ? llm : 0, purposes.includes('vision') ? vision : 0);
	return Math.max(0, Math.min(5, Number.isFinite(raw) ? raw : 0));
}

export function modelRecommendation(model: ModelOption, purpose?: ModelPurpose): string {
	const level = modelRecommendationLevel(model, purpose);
	return level > 0 ? `${'★'.repeat(level)}${'☆'.repeat(5 - level)} (${level}/5)` : '—';
}

// 一覧の並び。提供終了を末尾へ送り、その中で推奨度の高い順に見せる。取得ボタンは提供元の
// 順序で配列を作り直すため、カタログの配列順では順序を維持できない (v1.98)。
export function sortModels(models: ModelOption[], purpose?: ModelPurpose): ModelOption[] {
	return [...models].sort((a, b) => {
		const retired = Number(!!a.eol) - Number(!!b.eol);
		if (retired !== 0) return retired;
		const level = modelRecommendationLevel(b, purpose) - modelRecommendationLevel(a, purpose);
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

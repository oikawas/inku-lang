// Single source for formatting model evaluation metadata (purposes,
// recommendation, speed, comment). All model-picker surfaces read from here so
// the values and formatting stay consistent. The underlying data lives on
// ModelOption (server model catalog, editable via settings).
import type { ModelOption } from './models';

export function modelPurposes(model: ModelOption): string {
	return (model.purposes ?? ['llm']).map((purpose) => (purpose === 'vision' ? 'Vision' : 'LLM')).join(' / ');
}

export function modelRecommendation(model: ModelOption): string {
	const level = Math.max(0, Math.min(5, Number(model.recommendation_level ?? 0)));
	return level > 0 ? `${'★'.repeat(level)}${'☆'.repeat(5 - level)} (${level}/5)` : '—';
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

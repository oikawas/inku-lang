export type PluginOfferItem = { qualified_name: string; written_ja?: string; written_en?: string; reason: 'brace' | 'ddl' | 'name' };
export type PluginOfferRecord = { stage: string; offered: PluginOfferItem[]; omitted: PluginOfferItem[] };

export function offerName(item: PluginOfferItem, ja: boolean): string {
	return (ja ? item.written_ja : item.written_en) || item.qualified_name;
}

export function offerStage(stage: string, ja: boolean): string {
	const labels: Record<string, [string, string]> = {
		generate_normalized_ddl: ['下絵', 'Underdrawing'], write_description_ddl: ['書く', 'Writing'],
		review_description_ddl: ['見直す', 'Review'], chunk_rewrite: ['まとまりの書き直し', 'Chunk rewrite'],
	};
	return labels[stage]?.[ja ? 0 : 1] ?? stage;
}
export function offerReason(reason: PluginOfferItem['reason'], ja: boolean): string {
	return ({ brace: ['括弧で書いた', 'written in braces'], ddl: ['DDL にあった', 'in the DDL'], name: ['名が記述に現れた', 'name appeared in the description'] }[reason] ?? ['', ''])[ja ? 0 : 1];
}

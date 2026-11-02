export type CatalogReading = {
	method?: 'model' | 'seed' | null;
	reading_text?: string | null;
	dropped_axes?: number;
	dropped_colors?: number;
};

export function catalogReadingForWork(saved: { catalog_reading?: CatalogReading | null } | null, result: { catalog_reading?: CatalogReading | null } | null): CatalogReading | null {
	return saved ? saved.catalog_reading ?? null : result?.catalog_reading ?? null;
}

export function catalogReadingDetails(record: CatalogReading, isJapanese: boolean): { method: string; text: string; dropped: string | null } {
	const axes = record.dropped_axes ?? 0;
	const colors = record.dropped_colors ?? 0;
	const method = record.method === 'model'
		? (isJapanese ? '光と色の読みから選んだ' : 'Chosen from the light and color reading')
		: record.method === 'seed'
			? (isJapanese ? '読めるものが無く、実行の種で選んだ' : "Nothing could be read; chosen by the run's seed")
			: (isJapanese ? '選びに失敗し既定のカタログ' : 'The choice failed; the default catalog');
	return { method, text: record.reading_text ?? '', dropped: axes + colors > 0
		? (isJapanese ? `記述に無いため落とした項目：軸 ${axes}・色 ${colors}` : `Dropped as not in the description: ${axes} axes, ${colors} colors`)
		: null };
}

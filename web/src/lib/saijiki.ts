export type SaijikiCategory = {
	key: string;
	label: string;
	en: string;
	words: string[];
};

export const SAIJIKI: SaijikiCategory[] = [
	{
		key: 'katachi',
		label: 'かたち',
		en: 'forms',
		words: ['円', '楕円', '三角', '四角', '線', '弧']
	},
	{
		key: 'tezawari',
		label: 'てざわり',
		en: 'touches',
		words: [
			'髪',
			'鉛筆',
			'ペン',
			'ロットリング',
			'クレヨン',
			'チョーク',
			'細筆',
			'太筆',
			'縄'
		]
	},
	{
		key: 'tsuranari',
		label: 'つらなり',
		en: 'continuity',
		words: ['実線', '破線', '点線', '一点鎖線']
	},
	{
		key: 'iro',
		label: 'いろ',
		en: 'colors',
		words: ['白', '黒', '青', '赤', '緑', '灰']
	},
	{
		key: 'yuragi',
		label: 'ゆらぎ',
		en: 'movements',
		words: [
			'細かく',
			'大きく',
			'ゆっくり',
			'速く',
			'揺れる',
			'波打つ',
			'震える',
			'滲む'
		]
	},
	{
		key: 'basho',
		label: 'ばしょ',
		en: 'places',
		words: ['上', '下', '中央', '左端', '右端', '上端', '下端', '中心', '隅']
	},
	{
		key: 'ugoki',
		label: 'うごき',
		en: 'motions',
		words: ['置く', '並べる', '埋める', '散らす', '引く']
	},
	{
		key: 'wariai',
		label: 'わりあい',
		en: 'proportions',
		words: ['縦長', '横長', '全幅', '半幅', '半円', '上弦', '下弦', '三日月']
	}
];

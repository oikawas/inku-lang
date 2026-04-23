import { SAIJIKI } from './saijiki';

export type Part = {
	text: string;
	kind: 'saijiki' | 'emotion' | 'plain';
	category?: string;
};

const SAIJIKI_ENTRIES = SAIJIKI.flatMap((cat) =>
	cat.words.map((word) => ({ word, category: cat.label }))
).sort((a, b) => b.word.length - a.word.length);

const EMOTION_WORDS = [
	'美しい',
	'美しく',
	'激しい',
	'激しく',
	'静かな',
	'静かに',
	'素敵',
	'きれい',
	'やさしい',
	'切ない',
	'哀しい',
	'儚い',
	'神秘的',
	'幻想的',
	'寂しい',
	'爽やか'
].sort((a, b) => b.length - a.length);

/**
 * 文字列を Saijiki / 感情語 / 地 の 3 種に分割。
 * 貪欲な最長一致で走査する。
 */
export function annotate(text: string): Part[] {
	const parts: Part[] = [];
	let i = 0;

	const pushPlain = (ch: string) => {
		const last = parts[parts.length - 1];
		if (last && last.kind === 'plain') {
			last.text += ch;
		} else {
			parts.push({ text: ch, kind: 'plain' });
		}
	};

	while (i < text.length) {
		let matched = false;

		for (const entry of SAIJIKI_ENTRIES) {
			if (text.startsWith(entry.word, i)) {
				parts.push({
					text: entry.word,
					kind: 'saijiki',
					category: entry.category
				});
				i += entry.word.length;
				matched = true;
				break;
			}
		}
		if (matched) continue;

		for (const word of EMOTION_WORDS) {
			if (text.startsWith(word, i)) {
				parts.push({ text: word, kind: 'emotion' });
				i += word.length;
				matched = true;
				break;
			}
		}
		if (matched) continue;

		pushPlain(text[i]);
		i += 1;
	}

	return parts;
}

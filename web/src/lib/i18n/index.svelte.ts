import type { LangPack } from './types';
import { ja } from './ja';
import { en } from './en';

export type { LangPack };

export const PACKS: Record<string, LangPack> = { ja, en };
export const PACK_LIST: LangPack[] = [ja, en];

let _lang = $state<string>('ja');

export function initLang(): void {
	try {
		const saved = localStorage.getItem('inku-lang');
		if (saved && PACKS[saved]) _lang = saved;
	} catch {}
}

export function getLang(): string {
	return _lang;
}

export function setLang(code: string): void {
	if (!PACKS[code]) return;
	_lang = code;
	try {
		localStorage.setItem('inku-lang', code);
	} catch {}
}

export function t(): LangPack {
	return PACKS[_lang] ?? ja;
}

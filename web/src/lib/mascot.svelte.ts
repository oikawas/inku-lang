/**
 * Which mascot the drawing indicator shows.
 *
 * RunStatus is rendered from ten call sites, so the choice lives in a module
 * state read directly by the component (the same shape as the language pack in
 * `$lib/i18n/index.svelte`) instead of being threaded through as a prop.
 */
export type MascotKind = 'incu' | 'yuragi';

export const MASCOT_KINDS: MascotKind[] = ['incu', 'yuragi'];

/** Proper names, so they are not translated. */
export const MASCOT_NAMES: Record<MascotKind, string> = {
	incu: 'Incu',
	yuragi: 'Yuragi'
};

const MASCOT_KEY = 'inku-mascot';

let _mascot = $state<MascotKind>('incu');

function isKind(value: string | null): value is MascotKind {
	return value === 'incu' || value === 'yuragi';
}

export function initMascot(): void {
	try {
		const saved = localStorage.getItem(MASCOT_KEY);
		if (isKind(saved)) _mascot = saved;
	} catch {}
}

export function getMascot(): MascotKind {
	return _mascot;
}

export function setMascot(kind: MascotKind): void {
	_mascot = kind;
	try {
		localStorage.setItem(MASCOT_KEY, kind);
	} catch {}
}

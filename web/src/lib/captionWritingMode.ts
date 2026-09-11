import { resolveInstructionLang } from './instructionLang';

export type CaptionWritingMode = 'horizontal' | 'vertical';
export type CaptionPosition = 'left' | 'right';

export function normalizeCaptionWritingMode(value: unknown): CaptionWritingMode {
	return value === 'vertical' ? 'vertical' : 'horizontal';
}

export function normalizeCaptionPosition(value: unknown): CaptionPosition {
	return value === 'right' ? 'right' : 'left';
}

export function supportsVerticalCaption(text: unknown): boolean {
	return resolveInstructionLang(String(text ?? ''), 'en') === 'ja';
}

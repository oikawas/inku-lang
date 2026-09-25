import type { ResolvedInstructionLang } from '$lib/instructionLang';

export type SaijikiPreview = {
	categoryKey: string;
	word: string;
	canonicalWord: string;
	effect: string;
	example: string;
	svg: string;
	/** Raster artwork from a plugin's dedicated preview route. */
	image?: string;
	image2x?: string;
};

export type PluginEntry = {
	qualified_name: string;
	aliases?: string[];
	note_ja: string;
	note_en: string;
	fires_on_ja?: string[];
	fires_on_en?: string[];
	preview_url?: string;
	preview_url_2x?: string;
};

export type PreviewForWord = (
	categoryKey: string,
	canonicalWord: string,
	word: string,
	wordLang: ResolvedInstructionLang
) => SaijikiPreview;

export type PreviewForPlugin = (
	entry: PluginEntry,
	wordLang: ResolvedInstructionLang
) => SaijikiPreview;

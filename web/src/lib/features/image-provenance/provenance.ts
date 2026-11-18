import type { ExifFacts } from './exif';

export type ImageProvenanceOptions = {
	includeFileName: boolean;
	includeExif: boolean;
};

export const DEFAULT_IMAGE_PROVENANCE_OPTIONS: ImageProvenanceOptions = {
	includeFileName: true,
	includeExif: true,
};

/** The stored settings, with each missing or damaged field at its default. */
export function parseImageProvenanceOptions(raw: string | null): ImageProvenanceOptions {
	if (!raw) return { ...DEFAULT_IMAGE_PROVENANCE_OPTIONS };
	try {
		const value = JSON.parse(raw) as Partial<Record<keyof ImageProvenanceOptions, unknown>>;
		return {
			includeFileName: typeof value.includeFileName === 'boolean' ? value.includeFileName : DEFAULT_IMAGE_PROVENANCE_OPTIONS.includeFileName,
			includeExif: typeof value.includeExif === 'boolean' ? value.includeExif : DEFAULT_IMAGE_PROVENANCE_OPTIONS.includeExif,
		};
	} catch {
		return { ...DEFAULT_IMAGE_PROVENANCE_OPTIONS };
	}
}

export type ImageProvenanceLabels = {
	fileName: string;
	takenAt: string;
	camera: string;
	lens: string;
	exposure: string;
};

function trimNumber(value: number, digits: number): string {
	return String(Number(value.toFixed(digits)));
}

function exposureTime(seconds: number): string {
	// Shorter than half a second reads as a fraction, as cameras print it.
	if (seconds < 0.5) return `1/${Math.round(1 / seconds)} s`;
	return `${trimNumber(seconds, 1)} s`;
}

/** `Apple iPhone 15 Pro`, without the maker twice when the model already names it. */
function camera(facts: ExifFacts): string | undefined {
	const { make, model } = facts;
	if (make && model) return model.toLowerCase().startsWith(make.toLowerCase()) ? model : `${make} ${model}`;
	return model ?? make;
}

/**
 * File name and capture time share the first line; camera and exposure share
 * the second. Empty when nothing is chosen or known.
 */
export function imageProvenanceText(
	fileName: string,
	facts: ExifFacts | null,
	options: ImageProvenanceOptions,
	labels: ImageProvenanceLabels,
): string {
	const first: string[] = [];
	const second: string[] = [];
	if (options.includeFileName && fileName.trim()) first.push(`${labels.fileName}: ${fileName.trim()}`);
	if (options.includeExif && facts) {
		if (facts.takenAt) first.push(facts.takenAt);
		const body = camera(facts);
		if (body) second.push(body);
		const exposure = [
			facts.fNumber ? `f/${trimNumber(facts.fNumber, 1)}` : null,
			facts.exposureTime ? exposureTime(facts.exposureTime) : null,
			facts.iso ? `ISO ${Math.round(facts.iso)}` : null,
			facts.focalLength ? `${trimNumber(facts.focalLength, 1)} mm` : null,
		].filter((part): part is string => part !== null);
		second.push(...exposure);
	}
	return [first.join(' · '), second.join(' · ')].filter(Boolean).join('\n');
}

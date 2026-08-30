function fractionDigits(step: number): number {
	const [coefficient, exponentText] = String(step).toLowerCase().split('e');
	const fraction = coefficient.split('.')[1]?.length ?? 0;
	const exponent = Number(exponentText ?? 0);
	return Math.max(0, Math.min(20, fraction - exponent));
}

export function formatGroupedNumber(value: number, step: number): string {
	return new Intl.NumberFormat('en-US', {
		useGrouping: true,
		minimumFractionDigits: 0,
		maximumFractionDigits: fractionDigits(step)
	}).format(value);
}

export function parseGroupedNumber(value: string): number | null {
	const text = value.trim();
	if (!/^-?(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d+)?$/.test(text)) return null;
	const parsed = Number(text.replaceAll(',', ''));
	return Number.isFinite(parsed) ? parsed : null;
}

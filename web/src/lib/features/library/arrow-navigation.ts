export type LibraryArrowDestination =
	| { kind: 'index'; index: number }
	| { kind: 'previous-page' | 'next-page' | 'none' };

export function libraryArrowDestination(index: number, count: number, columns: number, key: string): LibraryArrowDestination {
	if (!Number.isInteger(index) || !Number.isInteger(count) || !Number.isInteger(columns) || count <= 0 || columns <= 0 || index < 0 || index >= count) return { kind: 'none' };
	switch (key) {
		case 'ArrowLeft': return index === 0 ? { kind: 'previous-page' } : { kind: 'index', index: index - 1 };
		case 'ArrowRight': return index === count - 1 ? { kind: 'next-page' } : { kind: 'index', index: index + 1 };
		case 'ArrowUp': return index < columns ? { kind: 'previous-page' } : { kind: 'index', index: index - columns };
		case 'ArrowDown':
			if (index + columns < count) return { kind: 'index', index: index + columns };
			return Math.floor(index / columns) === Math.floor((count - 1) / columns)
				? { kind: 'next-page' }
				: { kind: 'index', index: count - 1 };
		default: return { kind: 'none' };
	}
}

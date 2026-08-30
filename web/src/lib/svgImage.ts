export type SvgImageUrlEnvironment = {
	createObjectURL: (blob: Blob) => string;
	revokeObjectURL: (url: string) => void;
};

const browserEnvironment: SvgImageUrlEnvironment = {
	createObjectURL: (blob) => URL.createObjectURL(blob),
	revokeObjectURL: (url) => URL.revokeObjectURL(url)
};

/**
 * Present API-derived SVG as an image document instead of inserting its markup
 * into the application DOM. The image boundary prevents SVG elements, styles,
 * and event handlers from becoming part of the page; it is not a sanitizer for
 * callers that need to inspect or transform SVG text.
 *
 * Object URLs retain their Blob until explicitly released, so every update and
 * component teardown revokes the URL it replaces.
 */
export function createSvgImageAction(environment: SvgImageUrlEnvironment = browserEnvironment) {
	return (node: HTMLImageElement, initialSvg: string) => {
		let currentSvg: string | null = null;
		let currentUrl: string | null = null;

		function release(): void {
			if (!currentUrl) return;
			environment.revokeObjectURL(currentUrl);
			currentUrl = null;
		}

		function update(svg: string): void {
			if (svg === currentSvg) return;
			release();
			currentSvg = svg;
			if (!svg) {
				node.removeAttribute('src');
				return;
			}
			currentUrl = environment.createObjectURL(new Blob([svg], { type: 'image/svg+xml' }));
			node.src = currentUrl;
		}

		update(initialSvg);
		return {
			update,
			destroy() {
				release();
				currentSvg = null;
				node.removeAttribute('src');
			}
		};
	};
}

export const svgImage = createSvgImageAction();

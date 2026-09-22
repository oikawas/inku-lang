import { registerUserSettingsContributor } from '$lib/features/user-settings';

export const TEXT_SIZE_DEFAULT_STEP = 1;
export const TEXT_SIZE_SCALES = [0.9, 1, 1.1, 1.2, 1.3] as const;

export function normalizeTextSizeStep(value: unknown): number {
	return typeof value === 'number' && Number.isInteger(value) && value >= 0 && value < TEXT_SIZE_SCALES.length
		? value
		: TEXT_SIZE_DEFAULT_STEP;
}

export function textScaleForStep(step: unknown): number {
	return TEXT_SIZE_SCALES[normalizeTextSizeStep(step)];
}

type TextSizePersist = (step: number) => Promise<number>;

let persist: TextSizePersist | null = null;

class TextSizeSettings {
	step = $state(TEXT_SIZE_DEFAULT_STEP);
	saving = $state(false);
	saveError = $state(false);

	#context = 0;
	#revision = 0;
	#inFlight = false;
	#queued = false;

	get scale(): number {
		return textScaleForStep(this.step);
	}

	preview = (step: unknown): void => {
		this.step = normalizeTextSizeStep(step);
		this.#revision += 1;
		this.saveError = false;
	};

	/** Queue the last previewed value; a completed older write never replaces it. */
	save = (): void => {
		this.#queued = true;
		this.saving = true;
		this.saveError = false;
		if (!this.#inFlight) void this.#flush();
	};

	reset = (): void => {
		this.preview(TEXT_SIZE_DEFAULT_STEP);
		this.save();
	};

	/** A user switch invalidates every response that belonged to the old account. */
	apply = (stored: unknown): void => {
		this.#context += 1;
		this.#revision += 1;
		this.#queued = false;
		this.step = normalizeTextSizeStep(stored);
		this.saving = false;
		this.saveError = false;
	};

	async #flush(): Promise<void> {
		this.#inFlight = true;
		try {
			while (this.#queued) {
				this.#queued = false;
				const context = this.#context;
				const revision = this.#revision;
				const requested = this.step;
				try {
					if (!persist) throw new Error('Text-size persistence is not bound');
					const saved = normalizeTextSizeStep(await persist(requested));
					if (context === this.#context && revision === this.#revision && requested === this.step) {
						this.step = saved;
						this.saveError = false;
					}
				} catch {
					if (context === this.#context && revision === this.#revision && requested === this.step) {
						this.saveError = true;
					}
				}
			}
		} finally {
			this.#inFlight = false;
			this.saving = false;
		}
	}
}

export const textSizeSettings = new TextSizeSettings();

export function bindTextSizePersist(write: TextSizePersist): void {
	persist = write;
}

registerUserSettingsContributor({
	id: 'text-size',
	collect: () => ({ ui_text_size: textSizeSettings.step }),
	apply: (settings) => textSizeSettings.apply(settings.ui_text_size)
});

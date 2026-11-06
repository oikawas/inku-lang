import { createApiFetch, type ApiFetch } from '../../transport/api-fetch';

export class SvgQueue {
	private active = 0;
	private waiters: (() => void)[] = [];
	private readonly fetch: ApiFetch;
	private readonly limit: number;
	constructor(fetch: ApiFetch = createApiFetch(), limit = 4) { this.fetch = fetch; this.limit = limit; }
	async load(path: string, signal: AbortSignal): Promise<string> {
		if (signal.aborted) return '';
		if (this.active >= this.limit) await new Promise<void>((resolve) => this.waiters.push(resolve));
		else this.active++;
		try {
			if (signal.aborted) return '';
			const response = await this.fetch(path, { signal });
			return response.ok ? await response.text() : '';
		} finally {
			const next = this.waiters.shift();
			if (next) next();
			else this.active--;
		}
	}
}

export const thumbnailSvgQueue = new SvgQueue();

export type NoticeGroup = 'inku' | 'web' | 'server' | 'resources' | 'rust';
export type NoticeComponent = {
	id: string;
	group: NoticeGroup;
	name: string;
	version: string;
	license: string;
	source: string;
	textUrl: string;
};
export type NoticeState = {
	components: NoticeComponent[];
	failedGroups: ('web' | 'server')[];
	loading: boolean;
	selectedId: string | null;
	text: string;
	textLoading: boolean;
	textFailed: boolean;
};
export const NOTICE_GROUPS: NoticeGroup[] = ['inku', 'web', 'server', 'resources', 'rust'];
export const EMPTY_NOTICE_STATE: NoticeState = {
	components: [], failedGroups: [], loading: true,
	selectedId: null, text: '', textLoading: false, textFailed: false,
};

const INKU: NoticeComponent = {
	id: 'inku', group: 'inku', name: 'inku', version: '', license: 'MIT',
	source: 'https://github.com/oikawas/inku-lang', textUrl: '/licenses/inku-MIT.txt',
};

async function json(fetcher: typeof fetch, url: string, signal: AbortSignal): Promise<unknown> {
	const response = await fetcher(url, { signal });
	if (!response.ok) throw new Error('Notice catalog unavailable');
	return response.json();
}

function record(value: unknown): Record<string, unknown> {
	if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error('Invalid notice catalog');
	return value as Record<string, unknown>;
}

function webComponents(value: unknown): NoticeComponent[] {
	return Object.entries(record(record(value).packages)).map(([name, raw]) => {
		const item = record(raw);
		if (!/^(@[a-z0-9._-]+\/)?[a-z0-9._-]+$/.test(name)
			|| typeof item.version !== 'string' || !/^[a-zA-Z0-9.+_-]+$/.test(item.version)
			|| typeof item.file !== 'string' || !/^[a-zA-Z0-9_-]+\.txt$/.test(item.file)) {
			throw new Error('Invalid Web notice');
		}
		// The reviewed Web manifest currently contains MIT packages only.
		return { id: `web:${name}`, group: 'web', name, version: item.version, license: 'MIT',
			source: `https://www.npmjs.com/package/${name}/v/${item.version}`, textUrl: `/licenses/${item.file}` };
	});
}

function serverComponents(value: unknown): NoticeComponent[] {
	const entries = record(value).components;
	if (!Array.isArray(entries)) throw new Error('Invalid Server notices');
	return entries.map((raw) => {
		const item = record(raw);
		if (typeof item.id !== 'string' || !/^[a-z0-9-]+$/.test(item.id)
			|| !['server', 'resources', 'rust'].includes(String(item.group))
			|| !['name', 'version', 'license', 'source'].every((key) => typeof item[key] === 'string')
			|| !String(item.name).trim()) throw new Error('Invalid Server notice');
		const source = new URL(item.source as string);
		if (source.protocol !== 'https:' || source.username || source.password) throw new Error('Invalid notice source');
		return { id: `server:${item.id}`, group: item.group as NoticeGroup, name: item.name as string,
			version: item.version as string, license: item.license as string, source: source.href,
			textUrl: `/api/notices/${item.id}` };
	});
}

/** Each request owns its result; a late response cannot replace a newer selection. */
export class NoticeReader {
	state: NoticeState = EMPTY_NOTICE_STATE;
	private catalogRequest: AbortController | null = null;
	private textRequest: AbortController | null = null;
	private disposed = false;
	private fetcher: typeof fetch;
	private changed: (state: NoticeState) => void;

	constructor(fetcher: typeof fetch, changed: (state: NoticeState) => void) {
		this.fetcher = fetcher;
		this.changed = changed;
	}

	private update(patch: Partial<NoticeState>): void {
		this.state = { ...this.state, ...patch };
		this.changed(this.state);
	}

	async load(): Promise<void> {
		if (this.disposed) return;
		this.catalogRequest?.abort();
		this.textRequest?.abort();
		const request = new AbortController();
		this.catalogRequest = request;
		this.update({ loading: true, textLoading: false });
		const results = await Promise.allSettled([
			json(this.fetcher, '/licenses/manifest.json', request.signal).then(webComponents),
			json(this.fetcher, '/api/notices', request.signal).then(serverComponents),
		]);
		if (request.signal.aborted || this.disposed) return;
		const components = [INKU];
		const failedGroups: NoticeState['failedGroups'] = [];
		results.forEach((result, index) => {
			if (result.status === 'fulfilled') components.push(...result.value);
			else failedGroups.push(index === 0 ? 'web' : 'server');
		});
		this.update({ components, failedGroups, loading: false });
		await this.select(components.find((item) => item.id === this.state.selectedId)?.id ?? INKU.id);
	}

	async select(id: string): Promise<void> {
		const item = this.state.components.find((component) => component.id === id);
		if (!item || this.disposed) return;
		this.textRequest?.abort();
		const request = new AbortController();
		this.textRequest = request;
		this.update({ selectedId: id, text: '', textLoading: true, textFailed: false });
		try {
			const response = await this.fetcher(item.textUrl, { signal: request.signal });
			if (!response.ok || !/^text\/plain(?:;|$)/i.test(response.headers.get('content-type') ?? '')) {
				throw new Error('Notice unavailable');
			}
			const text = await response.text();
			if (!text.trim()) throw new Error('Empty notice');
			if (!request.signal.aborted && !this.disposed) this.update({ text, textLoading: false });
		} catch {
			if (!request.signal.aborted && !this.disposed) this.update({ textLoading: false, textFailed: true });
		}
	}

	dispose(): void {
		this.disposed = true;
		this.catalogRequest?.abort();
		this.textRequest?.abort();
	}
}

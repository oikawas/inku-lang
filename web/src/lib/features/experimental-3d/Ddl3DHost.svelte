<script lang="ts">
	import { onMount } from 'svelte';
	import { t } from '$lib/i18n/index.svelte';
	import type { PaintResult } from '$lib/features/run/current-work';
	import { snapshot } from './input';
	import { PROTOCOL, recall, remember, validViewState } from './protocol';
	let { result, viewerUrl, isJapanese, onReturn }: { result: PaintResult; viewerUrl: string; isJapanese: boolean; onReturn: () => void } = $props();
	let frame = $state<HTMLIFrameElement>();
	let ready = $state(false), failure = $state(''), preparing = $state(true), attempt = $state(0);
	const mountId = `ddl3d-${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
	let requestId = 0, timer: ReturnType<typeof setTimeout>, activeInput = '';
	const input = $derived.by(() => { try { return { json: snapshot(result), error: '' }; } catch (e) { return { json: '', error: e instanceof Error ? e.message : 'invalid_input' }; } });
	const src = $derived(`${viewerUrl}#mount=${encodeURIComponent(mountId)}-${attempt}`);
	function send(type: string, payload: Record<string, unknown> = {}) {
		frame?.contentWindow?.postMessage({ protocol: PROTOCOL, type, mountId: `${mountId}-${attempt}`, requestId, ...payload }, window.location.origin);
	}
	function waitForViewer() {
		clearTimeout(timer);
		timer = setTimeout(() => { failure = 'viewer_timeout'; preparing = false; }, 15_000);
	}
	function retry() { ready = false; failure = ''; preparing = true; attempt += 1; waitForViewer(); }
	onMount(() => {
		waitForViewer();
		const listener = (event: MessageEvent) => {
			if (event.origin !== window.location.origin || event.source !== frame?.contentWindow) return;
			const data = event.data;
			if (!data || data.mountId !== `${mountId}-${attempt}`) return;
			if (data.protocol !== PROTOCOL) { failure = 'protocol_mismatch'; preparing = false; clearTimeout(timer); return; }
			if (data.type === 'ready') { ready = true; return; }
			if (data.requestId !== requestId) return;
			if (data.type === 'rendered' && typeof data.inputDigest === 'string' && /^[0-9a-f]{64}$/.test(data.inputDigest)) {
				preparing = false; failure = ''; clearTimeout(timer);
			} else if (data.type === 'failed' && typeof data.reason === 'string') {
				failure = data.reason.slice(0, 500); preparing = false; clearTimeout(timer);
			} else if (data.type === 'view-state' && validViewState(data.viewState)) {
				remember(activeInput, data.viewState);
			} else if (data.type === 'return-2d') onReturn();
		};
		window.addEventListener('message', listener);
		return () => { send('dispose'); clearTimeout(timer); window.removeEventListener('message', listener); };
	});
	$effect(() => {
		if (input.error) { failure = input.error; preparing = false; return; }
		if (!ready) return;
		activeInput = input.json; requestId += 1; failure = ''; preparing = true; waitForViewer();
		send('load-work', { inputJson: activeInput, locale: isJapanese ? 'ja' : 'en',
			theme: document.documentElement.dataset.theme === 'dark' ? 'dark' : 'light', viewState: recall(activeInput) });
	});
</script>

<div class="ddl3d-host" aria-busy={preparing}>
	{#key attempt}
		<iframe bind:this={frame} {src} title={t().ddl3dTitle} allow="fullscreen" allowfullscreen referrerpolicy="no-referrer" inert={!!failure}></iframe>
	{/key}
	{#if failure}
		<div class="message" role="status">
			<p>{t().ddl3dFailed}</p>
			<details><summary>{t().ddl3dDetails}</summary><code>{failure}</code></details>
			<div><button onclick={retry}>{t().ddl3dRetry}</button><button onclick={onReturn}>{t().ddl3dReturn}</button></div>
		</div>
	{:else if preparing}
		<div class="preparing" role="status">{t().ddl3dPreparing}<button onclick={onReturn}>{t().ddl3dReturn}</button></div>
	{/if}
</div>

<style>
	.ddl3d-host { position: relative; flex: 1; min-width: 0; align-self: stretch; margin: 0 48px; background: var(--bg); }
	iframe { position: absolute; inset: 0; width: 100%; height: 100%; border: 0; }
	.message { position: absolute; inset: 0; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 12px; padding: 24px; background: var(--bg); color: var(--fg); }
	.message p { margin: 0; }.message code { display: block; overflow-wrap: anywhere; max-width: 30em; }
	.preparing { position: absolute; top: 8px; left: 8px; padding: 8px; border-radius: 4px; background: var(--bg); color: var(--fg); }
	button { margin: 0 4px; padding: var(--btn-sm-padding); border-radius: var(--btn-sm-radius); font-size: var(--btn-sm-font-size); border: 1px solid var(--border); background: var(--action-bg); color: var(--action-fg); cursor: pointer; }
</style>

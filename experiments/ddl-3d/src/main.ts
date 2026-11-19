import './style.css';
import { Viewer, type Unpainted } from './viewer/Viewer';
import { GlassViewer, GLASS_DEFAULTS, type GlassColor, type GlassSettings } from './viewer/GlassViewer';
import { labels, type Labels } from './viewer/labels';
import { PROTOCOL, MAX_INPUT_BYTES, validLoad, type LoadMessage } from './input/protocol';
import type { ScenePacket } from './scene/types';
import type { ViewState } from './input/protocol';
import type { Background } from './viewer/background';

const root = document.querySelector<HTMLElement>('#app')!;
const embedded = window.parent !== window;
const mountId = new URLSearchParams(location.hash.slice(1)).get('mount') || 'standalone';
let current: LoadMessage | null = null, viewer: Viewer | GlassViewer | null = null, worker: Worker | null = null;
// The glass is the first view; the solids stay one switch away.
let mode: 'glass' | 'solids' = 'glass', lastPacket: ScenePacket | null = null;
let glassSettings: GlassSettings = { ...GLASS_DEFAULTS };
let generation = 0, timeout = 0, locale: 'ja' | 'en' = 'ja';
let words = labels(locale);
let stage: HTMLElement, status: HTMLElement, details: HTMLElement, selection: HTMLElement, overlay: HTMLElement, recoveryNotice: HTMLElement, paintNotice: HTMLElement;
let cancel: HTMLButtonElement, retry: HTMLButtonElement;
const sceneControls: (HTMLButtonElement | HTMLInputElement | HTMLSelectElement)[] = [];
const urls = new Set<string>();

function post(type: string, extra: Record<string, unknown> = {}) {
  if (embedded) parent.postMessage({ protocol: PROTOCOL, type, mountId, requestId: current?.requestId ?? 0, ...extra }, location.origin);
}
function element<K extends keyof HTMLElementTagNameMap>(tag: K, parent: HTMLElement, text?: string) {
  const el = document.createElement(tag); if (text) el.textContent = text; parent.append(el); return el;
}
function button(parent: HTMLElement, label: string, action: () => void, needsScene = true) {
  const el = element('button', parent, label); el.type = 'button'; el.addEventListener('click', action);
  if (needsScene) sceneControls.push(el); return el;
}
function message(text: string, busy = false) {
  overlay.hidden = false; overlay.querySelector('p')!.textContent = text;
  cancel.hidden = !busy; retry.hidden = busy || !current; status.textContent = text;
  sceneControls.forEach(control => control.disabled = true);
}
function stop() {
  generation++; clearTimeout(timeout); worker?.terminate(); worker = null;
  viewer?.dispose(); viewer = null; stage.removeAttribute('aria-busy');
}
function fail(reason: string) {
  stop();
  const text = reason === 'context_lost' ? words.lost : reason === 'webgl_unavailable' ? words.noGpu : reason === 'timeout' ? words.timeout : reason === 'cancelled' ? words.cancelled : words.failed;
  message(text); details.textContent = reason.slice(0, 500); post('failed', { reason: reason.slice(0, 500) });
}

function ui() {
  root.replaceChildren(); sceneControls.length = 0;
  const toolbar = element('details', root); toolbar.className = 'toolbar';
  element('summary', toolbar, words.controls);
  const heading = element('div', toolbar); heading.className = 'heading'; element('strong', heading, words.title);
  if (!embedded) {
    const label = element('label', heading, words.open); label.className = 'file';
    const input = element('input', label); input.type = 'file'; input.accept = '.json,application/json';
    input.addEventListener('change', async () => {
      const file = input.files?.[0]; if (!file) return;
      if (file.size > MAX_INPUT_BYTES) { message(words.fileTooLarge); return; }
      try {
        let json = await file.text();
        const value = JSON.parse(json); if (!value.score) json = JSON.stringify({ score: value });
        load({ protocol: PROTOCOL, type: 'load-work', mountId, requestId: (current?.requestId ?? 0) + 1, inputJson: json, locale, theme: matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light' });
      } catch { fail('invalid_json'); }
    });
  }
  if (embedded) button(heading, words.back, () => { stop(); post('return-2d'); }, false);
  const controls = element('div', toolbar); controls.className = 'controls';
  button(controls, words.fit, () => viewer?.fit());
  button(controls, words.reset, () => {
    viewer?.reset(); updateDepthControls(1, 1); projection.value = 'orthographic'; spin.checked = false;
  });
  for (const [symbol, label, action] of [
    ['＋', words.zoomIn, () => viewer?.zoom(true)], ['−', words.zoomOut, () => viewer?.zoom(false)],
    ['←', words.panLeft, () => viewer?.pan(25, 0)], ['→', words.panRight, () => viewer?.pan(-25, 0)],
    ['↑', words.panUp, () => viewer?.pan(0, 25)], ['↓', words.panDown, () => viewer?.pan(0, -25)],
  ] as const) {
    const control = button(controls, symbol, action); control.title = label; control.setAttribute('aria-label', label);
  }
  for (const [name, label] of [['front', words.front], ['back', words.backView], ['left', words.left], ['right', words.right], ['top', words.top], ['bottom', words.bottom], ['iso', words.iso]]) {
    button(controls, label, () => viewer?.preset(name));
  }
  const projection = element('select', controls); projection.dataset.option = 'projection'; projection.setAttribute('aria-label', words.projection);
  for (const [value, label] of [['perspective', words.perspective], ['orthographic', words.orthographic]]) { const option = element('option', projection, label); option.value = value; }
  projection.addEventListener('change', () => viewer?.setProjection(projection.value as 'perspective' | 'orthographic')); sceneControls.push(projection);
  projection.value = 'orthographic';
  button(controls, words.full, () => { void (document.fullscreenElement ? document.exitFullscreen() : root.requestFullscreen()).catch(error => {
    status.textContent = words.fullFailed; element('p', details, error instanceof Error ? error.message : String(error));
  }); }, false);
  const options = element('div', toolbar); options.className = 'controls';
  const modeLabel = element('label', options, words.viewMode), modeSelect = element('select', modeLabel);
  modeSelect.dataset.option = 'viewMode'; modeSelect.setAttribute('aria-label', words.viewMode);
  for (const [value, label] of [['glass', words.glass], ['solids', words.solids]]) { const option = element('option', modeSelect, label); option.value = value; }
  modeSelect.value = mode;
  modeSelect.addEventListener('change', () => switchMode(modeSelect.value as 'glass' | 'solids')); sceneControls.push(modeSelect);
  let spin: HTMLInputElement;
  const backgroundLabel = element('label', options, words.background), background = element('select', backgroundLabel);
  background.dataset.option = 'background'; background.setAttribute('aria-label', words.background);
  for (const [value, label] of [['none', words.none], ['support', words.support], ['sky', words.sky], ['stars', words.stars],
    ['paint', words.backgroundFill], ['white', words.whiteBackground], ['black', words.blackBackground]]) {
    const option = element('option', background, label); option.value = value;
  }
  background.addEventListener('change', () => viewer?.setBackground(background.value as Background)); sceneControls.push(background);
  for (const key of ['grid', 'axes', 'wire', 'unlit', 'spin'] as const) {
    const label = element('label', options), input = element('input', label); input.type = 'checkbox'; input.dataset.option = key;
    label.append(key === 'spin' && mode === 'glass' ? words.sway : words[key]);
    if (mode === 'glass' && key !== 'spin') label.hidden = true;
    input.addEventListener('change', () => viewer?.setOption(key, input.checked)); sceneControls.push(input); if (key === 'spin') spin = input;
  }
  for (const [key, label, minimum, action] of [
    ['depth', words.depth, '0.1', (value: number) => viewer?.setDepth(value)],
    ['layerSpacing', words.layerDepth, '0', (value: number) => viewer?.setLayerSpacing(value)],
  ] as const) {
    const controlLabel = element('label', options, label), input = element('input', controlLabel);
    input.type = 'range'; input.min = minimum; input.max = '3'; input.step = mode === 'glass' ? '0.01' : '0.1'; input.value = '1'; input.dataset.option = key;
    const output = element('output', controlLabel, '1.0'); output.dataset.value = key;
    input.setAttribute('aria-label', label);
    input.addEventListener('input', () => { output.value = Number(input.value).toFixed(mode === 'glass' ? 2 : 1); action(Number(input.value)); });
    if (mode === 'glass' && key === 'depth') controlLabel.hidden = true;
    sceneControls.push(input);
  }
  if (mode === 'glass') glassControls(options);
  button(options, words.focus, () => viewer?.focus());
  for (const format of ['png', 'glb'] as const) button(options, words[format], () => { void save(format); });
  const help = element('details', toolbar); element('summary', help, words.help); element('p', help, words.helpText); element('p', help, words.layerHelp);
  recoveryNotice = element('details', toolbar); recoveryNotice.className = 'recovery-notice'; recoveryNotice.hidden = true;
  paintNotice = element('details', toolbar); paintNotice.className = 'recovery-notice'; paintNotice.hidden = true;
  stage = element('section', root); stage.className = 'stage'; stage.setAttribute('aria-label', '3D');
  overlay = element('div', stage); overlay.className = 'overlay'; overlay.setAttribute('role', 'status'); element('p', overlay);
  cancel = button(overlay, words.cancel, () => fail('cancelled'), false);
  retry = button(overlay, words.retry, () => { if (current) load({ ...current }); }, false);
  if (embedded) button(overlay, words.back, () => { stop(); post('return-2d'); }, false);
  const footer = element('footer', toolbar); status = element('span', footer); status.setAttribute('role', 'status');
  selection = element('span', footer, `${words.selected}: ${words.none}`);
  const info = element('details', footer); element('summary', info, words.details); details = element('div', info); details.className = 'diagnostics';
  message(words.ready);
}

function updateDepthControls(depth: number, layerSpacing: number) {
  for (const [key, value] of [['depth', depth], ['layerSpacing', layerSpacing]] as const) {
    root.querySelector<HTMLInputElement>(`input[data-option=${key}]`)!.value = String(value);
    root.querySelector<HTMLOutputElement>(`output[data-value=${key}]`)!.value = value.toFixed(1);
  }
}

function load(value: LoadMessage) {
  stop(); current = value; locale = value.locale; words = labels(locale); document.documentElement.lang = locale;
  document.documentElement.dataset.theme = value.theme; ui(); message(words.preparing, true);
  const localGeneration = generation;
  const started = performance.now();
  worker = new Worker(new URL('./worker/prepare.ts', import.meta.url), { type: 'module' });
  timeout = window.setTimeout(() => { if (localGeneration === generation) fail('timeout'); }, 10_000);
  worker.onerror = () => { if (localGeneration === generation) fail('worker_failed'); };
  worker.onmessage = async (event: MessageEvent<{ ok: boolean; packet?: ScenePacket; error?: string }>) => {
    if (localGeneration !== generation) return;
    clearTimeout(timeout); worker?.terminate(); worker = null;
    if (!event.data.ok || !event.data.packet) { fail(event.data.error ?? 'preparation_failed'); return; }
    lastPacket = event.data.packet;
    present(event.data.packet, value, started, localGeneration);
  };
  worker.postMessage({ inputJson: value.inputJson, wasmUrl: new URL('wasm/score_adapter.js', document.baseURI).href });
}

function present(packet: ScenePacket, value: LoadMessage, started: number, localGeneration: number) {
  try {
    const changed = (viewState: ViewState) => {
      root.querySelector<HTMLSelectElement>('select[data-option=projection]')!.value = viewState.projection;
      root.querySelector<HTMLSelectElement>('select[data-option=background]')!.value = viewState.background ?? 'paint';
      updateDepthControls(viewState.depth, viewState.layerSpacing ?? 1);
      if (viewer instanceof GlassViewer) {
        glassSettings = { ...viewer.settings }; root.querySelector<HTMLInputElement>('input[data-option=spin]')!.checked = viewer.settings.sway;
        for (const input of root.querySelectorAll<HTMLInputElement>('input[type=range][data-glass]')) {
          const key = input.dataset.glass as keyof GlassSettings; input.value = String(glassSettings[key]);
          const output = root.querySelector<HTMLOutputElement>(`output[data-glass=${key}]`); if (output) output.value = Number(glassSettings[key]).toFixed(key === 'backTilt' ? 1 : 2);
        }
      }
      else if (viewer) root.querySelector<HTMLInputElement>('input[data-option=spin]')!.checked = viewer.controls.autoRotate;
      post('view-state', { viewState });
    };
    const selected = (data: Record<string, unknown> | null) => {
      if (data && 'glassLayer' in data) {
        selection.textContent = `${words.selected}: ${words.glassLayer} ${Number(data.glassLayer) + 1}${data.name ? ` 「${data.name}」` : ''} · #${(data.instructions as number[]).join(', #')}`;
        return;
      }
      selection.textContent = data ? `${words.selected}: ${data.primitive} · #${Number(data.sourceIndex) + 1} (${Number(data.performedIndex) + 1}) · ${words.layer} ${Number(data.layerIndex) + 1}` : `${words.selected}: ${words.none}`;
    };
    viewer = mode === 'glass' ? new GlassViewer(stage, packet, changed, selected, fail, value.initialView)
      : new Viewer(stage, packet, changed, selected, fail, value.initialView);
    if (viewer instanceof GlassViewer) { viewer.settings = { ...glassSettings, sway: false }; viewer.set({}); }
    // The standalone page lets a trial script drive the viewer; embedded hosts never see it.
    if (!embedded) (window as unknown as { inkuViewer: unknown }).inkuViewer = viewer;
    const preparedViewer = viewer;
    // The plain solids come first; paint follows once they can be moved.
    viewer.prepareShape();
    if (value.viewState) {
      viewer.restore(value.viewState);
      root.querySelector<HTMLSelectElement>('select[data-option=projection]')!.value = value.viewState.projection;
      updateDepthControls(value.viewState.depth, value.viewState.layerSpacing ?? 1);
    }
    root.querySelector<HTMLSelectElement>('select[data-option=background]')!.value = viewer.background;
    viewer.drawNow();
    overlay.hidden = true; sceneControls.forEach(control => control.disabled = false);
    const counts = viewer instanceof GlassViewer
      ? `${words.objects}: ${packet.objectCount} · ${words.glassLayers}: ${viewer.layers.length}`
      : `${words.objects}: ${packet.objectCount} · ${words.triangles}: ${packet.triangles.toLocaleString(locale)} · ${words.layer}: ${packet.layerCount}`;
    if (viewer instanceof GlassViewer && viewer.plan.source === 'instructions' && packet.chunkSource !== 'ddl') element('p', details, words.layersByInstruction);
    status.textContent = counts;
    if (packet.recoveries.length || packet.emptyPaths.length) {
      recoveryNotice.hidden = false;
      element('summary', recoveryNotice, packet.recoveries.length ? `${words.recovered} (${packet.recoveries.length})` : `${words.emptyPaths} (${packet.emptyPaths.length})`);
      if (packet.recoveries.length) element('p', recoveryNotice, words.recoveredText);
      if (packet.emptyPaths.length) {
        element('p', recoveryNotice, `${words.emptyPaths}: ${packet.emptyPaths.length}`);
        element('p', recoveryNotice, words.emptyPathsText);
        element('p', recoveryNotice, `${words.instruction}: ${[...new Set(packet.emptyPaths.map(path => path.sourceIndex + 1))].join(', ')}`);
      }
      for (const recovery of packet.recoveries) {
        const source = recovery.anchor_index !== undefined ? `${words.anchor} #${recovery.anchor_index + 1}`
          : recovery.instruction_index !== undefined ? `${words.instruction} #${recovery.instruction_index + 1}` : words.resourceGroup;
        const action = recovery.kind === 'relation_omitted' || recovery.disposition === 'relation_omitted' ? words.relationRecovered : words.contentOmitted;
        element('p', recoveryNotice, `${source}: ${action}`);
        const info = element('details', recoveryNotice); element('summary', info, words.details);
        element('pre', info, JSON.stringify(recovery, null, 2));
      }
    }
    details.replaceChildren();
    element('p', details, viewer instanceof GlassViewer ? words.glassHelp : words.layerHelp);
    if (packet.diagnostics.length) element('strong', details, words.approximations);
    for (const note of packet.diagnostics) element('p', details, words[note as keyof Labels] ?? note);
    if (packet.clippedObjects) element('p', details, `${words.clipped}: ${packet.clippedObjects}`);
    element('p', details, `${packet.mappingVersion} · Engine ${packet.engineVersion} · ${packet.inputDigest}`);
    const total = viewer.paintTotal;
    if (total) { stage.setAttribute('aria-busy', 'true'); status.textContent = `${counts} · ${words.painting} 0/${total}`; }
    post('rendered', { inputDigest: packet.inputDigest, objectCount: packet.objectCount, triangles: packet.triangles, bytes: packet.bytes, preparationMs: Math.round(performance.now() - started) });
    post('view-state', { viewState: viewer.state() });
    if (packet.diagnostics.length) post('diagnostic', { diagnostics: packet.diagnostics });
    const shown = () => localGeneration === generation && viewer === preparedViewer;
    preparedViewer.paint((done, all) => {
      if (!shown()) return;
      status.textContent = `${counts} · ${words.painting} ${done}/${all}`;
      // Name the layer that has just appeared, from the back.
      if (preparedViewer instanceof GlassViewer) {
        const ready = preparedViewer.layers.filter(layer => layer.pixels).length;
        const name = ready ? preparedViewer.layers[ready - 1].name : null;
        if (name) status.textContent += ` · ${words.glassLayer} ${ready}「${name}」`;
      }
    }).then(unpainted => {
      if (!shown()) return;
      stage.removeAttribute('aria-busy'); status.textContent = counts;
      if (unpainted.length) showUnpainted(unpainted);
    }, error => { if (shown()) fail(error instanceof Error && error.message ? error.message : String(error) || 'paint_failed'); });
  } catch (error) {
    if (localGeneration !== generation) return;
    // Only a renderer that could not be created means no GPU; keep any other cause.
    fail(error instanceof Error && error.message ? error.message : String(error) || 'preparation_failed');
  }
}

function switchMode(next: 'glass' | 'solids') {
  if (next === mode) return;
  if (viewer instanceof GlassViewer) glassSettings = { ...viewer.settings };
  mode = next;
  if (!lastPacket || !current) { ui(); return; }
  const packet = lastPacket, value = { ...current, viewState: undefined };
  viewer?.dispose(); viewer = null;
  ui(); present(packet, value, performance.now(), generation);
}

/** The glass's own controls; uniforms only, so dragging moves the fan smoothly. */
function glassControls(parent: HTMLElement) {
  const glass = () => viewer instanceof GlassViewer ? viewer : null;
  const slider = (into: HTMLElement, key: keyof GlassSettings, label: string, min: number, max: number, step: number, digits = 2) => {
    const controlLabel = element('label', into, label), input = element('input', controlLabel);
    input.type = 'range'; input.min = String(min); input.max = String(max); input.step = String(step);
    input.value = String(glassSettings[key]); input.dataset.glass = key; input.setAttribute('aria-label', label);
    const output = element('output', controlLabel, Number(glassSettings[key]).toFixed(digits)); output.dataset.glass = key;
    input.addEventListener('input', () => {
      output.value = Number(input.value).toFixed(digits);
      glassSettings = { ...glassSettings, [key]: Number(input.value) }; glass()?.set({ [key]: Number(input.value) });
    });
    sceneControls.push(input);
  };
  slider(parent, 'angle', words.planeAngle, 0, 2, 0.01);
  slider(parent, 'leaf', words.leafSheen, 0, 1, 0.01);
  slider(parent, 'light', words.lightDirection, -1, 1, 0.01);
  const colorLabel = element('label', parent, words.glassColor), color = element('select', colorLabel);
  color.dataset.glass = 'glassColor'; color.setAttribute('aria-label', words.glassColor);
  for (const [value, label] of [['none', words.clearGlass], ['background', words.backgroundGlass], ['layers', words.layerGlass]] as const) {
    if (value === 'background' && lastPacket && !GlassViewer.hasHue(lastPacket.background)) continue;
    const option = element('option', color, label); option.value = value;
  }
  color.value = glassSettings.glassColor;
  color.addEventListener('change', () => { glassSettings = { ...glassSettings, glassColor: color.value as GlassColor }; glass()?.set({ glassColor: color.value as GlassColor }); });
  sceneControls.push(color);
  const trial = element('fieldset', parent); element('legend', trial, words.prototypeOnly);
  slider(trial, 'front', words.frontGlass, 0.03, 3, 0.01);
  slider(trial, 'backTilt', words.backTilt, 0, 30, 0.5, 1);
  slider(trial, 'room', words.roomDarkness, 0.5, 0.8, 0.01);
  for (const [into, key, label] of [[parent, 'frictionless', words.frictionless], [trial, 'swayOnce', words.swayOnce], [trial, 'bluish', words.bluishSilver]] as const) {
    const box = element('label', into), input = element('input', box); input.type = 'checkbox'; input.checked = glassSettings[key]; box.append(label);
    input.addEventListener('change', () => { glassSettings = { ...glassSettings, [key]: input.checked }; glass()?.set({ [key]: input.checked }); });
    sceneControls.push(input);
  }
}

function showUnpainted(unpainted: Unpainted[]) {
  paintNotice.hidden = false;
  element('summary', paintNotice, `${words.unpainted} (${unpainted.length})`);
  element('p', paintNotice, words.unpaintedText);
  const instructions = [...new Set(unpainted.flatMap(item => 'sourceIndex' in item ? [item.sourceIndex + 1] : []))];
  if (instructions.length) element('p', paintNotice, `${words.instruction}: ${instructions.join(', ')}`);
  if (unpainted.some(item => item.role === 'presence')) element('p', paintNotice, words.presenceUnpainted);
  const info = element('details', paintNotice); element('summary', info, words.details);
  element('pre', info, JSON.stringify(unpainted, null, 2));
}

async function save(format: 'png' | 'glb') {
  const source = viewer; if (!source) return;
  try {
    // Waits for the paint, so the file has every mark that could be painted.
    const blob = await source[format]();
    if (source !== viewer) return;
    const url = URL.createObjectURL(blob); urls.add(url);
    const link = document.createElement('a'); link.href = url; link.download = `inku-3d-${source.packet.inputDigest.slice(0, 12)}.${format}`;
    link.click(); setTimeout(() => { URL.revokeObjectURL(url); urls.delete(url); }, 1000);
  } catch { if (source === viewer) status.textContent = words.exportFailed; }
}

window.addEventListener('message', event => {
  if (!embedded || event.origin !== location.origin || event.source !== parent) return;
  if (event.data?.protocol === PROTOCOL && event.data.type === 'request-ready' && event.data.mountId === mountId) { post('ready'); return; }
  if (validLoad(event.data) && event.data.mountId === mountId && event.data.requestId > (current?.requestId ?? 0)) load(event.data);
  else if (event.data?.protocol === PROTOCOL && event.data.type === 'dispose' && event.data.mountId === mountId) stop();
  else if (event.data?.protocol === PROTOCOL && event.data.type === 'viewer-command' && event.data.mountId === mountId && event.data.requestId === current?.requestId) {
    if (event.data.action === 'zoom' && Number.isFinite(event.data.value)) viewer?.setZoom(event.data.value);
    if (event.data.action === 'reset') viewer?.match2D();
  }
});
document.addEventListener('keydown', event => { if (event.key === 'Escape' && embedded && !document.fullscreenElement) { stop(); post('return-2d'); } });
window.addEventListener('pagehide', () => { stop(); urls.forEach(url => URL.revokeObjectURL(url)); urls.clear(); });
ui(); post('ready');

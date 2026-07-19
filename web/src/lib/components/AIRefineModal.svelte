<script lang="ts">
  import { onDestroy } from 'svelte';
  import { qualifiedModelId, type Provider, type ProviderGroup } from '$lib/models';
  import type { LineageNode } from './LineagePanel.svelte';
  import HistoryThumbnail from './HistoryThumbnail.svelte';
  import ModelCardPicker from './ModelCardPicker.svelte';
  import { t } from '$lib/i18n/index.svelte';

  type RefineMode = 'random' | 'vision';
  type VisionAdvice = { observation: string; next_direction: string; suggested_kind: string; model: string };
  type Props = {
    node: LineageNode;
    visionModel: string;
    visionProviderGroups: ProviderGroup[];
    onClose: () => void;
    onPaintOne: (text: string, options: any) => Promise<any>;
    onVisionAdvice: (historyId: string, model: string, instruction: string, direction: string, enabledKinds: string[], signal: AbortSignal) => Promise<VisionAdvice>;
    onLoadBranch: (nodeId: string) => void | Promise<void>;
    onSaveVisionModel: (provider: Provider, model: string) => void | Promise<void>;
  };

  let { node, visionModel, visionProviderGroups, onClose, onPaintOne, onVisionAdvice, onLoadBranch, onSaveVisionModel }: Props = $props();
  let prompt = $state('');
  let generations = $state(5);
  let refineMode = $state<RefineMode>('random');
  let selectedVisionModel = $state('');
  let enableReading = $state(true);
  let enableColor = $state(true);
  let enableLayout = $state(true);
  let enableTouch = $state(true);
  let running = $state(false);
  let currentStep = $state(0);
  let statusText = $state('');
  let errorText = $state('');
  let lastGeneratedItem = $state<any>(null);
  let latestAdvice = $state<VisionAdvice | null>(null);
  let abortController: AbortController | null = null;

  $effect(() => { if (!selectedVisionModel) selectedVisionModel = visionModel; });
  onDestroy(() => abortController?.abort());

  const activeKinds = $derived.by(() => {
    const kinds: string[] = [];
    if (enableReading) kinds.push('reinterpretation');
    if (enableColor) kinds.push('catalog_change');
    if (enableLayout) kinds.push('layout_variation');
    if (enableTouch) kinds.push('touch_variation');
    return kinds;
  });

  function kindLabel(kind: string): string {
    const labels: Record<string, string> = {
      touch_variation: t().refineCostTouch,
      layout_variation: t().refineCostLayout,
      catalog_change: t().refineCostColor,
      reinterpretation: t().refineCostReading
    };
    return labels[kind] ?? kind;
  }

  async function readVisionAdvice(historyId: string, instruction: string): Promise<VisionAdvice> {
    if (!abortController) throw new Error('refinement was stopped');
    statusText = t().aiRefineVisionReading;
    const advice = await onVisionAdvice(historyId, selectedVisionModel, instruction, prompt, activeKinds, abortController.signal);
    latestAdvice = advice;
    return advice;
  }

  async function startRefinement() {
    if (activeKinds.length === 0) { errorText = t().aiRefineMinElementsError; return; }
    if (refineMode === 'vision' && (!selectedVisionModel || !node.history?.id)) { errorText = t().aiRefineVisionSourceError; return; }
    running = true;
    errorText = '';
    currentStep = 0;
    lastGeneratedItem = null;
    latestAdvice = null;
    abortController = new AbortController();
    let parentNodeId = node.id;
    let currentText = node.history?.source_text ?? node.history?.input ?? '';
    let advice: VisionAdvice | null = null;

    try {
      if (refineMode === 'vision') advice = await readVisionAdvice(node.history!.id!, currentText);
      for (let i = 0; i < generations; i++) {
        currentStep = i + 1;
        let kind = refineMode === 'vision' && advice ? advice.suggested_kind : activeKinds[Math.floor(Math.random() * activeKinds.length)];
        if (!activeKinds.includes(kind)) kind = activeKinds[0];
        if (refineMode === 'random' && prompt && enableReading && i === 0) kind = 'reinterpretation';
        statusText = t().aiRefineStepStatus(generations, currentStep, kindLabel(kind));

        const directions = refineMode === 'vision' && advice ? [prompt, advice.next_direction].filter(Boolean) : (prompt && kind === 'reinterpretation' ? [prompt] : []);
        const paintText = directions.length ? `${currentText}\n${t().aiRefineAppliedDirection}: ${directions.join(' / ')}` : currentText;
        const options: any = {
          lineageParentNodeId: parentNodeId,
          derivationKind: kind,
          derivationMetadata: {
            autonomous_refine_mode: refineMode,
            ...(advice ? { vision_model: advice.model, vision_observation: advice.observation, vision_next_direction: advice.next_direction } : {})
          },
          historyVisibility: i === generations - 1 ? 'normal' : 'lineage_only',
          saveHistory: true,
          countGeneration: true,
          signal: abortController.signal
        };
        if (kind === 'catalog_change') options.randomColorCatalog = true;
        const result = await onPaintOne(paintText, options);
        parentNodeId = result.lineage_node_id;
        lastGeneratedItem = result.history_id ? result : null;
        if (result.source_text) currentText = result.source_text;
        if (refineMode === 'vision' && result.history_id) advice = await readVisionAdvice(result.history_id, currentText);
      }
      statusText = t().aiRefineCompleted;
      await onLoadBranch(node.id);
    } catch (err: any) {
      if (err.name !== 'AbortError') errorText = err.message || String(err);
    } finally {
      running = false;
      abortController = null;
    }
  }
</script>

<div class="modal-backdrop" onclick={!running ? onClose : undefined} onkeydown={(e) => { if (e.key === 'Escape' && !running) onClose(); }} role="presentation">
  <div class="modal-content" onclick={(e) => e.stopPropagation()} role="dialog" aria-modal="true" aria-labelledby="modal-title" tabindex="-1">
    <header><h3 id="modal-title">{t().aiRefineTitle}</h3>{#if !running}<button class="close-btn" type="button" onclick={onClose} aria-label={t().closeLabel}>&times;</button>{/if}</header>
    <div class="modal-body">
      {#if running}
        <div class="running-state"><div class="spinner"></div><p class="status-message">{statusText}</p>{#if lastGeneratedItem}<div class="progress-preview"><HistoryThumbnail item={lastGeneratedItem} scope="ai-refine-progress" size="manager" /></div>{/if}</div>
      {:else}
        <fieldset class="mode-choice"><legend>{t().aiRefineModeLabel}</legend><label><input type="radio" bind:group={refineMode} value="random" /><span><b>{t().aiRefineRandomMode}</b><small>{t().aiRefineRandomModeHint}</small></span></label><label><input type="radio" bind:group={refineMode} value="vision" /><span><b>{t().aiRefineVisionMode}</b><small>{t().aiRefineVisionModeHint}</small></span></label></fieldset>
        {#if refineMode === 'vision'}<ModelCardPicker label={t().aiRefineVisionModel} selectedModel={selectedVisionModel} providerGroups={visionProviderGroups} onSelect={(provider: Provider, model: string) => { selectedVisionModel = qualifiedModelId(provider, model); void onSaveVisionModel(provider, model); }} />{/if}
        <div class="form-group"><label for="ai-direction">{t().aiRefineDirectionLabel}</label><textarea id="ai-direction" placeholder={t().aiRefineDirectionPlaceholder} bind:value={prompt} maxlength="160" rows="2"></textarea></div>
        <div class="form-row"><div class="form-group select-generations"><label for="ai-gens">{t().aiRefineGensLabel}</label><input id="ai-gens" type="number" min="1" max="10" bind:value={generations} /></div></div>
        <details class="advanced-settings" open><summary>{t().aiRefineElementsLabel}</summary><div class="checkbox-group"><label><input type="checkbox" bind:checked={enableReading} /><span>{t().refineCostReading} (Reading)</span></label><label><input type="checkbox" bind:checked={enableColor} /><span>{t().refineCostColor} (Color)</span></label><label><input type="checkbox" bind:checked={enableLayout} /><span>{t().refineCostLayout} (Layout)</span></label><label><input type="checkbox" bind:checked={enableTouch} /><span>{t().refineCostTouch} (Touch)</span></label></div></details>
      {/if}
      {#if latestAdvice}<section class="vision-advice"><h4>{t().aiRefineVisionObservation}</h4><p>{latestAdvice.observation}</p><h4>{t().aiRefineVisionDirection}</h4><p>{latestAdvice.next_direction}</p></section>{/if}
      {#if errorText}<div class="error-banner">{errorText}</div>{/if}
    </div>
    <footer>{#if !running}<button class="cancel-action" type="button" onclick={onClose}>{t().confirmCancel}</button><button class="confirm-action" type="button" disabled={activeKinds.length === 0 || (refineMode === 'vision' && (!selectedVisionModel || !node.history?.id))} onclick={startRefinement}>{t().aiRefineStartButton}</button>{:else}<button class="confirm-action active-loading" type="button" disabled>{t().aiRefineRunningButton}</button>{/if}</footer>
  </div>
</div>

<style>
  .modal-backdrop { position: fixed; inset: 0; z-index: 1500; display: grid; place-items: center; padding: 20px; background: rgba(0,0,0,.6); backdrop-filter: blur(2px); }
  .modal-content { box-sizing: border-box; width: 100%; max-width: 520px; display: flex; flex-direction: column; background: var(--panel); border: 1px solid var(--border2); border-radius: 12px; color: var(--fg); box-shadow: 0 20px 60px rgba(0,0,0,.45); overflow: hidden; }
  header { display:flex; align-items:center; justify-content:space-between; padding:14px 18px; border-bottom:1px solid var(--border); } header h3 { margin:0; font-size:1rem; font-weight:600; }
  .close-btn { border:0; background:transparent; color:var(--fg3); font-size:1.4rem; cursor:pointer; padding:0 4px; }
  .modal-body { padding:18px; min-height:200px; display:flex; flex-direction:column; gap:14px; overflow-y:auto; max-height:68vh; }
  .mode-choice { display:grid; grid-template-columns:1fr 1fr; gap:8px; margin:0; padding:0; border:0; } .mode-choice legend { margin-bottom:6px; color:var(--fg3); font-size:.76rem; font-weight:500; }
  .mode-choice label { display:flex; align-items:flex-start; gap:8px; padding:10px; border:1px solid var(--border2); border-radius:8px; background:var(--bg2); cursor:pointer; } .mode-choice input { margin-top:2px; accent-color:var(--accent); } .mode-choice span { display:grid; gap:3px; } .mode-choice b { font-size:.78rem; } .mode-choice small { color:var(--fg3); font-size:.68rem; line-height:1.35; }
  .form-group { display:flex; flex-direction:column; gap:6px; } .form-group label { font-size:.76rem; color:var(--fg3); font-weight:500; }
  textarea { box-sizing:border-box; width:100%; border:1px solid var(--border2); border-radius:6px; padding:8px 10px; background:var(--bg); color:var(--fg); font:inherit; font-size:.82rem; resize:none; line-height:1.4; }
  .form-row { display:flex; gap:12px; } .select-generations { width:120px; } input[type="number"] { box-sizing:border-box; width:100%; border:1px solid var(--border2); border-radius:6px; padding:6px 10px; background:var(--bg); color:var(--fg); font:inherit; font-size:.85rem; }
  .advanced-settings { border:1px solid var(--border); border-radius:8px; padding:8px 12px; background:var(--bg2); } .advanced-settings summary { font-size:.75rem; font-weight:600; color:var(--fg2); cursor:pointer; user-select:none; }
  .checkbox-group { display:grid; grid-template-columns:1fr 1fr; gap:8px; margin-top:8px; } .checkbox-group label { display:flex; align-items:center; gap:8px; font-size:.74rem; cursor:pointer; } .checkbox-group input { width:14px; height:14px; accent-color:var(--accent); margin:0; }
  .running-state { margin:auto; display:flex; flex-direction:column; align-items:center; text-align:center; gap:14px; padding:10px 0; } .spinner { width:28px; height:28px; border:3px solid var(--border2); border-top-color:var(--accent); border-radius:50%; animation:spin .8s linear infinite; } @keyframes spin { to { transform:rotate(360deg); } }
  .status-message { font-size:.82rem; color:var(--fg2); margin:0; } .progress-preview { width:110px; height:110px; border-radius:6px; overflow:hidden; background:var(--bg2); border:1px solid var(--border); box-shadow:0 4px 12px rgba(0,0,0,.15); } .progress-preview :global(.history-thumbnail) { width:100%; height:100%; aspect-ratio:auto; } .progress-preview :global(svg) { width:100%; height:100%; display:block; }
  .vision-advice { padding:10px 12px; border:1px solid var(--border); border-radius:8px; background:var(--bg2); } .vision-advice h4 { margin:0 0 3px; color:var(--fg3); font-size:.68rem; } .vision-advice p { margin:0 0 8px; color:var(--fg2); font-size:.76rem; line-height:1.45; } .vision-advice p:last-child { margin-bottom:0; }
  .error-banner { padding:8px 12px; background:color-mix(in srgb,var(--danger,#9b3d32) 10%,var(--panel)); border:1px solid var(--danger,#9b3d32); border-radius:6px; color:var(--danger,#9b3d32); font-size:.74rem; line-height:1.35; }
  footer { display:flex; align-items:center; justify-content:flex-end; gap:8px; padding:12px 18px; border-top:1px solid var(--border); background:var(--bg2); } footer button { border:1px solid var(--border2); border-radius:6px; padding:7px 14px; font-size:.8rem; font-weight:500; cursor:pointer; background:var(--panel); color:var(--fg); } .confirm-action { background:var(--accent); color:white; border-color:var(--accent); } .confirm-action:disabled { opacity:.5; cursor:default; } .confirm-action.active-loading { opacity:.8; cursor:default; } .cancel-action:hover { background:var(--bg); }
  @media (max-width:560px) { .mode-choice { grid-template-columns:1fr; } }
</style>

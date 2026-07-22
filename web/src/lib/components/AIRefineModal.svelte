<script lang="ts">
  import { onDestroy } from 'svelte';
  import { qualifiedModelId, type Provider, type ProviderGroup } from '$lib/models';
  import type { LineageNode } from './LineagePanel.svelte';
  import HistoryThumbnail from './HistoryThumbnail.svelte';
  import ModelCardPicker from './ModelCardPicker.svelte';
  import RunStatus from './RunStatus.svelte';
  import Tooltip from './Tooltip.svelte';
  import TenkeiSelect from './TenkeiSelect.svelte';
  import { normalizeTenkei, DEFAULT_TENKEI, type TenkeiLevel } from '$lib/tenkei';
  import { t } from '$lib/i18n/index.svelte';
  import { createElapsed } from '$lib/elapsed.svelte';

  type RefineMode = 'random' | 'vision';
  type HensouAmplitude = 'small' | 'medium' | 'large';
  type VisionAdvice = { observation: string; next_direction: string; suggested_kind: string; model: string };
  type Props = {
    node: LineageNode;
    visionModel: string;
    visionProviderGroups: ProviderGroup[];
    stage1ModelLabel: string;
    stage2ModelLabel: string;
    onClose: () => void;
    onPaintOne: (text: string, options: any) => Promise<any>;
    onVisionAdvice: (historyId: string, model: string, instruction: string, direction: string, enabledKinds: string[], signal: AbortSignal) => Promise<VisionAdvice>;
    onLoadBranch: (nodeId: string) => void | Promise<void>;
    onSaveVisionModel: (provider: Provider, model: string) => void | Promise<void>;
  };

  let { node, visionModel, visionProviderGroups, stage1ModelLabel, stage2ModelLabel, onClose, onPaintOne, onVisionAdvice, onLoadBranch, onSaveVisionModel }: Props = $props();

  function addTokens(total: number | null, delta: number): number | null {
    return (total ?? 0) + delta;
  }
  let prompt = $state('');
  let generations = $state(5);
  let refineMode = $state<RefineMode>('random');
  let selectedVisionModel = $state('');
  let enableReading = $state(true);
  let enableColor = $state(true);
  let enableLayout = $state(true);
  let enableTouch = $state(true);
  let enableHensou = $state(true);
  let hensouAmplitude = $state<HensouAmplitude>('medium');
  let running = $state(false);
  const refineElapsed = createElapsed();
  let refineTokensIn = $state<number | null>(null);
  let refineTokensOut = $state<number | null>(null);
  let currentStep = $state(0);
  let statusText = $state('');
  let errorText = $state('');
  let lastGeneratedItem = $state<any>(null);
  let latestAdvice = $state<VisionAdvice | null>(null);
  let abortController: AbortController | null = null;
  const isJapanese = $derived(t().code === 'ja');
  // null = inherit the parent artwork's level (field omitted).
  let tenkeiOverride = $state<TenkeiLevel | null>(null);
  const parentTenkei = $derived(normalizeTenkei(node.history?.tenkei) ?? DEFAULT_TENKEI);

  $effect(() => { if (!selectedVisionModel) selectedVisionModel = visionModel; });
  onDestroy(() => abortController?.abort());

  const activeKinds = $derived.by(() => {
    const kinds: string[] = [];
    if (enableReading) kinds.push('reinterpretation');
    if (enableColor) kinds.push('catalog_change');
    if (enableLayout) kinds.push('layout_variation');
    if (enableTouch) kinds.push('touch_variation');
    if (enableHensou) kinds.push('hensou');
    return kinds;
  });

  function kindLabel(kind: string): string {
    const labels: Record<string, string> = {
      touch_variation: t().refineCostTouch,
      layout_variation: t().refineCostLayout,
      catalog_change: t().refineCostColor,
      reinterpretation: t().refineCostReading,
      hensou: t().hensouTitle
    };
    return labels[kind] ?? kind;
  }

  // 変奏 seed はサーバーが採番する (UI が seed 空間を持たない)。
  async function allocateHensouSeed(amplitude: string): Promise<number> {
    const response = await fetch('/api/variation/seeds', {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ amplitude, count: 1 })
    });
    if (!response.ok) throw new Error(await response.text());
    return (await response.json()).seeds[0] as number;
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
    refineTokensIn = null;
    refineTokensOut = null;
    refineElapsed.start();
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
          ...(tenkeiOverride ? { tenkei: tenkeiOverride } : {}),
          historyVisibility: i === generations - 1 ? 'normal' : 'lineage_only',
          saveHistory: true,
          countGeneration: true,
          signal: abortController.signal
        };
        if (kind === 'catalog_change') options.randomColorCatalog = true;
        if (kind === 'hensou') {
          options.variationAmplitude = hensouAmplitude;
          options.variationSeed = await allocateHensouSeed(hensouAmplitude);
        }
        const result = await onPaintOne(paintText, options);
        refineTokensIn = addTokens(refineTokensIn, (result.tokens_in_stage1 ?? 0) + (result.tokens_in_stage2 ?? 0));
        refineTokensOut = addTokens(refineTokensOut, (result.tokens_out_stage1 ?? 0) + (result.tokens_out_stage2 ?? 0));
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
      refineElapsed.stop();
      abortController = null;
    }
  }

  function stopRefinement() {
    abortController?.abort();
  }
</script>

<div class="modal-backdrop" onclick={!running ? onClose : undefined} onkeydown={(e) => { if (e.key === 'Escape' && !running) onClose(); }} role="presentation">
  <div class="modal-content" onclick={(e) => e.stopPropagation()} role="dialog" aria-modal="true" aria-labelledby="modal-title" tabindex="-1">
    <header><h3 id="modal-title">{t().aiRefineTitle}</h3>{#if !running}<button class="close-btn" type="button" onclick={onClose} aria-label={t().closeLabel}>&times;</button>{/if}</header>
    <div class="modal-body">
      {#if running}
        <RunStatus
          label={statusText}
          stage1Model={stage1ModelLabel}
          stage2Model={stage2ModelLabel}
          elapsedMs={refineElapsed.ms}
          tokensIn={refineTokensIn}
          tokensOut={refineTokensOut}
          onStop={stopRefinement}
        >
          {#if lastGeneratedItem}<div class="progress-preview"><HistoryThumbnail item={lastGeneratedItem} scope="ai-refine-progress" size="manager" /></div>{/if}
        </RunStatus>
      {:else}
        <fieldset class="mode-choice"><legend>{t().aiRefineModeLabel}</legend><label><input type="radio" bind:group={refineMode} value="random" /><span><b>{t().aiRefineRandomMode}</b><small>{t().aiRefineRandomModeHint}</small></span></label><label><input type="radio" bind:group={refineMode} value="vision" /><span><b>{t().aiRefineVisionMode}</b><small>{t().aiRefineVisionModeHint}</small></span></label></fieldset>
        {#if refineMode === 'vision'}<ModelCardPicker label={t().aiRefineVisionModel} selectedModel={selectedVisionModel} providerGroups={visionProviderGroups} purpose="vision" onSelect={(provider: Provider, model: string) => { selectedVisionModel = qualifiedModelId(provider, model); void onSaveVisionModel(provider, model); }} />{/if}
        <div class="form-group"><label for="ai-direction">{t().aiRefineDirectionLabel}</label><textarea id="ai-direction" placeholder={t().aiRefineDirectionPlaceholder} bind:value={prompt} maxlength="160" rows="2"></textarea>{#if refineMode === 'random'}<small class="field-hint">{t().aiRefineDirectionRandomHint}</small>{/if}</div>
        <div class="form-row"><div class="form-group tenkei-group"><span class="tenkei-group-label">&nbsp;</span><TenkeiSelect compact value={tenkeiOverride ?? parentTenkei} {isJapanese} inherited={tenkeiOverride === null} onSelect={(level) => (tenkeiOverride = level)} /></div><div class="form-group select-generations"><label for="ai-gens">{t().aiRefineGensLabel}</label><div class="gen-stepper"><button type="button" aria-label="−" onclick={() => (generations = Math.max(1, generations - 1))} disabled={generations <= 1}>−</button><span id="ai-gens" class="gen-value">{generations}</span><button type="button" aria-label="＋" onclick={() => (generations = Math.min(10, generations + 1))} disabled={generations >= 10}>＋</button></div></div></div>
        <details class="advanced-settings" open><summary>{t().aiRefineElementsLabel}</summary><div class="checkbox-group"><Tooltip placement="bottom" text={t().refineCostReading}><label><input type="checkbox" bind:checked={enableReading} /><span>{t().canvasVaryInterpretation}</span></label></Tooltip><Tooltip placement="bottom" text={t().refineCostColor}><label><input type="checkbox" bind:checked={enableColor} /><span>{t().canvasVaryColor}</span></label></Tooltip><Tooltip placement="bottom" text={t().refineCostLayout}><label><input type="checkbox" bind:checked={enableLayout} /><span>{t().canvasVaryComposition}</span></label></Tooltip><Tooltip placement="bottom" text={t().refineCostTouch}><label><input type="checkbox" bind:checked={enableTouch} /><span>{t().canvasVaryPerformance}</span></label></Tooltip><Tooltip placement="bottom" text={t().tooltipHensou}><label><input type="checkbox" bind:checked={enableHensou} /><span>{t().hensouTitle}</span></label></Tooltip>{#if enableHensou}<div class="hensou-amplitude-field"><div class="hensou-amplitude-grid" role="radiogroup" aria-label={t().hensouTitle}>{#each [['small', t().hensouSmall, t().hensouTooltipSmall, 'top-right'], ['medium', t().hensouMedium, t().hensouTooltipMedium, 'top'], ['large', t().hensouLarge, t().hensouTooltipLarge, 'top-left']] as [level, label, hint, place] (level)}<label class="amplitude-choice" class:checked={hensouAmplitude === level}><input type="radio" name="ai-hensou-amplitude" value={level} checked={hensouAmplitude === level} onchange={() => (hensouAmplitude = level as HensouAmplitude)} /><Tooltip placement={place as 'top' | 'top-left' | 'top-right'} text={hint}><span class="amplitude-choice-label"><strong>{label}</strong><span class="amplitude-info-mark" aria-hidden="true">i</span></span></Tooltip></label>{/each}</div></div>{/if}</div></details>
      {/if}
      {#if latestAdvice}<section class="vision-advice"><h4>{t().aiRefineVisionObservation}</h4><p>{latestAdvice.observation}</p><h4>{t().aiRefineVisionDirection}</h4><p>{latestAdvice.next_direction}</p></section>{/if}
      {#if errorText}<div class="error-banner">{errorText}</div>{/if}
    </div>
    <footer>{#if !running}<button class="cancel-action" type="button" onclick={onClose}>{t().confirmCancel}</button><button class="confirm-action" type="button" disabled={activeKinds.length === 0 || (refineMode === 'vision' && (!selectedVisionModel || !node.history?.id))} onclick={startRefinement}>{t().aiRefineStartButton}</button>{/if}</footer>
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
  .field-hint { color:var(--fg3); font-size:.68rem; line-height:1.45; }
  textarea { box-sizing:border-box; width:100%; border:1px solid var(--border2); border-radius:6px; padding:8px 10px; background:var(--bg); color:var(--fg); font:inherit; font-size:.82rem; resize:none; line-height:1.4; }
  .form-row { display:flex; gap:12px; } .select-generations { width:120px; }
  .form-row { flex-wrap: wrap; align-items: flex-end; } .tenkei-group { order: 2; } .tenkei-group-label { display:none; }
  .gen-stepper { display:flex; align-items:center; width:fit-content; border:1px solid var(--border2); border-radius:6px; overflow:hidden; }
  .gen-stepper button { width:34px; height:32px; border:0; background:var(--bg); color:var(--fg); font-size:1rem; line-height:1; cursor:pointer; }
  .gen-stepper button:disabled { opacity:.4; cursor:default; }
  .gen-stepper button:hover:not(:disabled) { background:var(--bg2); }
  .gen-value { min-width:38px; text-align:center; font-size:.9rem; font-variant-numeric:tabular-nums; }
  .advanced-settings { border:1px solid var(--border); border-radius:8px; padding:8px 12px; background:var(--bg2); } .advanced-settings summary { font-size:.75rem; font-weight:600; color:var(--fg2); cursor:pointer; user-select:none; }
  .checkbox-group { display:grid; grid-template-columns:1fr 1fr; gap:8px; margin-top:8px; } .checkbox-group label { display:flex; align-items:center; gap:8px; font-size:.74rem; cursor:pointer; } .checkbox-group input { width:14px; height:14px; accent-color:var(--accent); margin:0; }
  /* 変奏の強度は変奏チェックボックスに従属するので、段落ち + border-left で示す (調整ダイアログと同型)。 */
  .hensou-amplitude-field { grid-column: 1 / -1; margin: 2px 0 0 20px; padding-left: 10px; border-left: 2px solid var(--border2); }
  .hensou-amplitude-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 6px; }
  /* .checkbox-group label / input より詳細度を上げる (同グリッド内のため)。 */
  .hensou-amplitude-field .amplitude-choice { display:flex; align-items:center; gap:6px; padding:6px; border:1px solid var(--border); border-radius:var(--r); background:var(--panel); color:var(--fg2); font-size:.68rem; cursor:pointer; }
  .hensou-amplitude-field .amplitude-choice.checked { border-color: var(--accent); color: var(--fg); }
  .hensou-amplitude-field .amplitude-choice input { width:12px; height:12px; accent-color:var(--accent); margin:0; }
  .amplitude-choice-label { display:inline-flex; align-items:center; gap:5px; min-width:0; }
  .amplitude-info-mark { display:inline-flex; align-items:center; justify-content:center; width:13px; height:13px; border:1px solid var(--border2); border-radius:50%; color:var(--fg3); font-size:9px; }
  .progress-preview { width:72px; height:72px; border-radius:6px; overflow:hidden; background:var(--bg2); border:1px solid var(--border); box-shadow:0 4px 12px rgba(0,0,0,.15); } .progress-preview :global(.history-thumbnail) { width:100%; height:100%; aspect-ratio:auto; } .progress-preview :global(svg) { width:100%; height:100%; display:block; }
  .vision-advice { padding:10px 12px; border:1px solid var(--border); border-radius:8px; background:var(--bg2); } .vision-advice h4 { margin:0 0 3px; color:var(--fg3); font-size:.68rem; } .vision-advice p { margin:0 0 8px; color:var(--fg2); font-size:.76rem; line-height:1.45; } .vision-advice p:last-child { margin-bottom:0; }
  .error-banner { padding:8px 12px; background:color-mix(in srgb,var(--danger,#9b3d32) 10%,var(--panel)); border:1px solid var(--danger,#9b3d32); border-radius:6px; color:var(--danger,#9b3d32); font-size:.74rem; line-height:1.35; white-space:pre-line; }
  footer { display:flex; align-items:center; justify-content:flex-end; gap:8px; padding:12px 18px; border-top:1px solid var(--border); background:var(--bg2); } footer button { border:1px solid var(--border2); border-radius:6px; padding:7px 14px; font-size:.8rem; font-weight:500; cursor:pointer; background:var(--panel); color:var(--fg); } .confirm-action { background:var(--accent); color:var(--accent-fg); border-color:var(--accent); } .confirm-action:disabled { opacity:.5; cursor:default; } .cancel-action:hover { background:var(--bg); }
  @media (max-width:560px) { .mode-choice { grid-template-columns:1fr; } }
</style>

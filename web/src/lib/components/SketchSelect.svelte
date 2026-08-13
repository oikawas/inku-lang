<!--
	写生 (Stage 0.5) selector. Three states in one control: off, cut fine, cut
	coarse. Same two shapes as WildToggle, for the same reason -- it sits in
	the same rows.
	- compact=false: dropdown trigger + menu, for the describe tab's control row.
	- compact=true: inline segmented control for the dialogs, where `inherited`
	  marks that nothing will be sent unless the author picks a state.
-->
<script lang="ts">
	import { SKETCH_MODES, sketchModeLabel, sketchModeHint, sketchModeNote, type SketchMode } from '$lib/sketch';

	type Props = {
		value: SketchMode;
		isJapanese: boolean;
		compact?: boolean;
		inherited?: boolean;
		disabled?: boolean;
		onSelect: (mode: SketchMode) => void;
	};

	let { value, isJapanese, compact = false, inherited = false, disabled = false, onSelect }: Props = $props();

	let open = $state(false);
	const title = $derived(isJapanese ? '写生' : 'Sketch from life');

	function choose(mode: SketchMode) {
		onSelect(mode);
		open = false;
	}
</script>

{#if compact}
	<div class="sketch-inline" role="group" aria-label={title}>
		<span class="sketch-inline-label"
			>{title}{#if inherited}<span class="sketch-inherit"
					>{isJapanese ? '（継承）' : '(inherited)'}</span
				>{/if}{isJapanese ? '：' : ':'}</span
		>
		<div class="sketch-seg">
			{#each SKETCH_MODES as mode (mode)}
				<button
					type="button"
					class:active={mode === value}
					{disabled}
					aria-pressed={mode === value}
					title={sketchModeHint(mode, isJapanese)}
					onclick={() => onSelect(mode)}
				>{sketchModeLabel(mode, isJapanese)}</button>
			{/each}
		</div>
	</div>
{:else}
	<div class="sketch-plugin">
		<button
			type="button"
			class="ghost-btn sketch-trigger"
			{disabled}
			aria-haspopup="menu"
			aria-expanded={open}
			onclick={(event) => { event.stopPropagation(); open = !open; }}
		>
			<span>{title}</span>
		</button>
		{#if open}
			<div class="sketch-menu" role="menu">
				<div class="sketch-menu-head">{isJapanese ? '区切りの大きさ' : 'Grain'}</div>
				{#each SKETCH_MODES as mode (mode)}
					<button
						type="button"
						class:selected={mode === value}
						role="menuitemradio"
						aria-checked={mode === value}
						onclick={() => choose(mode)}
					>
						<!-- The note is its own element, never joined onto the label:
						     joined, it would be indistinguishable from what
						     sketchModeLabel returns and would follow the label to
						     the three places that must not carry it. -->
						<span class="option-head"
							><span class="option-label">{sketchModeLabel(mode, isJapanese)}</span
							>{#if sketchModeNote(mode, isJapanese)}<span class="option-note"
									>{sketchModeNote(mode, isJapanese)}</span
								>{/if}</span
						>
						<span class="option-intent">{sketchModeHint(mode, isJapanese)}</span>
					</button>
				{/each}
			</div>
		{/if}
	</div>
{/if}

<style>
	/* dropdown variant (describe tab) */
	.sketch-plugin { position: relative; display: inline-flex; }
	.sketch-trigger { display: inline-flex; align-items: center; }
	.sketch-menu {
		position: absolute;
		top: calc(100% + 6px);
		left: 0;
		z-index: 80;
		width: 260px;
		border: 1px solid var(--border2);
		border-radius: var(--r-lg, var(--r));
		background: var(--panel);
		box-shadow: 0 10px 32px rgba(0, 0, 0, 0.18);
		padding: 6px;
	}
	.sketch-menu-head {
		padding: 6px 8px 8px;
		font-size: 11px;
		color: var(--fg3);
		border-bottom: 1px solid var(--border);
		margin-bottom: 4px;
	}
	.sketch-menu button {
		width: 100%;
		border: none;
		background: transparent;
		color: var(--fg);
		font-family: inherit;
		text-align: left;
		padding: 8px;
		border-radius: var(--r);
		cursor: pointer;
		display: grid;
		gap: 2px;
	}
	.sketch-menu button:hover { background: var(--bg2); }
	.sketch-menu button.selected { background: var(--bg2); box-shadow: inset 3px 0 0 var(--fg2); }
	.option-head { display: inline-flex; align-items: baseline; gap: 4px; }
	.option-label { font-size: 13px; font-weight: 500; }
	/* Weaker than the label: a note about the option, not part of its name. */
	.option-note { font-size: 11px; color: var(--fg3); font-weight: 400; }
	.option-intent { font-size: 11px; line-height: 1.35; color: var(--fg3); }

	/* compact variant (dialogs) */
	.sketch-inline { display: inline-flex; align-items: center; gap: 8px; min-width: 0; }
	.sketch-inline-label { font-size: 11px; color: var(--fg3); white-space: nowrap; }
	.sketch-inherit { margin-left: 2px; color: var(--fg3); }
	.sketch-seg { display: inline-flex; border: 1px solid var(--border2); border-radius: var(--r); overflow: hidden; }
	.sketch-seg button {
		padding: 5px 10px;
		border: 0;
		border-right: 1px solid var(--border2);
		background: var(--panel);
		color: var(--fg2);
		font: inherit;
		font-size: 11px;
		cursor: pointer;
		white-space: nowrap;
	}
	.sketch-seg button:last-child { border-right: 0; }
	.sketch-seg button:hover:not(:disabled) { background: var(--bg2); }
	.sketch-seg button.active { background: var(--accent); color: var(--accent-fg); }
	.sketch-seg button:disabled { opacity: .5; cursor: not-allowed; }
</style>

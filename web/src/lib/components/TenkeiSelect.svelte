<!--
	添景水準 (tenkei) selector.
	- compact=false: dropdown trigger + menu, matching the canvas-aspect plugin
	  control in the describe tab's generation control row.
	- compact=true: inline 3-way segmented control for the refine dialogs, where
	  the parent artwork's level is preselected and `inherited` marks that the
	  value will be inherited (nothing sent) unless the user picks one.
-->
<script lang="ts">
	import { TENKEI_LEVELS, tenkeiLabel, tenkeiHint, type TenkeiLevel } from '$lib/tenkei';

	type Props = {
		value: TenkeiLevel;
		isJapanese: boolean;
		compact?: boolean;
		inherited?: boolean;
		disabled?: boolean;
		onSelect: (level: TenkeiLevel) => void;
	};

	let { value, isJapanese, compact = false, inherited = false, disabled = false, onSelect }: Props = $props();

	let open = $state(false);
	const title = $derived(isJapanese ? '添景' : 'Staffage');

	function choose(level: TenkeiLevel) {
		onSelect(level);
		open = false;
	}
</script>

{#if compact}
	<div class="tenkei-inline" role="group" aria-label={title}>
		<span class="tenkei-inline-label">
			{title}{#if inherited}<span class="tenkei-inherit">{isJapanese ? '（継承）' : '(inherited)'}</span>{/if}
		</span>
		<div class="tenkei-seg">
			{#each TENKEI_LEVELS as level (level)}
				<button
					type="button"
					class:active={level === value}
					{disabled}
					aria-pressed={level === value}
					title={tenkeiHint(level, isJapanese)}
					onclick={() => onSelect(level)}
				>{tenkeiLabel(level, isJapanese)}</button>
			{/each}
		</div>
	</div>
{:else}
	<div class="tenkei-plugin">
		<button
			type="button"
			class="ghost-btn tenkei-trigger"
			{disabled}
			aria-haspopup="menu"
			aria-expanded={open}
			onclick={(event) => { event.stopPropagation(); open = !open; }}
		>
			<!-- The selected level is reported by the current-selection strip below
			     the button row, so the trigger stays a plain label. -->
			<span>{title}</span>
		</button>
		{#if open}
			<div class="tenkei-menu" role="menu">
				<div class="tenkei-menu-head">{isJapanese ? '添景水準' : 'Staffage level'}</div>
				{#each TENKEI_LEVELS as level (level)}
					<button
						type="button"
						class:selected={level === value}
						role="menuitemradio"
						aria-checked={level === value}
						onclick={() => choose(level)}
					>
						<span class="option-label">{tenkeiLabel(level, isJapanese)}</span>
						<span class="option-intent">{tenkeiHint(level, isJapanese)}</span>
					</button>
				{/each}
			</div>
		{/if}
	</div>
{/if}

<style>
	/* dropdown variant (describe tab) */
	.tenkei-plugin { position: relative; display: inline-flex; }
	.tenkei-trigger { display: inline-flex; align-items: center; }
	.ghost-btn {
		padding: var(--btn-sm-padding);
		border: 1px solid var(--border2);
		border-radius: var(--btn-sm-radius);
		background: var(--panel);
		color: var(--fg2);
		font-size: var(--btn-sm-font-size);
		cursor: pointer;
		font-family: inherit;
		white-space: nowrap;
	}
	.ghost-btn:hover:not(:disabled) { background: var(--bg2); }
	.ghost-btn:disabled { opacity: .5; cursor: not-allowed; }
	.tenkei-menu {
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
	.tenkei-menu-head {
		padding: 6px 8px 8px;
		font-size: 11px;
		color: var(--fg3);
		border-bottom: 1px solid var(--border);
		margin-bottom: 4px;
	}
	.tenkei-menu button {
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
	.tenkei-menu button:hover { background: var(--bg2); }
	.tenkei-menu button.selected { background: var(--bg2); box-shadow: inset 3px 0 0 var(--fg2); }
	.option-label { font-size: 13px; font-weight: 500; }
	.option-intent { font-size: 11px; line-height: 1.35; color: var(--fg3); }

	/* compact variant (refine dialogs) */
	.tenkei-inline { display: inline-flex; align-items: center; gap: 8px; min-width: 0; }
	.tenkei-inline-label { font-size: 11px; color: var(--fg3); white-space: nowrap; }
	.tenkei-inherit { margin-left: 2px; color: var(--fg3); }
	.tenkei-seg { display: inline-flex; border: 1px solid var(--border2); border-radius: var(--r); overflow: hidden; }
	.tenkei-seg button {
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
	.tenkei-seg button:last-child { border-right: 0; }
	.tenkei-seg button:hover:not(:disabled) { background: var(--bg2); }
	.tenkei-seg button.active { background: var(--accent); color: var(--accent-fg); }
	.tenkei-seg button:disabled { opacity: .5; cursor: not-allowed; }
</style>

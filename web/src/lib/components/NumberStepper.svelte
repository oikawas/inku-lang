<script lang="ts">
	type Props = {
		value: number;
		min: number;
		max: number;
		step?: number;
		disabled?: boolean;
		label: string;
		onChange: (value: number) => void | Promise<void>;
	};

	let { value, min, max, step = 1, disabled = false, label, onChange }: Props = $props();
	let current = $state(0);

	$effect(() => {
		current = value;
	});

	function normalize(next: number): number {
		const bounded = Math.min(max, Math.max(min, next));
		const decimals = String(step).split('.')[1]?.length ?? 0;
		return Number(bounded.toFixed(decimals));
	}

	function changeBy(direction: -1 | 1): void {
		current = normalize(current + step * direction);
		void onChange(current);
	}

	function commit(event: Event): void {
		const next = Number((event.currentTarget as HTMLInputElement).value);
		if (!Number.isFinite(next)) return;
		current = normalize(next);
		void onChange(current);
	}
</script>

<div class="number-stepper">
	<button type="button" aria-label={`${label} −`} disabled={disabled || current <= min} onclick={() => changeBy(-1)}>−</button>
	<input type="number" {min} {max} {step} value={current} aria-label={label} {disabled} onchange={commit} />
	<button type="button" aria-label={`${label} +`} disabled={disabled || current >= max} onclick={() => changeBy(1)}>+</button>
</div>

<style>
	.number-stepper {
		display: grid;
		grid-template-columns: auto minmax(0, 1fr) auto;
		align-items: stretch;
		gap: 4px;
		width: 100%;
		min-width: 0;
	}
	button {
		padding: var(--btn-sm-padding);
		border: 1px solid var(--border2);
		border-radius: var(--btn-sm-radius);
		background: var(--bg);
		color: var(--fg);
		font-family: inherit;
		font-size: var(--btn-sm-font-size);
		line-height: 1;
		cursor: pointer;
	}
	button:hover:not(:disabled) { background: var(--bg2); }
	button:disabled { opacity: 0.4; cursor: default; }
	input {
		box-sizing: border-box;
		width: 100%;
		min-width: 0;
		padding: 5px 4px;
		border: 1px solid var(--border2);
		border-radius: var(--r);
		appearance: textfield;
		background: var(--panel);
		color: var(--fg);
		font-family: inherit;
		font-size: 12px;
		font-variant-numeric: tabular-nums;
		text-align: center;
	}
	input::-webkit-inner-spin-button,
	input::-webkit-outer-spin-button {
		margin: 0;
		appearance: none;
	}
</style>

<script lang="ts">
	import { formatGroupedNumber, parseGroupedNumber } from '$lib/groupedNumber';

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
		const input = event.currentTarget as HTMLInputElement;
		const next = parseGroupedNumber(input.value);
		if (next === null) {
			input.value = formatGroupedNumber(current, step);
			return;
		}
		current = normalize(next);
		input.value = formatGroupedNumber(current, step);
		void onChange(current);
	}

	function handleKeydown(event: KeyboardEvent): void {
		if (disabled || (event.key !== 'ArrowDown' && event.key !== 'ArrowUp')) return;
		event.preventDefault();
		changeBy(event.key === 'ArrowDown' ? -1 : 1);
	}
</script>

<div class="number-stepper">
	<button type="button" aria-label={`${label} −`} disabled={disabled || current <= min} onclick={() => changeBy(-1)}>−</button>
	<input
		type="text"
		role="spinbutton"
		inputmode="decimal"
		aria-label={label}
		aria-valuemin={min}
		aria-valuemax={max}
		aria-valuenow={current}
		value={formatGroupedNumber(current, step)}
		{disabled}
		onchange={commit}
		onkeydown={handleKeydown}
	/>
	<button type="button" aria-label={`${label} +`} disabled={disabled || current >= max} onclick={() => changeBy(1)}>+</button>
</div>

<style>
	.number-stepper {
		display: grid;
		grid-template-columns: auto minmax(0, 1fr) auto;
		align-items: stretch;
		gap: 4px;
		width: min(136px, 100%);
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
</style>

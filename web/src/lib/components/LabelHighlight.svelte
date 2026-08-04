<script lang="ts">
	// A background layer for a textarea: a textarea cannot colour a range of its
	// own text, so an identical copy of the text sits behind it with the ranges
	// the drawing will not read painted grey.  Only the backgrounds are visible
	// (the text here is transparent); the textarea above draws the characters.
	//
	// The metrics below must stay equal to the textarea's: same font, same size,
	// same line-height, same padding, same wrapping.  Both editors that use this
	// are 13px/1.65 with 9px 10px of padding.
	import { labelSegments } from '$lib/description-labels';

	type Props = {
		text: string;
		/** false for the batch editor, which does not wrap and scrolls sideways. */
		wrap?: boolean;
		scrollTop?: number;
		scrollLeft?: number;
	};

	let { text, wrap = true, scrollTop = 0, scrollLeft = 0 }: Props = $props();

	const segments = $derived(labelSegments(text));
</script>

<div class="label-mirror" class:nowrap={!wrap} aria-hidden="true">
	<div class="label-mirror-inner" style={`transform: translate(${-scrollLeft}px, ${-scrollTop}px)`}
		>{#each segments as segment, index (index)}{#if segment.kind}<span
					class="label-muted"
					class:comment={segment.kind === 'comment'}>{segment.text}</span
				>{:else}{segment.text}{/if}{/each}<!-- A trailing break needs something after
		it or the last line has no height. --><span class="label-tail"> </span></div>
</div>

<style>
	.label-mirror {
		position: absolute;
		inset: 0;
		overflow: hidden;
		border-radius: var(--r);
		pointer-events: none;
		z-index: 0;
	}
	.label-mirror-inner {
		padding: 9px 10px;
		font-family: inherit;
		font-size: 13px;
		line-height: 1.65;
		color: transparent;
		white-space: pre-wrap;
		overflow-wrap: break-word;
		word-break: break-word;
	}
	.nowrap .label-mirror-inner {
		white-space: pre;
		overflow-wrap: normal;
		word-break: normal;
	}
	/* The band the author reads as "this is mine, not the drawing's". */
	.label-muted {
		background: color-mix(in srgb, var(--fg3) 22%, transparent);
		border-radius: 2px;
	}
	.label-tail {
		color: transparent;
	}
</style>

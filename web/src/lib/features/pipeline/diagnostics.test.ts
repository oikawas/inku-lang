import assert from 'node:assert/strict';
import test from 'node:test';

import { en } from '../../i18n/en.ts';
import { ja } from '../../i18n/ja.ts';
import { formatPipelineDiagnostic } from './diagnostics.ts';

test('resource omission names its owner, limit, omitted part, and continued drawing', () => {
	const actual = formatPipelineDiagnostic({
		channel: 'resource',
		value: {
			cause: {
				owner: { kind: 'object', value: { instruction_index: 0, kind: 'source_instruction' } },
				reason: {
					kind: 'budget_exceeded',
					value: { authority: 'hard_policy', dimension: 'logical_objects', maximum: 400, required: 6945 },
				},
			},
			owner: { kind: 'source_instruction', value: { source_instruction_index: 0 } },
		},
	}, ja);

	assert.equal(
		actual,
		'原文の指示 1 の箇所。 描画対象の数は 6945 必要でしたが、上限は 400 でした。 原文の指示 1 を省略しました。 ほかの部分の描画は続けました。',
	);
});

test('partial resource execution names requested and drawn counts without saying the instruction was omitted', () => {
	const actual = formatPipelineDiagnostic({
		channel: 'resource',
		value: {
			cause: {
				owner: { kind: 'object', value: { instruction_index: 0, kind: 'source_instruction' } },
				reason: {
					kind: 'budget_exceeded',
					value: { authority: 'hard_policy', dimension: 'maximum_per_template_primitive_marks', maximum: 240, required: 300 },
				},
			},
			owner: { kind: 'source_instruction', value: { source_instruction_index: 0 } },
			partial_execution: { requested_count: 300, executed_count: 240 },
		},
	}, ja);

	assert.equal(
		actual,
		'原文の指示 1 の箇所。 一つの描画指示が描く印の数は 300 必要でしたが、上限は 240 でした。 300個の要求のうち、実行可能な240個を描画しました。 ほかの部分の描画は続けました。',
	);
});

test('saved render clip omission names its instruction, reason, omission, and continuation', () => {
	const actual = formatPipelineDiagnostic({
		channel: 'render',
		value: {
			instruction_index: 2,
			reason: 'fill_clip_limit_exceeded',
			disposition: 'omitted',
		},
	}, ja);

	assert.equal(
		actual,
		'描画指示 3 の箇所。 クリップ処理の上限を超えました。 描画指示 3 を省略しました。 ほかの部分の描画は続けました。',
	);
});

test('words whose shape could not be decided are named as omitted source words', () => {
	const diagnostic = {
		channel: 'upstream' as const,
		value: {
			disposition: { kind: 'omitted', unit: { kind: 'source_occurrence', span: { start_byte: 12, end_byte: 18 } } },
			issue_kind: 'conflict',
			reason: 'ambiguous_entity_ownership',
			span: { start_byte: 12, end_byte: 18 },
		},
	};

	assert.equal(
		formatPipelineDiagnostic(diagnostic, ja),
		'原文のバイト位置 12〜18。 この言葉がどの形のものか決められませんでした。 原文の言葉 を省略しました。 ほかの部分の描画は続けました。',
	);
	assert.equal(
		formatPipelineDiagnostic(diagnostic, en),
		'Source byte range 12–18. Which shape these words belong to could not be decided. Omitted source words. The rest of the drawing continued.',
	);
});

test('a withheld plugin sentence is explained in the author\'s language', () => {
	assert.equal(
		formatPipelineDiagnostic({ channel: 'plugin', value: { name: 'Nature.若菜', reason: 'plugin_name_mismatch', suggestion: 'Nature.若葉', start_byte: 28, end_byte: 42 } }, ja),
		'プラグイン Nature.若菜 は登録名と一致しないため、この文は描かれていません。Nature.若葉 のことですか。',
	);
	assert.equal(
		formatPipelineDiagnostic({ channel: 'plugin', value: { name: 'Garden.薔薇', reason: 'plugin_not_installed', start_byte: 0, end_byte: 1 } }, ja),
		'プラグイン Garden.薔薇 はこの環境に登録されていないため、この文は描かれていません。',
	);
});

test('a render warning names the color the core would not use, and that drawing went on', () => {
	const actual = formatPipelineDiagnostic({ channel: 'warning', value: { kind: 'invalid_color', name: 'black' } }, ja);
	assert.equal(actual, '色表の「black」の値が#rrggbbの形ではないため、この値は使わずに描きました。名前つきの色は既定の色で描いています。');
});

test('a numeric range the author got wrong is said in words, whichever tag carries it', () => {
	// Upstream: the semantic association names its issue under `issue_kind`.
	const invalid = formatPipelineDiagnostic({
		channel: 'upstream',
		value: { issue_kind: 'invalid_numeric_range' },
	}, ja);
	assert.match(invalid, /数値の範囲が正しくありません。/);

	// Downstream: a Score gap is tagged with `type`, not `kind`.
	const unsupported = formatPipelineDiagnostic({
		channel: 'downstream',
		value: { reason: { type: 'unsupported_numeric_range' } },
	}, ja);
	assert.match(unsupported, /まだ数値の範囲を書けません。/);
	assert.doesNotMatch(unsupported, /diagnostic/);
});

test('a fade and colors that shift are said in words, in each language', () => {
	for (const [kind, japanese, english] of [
		['conflicting_fades', /薄れ（〜へ薄れさせて）が二つ書かれています。/, /Two fades \(fading …\) are written in one sentence\./],
		['shift_needs_colors', /段々に移せるのは色の列だけです。/, /Only colors shift through in order\./],
	] as const) {
		const upstream = { channel: 'upstream' as const, value: { issue_kind: kind } };
		assert.match(formatPipelineDiagnostic(upstream, ja), japanese);
		assert.match(formatPipelineDiagnostic(upstream, en), english);
	}
	for (const [type, japanese, english] of [
		['unsupported_fade', /2個以上を並べる列にだけ/, /only for a row of two or more marks/],
		['fade_direction_off_axis', /薄れの向きが列の向きに合いません。/, /does not run along its row/],
		['unsupported_color_shift', /並べる列と敷き詰めだけです。/, /only for marks that line up or a tile/],
		['color_shift_longer_than_count', /痕の数より多くなっています。/, /than there are marks/],
	] as const) {
		const downstream = { channel: 'downstream' as const, value: { reason: { type } } };
		assert.match(formatPipelineDiagnostic(downstream, ja), japanese);
		assert.match(formatPipelineDiagnostic(downstream, en), english);
		assert.doesNotMatch(formatPipelineDiagnostic(downstream, en), /Reason:/);
	}
});

test('two points written in numbers are said in words, in each language', () => {
	const invalid = { channel: 'upstream' as const, value: { issue_kind: 'invalid_numeric_segment' } };
	assert.match(formatPipelineDiagnostic(invalid, ja), /数値で書いた二つの点（〜から〜まで）が正しくありません。/);
	assert.match(formatPipelineDiagnostic(invalid, en), /The two points written in numbers \(from … to …\) are not valid\./);
	for (const [type, japanese, english] of [
		['unsupported_numeric_segment', /列の両端か、1本の線・自由線の両端にだけ使えます。/, /the ends of a row of two or more marks/],
		['numeric_segment_conflict', /並べる向きの言葉とは一緒に書けません。/, /already set the direction and the length/],
	] as const) {
		const downstream = { channel: 'downstream' as const, value: { reason: { type } } };
		assert.match(formatPipelineDiagnostic(downstream, ja), japanese);
		assert.match(formatPipelineDiagnostic(downstream, en), english);
		assert.doesNotMatch(formatPipelineDiagnostic(downstream, en), /Reason:/);
	}
});

test('an angle written in numbers is said in words, in each language', () => {
	const invalid = { channel: 'upstream' as const, value: { issue_kind: 'invalid_numeric_angle' } };
	assert.match(formatPipelineDiagnostic(invalid, ja), /数値で書いた角度（回転〜度）が正しくありません。/);
	assert.match(formatPipelineDiagnostic(invalid, en), /The angle written in numbers \(rotated … degrees\) is not valid\./);
	assert.doesNotMatch(formatPipelineDiagnostic(invalid, en), /Reason:/);
	const conflict = { channel: 'downstream' as const, value: { reason: { type: 'numeric_segment_conflict' } } };
	assert.match(formatPipelineDiagnostic(conflict, ja), /数値の角度/);
	assert.match(formatPipelineDiagnostic(conflict, en), /a numeric angle/);
});

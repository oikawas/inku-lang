// What each problem code a plugin package check returns means, in words an
// administrator can act on. The codes come from three places: the package
// file's own shape (Server), the shared core's definition checks (the table of
// PLUGIN.md §7.2), and drawing each example. A code missing here is shown as
// the code itself, so a new core code is never hidden.

type Message = { ja: string; en: string };

const MESSAGES: Record<string, Message> = {
	// The file's own shape
	invalid_json: { ja: 'JSON として読めません。', en: 'The file is not valid JSON.' },
	package_too_large: { ja: 'ファイルが大きすぎます。', en: 'The file is too large.' },
	not_an_object: { ja: '{ } のオブジェクトでなければなりません。', en: 'Must be an object ({ }).' },
	unknown_field: { ja: '知らない欄です。綴りを確かめるか、欄を消してください。', en: 'Unknown field. Check its spelling or remove it.' },
	wrong_schema: { ja: 'schema は inku.plugin-package.v2 にします。', en: 'schema must be inku.plugin-package.v2.' },
	rewrite_as_v2: { ja: '古い形式（v1）のファイルです。inku.plugin-package.v2 に書き直して入れ直してください。', en: 'This file uses the old v1 format. Rewrite it as inku.plugin-package.v2 and install it again.' },
	definition_requires_v2: { ja: '定義を v2 の形で書き直してください。', en: 'Rewrite the definition in v2 form.' },
	example_without_name: { ja: '例文では括弧つきの主の名で語を呼んでください。', en: 'Use the braced primary name in the example.' },
	invalid_identifier: { ja: '英字で始め、英数字・_・- だけで書きます。', en: 'Start with a letter and use only letters, digits, _ and -.' },
	invalid_semantic_version: { ja: 'バージョンは 1.0.0 の形で書きます。', en: 'Write the version as 1.0.0.' },
	not_a_string: { ja: '文字列で書きます。', en: 'Must be a string.' },
	not_a_list_of_strings: { ja: '文字列の配列で書きます。', en: 'Must be a list of strings.' },
	text_too_long: { ja: '長すぎます。', en: 'Too long.' },
	no_words: { ja: 'words に語が一つもありません。', en: 'words has no words.' },
	too_many_words: { ja: '語が多すぎます。', en: 'Too many words.' },
	namespace_differs_from_package: { ja: '定義の namespace が package の namespace と違います。', en: "The definition's namespace differs from the package's." },
	id_differs_from_directory: { ja: '置き場所のフォルダの名前と、ファイルの namespace.name が違います。', en: "The folder's name differs from the file's namespace.name." },
	invalid_package_id: { ja: 'プラグインの id は namespace.name の形です。', en: 'A plugin id has the form namespace.name.' },
	bundled_package_id: { ja: '同梱の Nature.leaves と同じ id は使えません。', en: 'The id of the bundled Nature.leaves package cannot be used.' },
	no_note: { ja: 'note_ja か note_en に、何の物かを一文で書いてください。', en: 'Write one sentence about the word in note_ja or note_en.' },
	// The shared core's definition checks
	invalid_canonical_definition: { ja: '定義の形が正しくありません。', en: 'The definition is not well formed.' },
	unknown_json_field: { ja: '定義に知らない欄があります。', en: 'The definition has an unknown field.' },
	duplicate_qualified_name: { ja: '同じ名前（正式名か別名）の語が package の中に二つあります。', en: 'Two words in the package share a name or alias.' },
	unknown_semantic_id: { ja: '歳時記に無い語です（例: 色の pink）。DDL の手引きにある値から選びます。', en: 'Not a Saijiki word (e.g. the color pink). Choose a value from the DDL reference.' },
	unknown_semantic_category: { ja: 'category の綴りが違います。', en: 'The category is misspelled.' },
	unknown_semantic_field: { ja: 'emit に無い欄の名前です。', en: 'Not a field emit has.' },
	semantic_field_requires_matching_reference: { ja: '欄と語の分類が合いません。', en: "The field and the word's category do not match." },
	geometry_field_requires_exact_decimal: { ja: '位置・寸法は exact_decimal で書きます。', en: 'Write positions and sizes with exact_decimal.' },
	invalid_count_parameter: { ja: '個数の引数の範囲・候補が決まりに合いません。', en: 'The count parameter’s range or choices break the rules.' },
	invalid_repeat_count: { ja: 'repeat の count が整数でないか、maximum を超えます。', en: "repeat's count is not an integer or exceeds maximum." },
	unbounded_repeat: { ja: 'repeat の maximum が 0 です。', en: "repeat's maximum is 0." },
	undefined_parameter: { ja: '宣言していない引数を読んでいます。', en: 'Reads a parameter that is not declared.' },
	undefined_local: { ja: '範囲の外の index・binding を読んでいます。', en: 'Reads an index or binding outside its scope.' },
	undefined_anchor: { ja: 'relation の from・to が binding や anchor の名前と合いません。', en: "relation's from or to names no binding or anchor." },
	invalid_alias: { ja: '別名に使えない文字があります。', en: 'The alias has characters it may not.' },
	duplicate_alias: { ja: '別名が見出しや他の別名と重なります。', en: 'The alias repeats the heading or another alias.' },
	component_cycle: { ja: '部品が自分自身を呼んでいます。', en: 'A component calls itself.' },
	name_taken: { ja: 'この名前は、もう入っている別のプラグインが使っています。', en: 'Another installed plugin already uses this name.' },
	name_is_core_word: { ja: '基本語と同じ名は使えません。', en: 'A plugin name cannot be a core word.' },
	invalid_plugin_name: { ja: '見える名に使えない文字か空白があります。', en: 'The visible name has invalid characters or spacing.' },
	invalid_plugin_id: { ja: '語の id は英字で始まる識別子にします。', en: 'The word id must be an identifier starting with a letter.' },
	invalid_plugin_kind: { ja: 'kind は object か scene にします。', en: 'kind must be object or scene.' },
	invalid_plugin_aspect: { ja: '物の縦横比は整数二つを : でつなぎます。', en: 'Write an object aspect as two integers separated by :.' },
	invalid_plugin_counter: { ja: '物の助数詞は使える値から選びます。', en: 'Choose a supported object counter.' },
	object_count_parameter: { ja: '物の語に個数を受ける引数は置けません。', en: 'An object word cannot declare a count receiver.' },
	scene_has_aspect: { ja: '情景の語に縦横比は置けません。', en: 'A scene word cannot have an aspect.' },
	scene_has_counter: { ja: '情景の語に助数詞は置けません。', en: 'A scene word cannot have a counter.' },
	duplicate_plugin_name: { ja: '同じ見える名が定義内で重なっています。', en: 'A visible name repeats within the definition.' },
	anchor_requires_one_explicit_position: { ja: 'anchor に明示位置を一つ書いてください。', en: 'Give the anchor exactly one explicit position.' },
	argument_type_mismatch: { ja: '引数に渡した値の型が合いません。', en: 'An argument has the wrong type.' },
	count_parameter_in_component: { ja: '部品内では個数を受ける引数を宣言できません。', en: 'A component cannot declare the count receiver.' },
	duplicate_anchor_or_binding: { ja: 'anchor または binding の名が重なっています。', en: 'An anchor or binding name repeats.' },
	duplicate_count_parameter: { ja: '個数を受ける引数が複数あります。', en: 'More than one parameter receives count.' },
	duplicate_local_binding: { ja: '局所 binding の名が重なっています。', en: 'A local binding name repeats.' },
	empty_cycle: { ja: 'cycle に候補がありません。', en: 'The cycle has no choices.' },
	empty_transform: { ja: 'transform に変更がありません。', en: 'The transform has no changes.' },
	empty_vary: { ja: 'vary に候補がありません。', en: 'The vary statement has no choices.' },
	external_component_reference: { ja: '別の定義の部品は呼べません。', en: 'A component from another definition cannot be used.' },
	heterogeneous_cycle: { ja: 'cycle の候補は同じ型にします。', en: 'Cycle choices must have the same type.' },
	invalid_anchor_or_binding_id: { ja: 'anchor または binding の識別子が正しくありません。', en: 'The anchor or binding identifier is invalid.' },
	invalid_component_id: { ja: '部品の識別子が正しくありません。', en: 'The component identifier is invalid.' },
	invalid_cycle_index: { ja: 'cycle の添字が範囲外です。', en: 'The cycle index is out of range.' },
	invalid_emit_count_type: { ja: 'emit の個数は整数にします。', en: 'An emit count must be an integer.' },
	invalid_endpoint_target: { ja: '端点の対象が使える形ではありません。', en: 'The endpoint target is invalid.' },
	invalid_local_binding_id: { ja: '局所 binding の識別子が正しくありません。', en: 'The local binding identifier is invalid.' },
	invalid_parameter_id: { ja: '引数の識別子が正しくありません。', en: 'The parameter identifier is invalid.' },
	invalid_semantic_dimension: { ja: '意味語の次元が合いません。', en: 'The semantic dimension is invalid.' },
	invalid_vary_domain: { ja: 'vary の範囲が正しくありません。', en: 'The vary domain is invalid.' },
	invalid_vary_range: { ja: 'vary の値の範囲が正しくありません。', en: 'The vary range is invalid.' },
	invalid_vary_source: { ja: 'vary の参照元が正しくありません。', en: 'The vary source is invalid.' },
	missing_argument: { ja: '必須の引数がありません。', en: 'A required argument is missing.' },
	non_finite_number: { ja: '有限でない数は使えません。', en: 'A number must be finite.' },
	path_position_requires_connected: { ja: '経路上の位置には connected の関係が必要です。', en: 'A path position needs a connected relation.' },
	path_position_requires_number: { ja: '経路上の位置は数で指定します。', en: 'A path position must be numeric.' },
	resource_bound_overflow: { ja: '定義の資源上限を超えます。', en: 'The definition exceeds its resource bound.' },
	transform_requires_number: { ja: 'transform の値は数にします。', en: 'A transform value must be numeric.' },
	undefined_component: { ja: '呼んだ部品が定義されていません。', en: 'The component is not defined.' },
	unknown_anchor_field: { ja: 'anchor に無い欄です。', en: 'The anchor has no such field.' },
	unknown_argument: { ja: '宣言していない引数を渡しています。', en: 'An undeclared argument was passed.' },
	unknown_schema: { ja: '定義の schema が正しくありません。', en: 'The definition schema is unknown.' },
	vary_choice_type_mismatch: { ja: 'vary の候補の型が合いません。', en: 'A vary choice has the wrong type.' },
	// Drawing the examples
	macro_binding_count_out_of_range: { ja: '例文の個数が、定義が受ける範囲の外です。', en: "The example's count is outside the range the definition takes." },
	macro_resolution_missing_lock: { ja: '例文の語が見つかりません。名前の綴りか、定義の誤りを確かめてください。', en: "The example's word is not found. Check its spelling or the definition." },
	compiler_diagnostics: { ja: '例文が DDL として描けません。', en: 'The example does not draw as DDL.' },
	example_draws_nothing: { ja: '例文を描いても、何も描かれません。', en: 'The example draws nothing.' },
	example_not_drawn: { ja: '例文を描けませんでした。', en: 'The example could not be drawn.' },
	// Pictures: a word's own in its zip, or a replacement
	not_a_png: { ja: 'PNG の画像ではありません。', en: 'Not a PNG picture.' },
	image_too_large: { ja: '画像が大きすぎます。', en: 'The picture is too large.' },
	preview_needs_zip: { ja: '絵（preview）は zip の中の PNG を名指します。JSON だけのファイルでは使えません。', en: 'preview names a PNG inside a zip; a JSON file alone cannot have one.' },
	preview_not_found: { ja: 'zip の中に、この名前の PNG がありません。', en: 'The zip has no PNG by this name.' },
	invalid_preview_path: { ja: '絵の場所は、zip の中の場所で書きます（「..」や「/」で始まる場所は使えません）。', en: 'Write the place inside the zip (not starting with "/" and without "..").' },
	// The zip itself
	invalid_zip: { ja: 'zip として読めません。', en: 'Not a readable zip.' },
	not_base64: { ja: 'ファイルを送れませんでした（base64 でない）。', en: 'The file could not be sent (not base64).' },
	archive_too_large: { ja: 'zip が大きすぎます。', en: 'The zip is too large.' },
	too_many_archive_members: { ja: 'zip の中のファイルが多すぎます。', en: 'The zip holds too many files.' },
	archive_without_package_json: { ja: 'zip の一番上に package.json がありません。', en: 'The zip has no package.json at its top.' },
	not_utf8: { ja: 'package.json が UTF-8 ではありません。', en: 'package.json is not UTF-8.' },
};

export function pluginProblemMessage(code: string, isJapanese: boolean): string {
	const message = MESSAGES[code];
	if (!message) return code;
	return isJapanese ? message.ja : message.en;
}

/** Installed-package rejection reasons carry a file path before the code. */
export function pluginRejectionMessage(reason: string, isJapanese: boolean): { message: string; path?: string } {
	const match = /^(.*):\s*([a-z0-9_]+)$/.exec(reason);
	const code = match?.[2] ?? reason;
	return { message: pluginProblemMessage(code, isJapanese), ...(match?.[1] ? { path: match[1] } : {}) };
}

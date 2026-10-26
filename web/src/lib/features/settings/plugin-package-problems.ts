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
	wrong_schema: { ja: 'schema は inku.plugin-package.v1 にします。', en: 'schema must be inku.plugin-package.v1.' },
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
	no_summary: { ja: '要約（summary_ja か summary_en）を書いてください。下絵が語を選ぶ時に読みます。', en: 'Write a summary (summary_ja or summary_en). Stage 1 reads it to choose the word.' },
	// The shared core's definition checks
	invalid_canonical_definition: { ja: '定義の形が正しくありません。', en: 'The definition is not well formed.' },
	unknown_json_field: { ja: '定義に知らない欄があります。', en: 'The definition has an unknown field.' },
	duplicate_qualified_name: { ja: '同じ名前（正式名か別名）の語が package の中に二つあります。', en: 'Two words in the package share a name or alias.' },
	unknown_semantic_id: { ja: '歳時記に無い語です（例: 色の pink）。PLUGIN.md §3.8 の一覧から選びます。', en: 'Not a Saijiki word (e.g. the color pink). Pick one from PLUGIN.md §3.8.' },
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

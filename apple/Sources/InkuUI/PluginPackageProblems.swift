import Foundation
import InkuHost

/// The problem descriptions mirror Web plugin-package-problems.ts; unknown codes remain visible.
enum PluginPackageProblems {
    private static let messages: [String: (String, String)] = [
        "invalid_json": ("JSON として読めません。", "The file is not valid JSON."),
        "package_too_large": ("ファイルが大きすぎます。", "The file is too large."),
        "not_an_object": ("{ } のオブジェクトでなければなりません。", "Must be an object ({ })."),
        "unknown_field": ("知らない欄です。綴りを確かめるか、欄を消してください。", "Unknown field. Check its spelling or remove it."),
        "wrong_schema": ("schema は inku.plugin-package.v1 にします。", "schema must be inku.plugin-package.v1."),
        "invalid_identifier": ("英字で始め、英数字・_・- だけで書きます。", "Start with a letter and use only letters, digits, _ and -."),
        "invalid_semantic_version": ("バージョンは 1.0.0 の形で書きます。", "Write the version as 1.0.0."),
        "not_a_string": ("文字列で書きます。", "Must be a string."),
        "not_a_list_of_strings": ("文字列の配列で書きます。", "Must be a list of strings."),
        "text_too_long": ("長すぎます。", "Too long."),
        "no_words": ("words に語が一つもありません。", "words has no words."),
        "too_many_words": ("語が多すぎます。", "Too many words."),
        "namespace_differs_from_package": ("定義の namespace が package の namespace と違います。", "The definition's namespace differs from the package's."),
        "id_differs_from_directory": ("置き場所のフォルダの名前と、ファイルの namespace.name が違います。", "The folder's name differs from the file's namespace.name."),
        "invalid_package_id": ("プラグインの id は namespace.name の形です。", "A plugin id has the form namespace.name."),
        "no_summary": ("要約（summary_ja か summary_en）を書いてください。下絵が語を選ぶ時に読みます。", "Write a summary (summary_ja or summary_en). Stage 1 reads it to choose the word."),
        "invalid_canonical_definition": ("定義の形が正しくありません。", "The definition is not well formed."),
        "unknown_json_field": ("定義に知らない欄があります。", "The definition has an unknown field."),
        "duplicate_qualified_name": ("同じ名前（正式名か別名）の語が package の中に二つあります。", "Two words in the package share a name or alias."),
        "unknown_semantic_id": ("歳時記に無い語です（例: 色の pink）。PLUGIN.md §3.8 の一覧から選びます。", "Not a Saijiki word (e.g. the color pink). Pick one from PLUGIN.md §3.8."),
        "unknown_semantic_category": ("category の綴りが違います。", "The category is misspelled."),
        "unknown_semantic_field": ("emit に無い欄の名前です。", "Not a field emit has."),
        "semantic_field_requires_matching_reference": ("欄と語の分類が合いません。", "The field and the word's category do not match."),
        "geometry_field_requires_exact_decimal": ("位置・寸法は exact_decimal で書きます。", "Write positions and sizes with exact_decimal."),
        "invalid_count_parameter": ("個数の引数の範囲・候補が決まりに合いません。", "The count parameter’s range or choices break the rules."),
        "invalid_repeat_count": ("repeat の count が整数でないか、maximum を超えます。", "repeat's count is not an integer or exceeds maximum."),
        "unbounded_repeat": ("repeat の maximum が 0 です。", "repeat's maximum is 0."),
        "undefined_parameter": ("宣言していない引数を読んでいます。", "Reads a parameter that is not declared."),
        "undefined_local": ("範囲の外の index・binding を読んでいます。", "Reads an index or binding outside its scope."),
        "undefined_anchor": ("relation の from・to が binding や anchor の名前と合いません。", "relation's from or to names no binding or anchor."),
        "invalid_alias": ("別名に使えない文字があります。", "The alias has characters it may not."),
        "duplicate_alias": ("別名が見出しや他の別名と重なります。", "The alias repeats the heading or another alias."),
        "component_cycle": ("部品が自分自身を呼んでいます。", "A component calls itself."),
        "name_taken": ("この名前は、もう入っている別のプラグインが使っています。", "Another installed plugin already uses this name."),
        "macro_binding_count_out_of_range": ("例文の個数が、定義が受ける範囲の外です。", "The example's count is outside the range the definition takes."),
        "macro_resolution_missing_lock": ("例文の語が見つかりません。名前の綴りか、定義の誤りを確かめてください。", "The example's word is not found. Check its spelling or the definition."),
        "compiler_diagnostics": ("例文が DDL として描けません。", "The example does not draw as DDL."),
        "example_draws_nothing": ("例文を描いても、何も描かれません。", "The example draws nothing."),
        "example_not_drawn": ("例文を描けませんでした。", "The example could not be drawn."),
        "not_a_png": ("PNG の画像ではありません。", "Not a PNG picture."),
        "image_too_large": ("画像が大きすぎます。", "The picture is too large."),
        "preview_needs_zip": ("絵（preview）は zip の中の PNG を名指します。JSON だけのファイルでは使えません。", "preview names a PNG inside a zip; a JSON file alone cannot have one."),
        "preview_not_found": ("zip の中に、この名前の PNG がありません。", "The zip has no PNG by this name."),
        "invalid_preview_path": ("絵の場所は、zip の中の場所で書きます（「..」や「/」で始まる場所は使えません）。", "Write the place inside the zip (not starting with \"/\" and without \"..\")."),
        "invalid_zip": ("zip として読めません。", "Not a readable zip."),
        "not_base64": ("ファイルを送れませんでした（base64 でない）。", "The file could not be sent (not base64)."),
        "archive_too_large": ("zip が大きすぎます。", "The zip is too large."),
        "too_many_archive_members": ("zip の中のファイルが多すぎます。", "The zip holds too many files."),
        "archive_without_package_json": ("zip の一番上に package.json がありません。", "The zip has no package.json at its top."),
        "not_utf8": ("package.json が UTF-8 ではありません。", "package.json is not UTF-8.")
    ]
    static func text(_ problem: ExactJSON, language: String) -> String {
        let code = problem["code"].string ?? ""
        let message = messages[code].map { language == "en" ? $0.1 : $0.0 } ?? code
        let detail = problem["detail"].string ?? ""
        let path = problem["path"].string ?? ""
        return (path.isEmpty ? "" : path + " ") + message + (detail.isEmpty ? "" : "（\(detail)）")
    }
}

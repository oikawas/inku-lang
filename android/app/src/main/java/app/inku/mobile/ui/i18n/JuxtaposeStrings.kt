package app.inku.mobile.ui.i18n

/** Text of the work-actions entry and dialog for 取り合わせ, as Web's `juxtapose*` keys. */
internal data class JuxtaposeStrings(
    val action: String,
    val title: String,
    val help: String,
    val description: String,
    val model: String,
    val ask: String,
    val askAgain: String,
    val asking: (String) -> String,
    val choices: (Int) -> String,
    val sentenceLabel: String,
    val reasonLabel: String,
    val joined: String,
    val draw: String,
    val cancel: String,
    val stop: String,
    val tooFew: String,
    val unusable: (String) -> String,
    val failed: String,
    /** Web `descriptionLockedReason`; the way back to the description is this menu's entry. */
    val heldReason: (String) -> String,
)

internal fun juxtaposeStrings(language: UiLanguage): JuxtaposeStrings =
    if (language.isEnglish) juxtaposeEn else juxtaposeJa

private val juxtaposeJa = JuxtaposeStrings(
    action = "取り合わせ",
    title = "取り合わせ",
    help = "ほかの作品の記述から、AIが一文を4つ選びます。1つを選ぶと、今の記述の後ろに足して、選択した作品の子を描画します。",
    description = "記述",
    model = "一文を選ぶVisionモデル",
    ask = "一文を選ばせる",
    askAgain = "選び直す",
    asking = { elapsed -> "一文を選んでいます… $elapsed" },
    choices = { count -> "${count}文から選んだ4つ" },
    sentenceLabel = "選択文",
    reasonLabel = "選択理由",
    joined = "足した後の記述",
    draw = "この記述で描く",
    cancel = "キャンセル",
    stop = "停止",
    tooFew = "ほかの作品の記述が足りず、4つの一文を選べません。",
    unusable = { detail -> "AIの選んだ一文を使えませんでした（$detail）" },
    failed = "一文を選べませんでした。",
    heldReason = { entry -> "DDLを編集した作品です。記述から描き直すとDDLの編集が失われるため、止めています。記述から作り直すときは、このメニューの「$entry」を使います。" },
)

private val juxtaposeEn = JuxtaposeStrings(
    action = "Juxtapose",
    title = "Juxtapose",
    help = "The AI picks four sentences from the descriptions of your other works. Choose one to add after this description and draw a child of the selected work.",
    description = "Description",
    model = "Vision model that picks the sentences",
    ask = "Pick sentences",
    askAgain = "Pick again",
    asking = { elapsed -> "Picking sentences… $elapsed" },
    choices = { count -> "Four picked from $count sentences" },
    sentenceLabel = "Sentence",
    reasonLabel = "Reason",
    joined = "The description with the sentence",
    draw = "Draw with this description",
    cancel = "Cancel",
    stop = "Stop",
    tooFew = "Your other works do not have enough sentences to pick four from.",
    unusable = { detail -> "The model's choices could not be used ($detail)" },
    failed = "The sentences could not be picked.",
    heldReason = { entry -> "This work's DDL was edited. Drawing it from the description would lose the edits, so this is not offered. To start again from the description, use $entry in this menu." },
)

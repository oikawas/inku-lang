package app.inku.mobile.ui.i18n

/** Web aiRefine* wording, with the app named as the host of the run. */
internal class AiRefineStrings(private val english: Boolean) {
    private val strings = if (!english) mapOf(
        "aiRefineTitle" to "AIに自律推敲させる",
        "aiRefineHelp" to "アプリが法則の手と取り合わせの手を打ち、親と見て分かるほど違う子だけを次の親にします。画面を閉じても続きます。",
        "aiRefineHeldNote" to "DDLを編集した作品です。記述に一文を足せないので、取り合わせの手は打てません。法則の手で進めます。",
        "aiRefineModel" to "推敲に使うモデル（一文を選び、子を描く）",
        "aiRefineDirectionLabel" to "方向性（法則の手に渡す）",
        "aiRefineDirectionPlaceholder" to "例：華やかで、かつ、涼しげに",
        "aiRefineMovesLabel" to "手数", "aiRefineKindsLabel" to "使う手",
        "aiRefineKindLaws" to "法則の手", "aiRefineKindJuxtaposition" to "取り合わせの手",
        "aiRefineKindsError" to "少なくとも1つの手を選んでください。",
        "aiRefineStartButton" to "推敲を開始", "aiRefineGoesOn" to "この画面を閉じても、推敲はアプリで続きます。",
        "aiRefineStop" to "止める", "aiRefineStopping" to "止めています…",
        "aiRefineTaking" to "%turn%手目：%kind%を打っています…", "aiRefineTurn" to "%turn%手目",
        "aiRefineOutcomeKept" to "残した", "aiRefineOutcomeNotVisible" to "差が小さい",
        "aiRefineOutcomeUnavailable" to "打てない", "aiRefineOutcomeFailed" to "使えなかった",
        "aiRefineShare" to "差 %percent%%",
        "aiRefineEndedMovesDone" to "手数を打ち終えました。",
        "aiRefineEndedNothingAvailable" to "どちらの手も打てないので止まりました。",
        "aiRefineEndedStalled" to "2手番続けて、差の見える子が出なかったので止まりました。",
        "aiRefineEndedStopped" to "止めました。", "aiRefineEndedInterrupted" to "アプリの再起動で途切れました。",
        "aiRefineEndedFailed" to "エラーで止まりました。", "aiRefineOpenLast" to "最後に残った子を開く",
        "aiRefineNoneKept" to "残った子はありません。",
    ) else mapOf(
        "aiRefineTitle" to "Autonomous refinement",
        "aiRefineHelp" to "The app takes laws moves and juxtaposition moves, and keeps a child as the next parent only when it looks different from its parent. It goes on after this window is closed.",
        "aiRefineHeldNote" to "This work's DDL was edited. No sentence can be added to its description, so the refinement takes laws moves only.",
        "aiRefineModel" to "Model for the refinement (chooses the sentence, draws the children)",
        "aiRefineDirectionLabel" to "Direction (for the laws move)",
        "aiRefineDirectionPlaceholder" to "e.g., vibrant and cool",
        "aiRefineMovesLabel" to "Moves", "aiRefineKindsLabel" to "Moves to take",
        "aiRefineKindLaws" to "Laws move", "aiRefineKindJuxtaposition" to "Juxtaposition move",
        "aiRefineKindsError" to "Choose at least one move.",
        "aiRefineStartButton" to "Start refining", "aiRefineGoesOn" to "The refinement goes on in the app after this window is closed.",
        "aiRefineStop" to "Stop", "aiRefineStopping" to "Stopping…",
        "aiRefineTaking" to "Move %turn%: taking the %kind%…", "aiRefineTurn" to "Move %turn%",
        "aiRefineOutcomeKept" to "Kept", "aiRefineOutcomeNotVisible" to "Too little change",
        "aiRefineOutcomeUnavailable" to "Could not start", "aiRefineOutcomeFailed" to "Not usable",
        "aiRefineShare" to "%percent%% changed",
        "aiRefineEndedMovesDone" to "All the moves were taken.",
        "aiRefineEndedNothingAvailable" to "Stopped: neither move could start.",
        "aiRefineEndedStalled" to "Stopped: two turns in a row kept no visibly different child.",
        "aiRefineEndedStopped" to "Stopped.", "aiRefineEndedInterrupted" to "Cut off when the app restarted.",
        "aiRefineEndedFailed" to "Stopped by an error.", "aiRefineOpenLast" to "Open the last kept child",
        "aiRefineNoneKept" to "No child was kept.",
    )
    operator fun get(key: String): String = strings.getValue(key)
    fun kind(kind: String): String = get(if (kind == "laws") "aiRefineKindLaws" else "aiRefineKindJuxtaposition")
    fun turn(turn: Int): String = get("aiRefineTurn").replace("%turn%", turn.toString())
    fun taking(turn: Int, kind: String): String = get("aiRefineTaking").replace("%turn%", turn.toString())
        .replace("%kind%", kind(kind).let { if (english) it.lowercase() else it })
    fun share(share: Double): String = get("aiRefineShare").replace("%percent%", String.format(java.util.Locale.ROOT, "%.1f", share * 100))
    fun outcome(outcome: String): String = get(when (outcome) {
        "kept" -> "aiRefineOutcomeKept"; "not_visible" -> "aiRefineOutcomeNotVisible"
        "unavailable" -> "aiRefineOutcomeUnavailable"; else -> "aiRefineOutcomeFailed"
    })
    fun ended(reason: String?): String = get(when (reason) {
        "moves_done" -> "aiRefineEndedMovesDone"; "nothing_available" -> "aiRefineEndedNothingAvailable"
        "stalled" -> "aiRefineEndedStalled"; "stopped" -> "aiRefineEndedStopped"
        "interrupted" -> "aiRefineEndedInterrupted"; else -> "aiRefineEndedFailed"
    })
}

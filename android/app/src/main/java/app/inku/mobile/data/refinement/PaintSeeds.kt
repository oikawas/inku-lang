package app.inku.mobile.data.refinement

import app.inku.mobile.data.db.HistoryItemEntity
import java.security.SecureRandom

/**
 * What a caller asks a drawing to be made with.
 *
 * The render, composition, and interpretation seeds are the active request
 * values; [seedText] supplies the words from which touch derives its render
 * seed. Every one of them is `null` by default, which is the server's
 * `None`: a caller that says nothing leaves every decision where it was.
 *
 * They travel together because every drawing entry point accepts the same
 * values, and a partial set at one of them would be a
 * silent sender.
 */
data class PaintSeeds(
    val renderSeed: Long? = null,
    val compositionSeed: Long? = null,
    val interpretationSeed: String? = null,
    val seedText: String? = null,
) {
    companion object {
        /**
         * What a work was made with, read back off its history row.
         *
         * A refinement that keeps something fixed keeps *this*, not whatever the
         * describe screen is set to. A work that was simply drawn says only what
         * it was performed with, so a refinement of it inherits a touch and
         * nothing else -- which is the right answer, not a missing one.
         */
        fun of(item: HistoryItemEntity): PaintSeeds = PaintSeeds(
            renderSeed = item.renderSeed?.let { parseSeed(it) },
            compositionSeed = item.compositionSeed?.let { parseSeed(it) },
            interpretationSeed = item.interpretationSeed,
            seedText = item.seedText,
        )

        /**
         * The stored form is text, and a touch seed can be larger than
         * `Long.MAX_VALUE`, so the unsigned reading is tried first -- the same
         * 64 bits come back, and the signed parse would have thrown.
         */
        private fun parseSeed(value: String): Long? = runCatching {
            java.lang.Long.parseUnsignedLong(value.trim())
        }.getOrElse { value.trim().toLongOrNull() }
    }
}

/**
 * Where new seeds come from.
 *
 * The device allocates render and composition seeds from a cryptographic
 * source, and interpretation seeds as UUIDs. Retired variation seeds are
 * retained only in saved history, and are never allocated or inherited here.
 */
object SeedFactory {

    private val random = SecureRandom()

    /** `secrets.randbits(53)` -- a JavaScript-safe integer. */
    fun newRenderSeed(): Long = random.nextLong() ushr 11

    /** The same, for the composition seed web allocates with `createSafeIntegerSeed`. */
    fun newCompositionSeed(excluded: Set<Long> = emptySet()): Long {
        repeat(32) {
            val seed = newRenderSeed()
            if (seed !in excluded) return seed
        }
        error("Could not allocate a unique seed")
    }

    /** `createInterpretationSeed` -- an opaque uuid4, never read as a number. */
    fun newInterpretationSeed(): String = java.util.UUID.randomUUID().toString()
}

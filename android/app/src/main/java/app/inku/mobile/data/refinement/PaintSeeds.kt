package app.inku.mobile.data.refinement

import app.inku.mobile.data.db.HistoryItemEntity
import java.security.MessageDigest
import java.security.SecureRandom

/**
 * What a caller asks a drawing to be made with.
 *
 * The five names and types are the server's request body
 * (`api_core/models.py:14-15`, `:42-45`); [seedText] is the sixth field the
 * touch refinement sends (`render.py:442`), from which the server derives the
 * render seed. Every one of them is `null` by default, which is the server's
 * `None`: a caller that says nothing leaves every decision where it was.
 *
 * They travel together rather than as six parameters because every entry point
 * in the repository takes all six, and a partial set at one of them would be a
 * silent sender.
 */
data class PaintSeeds(
    val renderSeed: Long? = null,
    val compositionSeed: Long? = null,
    val interpretationSeed: String? = null,
    val variationAmplitude: String? = null,
    val variationSeed: Long? = null,
    val seedText: String? = null,
) {
    companion object {
        /**
         * What a work was made with, read back off its history row.
         *
         * A refinement that keeps something fixed keeps *this*, not whatever the
         * describe screen is set to. Rows saved before the columns existed
         * report `null` for all of them, which is the same answer the server
         * gives for its own older rows.
         */
        fun of(item: HistoryItemEntity): PaintSeeds = PaintSeeds(
            renderSeed = item.renderSeed?.let { parseSeed(it) },
            compositionSeed = item.compositionSeed?.let { parseSeed(it) },
            interpretationSeed = item.interpretationSeed,
            variationAmplitude = item.variationAmplitude,
            variationSeed = item.variationSeed?.let { parseSeed(it) },
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
 * On the server this is two pieces: `new_render_seed()` (`renderer.py:635`) and
 * the `/api/variation/seeds` endpoint (`render.py:1288`), which exists so that
 * "seed 空間の管理と重複回避を UI に持ち込まない". There is no server here, so the
 * device allocates; what is ported is how the numbers are made, not who makes
 * them. All three use a cryptographic source, as `secrets` does.
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

    /**
     * `secrets.randbelow(2**31 - 1) + 1`, with the endpoint's own rule that the
     * seeds it hands back in one call are distinct.
     */
    fun newVariationSeeds(count: Int): List<Long> {
        val seeds = LinkedHashSet<Long>()
        while (seeds.size < count) {
            seeds.add(1L + (random.nextLong().toULong() % 2147483646UL).toLong())
        }
        return seeds.toList()
    }

    /** `createInterpretationSeed` -- an opaque uuid4, never read as a number. */
    fun newInterpretationSeed(): String = java.util.UUID.randomUUID().toString()

    /**
     * `_render_seed_from_text` (`rendering.py:324`): the first eight bytes of the
     * digest, big-endian, unsigned. The same words always give the same touch,
     * which is why the touch refinement can only offer one candidate.
     */
    fun renderSeedFromText(seedText: String): Long? {
        val normalized = seedText.trim()
        if (normalized.isEmpty()) return null
        val digest = MessageDigest.getInstance("SHA-256").digest(normalized.toByteArray(Charsets.UTF_8))
        var seed = 0L
        for (index in 0 until 8) {
            seed = (seed shl 8) or (digest[index].toLong() and 0xffL)
        }
        return seed
    }
}

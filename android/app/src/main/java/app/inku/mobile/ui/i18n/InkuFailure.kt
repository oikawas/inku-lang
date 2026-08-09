package app.inku.mobile.ui.i18n

/**
 * A failure whose wording is chosen where it is SHOWN, not where it is thrown.
 *
 * The data and llm layers run with no interface language in hand -- they are
 * below the composition and below the ViewModel -- so a message written there
 * would be fixed in one language at the moment the thing went wrong. The screen
 * puts `error.message` straight into the status line in thirteen places, so
 * those messages are interface wording rather than developer text.
 *
 * The web solves the same problem the same way round: the server answers with a
 * stable machine detail (`'render capacity is full'`) and the page maps it to
 * the reader's language (`+page.svelte:787-788`). Carrying a lambda instead of a
 * key does that without a registry the compiler cannot check -- a renamed entry
 * is a compile error rather than a lookup that quietly returns the key.
 *
 * [message] holds the Japanese so that logs, crash reports and any caller that
 * only knows `Throwable.message` keep reading what they read before.
 */
class InkuFailure(val text: (InkuStrings) -> String) : RuntimeException(text(InkuStringsJa))

/** Throws an [InkuFailure]; the shape of `error(...)`, with the language deferred. */
fun inkuError(text: (InkuStrings) -> String): Nothing = throw InkuFailure(text)

/**
 * What to show for [error] in [strings].
 *
 * A failure that is not an [InkuFailure] has no translation to offer -- it came
 * from the platform, a parser, or the network -- so its own message stands, and
 * [fallback] covers the ones that carry none.
 */
fun messageFor(error: Throwable, strings: InkuStrings, fallback: String): String =
    when (error) {
        is InkuFailure -> error.text(strings)
        else -> error.message ?: fallback
    }

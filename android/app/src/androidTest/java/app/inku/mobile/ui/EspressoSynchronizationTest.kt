package app.inku.mobile.ui

import androidx.test.espresso.Espresso
import androidx.test.espresso.IdlingRegistry
import androidx.test.espresso.IdlingResource
import androidx.test.ext.junit.runners.AndroidJUnit4
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicBoolean

/**
 * `Espresso.onIdle()` waits for what is registered with it.
 *
 * Compose's `waitForIdle()` reaches Espresso's idling machinery. Until I-064
 * this project replaced Espresso with a stub whose `onIdle()` returned at once,
 * because Espresso 3.6.1 died on API 37; every test that waited then waited on
 * nothing. This proves the real one is back: the resource only turns idle after
 * Espresso has asked it, so `onIdle()` can return after that only by asking and
 * then waiting for the callback.
 */
@RunWith(AndroidJUnit4::class)
class EspressoSynchronizationTest {

    @Test
    fun onIdleReturnsOnlyAfterARegisteredResourceTurnsIdle() {
        val resource = OneShotResource()
        val registry = IdlingRegistry.getInstance()
        registry.register(resource)
        val idler = Thread {
            try {
                if (resource.asked.await(ASK_TIMEOUT_SECONDS, TimeUnit.SECONDS)) resource.becomeIdle()
            } catch (_: InterruptedException) {
                // The test is over; an uncaught exception here would crash the runner.
            }
        }.apply {
            isDaemon = true
            start()
        }
        try {
            Espresso.onIdle()
            assertEquals("onIdle returned without asking the resource", 0L, resource.asked.count)
            assertTrue("onIdle returned before the resource turned idle", resource.idle.get())
        } finally {
            registry.unregister(resource)
            idler.interrupt()
        }
    }

    /** Busy until [becomeIdle]; [asked] opens the first time Espresso checks it. */
    private class OneShotResource : IdlingResource {
        val asked = CountDownLatch(1)
        val idle = AtomicBoolean(false)

        @Volatile
        private var callback: IdlingResource.ResourceCallback? = null

        override fun getName(): String = "EspressoSynchronizationTest.OneShotResource"

        override fun isIdleNow(): Boolean {
            asked.countDown()
            return idle.get()
        }

        override fun registerIdleTransitionCallback(callback: IdlingResource.ResourceCallback) {
            this.callback = callback
        }

        fun becomeIdle() {
            idle.set(true)
            callback?.onTransitionToIdle()
        }
    }

    private companion object {
        const val ASK_TIMEOUT_SECONDS = 10L
    }
}

package app.inku.mobile.pipeline

import app.inku.mobile.data.db.SharedPipelinePersistenceTest
import org.junit.runner.RunWith
import org.junit.runners.Suite

/** One safe-runner entrypoint for the two Step 14 Android device flows. */
@RunWith(Suite::class)
@Suite.SuiteClasses(
    AndroidSharedPipelineTest::class,
    SharedPipelinePersistenceTest::class,
)
class SharedPipelineDeviceAcceptanceTest

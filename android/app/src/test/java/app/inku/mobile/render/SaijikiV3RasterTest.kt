package app.inku.mobile.render

import java.io.File
import java.security.MessageDigest
import org.junit.Assert.*
import org.junit.Test

class SaijikiV3RasterTest {
    @Test fun deviceReferenceDigestsMatchTheRebuiltHostJni() {
        val root = generateSequence(File(".").canonicalFile) { it.parentFile }.first { File(it, "persistence/contract.json").isFile }
        val cases = listOf(
            "render-engine-41/A-pen-circle.svg" to "89f77c560b97e360ab740f1045da304c63df9ee55f44b111599f2484ef3d29a2",
            "render-engine-41/C-filter-display-pencil.svg" to "165e04ac91ff11bb05fcb99953d11100c9bdb63c9a2bf7e3144485cf130fa780",
            "render-engine-41/D-canvas-wide-region-single.svg" to "2912d5b6746b74b5f60b57d07c97b1b770b1443f33e18e9785b2037050eb88fe",
            "render-engine-21/G-scatter-edge.svg" to "1bbb4da477413c3f65f1732cff3e03afaf3f5417736ea929f2bbd8c3de223368",
        )
        for ((path, old) in cases) {
            val result = NativeRenderBridge.rasterize(root.resolve("server/reference/$path").readText(), "{\"target_width\":64,\"target_height\":64}")
            val digest = MessageDigest.getInstance("SHA-256").digest(result.pixels).joinToString("") { "%02x".format(it) }
            assertEquals(path, old, digest)
        }
    }
}

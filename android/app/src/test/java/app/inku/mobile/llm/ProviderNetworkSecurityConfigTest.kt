package app.inku.mobile.llm

import java.io.File
import javax.xml.parsers.DocumentBuilderFactory
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import org.w3c.dom.Element

class ProviderNetworkSecurityConfigTest {
    @Test
    fun manifestAllowsCleartextOnlyForExactLoopbackDestinations() {
        val manifest = projectFile("src/main/AndroidManifest.xml")
        assertTrue(
            manifest.readText().contains("android:networkSecurityConfig=\"@xml/network_security_config\""),
        )

        val config = projectFile("src/main/res/xml/network_security_config.xml")
        val text = config.readText()
        assertFalse(text.contains("<base-config cleartextTrafficPermitted=\"true\""))
        val document = DocumentBuilderFactory.newInstance().newDocumentBuilder().parse(config)
        val baseConfig = document.getElementsByTagName("base-config").item(0) as Element
        assertEquals("false", baseConfig.getAttribute("cleartextTrafficPermitted"))
        val domainConfig = document.getElementsByTagName("domain-config").item(0) as Element
        assertEquals("true", domainConfig.getAttribute("cleartextTrafficPermitted"))
        val domains = document.getElementsByTagName("domain")
        val values = (0 until domains.length).map { domains.item(it).textContent.trim() }.toSet()
        assertEquals(setOf("localhost", "127.0.0.1", "[::1]"), values)
    }

    private fun projectFile(relativePath: String): File {
        val direct = File(relativePath)
        return if (direct.isFile) direct else File("app", relativePath)
    }
}

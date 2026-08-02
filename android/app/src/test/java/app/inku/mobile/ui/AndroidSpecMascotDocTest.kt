package app.inku.mobile.ui

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

class AndroidSpecMascotDocTest {

    @Test
    fun t9_androidSpecDocumentationContainsNoKiwiAndMentionsIncuAndYuragi() {
        var jaSpec = File("ANDROID_SPEC.ja.md")
        if (!jaSpec.exists()) {
            jaSpec = File("../ANDROID_SPEC.ja.md")
        }
        var enSpec = File("ANDROID_SPEC.md")
        if (!enSpec.exists()) {
            enSpec = File("../ANDROID_SPEC.md")
        }

        assertTrue("ANDROID_SPEC.ja.md must exist (searched in . and ..)", jaSpec.exists())
        assertTrue("ANDROID_SPEC.md must exist (searched in . and ..)", enSpec.exists())

        val jaContent = jaSpec.readText()
        val enContent = enSpec.readText()

        assertFalse("ANDROID_SPEC.ja.md should not mention KiwiMascot", jaContent.contains("KiwiMascot"))
        assertFalse("ANDROID_SPEC.md should not mention KiwiMascot", enContent.contains("KiwiMascot"))

        assertTrue("ANDROID_SPEC.ja.md should mention IncuMascot", jaContent.contains("IncuMascot"))
        assertTrue("ANDROID_SPEC.ja.md should mention YuragiMascot", jaContent.contains("YuragiMascot"))

        assertTrue("ANDROID_SPEC.md should mention IncuMascot", enContent.contains("IncuMascot"))
        assertTrue("ANDROID_SPEC.md should mention YuragiMascot", enContent.contains("YuragiMascot"))
    }
}

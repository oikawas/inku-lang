package app.inku.mobile.llm

import app.inku.mobile.data.db.ProviderSettingEntity
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertSame
import org.junit.Test

class RoutingStageDefaultsTest {
    private val local = provider("local-litert-lm")
    private val cloud = provider("gemini", "shared")
    private val other = provider("ollama", "shared")
    private val providers = listOf(local, cloud, other)

    @Test
    fun stageOneCompositionAndStageTwoUseTheirConfiguredProviders() {
        val selection = JSONObject().put("stage1_provider", "gemini").put("stage2_provider", "ollama")
        for (action in listOf(null, "generate_normalized_ddl", "generate_sketch", "read_composition", REFINEMENT_VISION_ACTION)) {
            val fallback = RoutingModelProvider.configuredStageProvider(providers, selection, action)
            assertEquals("gemini", fallback)
            assertSame(cloud, RoutingModelProvider.resolveProviderForRouting(providers, "unknown", fallback))
        }
        val fallback = RoutingModelProvider.configuredStageProvider(providers, selection, "complete_visible_ddl_holes")
        assertEquals("ollama", fallback)
        assertSame(other, RoutingModelProvider.resolveProviderForRouting(providers, "shared", fallback))
    }

    @Test
    fun existingLocalDefaultAndFirstRunRemainLocal() {
        for (selection in listOf(null, JSONObject().put("stage1_model", "local-litert-lm:gemma-4-e2b")
            .put("stage2_model", "local-litert-lm:gemma-4-e2b"))) {
            for (action in listOf("generate_normalized_ddl", "complete_visible_ddl_holes")) {
                val fallback = RoutingModelProvider.configuredStageProvider(providers, selection, action)
                assertEquals("local-litert-lm", fallback)
                assertSame(local, RoutingModelProvider.resolveProviderForRouting(providers, "unknown", fallback))
            }
        }
    }

    @Test
    fun oldQualifiedSelectionsSupplyEachStageWithoutMigration() {
        val selection = JSONObject().put("stage1_model", "gemini:first").put("stage2_model", "ollama:second")
        assertEquals("gemini", RoutingModelProvider.configuredStageProvider(providers, selection, "read_composition"))
        assertEquals("ollama", RoutingModelProvider.configuredStageProvider(providers, selection, "complete_visible_ddl_holes"))
    }

    @Test
    fun explicitAndUniqueOwnerWinOverStageDefault() {
        assertSame(other, RoutingModelProvider.resolveProviderForRouting(providers, "ollama:qwen:4b", "gemini"))
        val unique = provider("single", "only")
        assertSame(unique, RoutingModelProvider.resolveProviderForRouting(providers + unique, "only", "gemini"))
        assertSame(cloud, RoutingModelProvider.resolveProviderForRouting(providers, "shared", "gemini"))
        val plan = provider("chatgpt", "plan-only")
        assertSame(plan, RoutingModelProvider.resolveProviderForRouting(providers + plan, "plan-only", "gemini"))
        assertSame(plan, RoutingModelProvider.resolveProviderForRouting(providers + plan, "unknown", "chatgpt"))
    }

    @Test
    fun missingOrDisabledDefaultNeverSilentlyBecomesLocal() {
        assertNull(RoutingModelProvider.resolveProviderForRouting(providers, "unknown", "removed"))
        val disabled = cloud.copy(isEnabled = false)
        val selected = RoutingModelProvider.resolveProviderForRouting(listOf(local, disabled), "unknown", "gemini")
        assertSame(disabled, selected)
        assertEquals(false, RoutingModelProvider.canGenerateWith(disabled))
        val unresolvable = JSONObject().put("stage1_model", "unowned:tag")
        assertNull(RoutingModelProvider.configuredStageProvider(providers, unresolvable, "read_composition"))
    }

    private fun provider(id: String, model: String? = null) = ProviderSettingEntity(
        providerId = id, displayName = id, kind = "openai-compatible", baseUrl = null,
        encryptedApiKey = null, publishedModelsJson = if (model == null) "[]" else "[\"$model\"]",
        isEnabled = true, isDefaultLocal = id == "local-litert-lm", updatedAt = 0,
    )
}

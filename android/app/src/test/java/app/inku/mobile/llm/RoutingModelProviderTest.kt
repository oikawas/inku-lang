package app.inku.mobile.llm

import app.inku.mobile.data.db.ProviderSettingEntity
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertSame
import org.junit.Test

class RoutingModelProviderTest {
    @Test
    fun `an enabled provider named by an explicit prefix wins`() {
        val local = provider("local-litert-lm", isDefaultLocal = true)
        val ollama = provider("ollama", models = "[\"qwen3.5:4b-q4_K_M\"]")

        assertSame(ollama, RoutingModelProvider.resolveProviderForRouting(listOf(local, ollama), "ollama:qwen3.5:4b-q4_K_M"))
    }

    @Test
    fun `a sole enabled published owner wins for an unqualified id`() {
        val local = provider("local-litert-lm", isDefaultLocal = true)
        val nvidia = provider("nvidia", models = "[\"google/gemma-4-31b-it\"]")

        assertSame(nvidia, RoutingModelProvider.resolveProviderForRouting(listOf(local, nvidia), "google/gemma-4-31b-it"))
    }

    @Test
    fun `ambiguous published owners resolve to default local regardless of input order`() {
        val local = provider("local-litert-lm", isDefaultLocal = true)
        val openai = provider("openai", models = "[\"shared-model\"]")
        val ollama = provider("ollama", models = "[\"shared-model\"]")

        assertSame(local, RoutingModelProvider.resolveProviderForRouting(listOf(openai, ollama, local), "shared-model"))
        assertSame(local, RoutingModelProvider.resolveProviderForRouting(listOf(local, ollama, openai), "shared-model"))
    }

    @Test
    fun `unknown ids resolve to default local without altering the model id`() {
        val local = provider("local-litert-lm", isDefaultLocal = true)
        val modelId = "unknown:qwen3.5:4b-q4_K_M"

        assertSame(local, RoutingModelProvider.resolveProviderForRouting(listOf(local), modelId))
        assertEquals(modelId, OpenAiCompatibleProvider.modelForRequest("local-litert-lm", modelId))
    }

    @Test
    fun `disabled providers are not owners but an explicit disabled provider keeps its identity`() {
        val local = provider("local-litert-lm", isDefaultLocal = true)
        val disabled = provider("ollama", models = "[\"qwen3.5:4b-q4_K_M\"]", isEnabled = false)

        assertSame(local, RoutingModelProvider.resolveProviderForRouting(listOf(disabled, local), "qwen3.5:4b-q4_K_M"))
        assertSame(disabled, RoutingModelProvider.resolveProviderForRouting(listOf(local, disabled), "ollama:qwen3.5:4b-q4_K_M"))
        assertEquals(false, RoutingModelProvider.canGenerateWith(disabled))
    }

    @Test
    fun `an internal colon is not a provider prefix and resolves by exact ownership or default`() {
        val local = provider("local-litert-lm", isDefaultLocal = true)
        val ollama = provider("ollama", models = "[\"qwen3.5:4b-q4_K_M\"]")

        assertSame(ollama, RoutingModelProvider.resolveProviderForRouting(listOf(local, ollama), "qwen3.5:4b-q4_K_M"))
        assertSame(local, RoutingModelProvider.resolveProviderForRouting(listOf(local), "qwen3.5:4b-q4_K_M"))
    }

    @Test
    fun `no default local means no provider is guessed`() {
        val openai = provider("openai")
        val ollama = provider("ollama")

        assertNull(RoutingModelProvider.resolveProviderForRouting(listOf(openai, ollama), "unknown-model"))
    }

    @Test
    fun `openai compatible requests remove only their own prefix`() {
        assertEquals(
            "qwen3.5:4b-q4_K_M",
            OpenAiCompatibleProvider.modelForRequest("ollama", "ollama:qwen3.5:4b-q4_K_M"),
        )
        assertEquals(
            "nvidia:qwen3.5:4b-q4_K_M",
            OpenAiCompatibleProvider.modelForRequest("ollama", "nvidia:qwen3.5:4b-q4_K_M"),
        )
    }

    private fun provider(
        providerId: String,
        models: String = "[]",
        isEnabled: Boolean = true,
        isDefaultLocal: Boolean = false,
    ) = ProviderSettingEntity(
        providerId = providerId,
        displayName = providerId,
        kind = "openai-compatible",
        baseUrl = null,
        encryptedApiKey = null,
        publishedModelsJson = models,
        isEnabled = isEnabled,
        isDefaultLocal = isDefaultLocal,
        updatedAt = 0,
    )
}

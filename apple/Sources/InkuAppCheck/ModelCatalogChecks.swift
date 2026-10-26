import Foundation
import InkuHost
import InkuUI

@MainActor func runModelCatalogChecks(casesURL: URL) async throws {
    // The old two-flag selector missed four labels, metadata and ChatGPT evaluations.
    // Exercise the shared cases with the real Host resolver and the generated v2 resource.
    let data = try Data(contentsOf: casesURL)
    guard let fixture = try JSONSerialization.jsonObject(with: data) as? [String: Any],
          fixture["schema"] as? String == "inku.model-catalog-cases.v1",
          let cases = fixture["cases"] as? [[String: Any]], cases.count == 15 else {
        throw CheckFailure.message("Shared model catalog cases unavailable")
    }
    for item in cases {
        guard let record = item["model"] as? [String: Any],
              let expectedLabels = item["labels"] as? [String],
              let expectedPublishable = item["publishable"] as? Bool else {
            throw CheckFailure.message("Shared model catalog case malformed")
        }
        let model = try ModelGuidanceCatalog.modelSettings(recordData: JSONSerialization.data(withJSONObject: record))
        guard model.resolvedLabels.map(\.id) == expectedLabels,
              model.modelFold == item["fold"] as? String,
              model.isSelectable == expectedPublishable else {
            throw CheckFailure.message("Model catalog rules disagree: \(item["name"] as? String ?? "unnamed")")
        }
    }

    let serverDirectory = casesURL.deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
    let sourceURL = serverDirectory.appendingPathComponent("src/inku_server/model_catalog.json")
    let source = try JSONSerialization.jsonObject(with: Data(contentsOf: sourceURL)) as? NSDictionary
    let manifest = try JSONSerialization.jsonObject(with: ModelGuidanceCatalog.bundledManifestData()) as? [String: Any]
    guard let source, let exported = manifest?["model_catalog"] as? NSDictionary,
          source.isEqual(exported), manifest?["model_guidance"] == nil else {
        throw CheckFailure.message("Generated v2 catalog differs from canonical source or retains v1 guidance")
    }
    let catalog = try ModelGuidanceCatalog.loadBundled()
    guard catalog.labelDefinitions == ModelCatalogLabels.definitions else {
        throw CheckFailure.message("Host and UI label tables differ")
    }
    let emptyUnsupported = try ModelGuidanceCatalog.modelSettings(recordData: Data(#"{"unsupported_purposes":[]}"#.utf8))
    let nullMeasurement = try ModelGuidanceCatalog.modelSettings(recordData: Data(#"{"speed_llm_seconds":null}"#.utf8))
    guard emptyUnsupported.resolvedLabels.isEmpty, nullMeasurement.resolvedLabels.isEmpty else {
        throw CheckFailure.message("An empty or null measurement key became unmeasured")
    }

    let endpoint = URL(string: "http://127.0.0.1:1/v1")!
    guard let sourceProviders = source["providers"] as? [String: Any],
          let sourceChatGPT = sourceProviders["chatgpt"] as? [String: Any],
          let chatGPTRecords = sourceChatGPT["models"] as? [[String: Any]],
          let measuredPlanRecord = chatGPTRecords.first(where: { $0["recommendation_vision"] != nil }),
          let sourceCloud = sourceProviders["ollama-cloud"] as? [String: Any],
          let cloudRecords = sourceCloud["models"] as? [[String: Any]],
          let paidRecord = cloudRecords.first(where: { ($0["labels"] as? [String])?.contains("subscription") == true }),
          let paidID = paidRecord["id"] as? String else {
        throw CheckFailure.message("Canonical measured ChatGPT or subscription records unavailable")
    }
    let expectedPlan = try ModelGuidanceCatalog.modelSettings(recordData: JSONSerialization.data(withJSONObject: measuredPlanRecord))
    let saved = ProviderModelSettings(id: expectedPlan.id, label: "My selected plan model", purposes: ["vision"],
                                      recommendationLLM: 1, labels: ["legacy", "not_supported"])
    let plan = ProviderSettings(id: "chatgpt", kind: .chatGPTPlan, baseURL: endpoint,
                                requiresAPIKey: false, models: [saved], enabledModels: [saved.id: false])
    let updated = catalog.registeredModelSettings(for: plan)
    guard updated.count == 1, let chatGPT = updated.first,
          chatGPT.label == saved.label, chatGPT.purposes == saved.purposes,
          chatGPT.recommendationLLM == expectedPlan.recommendationLLM,
          chatGPT.recommendationVision == expectedPlan.recommendationVision,
          chatGPT.speedLLMSeconds == expectedPlan.speedLLMSeconds, chatGPT.speedVisionSeconds == expectedPlan.speedVisionSeconds,
          chatGPT.costUSDLLM == expectedPlan.costUSDLLM, chatGPT.costUSDVision == expectedPlan.costUSDVision,
          chatGPT.commentJA == expectedPlan.commentJA, chatGPT.commentEN == expectedPlan.commentEN,
          chatGPT.labels == expectedPlan.labels,
          catalog.registeredModelSettings(for: .personalPlan).isEmpty,
          catalog.registeredModels(for: plan).isEmpty,
          catalog.guidance(for: "chatgpt:\(saved.id)", providers: [plan])?.visionLevel == expectedPlan.recommendationVision else {
        throw CheckFailure.message("ChatGPT metadata, local label/purposes, stale source labels or unpublished defaults changed")
    }

    let paid = ProviderModelSettings(id: paidID, requiresSubscription: false)
    let accessible = catalog.applyingCatalog(to: paid, providerID: "ollama-cloud", kind: .openAICompatible)
    guard accessible.isSelectable, !accessible.resolvedLabels.contains(where: { $0.id == "subscription" }) else {
        throw CheckFailure.message("Catalog overlay ignored the successful account access probe")
    }
    var retired = paid
    retired.eol = true; retired.eolDate = "2026-10-12"; retired.requiresSubscription = true
    let merged = ProviderModelCatalog.merge(fetched: [.init(id: paid.id, label: paid.id)], previous: [retired],
                                           previousEnabled: [paid.id: true], access: [paid.id: .subscription(false)], today: "2026-10-13")
    let reoffered = catalog.applyingCatalog(to: merged.models[0], providerID: "ollama-cloud", kind: .openAICompatible)
    guard reoffered.eol == false, reoffered.eolDate == nil, reoffered.requiresSubscription == false,
          reoffered.isSelectable, merged.enabled[paid.id] == true else {
        throw CheckFailure.message("Re-offered model lost local eol/access corrections on canonical overlay")
    }
    let custom = ProviderSettings(id: "custom", baseURL: endpoint, models: [saved])
    let wrongKind = ProviderSettings(id: "chatgpt", baseURL: endpoint, models: [saved])
    guard catalog.registeredModelSettings(for: custom) == [saved],
          catalog.registeredModelSettings(for: wrongKind) == [saved] else {
        throw CheckFailure.message("Catalog inferred canonical metadata for a custom provider or wrong kind")
    }
    let old = try JSONDecoder().decode(ProviderModelSettings.self, from: Data(#"{"id":"old","label":"Saved","purposes":["llm"],"requiresSubscription":true}"#.utf8))
    guard old.label == "Saved", old.modelFold == "subscription", !old.isSelectable,
          try JSONDecoder().decode(ProviderModelSettings.self, from: JSONEncoder().encode(reoffered)) == reoffered else {
        throw CheckFailure.message("Old settings compatibility or persistent access corrections failed")
    }
    // Clearing the last local purpose must not trap its editor. A purpose measured without a response can be
    // chosen, as not recommended, and is kept as chosen (the author, 2026-10-26).
    let cleared = ProviderModelSettings(id: "local", purposes: [])
    let blocked = ProviderModelSettings(id: "blocked", purposes: [], unsupportedPurposes: ["llm", "vision"])
    let unsupported = ProviderModelSettings(id: "unsupported", purposes: ["llm"], unsupportedPurposes: ["vision"])
    var draft = ProviderModelsDraft(models: [cleared, blocked, unsupported], enabled: [:])
    draft.setVisible(models: draft.models, enabled: true)
    guard !draft.isEnabled(modelID: cleared.id), !draft.isEnabled(modelID: blocked.id), draft.isEnabled(modelID: unsupported.id),
          blocked.isSelectable, !blocked.isPublishable, blocked.resolvedLabels.map(\.id).contains("no_response") else {
        throw CheckFailure.message("Selecting everything published a model offered for no purpose")
    }
    draft.togglePurpose(modelID: cleared.id, purpose: "llm")
    draft.togglePurpose(modelID: blocked.id, purpose: "llm")
    draft.togglePurpose(modelID: unsupported.id, purpose: "vision")
    guard let chosenBlocked = draft.model(modelID: blocked.id), let chosenVision = draft.model(modelID: unsupported.id),
          draft.model(modelID: cleared.id)?.isSelectable == true,
          chosenBlocked.purposes == ["llm"], chosenBlocked.allowedUnsupportedPurposes == ["llm"], chosenBlocked.offers("llm"),
          chosenBlocked.resolvedLabels.map(\.id).contains("no_response"), draft.isEnabled(modelID: blocked.id),
          chosenVision.purposes == ["llm", "vision"], chosenVision.allowedUnsupportedPurposes == ["vision"],
          chosenVision.offers("vision"), chosenVision.isNotRecommended(for: "vision"), !chosenVision.isNotRecommended(for: "llm") else {
        throw CheckFailure.message("Purpose editing trapped a local empty model or refused a purpose measured without a response")
    }
    draft.togglePurpose(modelID: unsupported.id, purpose: "vision")
    guard draft.model(modelID: unsupported.id)?.allowedUnsupportedPurposes == nil else {
        throw CheckFailure.message("Clearing a chosen unrecommended purpose left it allowed")
    }
    // The catalog keeps such a purpose out of its defaults, and keeps it only where it was chosen.
    let openAI = ProviderSettings(id: "openai", kind: .openAICompatible, baseURL: endpoint)
    var chosen = ProviderModelSettings(id: "gpt-4", purposes: ["llm", "vision"])
    let catalogDefault = catalog.applyingCatalog(to: chosen, providerID: "openai", kind: .openAICompatible)
    chosen.allowedUnsupportedPurposes = ["vision"]
    let kept = catalog.applyingCatalog(to: chosen, providerID: "openai", kind: .openAICompatible)
    let keptProvider = ProviderSettings(id: "openai", kind: .openAICompatible, baseURL: endpoint, models: [kept])
    guard catalogDefault.purposes == ["llm"], catalogDefault.allowedUnsupportedPurposes == nil,
          kept.purposes == ["llm", "vision"], kept.allowedUnsupportedPurposes == ["vision"], kept.isNotRecommended(for: "vision"),
          catalog.applyingCatalog(to: kept, providerID: "openai", kind: .openAICompatible) == kept,
          SettingsModel.registeredModels(for: keptProvider, purpose: "vision").map(\.id) == ["gpt-4"],
          SettingsModel.isRegisteredModelAvailable("openai:gpt-4", purpose: "vision", settings: HostSettings(providers: [keptProvider])),
          SettingsModel.registeredModels(for: openAI, purpose: "vision").allSatisfy({ !$0.isNotRecommended(for: "vision") }),
          try JSONDecoder().decode(ProviderModelSettings.self, from: JSONEncoder().encode(kept)) == kept else {
        throw CheckFailure.message("A purpose chosen against the measurement was lost, or the catalog's defaults chose one")
    }
    // The Web displays three tiers while retaining the measured five-step ordering.
    guard [1, 2, 3, 4, 5].map({ ModelGuidance.recommendationTier($0) }) == [1, 1, 2, 3, 3],
          ModelGuidance.recommendation(4) == "★★★ (3/3)",
          ModelGuidance.recommendation(nil) == "—" else {
        throw CheckFailure.message("Model recommendations diverged from the Web three-tier presentation")
    }
    let measured = ProviderModelSettings(id: "measured", purposes: ["llm"], unsupportedPurposes: ["vision"],
        speedLLMSeconds: 12.34, costUSDLLM: 0, costUSDVision: 0.00001)
    guard ModelMetadataPresentation.speed(measured, language: "ja") == "LLM 平均 12.3秒（参考値）",
          ModelMetadataPresentation.speed(measured, language: "en") == "LLM mean 12.3 s (reference)",
          ModelMetadataPresentation.speed(measured, hidden: true, language: "en") == "—",
          ModelMetadataPresentation.cost(measured, language: "en") == "LLM $0 per drawing / Vision <$0.0001 per picture",
          ModelMetadataPresentation.cost(.init(id: "unknown"), language: "en") == "—",
          ModelMetadataPresentation.supports(measured, purpose: "llm"),
          !ModelMetadataPresentation.supports(measured, purpose: "vision") else {
        throw CheckFailure.message("Model metadata lost purpose availability, free cost, missing values or mean/reference units")
    }
    let inconsistent = ProviderModelSettings(id: "blocked-purpose", purposes: ["llm"], unsupportedPurposes: ["llm"])
    let inconsistentProvider = ProviderSettings(id: "custom", baseURL: endpoint, models: [inconsistent])
    guard SettingsModel.registeredModels(for: inconsistentProvider, purpose: "llm").isEmpty,
          !SettingsModel.isBatchModelAvailable("custom:blocked-purpose", settings: HostSettings(providers: [inconsistentProvider])) else {
        throw CheckFailure.message("A purpose explicitly marked unsupported was offered for a new request")
    }
    let noRegisteredModels = ProviderSettings(id: "anthropic", kind: .anthropic, baseURL: endpoint, models: [])
    let historicalNaming = ModelNaming(providers: [noRegisteredModels])
    guard historicalNaming.resolve("claude-haiku-5-5").provider == "anthropic",
          historicalNaming.modelShortName("claude-haiku-5-5") == "Claude Haiku 5.5",
          historicalNaming.modelShortName("chatgpt:gpt-6-astra") == "GPT-6-Astra",
          SettingsModel.batchModels(for: noRegisteredModels).isEmpty,
          ModelNaming(providers: [plan]).modelShortName("chatgpt:\(saved.id)") == saved.label else {
        throw CheckFailure.message("Historical naming lost canonical/local labels or registered a removed model")
    }
    print("Model catalog passed: shared 15 cases; exact v2 export and Host label table; measurement key presence; ChatGPT evaluations and author purposes; stale labels refreshed; account/re-offer corrections; custom/wrong-kind boundaries; old settings compatibility; three-tier presentation; measured units and absent values; unsupported purposes chosen as not recommended and kept only where chosen; historical naming without registration. Zero provider calls.")
}

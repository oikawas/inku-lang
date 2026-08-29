use inku_ddl::{
    PROMPT_BODY_TEMPLATE_ASSET_BYTES, PROMPT_BODY_TEMPLATE_ASSET_ID, PromptBodyTemplateSlot,
    PromptBodyTemplateStage, ResolvedInstructionLanguage, prompt_body_template,
    prompt_body_template_asset, prompt_body_template_asset_sha256_hex,
};
use sha2::{Digest, Sha256};

#[test]
fn embedded_asset_has_stable_identity_and_exact_digest() {
    let asset = prompt_body_template_asset();

    assert_eq!(asset.schema_version, 1);
    assert_eq!(asset.asset_id, PROMPT_BODY_TEMPLATE_ASSET_ID);
    assert_eq!(
        PROMPT_BODY_TEMPLATE_ASSET_ID,
        "inku.prompt-body-templates.v1"
    );
    assert_eq!(
        prompt_body_template_asset_sha256_hex(),
        "0cb45ea34cad2eb53a3542e8b305b680c6759c8bdbe1cc71deb1b0e7f86a8ef9"
    );
    assert_eq!(
        prompt_body_template_asset_sha256_hex(),
        Sha256::digest(PROMPT_BODY_TEMPLATE_ASSET_BYTES)
            .iter()
            .map(|byte| format!("{byte:02x}"))
            .collect::<String>()
    );
    assert!(!PROMPT_BODY_TEMPLATE_ASSET_BYTES.starts_with(&[0xef, 0xbb, 0xbf]));
    assert!(PROMPT_BODY_TEMPLATE_ASSET_BYTES.ends_with(b"\n"));
    assert!(!PROMPT_BODY_TEMPLATE_ASSET_BYTES.ends_with(b"\n\n"));
}

#[test]
fn embedded_asset_has_exact_rows_slot_orders_and_no_unknown_slots() {
    let asset = prompt_body_template_asset();
    assert_eq!(
        asset
            .stages
            .iter()
            .map(|stage| stage.stage)
            .collect::<Vec<_>>(),
        [
            PromptBodyTemplateStage::Stage1,
            PromptBodyTemplateStage::Stage2
        ]
    );
    assert_eq!(
        asset.languages,
        [
            ResolvedInstructionLanguage::Ja,
            ResolvedInstructionLanguage::En
        ]
    );

    let cases = [
        (
            PromptBodyTemplateStage::Stage1,
            [
                PromptBodyTemplateSlot::TextureMaterialEnumeration,
                PromptBodyTemplateSlot::CountClamp,
                PromptBodyTemplateSlot::CountRangeHeading,
                PromptBodyTemplateSlot::CountBands,
                PromptBodyTemplateSlot::TileCount,
                PromptBodyTemplateSlot::SaijikiPromptBlock,
            ]
            .as_slice(),
        ),
        (
            PromptBodyTemplateStage::Stage2,
            [
                PromptBodyTemplateSlot::Canvas,
                PromptBodyTemplateSlot::CountDensity,
                PromptBodyTemplateSlot::GridCount,
            ]
            .as_slice(),
        ),
    ];
    for (stage, expected_slots) in cases {
        for language in [
            ResolvedInstructionLanguage::Ja,
            ResolvedInstructionLanguage::En,
        ] {
            let template = prompt_body_template(stage, language);
            assert!(!template.body.is_empty());
            assert_eq!(template.required_slots, expected_slots);
            assert_eq!(
                body_slot_names(template.body),
                expected_slots
                    .iter()
                    .map(|slot| slot.token())
                    .collect::<Vec<_>>()
            );
            for slot in expected_slots {
                assert_eq!(template.body.matches(slot.token()).count(), 1);
            }
        }
    }
}

fn body_slot_names(body: &str) -> Vec<&str> {
    let mut tokens = Vec::new();
    let mut remainder = body;
    while let Some(start) = remainder.find("%%") {
        remainder = &remainder[start..];
        let end = remainder[2..]
            .find("%%")
            .expect("all embedded slot tokens must be closed")
            + 4;
        tokens.push(&remainder[..end]);
        remainder = &remainder[end..];
    }
    tokens
}

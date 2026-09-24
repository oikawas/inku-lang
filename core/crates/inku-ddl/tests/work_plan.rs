use inku_ddl::ResolvedInstructionLanguage;
use inku_ddl::work_plan::{
    WorkPlan, WorkPlanLayer, WorkPlanSlot, derive_work_plan_capabilities, normalize_work_plan,
    print_work_plan, work_plan_capabilities, work_plan_response_schema,
    work_plan_source_compiles_cleanly, work_plan_vocabulary,
};
use serde_json::json;

/// A stale matrix would let the schema offer combinations the compiler rejects.
#[test]
fn embedded_capabilities_match_the_current_compiler() {
    assert_eq!(&derive_work_plan_capabilities(), work_plan_capabilities());
}

struct SplitMix(u64);

impl SplitMix {
    fn next(&mut self) -> u64 {
        self.0 = self.0.wrapping_add(0x9e37_79b9_7f4a_7c15);
        let mut z = self.0;
        z = (z ^ (z >> 30)).wrapping_mul(0xbf58_476d_1ce4_e5b9);
        z = (z ^ (z >> 27)).wrapping_mul(0x94d0_49bb_1331_11eb);
        z ^ (z >> 31)
    }

    fn pick<'a, T>(&mut self, items: &'a [T]) -> Option<&'a T> {
        (!items.is_empty())
            .then(|| &items[usize::try_from(self.next() % items.len() as u64).unwrap()])
    }

    fn chance(&mut self, percent: u64) -> bool {
        self.next() % 100 < percent
    }
}

fn random_layer(rng: &mut SplitMix) -> WorkPlanLayer {
    let capabilities = work_plan_capabilities();
    let forms: Vec<&String> = capabilities.forms.keys().collect();
    let form = (*rng.pick(&forms).unwrap()).clone();
    let slots = &capabilities.forms[&form];
    let (shape, proportion) = match form.split_once('/') {
        Some((shape, proportion)) => (shape.to_owned(), Some(proportion.to_owned())),
        None => (form.clone(), None),
    };
    let mut layer = WorkPlanLayer {
        shape,
        proportion,
        action: rng.pick(&slots[&WorkPlanSlot::Action]).unwrap().clone(),
        count: *rng.pick(&[1, 2, 3, 5, 8, 12, 20, 30, 40]).unwrap(),
        ..WorkPlanLayer::default()
    };
    for slot in [
        WorkPlanSlot::Place,
        WorkPlanSlot::Size,
        WorkPlanSlot::Color,
        WorkPlanSlot::Tool,
        WorkPlanSlot::Thinness,
        WorkPlanSlot::Continuity,
        WorkPlanSlot::Surface,
        WorkPlanSlot::Angle,
        WorkPlanSlot::Bleeding,
    ] {
        if rng.chance(50)
            && let Some(value) = rng.pick(&slots[&slot])
        {
            layer.attributes.insert(slot, value.clone());
        }
    }
    if rng.chance(40)
        && let Some(quality) = rng.pick(&slots[&WorkPlanSlot::MotionQuality])
    {
        layer
            .attributes
            .insert(WorkPlanSlot::MotionQuality, quality.clone());
        for slot in [WorkPlanSlot::MotionAmplitude, WorkPlanSlot::MotionSpeed] {
            if rng.chance(50)
                && let Some(value) = rng.pick(&slots[&slot])
            {
                layer.attributes.insert(slot, value.clone());
            }
        }
    }
    if layer
        .attributes
        .get(&WorkPlanSlot::Surface)
        .map(String::as_str)
        == Some("solid")
        && rng.chance(30)
        && let Some(value) = rng.pick(&slots[&WorkPlanSlot::SurfaceIntensity])
    {
        layer
            .attributes
            .insert(WorkPlanSlot::SurfaceIntensity, value.clone());
    }
    if layer.action == "line_up"
        && rng.chance(50)
        && let Some(value) = rng.pick(&slots[&WorkPlanSlot::LineUpDirection])
    {
        layer
            .attributes
            .insert(WorkPlanSlot::LineUpDirection, value.clone());
    }
    layer
}

/// Every plan inside the matrix prints to DDL that compiles with no diagnostic,
/// in both languages. This is the structural guarantee against dropped clauses.
#[test]
fn random_plans_inside_the_matrix_compile_cleanly_in_both_languages() {
    let vocabulary = work_plan_vocabulary();
    let mut rng = SplitMix(20_260_924);
    for _ in 0..120 {
        let layers = (0..1 + rng.next() % 5)
            .map(|_| random_layer(&mut rng))
            .collect();
        let plan = WorkPlan {
            ground: rng.chance(40).then(|| {
                rng.pick(vocabulary.terms(WorkPlanSlot::Ground))
                    .unwrap()
                    .id
                    .clone()
            }),
            background: rng.chance(40).then(|| {
                rng.pick(vocabulary.terms(WorkPlanSlot::Color))
                    .unwrap()
                    .id
                    .clone()
            }),
            layers,
        };
        for language in [
            ResolvedInstructionLanguage::Ja,
            ResolvedInstructionLanguage::En,
        ] {
            let source = print_work_plan(&plan, language);
            assert!(
                work_plan_source_compiles_cleanly(&source, language),
                "{language:?}: {source}"
            );
        }
    }
}

#[test]
fn normalization_turns_unusable_values_into_diagnostics_without_stopping() {
    let (plan, diagnostics) = normalize_work_plan(&json!({
        "background": "sky",
        "ground": "paper",
        "layers": [
            {"shape": "moon", "action": "place", "count": 1},
            {"shape": "arc", "proportion": "crescent", "action": "draw", "count": 3,
             "surface": "grain", "size": "medium", "color": "blue",
             "motion_quality": "still", "motion_amplitude": "large"},
            {"shape": "point", "action": "draw", "count": 999, "angle": "horizontal"}
        ]
    }));
    assert_eq!(plan.ground.as_deref(), Some("paper"));
    assert_eq!(plan.background, None);
    assert_eq!(plan.layers.len(), 2);
    let arc = &plan.layers[0];
    assert_eq!(arc.form(), "arc/crescent");
    assert_eq!(
        arc.attributes.get(&WorkPlanSlot::Color).map(String::as_str),
        Some("blue")
    );
    assert!(!arc.attributes.contains_key(&WorkPlanSlot::Surface));
    assert!(!arc.attributes.contains_key(&WorkPlanSlot::Size));
    assert!(!arc.attributes.contains_key(&WorkPlanSlot::MotionAmplitude));
    let point = &plan.layers[1];
    assert_ne!(point.action, "draw");
    assert_eq!(point.count, 60);
    assert!(!point.attributes.contains_key(&WorkPlanSlot::Angle));
    let reasons: Vec<&str> = diagnostics.iter().map(|item| item.reason).collect();
    for reason in [
        "unknown_value",
        "layer_without_known_shape",
        "unsupported_for_form",
        "requires_motion_quality",
        "over_count_limit",
    ] {
        assert!(reasons.contains(&reason), "{reason}: {diagnostics:?}");
    }
    for language in [
        ResolvedInstructionLanguage::Ja,
        ResolvedInstructionLanguage::En,
    ] {
        assert!(work_plan_source_compiles_cleanly(
            &print_work_plan(&plan, language),
            language
        ));
    }
    for garbage in [
        json!(null),
        json!("text"),
        json!({"layers": "x"}),
        json!({"layers": [1, null]}),
    ] {
        let (plan, _) = normalize_work_plan(&garbage);
        assert!(plan.layers.is_empty());
    }
}

#[test]
fn response_schema_uses_the_portable_subset_and_the_projected_vocabulary() {
    let schema = work_plan_response_schema();
    let text = schema.to_string();
    // Gemini rejects array item-count bounds in function schemas (HTTP 400);
    // normalization enforces the layer limit instead.
    for forbidden in ["oneOf", "anyOf", "\"null\"", "minItems", "maxItems"] {
        assert!(!text.contains(forbidden), "{forbidden}");
    }
    let colors = schema["properties"]["layers"]["items"]["properties"]["color"]["enum"]
        .as_array()
        .unwrap();
    assert_eq!(
        colors.len(),
        1 + work_plan_vocabulary().terms(WorkPlanSlot::Color).len()
    );
}

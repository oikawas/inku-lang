mod common;

use inku_ddl::ResolvedInstructionLanguage;
use inku_ddl::work_plan::{
    NumericPlace, NumericSize, NumericWriting, WorkPlan, WorkPlanLayer, WorkPlanSlot,
    derive_work_plan_capabilities, normalize_work_plan, number, print_work_plan,
    print_work_plan_with_numbers, work_plan_capabilities, work_plan_response_schema,
    work_plan_source_compiles_cleanly, work_plan_vocabulary,
};
use serde_json::json;

/// A stale matrix would let the schema offer combinations the compiler rejects.
#[test]
fn embedded_capabilities_match_the_current_compiler() {
    assert_eq!(&derive_work_plan_capabilities(), work_plan_capabilities());
}

/// `vertical` turns a shape 90°, so a tall shape that took it would lie down
/// although both words say upright. The plan drops the angle there and keeps
/// it where the turn and the proportion do not contradict each other (I-710).
#[test]
fn a_tall_shape_does_not_take_vertical() {
    let layer = |proportion: &str, angle: &str| {
        json!({"shape": "square", "proportion": proportion, "action": "fill", "count": 1,
               "angle": angle})
    };
    let (plan, diagnostics) = normalize_work_plan(&json!({"layers": [
        layer("tall", "vertical"), layer("tall", "rising"), layer("wide", "vertical"),
    ]}));
    let angles: Vec<Option<&str>> = plan
        .layers
        .iter()
        .map(|layer| {
            layer
                .attributes
                .get(&WorkPlanSlot::Angle)
                .map(String::as_str)
        })
        .collect();
    assert_eq!(angles, [None, Some("rising"), Some("vertical")]);
    let dropped: Vec<_> = diagnostics
        .iter()
        .map(|item| {
            (
                item.layer,
                item.field.as_str(),
                item.value.as_str(),
                item.reason,
            )
        })
        .collect();
    assert_eq!(
        dropped,
        [(Some(0), "angle", "vertical", "unsupported_for_form")]
    );
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
        WorkPlanSlot::Position,
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
        for slot in [WorkPlanSlot::MotionAmplitude, WorkPlanSlot::MotionSpacing] {
            if rng.chance(50)
                && let Some(value) = rng.pick(&slots[&slot])
            {
                layer.attributes.insert(slot, value.clone());
            }
        }
    }
    if rng.chance(30)
        && let Some(value) = rng.pick(&slots[&WorkPlanSlot::Handling])
    {
        layer
            .attributes
            .insert(WorkPlanSlot::Handling, value.clone());
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
    let mut plans = Vec::new();
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
            // The clean-compile check runs without installed definitions.
            plugins: Vec::new(),
            layers,
        };
        plans.push(plan);
    }
    common::par_map(&plans, |plan| {
        for language in [
            ResolvedInstructionLanguage::Ja,
            ResolvedInstructionLanguage::En,
        ] {
            let source = print_work_plan(plan, language);
            assert!(
                work_plan_source_compiles_cleanly(&source, language),
                "{language:?}: {source}"
            );
        }
    });
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
             "motion_quality": "still", "motion_amplitude": "broadly"},
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
    assert_eq!(point.count, 240);
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

/// The reader reads and writes the plan's values and field names, so they keep
/// the Saijiki's one word, one meaning: each value is its word's own English,
/// and no token names two meanings in two fields. Color is also the background,
/// and a direction is both an angle and a line-up direction, with one meaning.
#[test]
fn plan_values_are_the_words_english_with_one_meaning_each() {
    let vocabulary = work_plan_vocabulary();
    let mut meanings: std::collections::BTreeMap<String, Vec<(WorkPlanSlot, String)>> =
        std::collections::BTreeMap::new();
    let slots = WorkPlanSlot::LAYER_ATTRIBUTES.into_iter().chain([
        WorkPlanSlot::Shape,
        WorkPlanSlot::Proportion,
        WorkPlanSlot::Ground,
    ]);
    let mut compared = 0;
    for slot in slots {
        for term in vocabulary.terms(slot) {
            assert_eq!(
                term.id,
                term.en.replace(['-', ' '], "_"),
                "{slot:?}: the value is not the word's English"
            );
            meanings
                .entry(term.id.clone())
                .or_default()
                .push((slot, term.ja.clone()));
            compared += 1;
        }
    }
    assert!(compared > 100, "compared {compared}");
    for (value, uses) in &meanings {
        let words: std::collections::BTreeSet<&String> = uses.iter().map(|(_, ja)| ja).collect();
        assert_eq!(words.len(), 1, "{value} names two meanings: {uses:?}");
    }
    let schema = work_plan_response_schema();
    let fields = schema["properties"]["layers"]["items"]["properties"]
        .as_object()
        .unwrap();
    for field in ["position", "handling", "motion_spacing"] {
        assert!(fields.contains_key(field), "{field}");
    }
    for retired in ["place", "surface_intensity", "motion_speed"] {
        assert!(!fields.contains_key(retired), "{retired}");
    }
    let values = |field: &str| fields[field]["enum"].to_string();
    for (field, value) in [
        ("surface", "\"flat\""),
        ("surface", "\"empty\""),
        ("surface", "\"sweep\""),
        ("thinness", "\"thin\""),
        ("handling", "\"faint\""),
        ("motion_amplitude", "\"narrowly\""),
        ("motion_spacing", "\"loosely\""),
    ] {
        assert!(values(field).contains(value), "{field} {value}");
    }
    for (field, value) in [
        ("surface", "\"solid\""),
        ("surface", "\"wash\""),
        ("thinness", "\"fine\""),
        ("motion_amplitude", "\"large\""),
    ] {
        assert!(!values(field).contains(value), "{field} {value}");
    }
}

/// Every value of every layer field prints in Japanese with a single の after it
/// (I-709: the size 特大の, whose word already carries の, printed as 特大のの).
#[test]
fn japanese_layers_never_double_the_particle_no() {
    let vocabulary = work_plan_vocabulary();
    let quality = vocabulary.terms(WorkPlanSlot::MotionQuality)[0].id.clone();
    let (mut printed, mut doubled) = (0, Vec::new());
    for slot in WorkPlanSlot::LAYER_ATTRIBUTES
        .into_iter()
        .chain([WorkPlanSlot::Proportion])
    {
        let terms = vocabulary.terms(slot);
        assert!(!terms.is_empty(), "{slot:?} has no values to print");
        for term in terms {
            let mut layer = WorkPlanLayer {
                shape: "square".into(),
                action: "place".into(),
                count: 1,
                ..WorkPlanLayer::default()
            };
            match slot {
                WorkPlanSlot::Action => layer.action = term.id.clone(),
                WorkPlanSlot::Proportion => layer.proportion = Some(term.id.clone()),
                _ => {
                    layer.attributes.insert(slot, term.id.clone());
                }
            }
            // Amplitude and spacing are printed only beside a motion quality.
            if matches!(
                slot,
                WorkPlanSlot::MotionAmplitude | WorkPlanSlot::MotionSpacing
            ) {
                layer
                    .attributes
                    .insert(WorkPlanSlot::MotionQuality, quality.clone());
            }
            let plan = WorkPlan {
                layers: vec![layer],
                ..WorkPlan::default()
            };
            let source = print_work_plan(&plan, ResolvedInstructionLanguage::Ja);
            if source.contains("のの") {
                doubled.push(format!("{slot:?} {}: {source}", term.id));
            }
            printed += 1;
        }
    }
    assert!(
        doubled.is_empty(),
        "{} of {printed} layers double の:\n{}",
        doubled.len(),
        doubled.join("\n")
    );
}

/// A number the laws stage writes has six decimals at most and no trailing
/// zeros, rounded from the binary value as the prototype's Python wrote it.
#[test]
fn laws_numbers_drop_trailing_zeros() {
    for (value, written) in [
        (0.0, "0"),
        (-0.000_000_1, "0"),
        (0.5, "0.5"),
        (1.0, "1"),
        (2.0 / 3.0, "0.666667"),
        (0.381_966_011_250_105_1, "0.381966"),
        (0.118_034, "0.118034"),
        (0.000_000_5, "0"),
        (10.25, "10.25"),
    ] {
        assert_eq!(number(value), written, "{value}");
    }
}

fn numeric_layer(
    shape: &str,
    action: &str,
    count: u32,
    attributes: &[(WorkPlanSlot, &str)],
) -> WorkPlanLayer {
    WorkPlanLayer {
        shape: shape.into(),
        action: action.into(),
        count,
        attributes: attributes
            .iter()
            .map(|(slot, value)| (*slot, (*value).to_owned()))
            .collect(),
        ..WorkPlanLayer::default()
    }
}

/// The laws stage writes a place and a size in numbers (stage B-2c). The place
/// takes the place word's or range's spot, the size heads the Japanese noun
/// phrase and follows the English noun, and every form compiles cleanly. A
/// layer without numbers prints as the composition prints it.
#[test]
fn numeric_places_and_sizes_print_where_the_compiler_reads_them() {
    let point = |x, y| Some(NumericPlace::Point { at: [x, y] });
    let segment = |x0, y0, x1, y1| {
        Some(NumericPlace::Segment {
            from: [x0, y0],
            to: [x1, y1],
        })
    };
    let cases = [
        (
            numeric_layer("circle", "place", 1, &[(WorkPlanSlot::Color, "blue")]),
            NumericWriting {
                place: point(0.381_966, 0.5),
                size: Some(NumericSize::Radius { radius: 0.05 }),
                ..NumericWriting::default()
            },
            "画面の横0.381966、縦0.5の位置に、半径0.05の青の円を1個置く。",
            "Place one blue circle radius 0.05 at horizontal 0.381966, vertical 0.5.",
        ),
        (
            numeric_layer("line", "draw", 1, &[]),
            NumericWriting {
                place: segment(0.118, 0.118, 0.882, 0.882),
                size: None,
                ..NumericWriting::default()
            },
            "画面の横0.118、縦0.118から横0.882、縦0.882まで、線を1個引く。",
            "Draw one line from horizontal 0.118, vertical 0.118 to horizontal 0.882, vertical 0.882.",
        ),
        (
            numeric_layer("circle", "line_up", 5, &[]),
            NumericWriting {
                place: segment(0.118, 0.5, 0.882, 0.5),
                size: Some(NumericSize::Radius { radius: 0.03 }),
                ..NumericWriting::default()
            },
            "画面の横0.118、縦0.5から横0.882、縦0.5まで、半径0.03の円を5個並べる。",
            "Line up 5 circles radius 0.03 from horizontal 0.118, vertical 0.5 to horizontal 0.882, vertical 0.5.",
        ),
        (
            numeric_layer("point", "scatter", 12, &[(WorkPlanSlot::Color, "white")]),
            NumericWriting {
                place: Some(NumericPlace::Range {
                    bounds: [0.2, 0.3, 0.8, 0.6],
                }),
                size: None,
                ..NumericWriting::default()
            },
            "画面の横0.2〜0.8、縦0.3〜0.6の範囲に、白の点を12個散らす。",
            "Scatter 12 white points in the range horizontal 0.2 to 0.8, vertical 0.3 to 0.6.",
        ),
        // An English sentence that ends in its place's whole number writes it
        // with one decimal, which the reader does not take for a decimal point.
        (
            numeric_layer("point", "scatter", 12, &[(WorkPlanSlot::Color, "white")]),
            NumericWriting {
                place: Some(NumericPlace::Range {
                    bounds: [0.2, 0.333_333, 0.8, 1.0],
                }),
                size: None,
                ..NumericWriting::default()
            },
            "画面の横0.2〜0.8、縦0.333333〜1の範囲に、白の点を12個散らす。",
            "Scatter 12 white points in the range horizontal 0.2 to 0.8, vertical 0.333333 to 1.0.",
        ),
        (
            numeric_layer("line", "draw", 1, &[]),
            NumericWriting {
                place: segment(0.0, 0.5, 1.0, 1.0),
                size: None,
                ..NumericWriting::default()
            },
            "画面の横0、縦0.5から横1、縦1まで、線を1個引く。",
            "Draw one line from horizontal 0, vertical 0.5 to horizontal 1, vertical 1.0.",
        ),
        (
            numeric_layer("ellipse", "place", 1, &[]),
            NumericWriting {
                place: point(0.5, 0.25),
                size: Some(NumericSize::WidthHeight {
                    width: 0.2,
                    height: 0.1,
                }),
                ..NumericWriting::default()
            },
            "画面の横0.5、縦0.25の位置に、幅0.2、高さ0.1の楕円を1個置く。",
            "Place one ellipse width 0.2, height 0.1 at horizontal 0.5, vertical 0.25.",
        ),
        (
            numeric_layer("arc", "draw", 1, &[]),
            NumericWriting {
                place: point(0.5, 0.5),
                size: Some(NumericSize::ChordSagitta {
                    chord: 0.2,
                    sagitta: 0.05,
                }),
                ..NumericWriting::default()
            },
            "画面の横0.5、縦0.5の位置に、弦長0.2、矢高0.05の弧を1個引く。",
            "Draw one arc chord 0.2, sagitta 0.05 at horizontal 0.5, vertical 0.5.",
        ),
        // A semicircle whose sagitta, rounded alone, would pass half the
        // written chord (0.046729 against 0.0467285) is written at that half
        // cut to six decimals; one that stays within keeps its digits.
        (
            numeric_layer("arc", "draw", 1, &[]),
            NumericWriting {
                place: point(0.5, 0.5),
                size: Some(NumericSize::ChordSagitta {
                    chord: 0.093_457_2,
                    sagitta: 0.046_728_6,
                }),
                ..NumericWriting::default()
            },
            "画面の横0.5、縦0.5の位置に、弦長0.093457、矢高0.046728の弧を1個引く。",
            "Draw one arc chord 0.093457, sagitta 0.046728 at horizontal 0.5, vertical 0.5.",
        ),
        (
            numeric_layer("arc", "draw", 1, &[]),
            NumericWriting {
                place: point(0.5, 0.5),
                size: Some(NumericSize::ChordSagitta {
                    chord: 0.151_216_8,
                    sagitta: 0.075_608_4,
                }),
                ..NumericWriting::default()
            },
            "画面の横0.5、縦0.5の位置に、弦長0.151217、矢高0.075608の弧を1個引く。",
            "Draw one arc chord 0.151217, sagitta 0.075608 at horizontal 0.5, vertical 0.5.",
        ),
        (
            numeric_layer("triangle", "place", 1, &[]),
            NumericWriting {
                place: point(0.3, 0.7),
                size: Some(NumericSize::WidthHeight {
                    width: 0.2,
                    height: 0.15,
                }),
                ..NumericWriting::default()
            },
            "画面の横0.3、縦0.7の位置に、幅0.2、高さ0.15の三角を1個置く。",
            "Place one triangle width 0.2, height 0.15 at horizontal 0.3, vertical 0.7.",
        ),
        // A size alone keeps the layer's own place word.
        (
            numeric_layer("square", "place", 3, &[(WorkPlanSlot::Position, "center")]),
            NumericWriting {
                place: None,
                size: Some(NumericSize::Side { side: 0.1 }),
                ..NumericWriting::default()
            },
            "中心に、一辺0.1の四角を3個置く。",
            "Place 3 squares side length 0.1 at the center.",
        ),
        (
            numeric_layer("free_line", "draw", 1, &[(WorkPlanSlot::Position, "top")]),
            NumericWriting {
                place: None,
                size: Some(NumericSize::Length { length: 0.4 }),
                ..NumericWriting::default()
            },
            "上に、長さ0.4の自由線を1個引く。",
            "Draw one free line length 0.4 at the top.",
        ),
    ];
    for (layer, written, ja, en) in cases {
        let plan = WorkPlan {
            layers: vec![layer],
            ..WorkPlan::default()
        };
        for (language, expected) in [
            (ResolvedInstructionLanguage::Ja, ja),
            (ResolvedInstructionLanguage::En, en),
        ] {
            let source = print_work_plan_with_numbers(
                &plan,
                language,
                &[],
                &[],
                &[],
                &[Some(written.clone())],
            );
            assert_eq!(source, expected, "{language:?}");
            assert!(
                work_plan_source_compiles_cleanly(&source, language),
                "{language:?}: {source}"
            );
            assert_eq!(
                print_work_plan_with_numbers(&plan, language, &[], &[], &[], &[None]),
                print_work_plan(&plan, language)
            );
        }
    }
}

/// The Score of a printed sentence, compiled whole on the square canvas with
/// room for every mark it repeats.
fn printed_score(source: &str, language: ResolvedInstructionLanguage) -> inku_score::Score {
    let hard = inku_score::HardResourcePolicy {
        identity: "work-plan-numeric-test.v1".into(),
        budget: inku_score::ResourceBudget {
            maximum: inku_score::ResourceDemand {
                logical_objects: 400,
                primitive_marks: 400,
                object_templates: 64,
                maximum_per_template_primitive_marks: 240,
                maximum_resolved_count: 2000,
                template_nodes: 512,
                anchor_instances: 400,
                transform_instances: 400,
                placement_instances: 400,
                fill_instances: 400,
            },
        },
    };
    let result = inku_ddl::compile_ddl_to_score_with_resources(
        inku_ddl::NormalizedDdlDocument::new(source, language, Vec::new()).unwrap(),
        &[],
        Some(19),
        inku_ddl::MacroExpansionLimits {
            max_invocations: 8,
            max_depth: 8,
            max_evaluation_steps: 128,
            max_nodes_per_invocation: 32,
            max_total_nodes: 64,
        },
        inku_ddl::ScoreLoweringContext::resolve("square", inku_score::Color::White).unwrap(),
        inku_ddl::ScoreErrorPolicy::Stop,
        hard.clone(),
        inku_score::OperationalResourceBudget(hard.budget),
    );
    assert!(
        result.downstream_diagnostics().is_empty(),
        "{source}: {:?}",
        result.downstream_diagnostics()
    );
    result
        .score()
        .cloned()
        .unwrap_or_else(|| panic!("{source}"))
}

/// The laws stage writes a turn, two alternating colors and a polygon too
/// (stage B-4a): each compiles cleanly to the turn, the cycle and the sides it
/// writes, in both languages.
#[test]
fn numeric_turns_cycles_and_polygons_print_where_the_compiler_reads_them() {
    let point = |x, y| Some(NumericPlace::Point { at: [x, y] });
    let range = |bounds| Some(NumericPlace::Range { bounds });
    let cases = [
        (
            numeric_layer("square", "place", 1, &[(WorkPlanSlot::Color, "red")]),
            NumericWriting {
                place: point(0.5, 0.5),
                size: Some(NumericSize::Side { side: 0.1 }),
                turn: Some(30.0),
                ..NumericWriting::default()
            },
            "画面の横0.5、縦0.5の位置に、一辺0.1の回転30度の赤の四角を1個置く。",
            "Place one red square side length 0.1 rotated 30 degrees at horizontal 0.5, vertical 0.5.",
        ),
        (
            numeric_layer("arc", "draw", 1, &[(WorkPlanSlot::Color, "blue")]),
            NumericWriting {
                place: point(0.5, 0.5),
                size: Some(NumericSize::ChordSagitta {
                    chord: 0.2,
                    sagitta: 0.1,
                }),
                turn: Some(1.0),
                ..NumericWriting::default()
            },
            "画面の横0.5、縦0.5の位置に、弦長0.2、矢高0.1の回転1度の青の弧を1個引く。",
            "Draw one blue arc chord 0.2, sagitta 0.1 rotated 1 degree at horizontal 0.5, vertical 0.5.",
        ),
        (
            numeric_layer("ellipse", "line_up", 4, &[(WorkPlanSlot::Color, "black")]),
            NumericWriting {
                place: Some(NumericPlace::Segment {
                    from: [0.2, 0.5],
                    to: [0.8, 0.5],
                }),
                turn: Some(337.5),
                ..NumericWriting::default()
            },
            "画面の横0.2、縦0.5から横0.8、縦0.5まで、回転337.5度の黒の楕円を4個並べる。",
            "Line up 4 black ellipses rotated 337.5 degrees from horizontal 0.2, vertical 0.5 to horizontal 0.8, vertical 0.5.",
        ),
        (
            numeric_layer(
                "square",
                "tile",
                49,
                &[
                    (WorkPlanSlot::Color, "white"),
                    (WorkPlanSlot::Surface, "flat"),
                ],
            ),
            NumericWriting {
                place: range([0.0, 0.0, 1.0, 1.0]),
                size: Some(NumericSize::Side { side: 0.142_857 }),
                cycle: Some(vec![inku_score::Color::White, inku_score::Color::Blue]),
                ..NumericWriting::default()
            },
            "画面の横0〜1、縦0〜1の範囲に、白と青を交互にして、一辺0.142857の塗りの四角を49個敷き詰める。",
            "Tile 49 flat squares side length 0.142857 in the range horizontal 0 to 1, vertical 0 to 1, alternating white and blue.",
        ),
        (
            numeric_layer(
                "circle",
                "tile",
                9,
                &[
                    (WorkPlanSlot::Color, "black"),
                    (WorkPlanSlot::Surface, "empty"),
                ],
            ),
            NumericWriting {
                place: range([0.1, 0.1, 0.9, 0.9]),
                size: Some(NumericSize::Radius { radius: 0.072 }),
                sides: Some(6),
                ..NumericWriting::default()
            },
            "画面の横0.1〜0.9、縦0.1〜0.9の範囲に、半径0.072の黒の空の六角形を9個敷き詰める。",
            "Tile 9 black empty hexagon radius 0.072 in the range horizontal 0.1 to 0.9, vertical 0.1 to 0.9.",
        ),
        (
            numeric_layer(
                "circle",
                "line_up",
                7,
                &[
                    (WorkPlanSlot::Color, "black"),
                    (WorkPlanSlot::Surface, "empty"),
                ],
            ),
            NumericWriting {
                place: Some(NumericPlace::Segment {
                    from: [0.1, 0.1],
                    to: [0.9, 0.1],
                }),
                size: Some(NumericSize::Radius { radius: 0.072 }),
                sides: Some(6),
                ..NumericWriting::default()
            },
            "画面の横0.1、縦0.1から横0.9、縦0.1まで、半径0.072の黒の空の六角形を7個並べる。",
            "Line up 7 black empty hexagon radius 0.072 from horizontal 0.1, vertical 0.1 to horizontal 0.9, vertical 0.1.",
        ),
    ];
    for (layer, written, ja, en) in cases {
        let plan = WorkPlan {
            layers: vec![layer],
            ..WorkPlan::default()
        };
        let mut scores = Vec::new();
        for (language, expected) in [
            (ResolvedInstructionLanguage::Ja, ja),
            (ResolvedInstructionLanguage::En, en),
        ] {
            let source = print_work_plan_with_numbers(
                &plan,
                language,
                &[],
                &[],
                &[],
                &[Some(written.clone())],
            );
            assert_eq!(source, expected, "{language:?}");
            assert!(
                work_plan_source_compiles_cleanly(&source, language),
                "{language:?}: {source}"
            );
            let score = printed_score(&source, language);
            let instruction = &score.instructions[0];
            assert_eq!(instruction.rotation, written.turn, "{source}");
            if let Some(cycle) = &written.cycle {
                assert_eq!(
                    &instruction.arrangement.as_ref().unwrap().color_cycle,
                    cycle,
                    "{source}"
                );
            }
            if let Some(sides) = written.sides {
                assert_eq!(instruction.primitive, inku_score::Primitive::Polygon);
                assert_eq!(instruction.sides, Some(sides), "{source}");
            }
            scores.push(score);
        }
        assert_eq!(scores[0].instructions, scores[1].instructions, "{ja}");
    }
}

/// The color stage writes colors of any number in turn, colors that shift and
/// fades (DDL 23): two colors alternate, three or more repeat in order, colors
/// that shift run once through the marks, and a fade follows the colors in
/// Japanese and ends the English sentence. Each form compiles back to the
/// Score's color cycle and fade in both languages.
#[test]
fn numeric_colors_and_fades_print_where_the_compiler_reads_them() {
    use inku_ddl::FadeDirection;
    use inku_score::Color::{Blue, Orange, Red, White, Yellow};
    use inku_score::Fade;
    let row = Some(NumericPlace::Segment {
        from: [0.1, 0.5],
        to: [0.9, 0.5],
    });
    let column = Some(NumericPlace::Segment {
        from: [0.5, 0.1],
        to: [0.5, 0.9],
    });
    let radius = Some(NumericSize::Radius { radius: 0.03 });
    let circles =
        |attributes: &[(WorkPlanSlot, &str)]| numeric_layer("circle", "line_up", 9, attributes);
    let empty = [(WorkPlanSlot::Surface, "empty")];
    let cases = [
        (
            circles(&empty),
            NumericWriting {
                place: row,
                size: radius,
                cycle: Some(vec![Red, Orange, Yellow]),
                ..NumericWriting::default()
            },
            "画面の横0.1、縦0.5から横0.9、縦0.5まで、赤・橙・黄の順に繰り返して、半径0.03の空の円を9個並べる。",
            "Line up 9 empty circles radius 0.03 from horizontal 0.1, vertical 0.5 to horizontal 0.9, vertical 0.5, repeating red, orange, and yellow in order.",
            vec![Red, Orange, Yellow],
            Fade::None,
        ),
        (
            circles(&empty),
            NumericWriting {
                place: row,
                size: radius,
                cycle: Some(vec![Yellow, Orange, Red]),
                shift: true,
                ..NumericWriting::default()
            },
            "画面の横0.1、縦0.5から横0.9、縦0.5まで、黄・橙・赤の順に段々に移して、半径0.03の空の円を9個並べる。",
            "Line up 9 empty circles radius 0.03 from horizontal 0.1, vertical 0.5 to horizontal 0.9, vertical 0.5, shifting through yellow, orange, and red in order.",
            vec![
                Yellow, Yellow, Yellow, Orange, Orange, Orange, Red, Red, Red,
            ],
            Fade::None,
        ),
        (
            circles(&[
                (WorkPlanSlot::Color, "red"),
                (WorkPlanSlot::Surface, "empty"),
            ]),
            NumericWriting {
                place: row,
                size: radius,
                fade: Some(FadeDirection::LeftToRight),
                ..NumericWriting::default()
            },
            "画面の横0.1、縦0.5から横0.9、縦0.5まで、左から右へ薄れさせて、半径0.03の赤の空の円を9個並べる。",
            "Line up 9 red empty circles radius 0.03 from horizontal 0.1, vertical 0.5 to horizontal 0.9, vertical 0.5, fading from left to right.",
            Vec::new(),
            Fade::Directional,
        ),
        (
            circles(&empty),
            NumericWriting {
                place: row,
                size: radius,
                cycle: Some(vec![White, Blue]),
                fade: Some(FadeDirection::Outward),
                ..NumericWriting::default()
            },
            "画面の横0.1、縦0.5から横0.9、縦0.5まで、白と青を交互にして、中心から外へ薄れさせて、半径0.03の空の円を9個並べる。",
            "Line up 9 empty circles radius 0.03 from horizontal 0.1, vertical 0.5 to horizontal 0.9, vertical 0.5, alternating white and blue, fading outward from the center.",
            vec![White, Blue],
            Fade::Outward,
        ),
        (
            numeric_layer("point", "scatter", 30, &[]),
            NumericWriting {
                place: Some(NumericPlace::Range {
                    bounds: [0.0, 0.0, 1.0, 1.0],
                }),
                cycle: Some(vec![Red, Orange, Yellow]),
                fade: Some(FadeDirection::Outward),
                ..NumericWriting::default()
            },
            "画面の横0〜1、縦0〜1の範囲に、赤・橙・黄の順に繰り返して、中心から外へ薄れさせて、点を30個散らす。",
            "Scatter 30 points in the range horizontal 0 to 1, vertical 0 to 1, repeating red, orange, and yellow in order, fading outward from the center.",
            vec![Red, Orange, Yellow],
            Fade::Outward,
        ),
        (
            circles(&empty),
            NumericWriting {
                place: row,
                size: radius,
                cycle: Some(vec![Red, Orange, Yellow, White]),
                ..NumericWriting::default()
            },
            "画面の横0.1、縦0.5から横0.9、縦0.5まで、赤・橙・黄・白の順に繰り返して、半径0.03の空の円を9個並べる。",
            "Line up 9 empty circles radius 0.03 from horizontal 0.1, vertical 0.5 to horizontal 0.9, vertical 0.5, repeating red, orange, yellow, and white in order.",
            vec![Red, Orange, Yellow, White],
            Fade::None,
        ),
        (
            circles(&empty),
            NumericWriting {
                place: row,
                size: radius,
                cycle: Some(vec![Red, Yellow]),
                shift: true,
                ..NumericWriting::default()
            },
            "画面の横0.1、縦0.5から横0.9、縦0.5まで、赤・黄の順に段々に移して、半径0.03の空の円を9個並べる。",
            "Line up 9 empty circles radius 0.03 from horizontal 0.1, vertical 0.5 to horizontal 0.9, vertical 0.5, shifting through red and yellow in order.",
            vec![Red, Red, Red, Red, Red, Yellow, Yellow, Yellow, Yellow],
            Fade::None,
        ),
        (
            circles(&empty),
            NumericWriting {
                place: row,
                size: radius,
                cycle: Some(vec![Red, Orange, Yellow, White]),
                shift: true,
                ..NumericWriting::default()
            },
            "画面の横0.1、縦0.5から横0.9、縦0.5まで、赤・橙・黄・白の順に段々に移して、半径0.03の空の円を9個並べる。",
            "Line up 9 empty circles radius 0.03 from horizontal 0.1, vertical 0.5 to horizontal 0.9, vertical 0.5, shifting through red, orange, yellow, and white in order.",
            vec![Red, Red, Red, Orange, Orange, Yellow, Yellow, White, White],
            Fade::None,
        ),
        (
            circles(&[
                (WorkPlanSlot::Color, "red"),
                (WorkPlanSlot::Surface, "empty"),
            ]),
            NumericWriting {
                place: row,
                size: radius,
                fade: Some(FadeDirection::RightToLeft),
                ..NumericWriting::default()
            },
            "画面の横0.1、縦0.5から横0.9、縦0.5まで、右から左へ薄れさせて、半径0.03の赤の空の円を9個並べる。",
            "Line up 9 red empty circles radius 0.03 from horizontal 0.1, vertical 0.5 to horizontal 0.9, vertical 0.5, fading from right to left.",
            Vec::new(),
            Fade::Directional,
        ),
        (
            circles(&[
                (WorkPlanSlot::Color, "red"),
                (WorkPlanSlot::Surface, "empty"),
            ]),
            NumericWriting {
                place: column,
                size: radius,
                fade: Some(FadeDirection::TopToBottom),
                ..NumericWriting::default()
            },
            "画面の横0.5、縦0.1から横0.5、縦0.9まで、上から下へ薄れさせて、半径0.03の赤の空の円を9個並べる。",
            "Line up 9 red empty circles radius 0.03 from horizontal 0.5, vertical 0.1 to horizontal 0.5, vertical 0.9, fading from top to bottom.",
            Vec::new(),
            Fade::Directional,
        ),
        (
            circles(&[
                (WorkPlanSlot::Color, "red"),
                (WorkPlanSlot::Surface, "empty"),
            ]),
            NumericWriting {
                place: column,
                size: radius,
                fade: Some(FadeDirection::BottomToTop),
                ..NumericWriting::default()
            },
            "画面の横0.5、縦0.1から横0.5、縦0.9まで、下から上へ薄れさせて、半径0.03の赤の空の円を9個並べる。",
            "Line up 9 red empty circles radius 0.03 from horizontal 0.5, vertical 0.1 to horizontal 0.5, vertical 0.9, fading from bottom to top.",
            Vec::new(),
            Fade::Directional,
        ),
    ];
    for (layer, written, ja, en, cycle, fade) in cases {
        let plan = WorkPlan {
            layers: vec![layer],
            ..WorkPlan::default()
        };
        let mut scores = Vec::new();
        for (language, expected) in [
            (ResolvedInstructionLanguage::Ja, ja),
            (ResolvedInstructionLanguage::En, en),
        ] {
            let source = print_work_plan_with_numbers(
                &plan,
                language,
                &[],
                &[],
                &[],
                &[Some(written.clone())],
            );
            assert_eq!(source, expected, "{language:?}");
            assert!(
                work_plan_source_compiles_cleanly(&source, language),
                "{language:?}: {source}"
            );
            let score = printed_score(&source, language);
            let arrangement = score.instructions[0].arrangement.as_ref().unwrap();
            assert_eq!(arrangement.color_cycle, cycle, "{source}");
            assert_eq!(arrangement.fade, fade, "{source}");
            scores.push(score);
        }
        assert_eq!(scores[0].instructions, scores[1].instructions, "{ja}");
    }
}

/// The fineness and underlayer words (DDL 24) are optional plan fields named
/// as their classes. They are offered on the closed shapes and kept only on a
/// named texture, as an amplitude is kept only with a sway.
#[test]
fn texture_words_are_optional_fields_kept_on_a_named_texture() {
    let schema = work_plan_response_schema();
    let layer = &schema["properties"]["layers"]["items"];
    let required = layer["required"].as_array().unwrap();
    for (field, words) in [
        (
            "fineness",
            json!([
                "unspecified",
                "fine_grained",
                "coarse_grained",
                "packed",
                "sparse"
            ]),
        ),
        ("underlayer", json!(["unspecified", "underpainted"])),
    ] {
        assert_eq!(layer["properties"][field]["enum"], words, "{field}");
        assert!(!required.contains(&json!(field)), "{field}");
    }
    let (plan, diagnostics) = normalize_work_plan(&json!({"layers": [
        {"shape": "circle", "action": "place", "count": 1, "surface": "stipple",
         "fineness": "fine_grained", "underlayer": "underpainted"},
        {"shape": "circle", "action": "place", "count": 1, "surface": "flat",
         "fineness": "packed", "underlayer": "underpainted"},
        {"shape": "line", "action": "draw", "count": 1, "surface": "sweep",
         "fineness": "sparse"},
    ]}));
    let attribute = |layer: usize, slot: WorkPlanSlot| {
        plan.layers[layer].attributes.get(&slot).map(String::as_str)
    };
    assert_eq!(attribute(0, WorkPlanSlot::Fineness), Some("fine_grained"));
    assert_eq!(attribute(0, WorkPlanSlot::Underlayer), Some("underpainted"));
    for (layer, slot) in [
        (1, WorkPlanSlot::Fineness),
        (1, WorkPlanSlot::Underlayer),
        (2, WorkPlanSlot::Fineness),
    ] {
        assert_eq!(attribute(layer, slot), None, "{layer} {slot:?}");
    }
    let reasons: Vec<(Option<usize>, &str, &str)> = diagnostics
        .iter()
        .map(|diagnostic| {
            (
                diagnostic.layer,
                diagnostic.field.as_str(),
                diagnostic.reason,
            )
        })
        .collect();
    assert_eq!(
        reasons,
        vec![
            (Some(1), "fineness", "requires_texture"),
            (Some(1), "underlayer", "requires_texture"),
            (Some(2), "fineness", "unsupported_for_form"),
        ]
    );
}

/// Every closed shape prints each named texture with each fineness, with the
/// underlayer and with both, in both languages, and compiles with no
/// diagnostic. Japanese then writes the handling after the texture, so that
/// two attributive adjectives do not stand in a row.
#[test]
fn texture_words_print_and_compile_cleanly_on_every_closed_shape() {
    let fineness: Vec<String> = work_plan_vocabulary()
        .terms(WorkPlanSlot::Fineness)
        .iter()
        .map(|term| term.id.clone())
        .collect();
    assert_eq!(fineness.len(), 4);
    let layer_of = |shape: &str, words: &[(WorkPlanSlot, &str)]| WorkPlanLayer {
        shape: shape.to_owned(),
        action: "place".to_owned(),
        count: 1,
        attributes: [
            (WorkPlanSlot::Color, "red"),
            (WorkPlanSlot::Tool, "pen"),
            (WorkPlanSlot::Handling, "faint"),
        ]
        .iter()
        .chain(words)
        .map(|(slot, value)| (*slot, (*value).to_owned()))
        .collect(),
        ..WorkPlanLayer::default()
    };
    let mut layers = Vec::new();
    for shape in ["circle", "ellipse", "triangle", "square", "cloudform"] {
        for texture in [
            "sweep",
            "grain",
            "stipple",
            "hatch",
            "crosshatch",
            "aquatint",
        ] {
            let surface = (WorkPlanSlot::Surface, texture);
            let under = (WorkPlanSlot::Underlayer, "underpainted");
            layers.push(layer_of(shape, &[surface, under]));
            for word in &fineness {
                let fine = (WorkPlanSlot::Fineness, word.as_str());
                layers.push(layer_of(shape, &[surface, fine]));
                layers.push(layer_of(shape, &[surface, fine, under]));
            }
        }
    }
    assert_eq!(layers.len(), 5 * 6 * 9);
    common::par_map(&layers, |layer| {
        for language in [
            ResolvedInstructionLanguage::Ja,
            ResolvedInstructionLanguage::En,
        ] {
            let plan = WorkPlan {
                layers: vec![layer.clone()],
                ..WorkPlan::default()
            };
            let source = print_work_plan(&plan, language);
            assert!(
                work_plan_source_compiles_cleanly(&source, language),
                "{language:?}: {source}"
            );
        }
    });
    let plan = WorkPlan {
        layers: vec![layer_of(
            "circle",
            &[
                (WorkPlanSlot::Surface, "stipple"),
                (WorkPlanSlot::Fineness, "fine_grained"),
                (WorkPlanSlot::Underlayer, "underpainted"),
            ],
        )],
        ..WorkPlan::default()
    };
    assert_eq!(
        print_work_plan(&plan, ResolvedInstructionLanguage::Ja),
        "赤のペンの下塗りの細かい点描の薄い円を1個置く。"
    );
    assert_eq!(
        print_work_plan(&plan, ResolvedInstructionLanguage::En),
        "Place one red pen faint underpainted fine-grained stipple circle."
    );
}

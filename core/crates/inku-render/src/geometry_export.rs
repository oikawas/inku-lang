//! Optional read-only geometry boundary. The normal SVG path does not call it.

use serde::Serialize;

use crate::affine::AffineTransform;
use crate::arrangement::{ArrangedCopy, ArrangementRequest, expand_arrangement};
use crate::checked_performance::resolve_checked_performance_with_resources;
use crate::cloudform::{CloudformRequest, generate_cloudform_contour, sample_closed_catmull_rom};
use crate::geometry::{
    crescent_contour_points, open_line_with_variation, point_to_pixels, polygon_points,
    size_to_pixels,
};
use crate::mark_geometry::MarkGeometry;
use crate::marks::{MarkContext, free_line_centerline, free_line_obstacle, mark_style, style_dash};
use crate::performance::PerformanceRequest;
use crate::planning::instruction_anchor_on_canvas;
use crate::support::{DEFAULT_SUPPORT, support_for_ground};
use crate::types::*;
use inku_score::{
    HardResourcePolicy, OperationalResourceBudget, SavedScoreRelationDiagnostic,
    SavedScoreResourceOwner, ScoreExecutionDiagnostic,
};

#[derive(Clone, Debug, Serialize)]
#[serde(tag = "kind", rename_all = "snake_case")]
pub enum GeometryShape {
    Round { center: [f64; 2], radii: [f64; 2] },
    Contour { points: Vec<[f64; 2]> },
    Path { points: Vec<[f64; 2]> },
}

#[derive(Clone, Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct GeometryMark {
    pub source_index: usize,
    pub performed_index: usize,
    pub instance_index: usize,
    pub primitive: Primitive,
    pub shape: GeometryShape,
    /// Canvas-space affine, applied once after the local shape.
    pub transform: [f64; 6],
    pub color: String,
    pub width: f64,
    pub filled: bool,
    pub opacity: f64,
    pub dash: Vec<f64>,
    pub weight: Weight,
    pub clips: Vec<Vec<[f64; 2]>>,
    pub pair_fill: Option<GeometryPairFill>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub appearance: Option<GeometryAppearance>,
}

/// An isolated mark rendered by the existing 2D painter. Bounds use canvas units.
#[derive(Clone, Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct GeometryAppearance {
    pub svg: String,
    pub bounds: [f64; 4],
    pub center: [f64; 2],
}

fn round_appearance(
    instruction: &Instruction,
    geometry: MarkGeometry,
    context: MarkContext<'_>,
    transform: AffineTransform,
    clips: &[Vec<[f64; 2]>],
) -> Result<GeometryAppearance, String> {
    use crate::svg::{Document, Element, format_number};
    let unit = context.canvas.unit();
    let (x, y, width, height) = crate::surface_geometry::mark_bbox(
        geometry,
        instruction,
        MarkContext {
            geometry_transform: AffineTransform::identity(),
            ..context
        },
    )
    .ok_or("invalid_round_appearance")?;
    let corners = [
        (x, y),
        (x + width, y),
        (x + width, y + height),
        (x, y + height),
    ]
    .map(|(x, y)| transform.apply(Point::new(x / unit, y / unit)));
    let x = corners
        .iter()
        .map(|p| p.x * unit)
        .fold(f64::INFINITY, f64::min);
    let y = corners
        .iter()
        .map(|p| p.y * unit)
        .fold(f64::INFINITY, f64::min);
    let width = corners
        .iter()
        .map(|p| p.x * unit)
        .fold(f64::NEG_INFINITY, f64::max)
        - x;
    let height = corners
        .iter()
        .map(|p| p.y * unit)
        .fold(f64::NEG_INFINITY, f64::max)
        - y;
    // Keep the brush fringe and contour variation outside the nominal ellipse.
    let padding = (crate::marks::mark_style(instruction, context).width * 8.0)
        .max(crate::mark_paths::amplitude(instruction, context.canvas) * 2.0)
        .max(width.max(height) * 0.15)
        .max(unit * 0.01);
    let bounds = [
        x - padding,
        y - padding,
        width + padding * 2.0,
        height + padding * 2.0,
    ];
    if bounds.iter().any(|v| !v.is_finite()) || bounds[2] <= 0.0 || bounds[3] <= 0.0 {
        return Err("invalid_round_appearance_bounds".into());
    }
    let mut document = Document::new(CanvasSize {
        width: bounds[2],
        height: bounds[3],
    });
    if context.use_filters {
        if let Some(filter) = crate::materials::texture_filter(instruction.weight, context.canvas) {
            document.push_definition(filter);
        }
    }
    if context.profile != SvgProfile::Compat
        && crate::fills::is_noncomputer_solid_fill(instruction)
        && instruction.weight != Weight::OilPaint
        && !crate::accepted_fills::active(instruction)
    {
        let (id, seed) = crate::fills::solid_mottle_filter_id(instruction, context);
        document.push_definition(crate::fills::solid_mottle_filter(&id, seed));
    }
    for definition in crate::accepted_fills::definitions(instruction, geometry, context) {
        document.push_definition(definition);
    }
    let mut mark =
        crate::marks::render_instruction(instruction, context).map_err(|e| e.to_string())?;
    if let Some(surface) = crate::surfaces::render_surface(instruction, geometry, context) {
        let mut group = Element::new("g");
        group.push(mark);
        group.push(surface.group);
        mark = group;
        for definition in surface.definitions {
            document.push_definition(definition);
        }
    }
    mark = crate::ink_spread::wrap(mark, instruction, context);
    if context.use_filters {
        if let Some(seed) = context.render_seed {
            let (id, filter) = crate::materials::performance_touch_filter(seed, context.canvas);
            document.push_definition(filter);
            mark = Element::new("g")
                .attr("filter", format!("url(#{id})"))
                .with_children(vec![mark.into()]);
        }
    }
    // Each fill scope and the canvas crop operate in final canvas coordinates.
    for (index, contour) in clips.iter().enumerate() {
        let id = format!("appearance-clip-{index}");
        let mut definition = Element::new("clipPath")
            .attr("id", &id)
            .attr("clipPathUnits", "userSpaceOnUse");
        definition.push(
            Element::new("polygon").attr(
                "points",
                contour
                    .iter()
                    .map(|p| {
                        format!(
                            "{},{}",
                            format_number(p[0] * unit),
                            format_number(p[1] * unit)
                        )
                    })
                    .collect::<Vec<_>>()
                    .join(" "),
            ),
        );
        document.push_definition(definition);
        mark = Element::new("g")
            .attr("clip-path", format!("url(#{id})"))
            .with_children(vec![mark.into()]);
    }
    let mut crop = Element::new("clipPath")
        .attr("id", "appearance-canvas")
        .attr("clipPathUnits", "userSpaceOnUse");
    crop.push(
        Element::new("rect")
            .attr("width", format_number(context.canvas.width))
            .attr("height", format_number(context.canvas.height)),
    );
    document.push_definition(crop);
    mark = Element::new("g")
        .attr("clip-path", "url(#appearance-canvas)")
        .with_children(vec![mark.into()]);
    document.push(
        Element::new("g")
            .attr(
                "transform",
                format!(
                    "translate({} {})",
                    format_number(-bounds[0]),
                    format_number(-bounds[1])
                ),
            )
            .with_children(vec![mark.into()]),
    );
    let svg = document.serialize();
    if svg.len() > 2 * 1024 * 1024 {
        return Err("appearance_budget_exceeded".into());
    }
    let center = match geometry {
        MarkGeometry::Circle { center, .. } | MarkGeometry::Ellipse { center, .. } => {
            let center = point_to_pixels(center, context.canvas);
            transform.apply(Point::new(center.x / unit, center.y / unit))
        }
        _ => return Err("invalid_round_appearance".into()),
    };
    Ok(GeometryAppearance {
        svg,
        bounds: bounds.map(|v| v / unit),
        center: [center.x, center.y],
    })
}

#[derive(Clone, Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct GeometryPairFill {
    pub points: Vec<[f64; 2]>,
    pub source_index: usize,
    pub color: String,
    pub opacity: f64,
}

#[derive(Clone, Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct GeometryScene {
    pub canvas: [f64; 2],
    pub background: String,
    pub ground: bool,
    pub marks: Vec<GeometryMark>,
    pub diagnostics: Vec<String>,
    pub recoveries: Vec<GeometryRecovery>,
}

/// Keep the shared performance's recovery decisions alongside the visible marks.
/// A recovered relation does not imply that its source geometry was omitted.
#[derive(Clone, Debug, Serialize)]
#[serde(tag = "kind", rename_all = "snake_case")]
pub enum GeometryRecovery {
    ResourceOmitted {
        owner: SavedScoreResourceOwner,
        cause_owner: SavedScoreResourceOwner,
        reason: String,
    },
    RelationOmitted {
        #[serde(flatten)]
        diagnostic: SavedScoreRelationDiagnostic,
    },
    Execution {
        #[serde(flatten)]
        diagnostic: ScoreExecutionDiagnostic,
    },
}

fn xy(point: Point, unit: f64) -> [f64; 2] {
    [point.x / unit, point.y / unit]
}

fn matrix(transform: AffineTransform) -> [f64; 6] {
    [
        transform.a,
        transform.b,
        transform.c,
        transform.d,
        transform.e,
        transform.f,
    ]
}

/// Resolve the existing performance and expose its geometry in short-side units.
/// Retain independently drawable content, with the same recovery decisions as 2D.
pub fn export_geometry(
    request: &RenderRequest,
    hard: &HardResourcePolicy,
    budget: OperationalResourceBudget,
    maximum_marks: usize,
) -> Result<GeometryScene, String> {
    let canvas = request.options.canvas;
    let unit = canvas.unit();
    if !unit.is_finite() || unit <= 0.0 {
        return Err("invalid_canvas".into());
    }
    request
        .score
        .validate_work_ranges()
        .map_err(|e| format!("invalid_score_range: {e}"))?;
    let plan = resolve_checked_performance_with_resources(
        PerformanceRequest {
            score: &request.score,
            performance_seed: request.options.render_seed,
            composition_seed: request.options.composition_seed,
            canvas: Some(canvas),
        },
        ScoreErrorPolicy::Stop,
        hard,
        budget,
    )
    .map_err(|e| format!("score_execution: {e:?}"))?;
    if plan.score.presence.is_some() {
        return Err("unsupported_presence_layer".into());
    }
    let mut colors = request.options.resolved_color_map.clone();
    let invalid_colors = crate::palette::sanitize_color_map(&mut colors);
    let assignment = crate::palette::work_color_assignment(
        &colors,
        request.options.render_seed,
        request.options.catalog_id.as_deref(),
    );
    let background = crate::palette::resolve_color(
        crate::ground::shown_background(&plan.score).unwrap_or(plan.score.background),
        None,
        &colors,
        &assignment,
    );
    let ground = match &plan.score.canvas {
        Canvas::Spec(spec) => spec
            .ground
            .as_ref()
            .filter(|g| g.material != GroundMaterial::Plain),
        Canvas::Id(_) => None,
    };
    let support = ground
        .as_ref()
        .map_or(DEFAULT_SUPPORT, |g| support_for_ground(g.material));
    let mut recoveries = Vec::new();
    for diagnostic in &plan.resource_diagnostics {
        recoveries.push(GeometryRecovery::ResourceOmitted {
            owner: diagnostic.owner.clone(),
            cause_owner: diagnostic.cause_owner.clone(),
            reason: format!("{:?}", diagnostic.failure),
        });
    }
    for diagnostic in &plan.relation_diagnostics {
        recoveries.push(GeometryRecovery::RelationOmitted {
            diagnostic: diagnostic.clone(),
        });
    }
    if let Some(execution) = &plan.execution {
        recoveries.extend(
            execution
                .diagnostics
                .iter()
                .cloned()
                .map(|diagnostic| GeometryRecovery::Execution { diagnostic }),
        );
    }
    let mut scene = GeometryScene {
        canvas: [canvas.width / unit, canvas.height / unit],
        background,
        ground: ground.is_some(),
        marks: Vec::new(),
        diagnostics: Vec::new(),
        recoveries,
    };
    if !invalid_colors.is_empty() {
        scene.diagnostics.push("invalid_color_defaulted".into());
    }
    if ground.is_some() {
        scene
            .diagnostics
            .push("ground_material_approximated".into());
    }
    let mut ordered = plan
        .performed_instructions()
        .enumerate()
        .collect::<Vec<_>>();
    ordered.sort_by_key(|(_, (i, _))| i.mode_ == InstructionMode::Carve);
    let mut obstacles = Vec::new();
    let mut point_count = 0;
    let mut appearance_bytes = 0usize;
    let oil_fill_pass_limit = crate::fills::oil_fill_pass_limit(&plan.score.instructions);
    for (performed_index, (instruction, performed)) in ordered {
        let copies = if instruction.arrangement.is_some() {
            expand_arrangement(ArrangementRequest {
                instruction,
                placement_seed: request
                    .options
                    .composition_seed
                    .or(request.options.render_seed),
                performance_seed: request.options.render_seed,
                canvas: Some(canvas),
            })
        } else {
            vec![ArrangedCopy {
                instruction: instruction.clone(),
                effects: performed.effects,
            }]
        };
        if scene.marks.len().saturating_add(copies.len()) > maximum_marks {
            return Err("object_budget_exceeded".into());
        }
        for (instance_index, copy) in copies.iter().enumerate() {
            let instruction = &copy.instruction;
            let geometry = MarkGeometry::of(instruction).map_err(|e| e.to_string())?;
            let context = MarkContext {
                canvas,
                color_map: &colors,
                work_assignment: &assignment,
                render_seed: request.options.render_seed,
                instruction_seed_override: performed.seed_override,
                instruction_index: performed.instruction_index,
                mark_index: instance_index,
                wild: request.options.wild,
                use_filters: false,
                profile: SvgProfile::Editable,
                support,
                geometry_transform: performed.transform.in_pixels(unit),
                oil_fill_pass_limit: 0,
                effects: copy.effects,
            };
            let style = mark_style(instruction, context);
            if let Some((_, _, width, height)) =
                crate::surface_geometry::mark_bbox(geometry, instruction, context)
                && !(width.abs() <= crate::render::MAX_MARK_EXTENT * unit
                    && height.abs() <= crate::render::MAX_MARK_EXTENT * unit)
            {
                return Err("mark_extent_exceeded".into());
            }
            let pivot = point_to_pixels(
                instruction_anchor_on_canvas(instruction, Some(canvas)),
                canvas,
            );
            let rotation = AffineTransform::around(
                Point::new(pivot.x / unit, pivot.y / unit),
                1.0,
                1.0,
                instruction.rotation.unwrap_or(0.0),
                Point::new(0.0, 0.0),
            );
            let mut transform = performed.transform.compose(rotation);
            let points = |p: Vec<Point>| p.into_iter().map(|p| xy(p, unit)).collect::<Vec<_>>();
            let shape = match geometry {
                MarkGeometry::Circle { center, radius } => GeometryShape::Round {
                    center: xy(point_to_pixels(center, canvas), unit),
                    radii: [radius, radius],
                },
                MarkGeometry::Ellipse { center, size } => GeometryShape::Round {
                    center: xy(point_to_pixels(center, canvas), unit),
                    radii: [size.x / 2.0, size.y / 2.0],
                },
                MarkGeometry::Square { position, size }
                | MarkGeometry::Triangle { position, size } => {
                    let p = point_to_pixels(position, canvas);
                    let size = size_to_pixels(size, canvas);
                    let vertices = if instruction.primitive == Primitive::Triangle {
                        vec![
                            Point::new(p.x, p.y + size.y),
                            Point::new(p.x + size.x, p.y + size.y),
                            Point::new(p.x + size.x / 2.0, p.y),
                        ]
                    } else {
                        vec![
                            p,
                            Point::new(p.x + size.x, p.y),
                            Point::new(p.x + size.x, p.y + size.y),
                            Point::new(p.x, p.y + size.y),
                        ]
                    };
                    GeometryShape::Contour {
                        points: points(vertices),
                    }
                }
                MarkGeometry::Polygon {
                    center,
                    radius,
                    sides,
                } => GeometryShape::Contour {
                    points: points(polygon_points(
                        point_to_pixels(center, canvas),
                        radius * unit,
                        sides,
                        0.0,
                    )),
                },
                MarkGeometry::Crescent { center, size } => GeometryShape::Contour {
                    points: points(crescent_contour_points(
                        point_to_pixels(center, canvas),
                        size_to_pixels(size, canvas),
                        24,
                    )),
                },
                MarkGeometry::Cloudform { center, size } => {
                    let controls = generate_cloudform_contour(CloudformRequest {
                        center: point_to_pixels(center, canvas),
                        size: size_to_pixels(size, canvas),
                        performance_seed: Some(context.seed_for(instruction)),
                        instruction_index: performed.instruction_index,
                        mark_index: instance_index,
                        variation: instruction.variation.as_ref(),
                        weight: instruction.weight,
                        point_count: 49,
                    });
                    GeometryShape::Contour {
                        points: points(sample_closed_catmull_rom(&controls, 3)),
                    }
                }
                MarkGeometry::FreeLine { from, to } => {
                    transform = AffineTransform::identity();
                    GeometryShape::Path {
                        points: points(
                            free_line_centerline(instruction, from, to, context, &obstacles).0,
                        ),
                    }
                }
                MarkGeometry::Line { from, to } => {
                    let line = if let Some(path) = &performed.line_centerline {
                        transform = AffineTransform::identity();
                        path.iter()
                            .map(|p| Point::new(p.x * unit, p.y * unit))
                            .collect()
                    } else if let Some(variation) = instruction
                        .variation
                        .as_ref()
                        .filter(|v| crate::determinism::needs_path_variation(v))
                    {
                        open_line_with_variation(
                            point_to_pixels(from, canvas),
                            point_to_pixels(to, canvas),
                            variation,
                            context.seed_for(instruction),
                            crate::mark_paths::amplitude(instruction, canvas),
                            canvas,
                        )
                    } else {
                        vec![point_to_pixels(from, canvas), point_to_pixels(to, canvas)]
                    };
                    GeometryShape::Path {
                        points: points(line),
                    }
                }
                MarkGeometry::Arc(arc) => {
                    transform = AffineTransform::identity();
                    GeometryShape::Path {
                        points: points(crate::marks::export_arc_centerline(
                            instruction,
                            arc,
                            context,
                        )),
                    }
                }
            };
            if let Some(obstacle) =
                free_line_obstacle(instruction, geometry, context, performed.transform)
            {
                obstacles.push(obstacle);
            }
            let mut clips = Vec::new();
            let mut scope = performed.fill_scope_index;
            while let Some(index) = scope {
                let fill = &plan.fill_scopes[index];
                clips.push(
                    fill.prepared_region
                        .contour()
                        .iter()
                        .map(|p| xy(*p, unit))
                        .collect(),
                );
                scope = fill.parent_scope_index;
                if clips.len() > 32 {
                    return Err("clip_depth_exceeded".into());
                }
            }
            point_count += match &shape {
                GeometryShape::Round { .. } => 1,
                GeometryShape::Contour { points } | GeometryShape::Path { points } => points.len(),
            };
            point_count += clips.iter().map(Vec::len).sum::<usize>();
            if point_count > 524_288 {
                return Err("geometry_budget_exceeded".into());
            }
            let appearance = if matches!(
                instruction.primitive,
                Primitive::Circle | Primitive::Ellipse
            ) {
                // Geometry requests use Editable, but this isolated raster is
                // the normal on-screen painter, including its material filters.
                let profile = SvgProfile::Display;
                let appearance = round_appearance(
                    instruction,
                    geometry,
                    MarkContext {
                        profile,
                        use_filters: matches!(profile, SvgProfile::Display | SvgProfile::Live),
                        oil_fill_pass_limit,
                        ..context
                    },
                    transform,
                    &clips,
                )?;
                appearance_bytes = appearance_bytes.saturating_add(appearance.svg.len());
                if appearance_bytes > 16 * 1024 * 1024 {
                    return Err("appearance_budget_exceeded".into());
                }
                Some(appearance)
            } else {
                None
            };
            if instruction.variation.is_some() && appearance.is_none() {
                scene.diagnostics.push("variation_approximated".into());
            }
            if appearance.is_none()
                && (instruction.surface.is_some()
                    || instruction.ink_spread.is_some()
                    || instruction.weight != Weight::Rotring)
            {
                scene.diagnostics.push("tool_material_approximated".into());
            }
            scene.marks.push(GeometryMark {
                source_index: performed.original_instruction_index,
                performed_index,
                instance_index,
                primitive: instruction.primitive,
                shape,
                transform: matrix(transform),
                color: style.color,
                width: style.width / unit,
                filled: style.fill,
                opacity: if style.fill {
                    style.fill_opacity.unwrap_or(style.stroke_opacity)
                } else {
                    style.stroke_opacity
                },
                dash: if instruction.style == LineStyle::Solid {
                    vec![]
                } else {
                    style_dash(instruction.style, instruction.weight, 0.001)
                        .unwrap_or_default()
                        .split(',')
                        .filter_map(|s| s.parse::<f64>().ok())
                        .collect()
                },
                weight: instruction.weight,
                clips,
                pair_fill: None,
                appearance,
            });
        }
    }
    // The two strokes keep their identities; the closed interior belongs to
    // their leader and records the follower as a second source.
    for (leader, performed) in plan.performed.iter().enumerate() {
        let Some(follower) = performed.closed_arc_pair_follower else {
            continue;
        };
        let Some(first_index) = scene.marks.iter().position(|m| m.performed_index == leader) else {
            continue;
        };
        let Some(second) = scene.marks.iter().find(|m| m.performed_index == follower) else {
            continue;
        };
        let instruction = &plan.score.instructions[follower];
        if !crate::accepted_fills::solid_fill(instruction) {
            continue;
        }
        let (
            GeometryShape::Path { points: first },
            GeometryShape::Path {
                points: second_points,
            },
        ) = (&scene.marks[first_index].shape, &second.shape)
        else {
            return Err("unsupported_closed_arc_pair".into());
        };
        if first.len() < 2 || second_points.len() < 2 {
            return Err("invalid_closed_arc_pair".into());
        }
        let distance = |a: [f64; 2], b: [f64; 2]| (a[0] - b[0]).hypot(a[1] - b[1]);
        let same = distance(first[0], second_points[0])
            + distance(*first.last().unwrap(), *second_points.last().unwrap());
        let opposite = distance(first[0], *second_points.last().unwrap())
            + distance(*first.last().unwrap(), second_points[0]);
        let mut boundary = second_points.clone();
        if same <= opposite {
            boundary.reverse();
        }
        let mut contour = first.clone();
        contour.extend(boundary.into_iter().skip(1));
        let fill = GeometryPairFill {
            points: contour,
            source_index: second.source_index,
            color: second.color.clone(),
            opacity: second.opacity,
        };
        scene.marks[first_index].pair_fill = Some(fill);
    }
    if scene.marks.is_empty() && !scene.ground {
        return Err("no_drawable_content".into());
    }
    scene.diagnostics.sort();
    scene.diagnostics.dedup();
    Ok(scene)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::collections::BTreeMap;

    // Failure: outlined rounds receive extra latitude/longitude bands in 3D.
    #[test]
    fn outlined_rounds_export_the_single_painted_outline() {
        let score: Score = serde_json::from_str(r#"{
            "version":"0.1.0","canvas":"square","background":"white","instructions":[
                {"primitive":"circle","center":[0.3,0.5],"radius":0.12,"filled":false,"weight":"rotring"},
                {"primitive":"ellipse","center":[0.7,0.5],"size":[0.2,0.1],"filled":false,"weight":"rotring"},
                {"primitive":"point","center":[0.5,0.8],"radius":0.002,"filled":true,"weight":"rotring"}
            ]}"#).unwrap();
        let request = RenderRequest {
            score,
            options: RenderOptions {
                resolved_color_map: BTreeMap::new(),
                catalog_id: None,
                canvas: CanvasSize::new(1000.0, 1000.0),
                canvas_aspect_id: "square".into(),
                svg_profile: SvgProfile::Editable,
                render_seed: Some(163717),
                composition_seed: None,
                wild: false,
                error_policy: ScoreErrorPolicy::Stop,
            },
        };
        let budget = inku_score::ResourceBudget {
            maximum: inku_score::ResourceDemand {
                logical_objects: 16,
                primitive_marks: 16,
                object_templates: 16,
                maximum_per_template_primitive_marks: 16,
                maximum_resolved_count: 16,
                template_nodes: 16,
                anchor_instances: 16,
                transform_instances: 16,
                placement_instances: 16,
                fill_instances: 16,
            },
        };
        let hard = HardResourcePolicy {
            identity: "round-appearance-test".into(),
            budget,
        };
        let scene =
            export_geometry(&request, &hard, OperationalResourceBudget(budget), 16).unwrap();
        assert_eq!(scene.marks.len(), 3);
        assert!(!scene.marks[0].filled && !scene.marks[1].filled);
        assert_eq!(
            scene.marks[0]
                .appearance
                .as_ref()
                .unwrap()
                .svg
                .matches("<circle")
                .count(),
            1
        );
        assert_eq!(
            scene.marks[1]
                .appearance
                .as_ref()
                .unwrap()
                .svg
                .matches("<ellipse")
                .count(),
            1
        );
        assert!(scene.marks[2].appearance.is_none());
    }

    // Failure: the saved work's dense oil circle becomes an ideal, uniform ball.
    #[test]
    fn round_appearance_keeps_isolated_dense_oil_passes() {
        let instruction: Instruction = serde_json::from_str(
            r#"{"primitive":"circle","center":[0.5,0.5],"radius":0.12,"color":"red","filled":true,"style":"solid","weight":"oil_paint","surface_intensity":"dense"}"#,
        ).unwrap();
        let colors = BTreeMap::from([("red".into(), "#bf3221".into())]);
        let assignment = BTreeMap::new();
        let context = MarkContext {
            canvas: CanvasSize::new(1000.0, 1000.0),
            color_map: &colors,
            work_assignment: &assignment,
            render_seed: Some(163717),
            instruction_seed_override: None,
            instruction_index: 4,
            mark_index: 0,
            wild: false,
            use_filters: true,
            profile: SvgProfile::Display,
            support: DEFAULT_SUPPORT,
            geometry_transform: AffineTransform::identity(),
            oil_fill_pass_limit: crate::fills::oil_fill_pass_limit(std::slice::from_ref(
                &instruction,
            )),
            effects: Default::default(),
        };
        let geometry = MarkGeometry::of(&instruction).unwrap();
        let first = round_appearance(
            &instruction,
            geometry,
            context,
            AffineTransform::identity(),
            &[],
        )
        .unwrap();
        let second = round_appearance(
            &instruction,
            geometry,
            context,
            AffineTransform::identity(),
            &[],
        )
        .unwrap();
        assert_eq!(first.svg, second.svg);
        assert_eq!(first.center, [0.5, 0.5]);
        assert!(first.bounds[0] < 0.38 && first.bounds[0] + first.bounds[2] > 0.62);
        assert!(first.svg.matches("oil-paint-body-v1").count() > 10);
        assert!(first.svg.contains("#bf3221"));
        assert!(!first.svg.contains("<circle"));
        assert!(!first.svg.contains("href="));
        assert!(!first.svg.contains("<image"));
        assert!(!first.svg.contains("layer_00_background"));
        assert!(first.svg.len() < 2 * 1024 * 1024);
    }
}

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
use inku_score::{HardResourcePolicy, OperationalResourceBudget};

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
/// Refuse partial execution rather than presenting an incomplete scene as whole.
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
    if !plan.resource_diagnostics.is_empty()
        || !plan.relation_diagnostics.is_empty()
        || plan
            .execution
            .as_ref()
            .is_some_and(|e| !e.diagnostics.is_empty())
    {
        return Err("score_execution_omitted_content".into());
    }
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
    let mut scene = GeometryScene {
        canvas: [canvas.width / unit, canvas.height / unit],
        background,
        ground: ground.is_some(),
        marks: Vec::new(),
        diagnostics: Vec::new(),
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
            if instruction.variation.is_some() {
                scene.diagnostics.push("variation_approximated".into());
            }
            if instruction.surface.is_some()
                || instruction.ink_spread.is_some()
                || instruction.weight != Weight::Rotring
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

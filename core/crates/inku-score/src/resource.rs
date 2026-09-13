//! Host-neutral resource units. These are counts, not SVG-node or runtime estimates.

use serde::{Deserialize, Serialize};

pub const RESOURCE_ACCOUNTING_ID: &str = "inku.resource-accounting.v1";

#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ResourceDimension {
    LogicalObjects,
    PrimitiveMarks,
    ObjectTemplates,
    MaximumPerTemplatePrimitiveMarks,
    MaximumResolvedCount,
    TemplateNodes,
    AnchorInstances,
    TransformInstances,
    PlacementInstances,
    FillInstances,
}

impl ResourceDimension {
    pub const ALL: [Self; 10] = [
        Self::LogicalObjects,
        Self::PrimitiveMarks,
        Self::ObjectTemplates,
        Self::MaximumPerTemplatePrimitiveMarks,
        Self::MaximumResolvedCount,
        Self::TemplateNodes,
        Self::AnchorInstances,
        Self::TransformInstances,
        Self::PlacementInstances,
        Self::FillInstances,
    ];
}

/// Exact structural demand before materialization. Appearance work and renderer
/// allocations require their own accounting; a primitive mark is not an SVG node.
#[derive(Clone, Copy, Debug, Default, Eq, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ResourceDemand {
    /// Outer source occurrences: each complete Macro body counts as one object.
    pub logical_objects: u64,
    /// Actual drawable marks, including internal and outer repetitions.
    pub primitive_marks: u64,
    /// Stored drawable recipes (each Macro Emit is a separate template).
    pub object_templates: u64,
    /// Largest per-template mark demand after all outer repetitions.
    pub maximum_per_template_primitive_marks: u64,
    /// Largest object internal count or member outer count, without clamping.
    pub maximum_resolved_count: u64,
    /// Source object, anchor, transform, placement and fill nodes, before repetition.
    pub template_nodes: u64,
    pub anchor_instances: u64,
    pub transform_instances: u64,
    pub placement_instances: u64,
    pub fill_instances: u64,
}

impl ResourceDemand {
    pub const fn get(self, dimension: ResourceDimension) -> u64 {
        match dimension {
            ResourceDimension::LogicalObjects => self.logical_objects,
            ResourceDimension::PrimitiveMarks => self.primitive_marks,
            ResourceDimension::ObjectTemplates => self.object_templates,
            ResourceDimension::MaximumPerTemplatePrimitiveMarks => {
                self.maximum_per_template_primitive_marks
            }
            ResourceDimension::MaximumResolvedCount => self.maximum_resolved_count,
            ResourceDimension::TemplateNodes => self.template_nodes,
            ResourceDimension::AnchorInstances => self.anchor_instances,
            ResourceDimension::TransformInstances => self.transform_instances,
            ResourceDimension::PlacementInstances => self.placement_instances,
            ResourceDimension::FillInstances => self.fill_instances,
        }
    }

    /// Sum additive dimensions with checked arithmetic; merge peak dimensions
    /// by maximum. Shared by plan and future saved-Score accounting.
    pub fn checked_add(self, other: Self) -> Result<Self, ResourceDimension> {
        let add = |dimension| {
            self.get(dimension)
                .checked_add(other.get(dimension))
                .ok_or(dimension)
        };
        Ok(Self {
            logical_objects: add(ResourceDimension::LogicalObjects)?,
            primitive_marks: add(ResourceDimension::PrimitiveMarks)?,
            object_templates: add(ResourceDimension::ObjectTemplates)?,
            maximum_per_template_primitive_marks: self
                .maximum_per_template_primitive_marks
                .max(other.maximum_per_template_primitive_marks),
            maximum_resolved_count: self
                .maximum_resolved_count
                .max(other.maximum_resolved_count),
            template_nodes: add(ResourceDimension::TemplateNodes)?,
            anchor_instances: add(ResourceDimension::AnchorInstances)?,
            transform_instances: add(ResourceDimension::TransformInstances)?,
            placement_instances: add(ResourceDimension::PlacementInstances)?,
            fill_instances: add(ResourceDimension::FillInstances)?,
        })
    }
}

/// Explicit maxima in RESOURCE_ACCOUNTING_ID units. No installation default is implied.
#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ResourceBudget {
    pub maximum: ResourceDemand,
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct HardResourcePolicy {
    /// Caller-owned versioned policy identity; this module selects no policy.
    pub identity: String,
    pub budget: ResourceBudget,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(transparent)]
pub struct OperationalResourceBudget(pub ResourceBudget);

#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ResourceAuthority {
    HardPolicy,
    OperationalBudget,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize, Deserialize)]
pub struct ResourceBudgetExceeded {
    pub authority: ResourceAuthority,
    pub dimension: ResourceDimension,
    pub required: u64,
    pub maximum: u64,
}

impl ResourceBudget {
    pub fn check(
        self,
        demand: ResourceDemand,
        authority: ResourceAuthority,
    ) -> Result<(), ResourceBudgetExceeded> {
        for dimension in ResourceDimension::ALL {
            let required = demand.get(dimension);
            let maximum = self.maximum.get(dimension);
            if required > maximum {
                return Err(ResourceBudgetExceeded {
                    authority,
                    dimension,
                    required,
                    maximum,
                });
            }
        }
        Ok(())
    }
}

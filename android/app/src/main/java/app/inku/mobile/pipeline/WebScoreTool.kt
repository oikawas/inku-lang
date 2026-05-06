package app.inku.mobile.pipeline

import app.inku.mobile.llm.ModelTool

internal object WebScoreTool {
    val submitScore = ModelTool(
        name = "submit_score",
        description = "正規化DDLから導出した JSON Score を提出する。",
        parametersJson = """
            {
              "type": "object",
              "additionalProperties": false,
              "properties": {
                "version": {"type": "string"},
                "canvas": {"type": "string"},
                "background": {"type": "string", "enum": ["white", "black", "blue", "red", "green", "gray"]},
                "presence": {
                  "type": "object",
                  "additionalProperties": false,
                  "properties": {
                    "kind": {"type": "string", "enum": ["none", "figure_like", "creature_like", "group_like"]},
                    "intensity": {"type": "string", "enum": ["low", "medium", "high"]},
                    "center": {"type": "array", "items": {"type": "number"}, "minItems": 2, "maxItems": 2},
                    "symmetry": {"type": "string", "enum": ["none", "bilateral", "radial"]},
                    "gaze_pressure": {"type": "string", "enum": ["none", "low", "medium", "high"]},
                    "contour_density": {"type": "string", "enum": ["low", "medium", "high"]}
                  }
                },
                "instructions": {
                  "type": "array",
                  "items": {
                    "type": "object",
                    "additionalProperties": false,
                    "properties": {
                      "primitive": {"type": "string", "enum": ["line", "circle", "ellipse", "triangle", "square", "polygon", "arc"]},
                      "from": {"type": "array", "items": {"type": "number"}, "minItems": 2, "maxItems": 2},
                      "to": {"type": "array", "items": {"type": "number"}, "minItems": 2, "maxItems": 2},
                      "center": {"type": "array", "items": {"type": "number"}, "minItems": 2, "maxItems": 2},
                      "radius": {"type": "number"},
                      "sides": {"type": "integer", "minimum": 5, "maximum": 8},
                      "position": {"type": "array", "items": {"type": "number"}, "minItems": 2, "maxItems": 2},
                      "size": {"type": "array", "items": {"type": "number"}, "minItems": 2, "maxItems": 2},
                      "angle_start": {"type": "number"},
                      "angle_end": {"type": "number"},
                      "rotation": {"type": "number"},
                      "filled": {"type": "boolean"},
                      "style": {"type": "string", "enum": ["solid", "dashed", "dotted", "dash_dot"]},
                      "weight": {"type": "string", "enum": ["hair", "pencil", "pen", "rotring", "crayon", "chalk", "brush_thin", "brush_thick", "rope"]},
                      "color": {"type": "string", "enum": ["white", "black", "blue", "red", "green", "gray"]},
                      "color_hint": {"type": "string"},
                      "variation": {
                        "type": "object",
                        "additionalProperties": false,
                        "properties": {
                          "amplitude": {"type": "string", "enum": ["fine", "medium", "broad"]},
                          "frequency": {"type": "string", "enum": ["slow", "medium", "high"]},
                          "quality": {"type": "string", "enum": ["none", "white", "perlin", "pink", "wave"]},
                          "dimensions": {
                            "type": "array",
                            "items": {"type": "string", "enum": ["position_x", "position_y", "angle", "length", "thickness", "rotation", "radius"]}
                          }
                        }
                      },
                      "arrangement": {
                        "type": "object",
                        "additionalProperties": false,
                        "properties": {
                          "count": {"type": "integer", "minimum": 1, "maximum": 1000},
                          "layout": {"type": "string", "enum": ["horizontal", "vertical", "radial", "scatter"]},
                          "path": {"type": "string", "enum": ["none", "diagonal", "wave", "top_to_bottom", "left_to_right", "right_half"]},
                          "color_cycle": {
                            "type": "array",
                            "items": {"type": "string", "enum": ["white", "black", "blue", "red", "green", "gray"]}
                          },
                          "margin": {"type": "number", "minimum": 0.0, "maximum": 0.45},
                          "center": {"type": "array", "items": {"type": "number"}, "minItems": 2, "maxItems": 2},
                          "radius": {"type": "number"},
                          "density": {"type": "string", "enum": ["none", "low", "medium", "high"]},
                          "cluster_count": {"type": "integer", "minimum": 1, "maximum": 12},
                          "fade": {"type": "string", "enum": ["none", "outward", "directional"]},
                          "preserve_space": {"type": "boolean"}
                        }
                      }
                    },
                    "required": ["primitive"]
                  }
                }
              },
              "required": ["instructions"]
            }
        """.trimIndent(),
    )
}

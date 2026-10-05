import Foundation
import InkuCore

private struct CheckFailure: Error {
    let reason: String
}

@main
enum CoreCheck {
    static func require(_ condition: Bool, _ reason: String) throws {
        if !condition { throw CheckFailure(reason: reason) }
    }

    static func object(_ bytes: Data) throws -> [String: Any] {
        guard let value = try JSONSerialization.jsonObject(with: bytes) as? [String: Any] else {
            throw CheckFailure(reason: "expected an object")
        }
        if let error = value["error"] {
            throw CheckFailure(reason: "core refused: \(error): \(value["message"] ?? "")")
        }
        return value
    }

    static func bytes(_ value: [String: Any]) throws -> Data {
        try JSONSerialization.data(withJSONObject: value, options: [.sortedKeys])
    }

    static func main() throws {
        let versions = try object(Data(InkuCore.versionReport.utf8))
        try require(versions["binding_version"] as? String == "1.1.0", "binding identity mismatch")
        try require(versions["protocol_version"] as? String == "1.0.0", "protocol identity mismatch")
        let registry = try object(InkuCore.canvasRegistry)
        guard let digest = registry["digest"] as? String else {
            throw CheckFailure(reason: "missing canonical registry digest")
        }

        // This is a bounded fixture policy, not a default chosen for a user execution.
        let budget: [String: Any] = ["maximum": [
            "logical_objects": 400, "primitive_marks": 400, "object_templates": 64,
            "maximum_per_template_primitive_marks": 240, "maximum_resolved_count": 2000,
            "template_nodes": 512, "anchor_instances": 400, "transform_instances": 400,
            "placement_instances": 400, "fill_instances": 400,
        ]]
        let seed = "18446744073709551615"
        let palette = try object(InkuCore.resolvePalette(try bytes([
            "color_map": [:], "catalog_id": "default", "render_seed": seed, "background": "white",
        ])))
        let compiler: [String: Any] = [
            "host": [
                "canvas_format_id": "square", "canvas_format_registry_id": "inku.canvas-format-registry.v1",
                "canvas_format_registry_digest": digest, "resolved_catalog_id": "default",
                "catalog_mode": "default", "background": "white", "palette": palette,
            ],
            "composition_seed": seed,
            "macro_expansion_limits": [
                "max_invocations": "16", "max_depth": "16", "max_evaluation_steps": "1000",
                "max_nodes_per_invocation": "100", "max_total_nodes": "500",
            ],
            "stage15_variation": NSNull(), "error_policy": "omit_and_continue",
            "hard_resource_policy": ["identity": "apple.core-check.v1", "budget": budget],
            "operational_resource_budget": budget,
        ]
        let compileInput = try bytes([
            "document": [
                "source": "place one red circle at center.", "language": "en",
                "macro_locks": [], "saijiki": "inku.saijiki.v2",
            ],
            "definitions": [], "compiler": compiler,
        ])
        let delivery = try object(InkuCore.compile(compileInput))
        let repeated = try object(InkuCore.compile(compileInput))
        guard let score = delivery["score"] as? [String: Any],
              let instructions = score["instructions"] as? [Any],
              let scoreDigest = delivery["score_digest"] as? String,
              let returnedCompiler = delivery["compiler_options"] as? [String: Any]
        else { throw CheckFailure(reason: "no compiled Score: \(delivery)") }
        try require(!instructions.isEmpty, "compiled Score has no marks")
        try require(returnedCompiler["composition_seed"] as? String == seed, "seed was rounded")
        try require(repeated["score_digest"] as? String == scoreDigest, "compile changed a fixed seed")

        let options: [String: Any] = [
            "resolved_color_map": [:], "catalog_id": "default",
            "canvas": ["width": 256, "height": 256], "canvas_aspect_id": "square",
            "svg_profile": "display", "render_seed": seed, "composition_seed": seed,
            "wild": false, "error_policy": "omit_and_continue",
        ]
        let clip: [String: Any] = [
            "tolerance_pixels": 0.1, "max_nodes": "50000", "max_path_elements": "200000",
            "max_flattened_points": "200000", "max_work": "10000000", "max_output_vertices": "200000",
        ]
        let rendered = try object(InkuCore.renderCompiled(try bytes([
            "delivery": delivery, "options": options, "compiler": compiler, "clip": clip,
        ])))
        guard let svg = rendered["svg"] as? String else {
            throw CheckFailure(reason: "missing SVG")
        }
        let artwork = try InkuCore.rasterize(svg: svg, targetWidth: 64, targetHeight: 64)
        try require(artwork.width == 64 && artwork.height == 64, "wrong artwork geometry")
        try require(artwork.makeCGImage() != nil, "owned raster did not form a CGImage")

        let redSVG = #"<svg xmlns="http://www.w3.org/2000/svg" width="2" height="1"><rect width="2" height="1" fill="red"/></svg>"#
        let owned = try InkuCore.rasterize(svg: redSVG, targetWidth: 2)
        _ = try InkuCore.rasterize(svg: svg, targetWidth: 8)
        try require(owned.pixels == Data([255, 0, 0, 255, 255, 0, 0, 255]), "pixels lost ownership or byte order")
        try require(owned.stride == 8 && owned.pixelFormat == "rgba8-premultiplied", "wrong raster layout")
        do {
            _ = try InkuCore.rasterize(svg: redSVG, targetWidth: 0)
            throw CheckFailure(reason: "zero raster width was accepted")
        } catch CoreFailure.rasterRefused(let code, _) {
            try require(code == "invalid_target_dimension", "wrong raster refusal")
        }
        let invalid = try JSONSerialization.jsonObject(with: InkuCore.compile(Data("{".utf8))) as? [String: Any]
        try require(invalid?["error"] as? String == "invalid_compile_input", "malformed compile escaped the boundary")
        print("InkuCoreCheck OK binding=1.1.0 protocol=1.0.0 raster=\(InkuCore.rasterAPIVersion)")
        print("DDL -> Score(\(instructions.count) instructions, \(scoreDigest)) -> SVG(\(svg.utf8.count) bytes) -> RGBA(\(artwork.width)x\(artwork.height), \(artwork.pixels.count) owned bytes)")
        print("UInt64.max seed preserved; owned pixels and typed error checked; native CGImage created.")
    }
}

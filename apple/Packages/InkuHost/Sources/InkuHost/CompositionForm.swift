import Foundation

/// The composition forms a "change the composition form" refinement may ask for (Web `composition-form.ts`
/// `COMPOSITION_FORMS`, Server `pipeline_product.py`). The core decides the form from them through
/// `authoring.composition.form`.
public enum CompositionForm {
    public static let all = ["one_corner", "all_over", "bands", "dividing_line", "grid", "flock_and_stray", "unequal_triangle"]
    public static let derivationKind = "composition_form_change"

    /// Server `pipeline_product.py`: a form is accepted only when drawing in words with composition on, and only one
    /// of the seven.
    static func validate(_ request: GenerationRequest) throws {
        guard let form = request.descriptionCompositionForm else { return }
        guard case .description = request.authoring, request.drawRoute == "read_and_draw",
              request.descriptionComposition == true, all.contains(form) else {
            throw HostError("invalid_authoring_options")
        }
    }
}

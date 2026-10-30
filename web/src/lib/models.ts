export type Provider = string;

export type ModelOption = {
	id: string;
	qualified_id?: string;
	label: string;
	selection?: {
		unselectable: boolean;
		unsupported: Record<'llm' | 'vision', boolean>;
		levels: Record<'none' | 'llm' | 'vision', Record<'none' | 'stage1' | 'stage2' | 'both', number>>;
		sort_keys: Record<'none' | 'llm' | 'vision', Record<'none' | 'stage1' | 'stage2' | 'both', string>>;
	};
	notes?: string;
	purposes?: ('llm' | 'vision')[];
	// Purposes the model was measured not to answer (2026-10-13). The server keeps
	// them out of purposes unless an administrator chose them anyway.
	unsupported_purposes?: ('llm' | 'vision')[];
	// The purposes an administrator chose against the measurement, as not
	// recommended (the author, 2026-10-26). The server keeps only these of them.
	allowed_unsupported_purposes?: ('llm' | 'vision')[];
	// Left out of the benchmark as a kind inku does not draw with (2026-10-13).
	// Not published; model administration folds it away.
	not_supported?: boolean;
	// An older generation the provider has superseded (2026-10-13). It can still be
	// published; model administration folds it away as an older model.
	legacy?: boolean;
	// Every label of the model and the fold it is filed in, worked out by the Server from
	// the model catalog's label table (ModelLabel, 2026-10-13). The marks above stay for
	// an older reader.
	labels?: string[];
	fold?: string | null;
	enabled?: boolean;
	// v1.98: Recommendations are per purpose; recommendation_level reads the legacy format.
	recommendation_llm?: number;
	recommendation_vision?: number;
	recommendation_level?: number;
	// Stage-specific recommendations narrow recommendation_llm rather than replace it.
	// End-to-end measurements (all NVIDIA and Ollama Cloud models) have one value
	// read by both stages; local Ollama models are measured separately per stage.
	recommendation_stage1?: number;
	recommendation_stage2?: number;
	speed_class?: string;
	speed_label?: string;
	// Measured reference numbers (2026-10-13): approximate USD for one drawing and
	// for one Vision image, and the mean seconds each took. Absent means not measured.
	cost_usd_llm?: number;
	cost_usd_vision?: number;
	speed_llm_seconds?: number;
	speed_vision_seconds?: number;
	comment_ja?: string;
	comment_en?: string;
	// v1.98: A provider-retired model remains listed but cannot start a new drawing.
	eol?: boolean;
	eol_date?: string;
	// A model limited to the provider's paid tier. It is unselectable like EOL,
	// but the reason is subscription access rather than retirement.
	requires_subscription?: boolean;
};

// One row of the model catalog's label table (`model_labels` in every model list), in
// fold order.
export type ModelLabel = {
	id: string;
	ja: string;
	en: string;
	publishable: boolean;
};

export type ProviderGroup = {
	id: Provider;
	label: string;
	kind?: string;
	builtin?: boolean;
	requires_api_key?: boolean;
	memo?: string;
	models: ModelOption[];
};

// The API supplies model-reference decisions from core.
import { modelReference } from './modelReferences';

export const DEFAULT_PROVIDER: Provider = 'nvidia';
export const DEFAULT_MODEL = 'google/gemma-4-31b-it';
export function qualifiedModelRef(provider: Provider, ref: string): string {
    if (!provider || !ref) return ref || '';
    return modelReference({action:'qualify_ref', provider, ref})?.ref ?? '';
}
export function splitModelReference(ref: string, _groups?: ProviderGroup[]): {provider: Provider | null; model: string} {
    const answer = modelReference({action:'split_ref', ref});
    return {provider: answer?.provider ?? null, model: answer?.model ?? ref};
}
export function displayModelReference(ref: string, _groups?: ProviderGroup[], defaultProvider?: Provider): {provider: Provider; model: string; providerLabel: string} {
    const answer = modelReference({action:'resolve_display', ref, default_provider: defaultProvider});
    return {provider: answer?.provider ?? '', model: answer?.model ?? ref, providerLabel: answer?.provider_label ?? ''};
}
export function modelDisplayName(ref: string | null | undefined, _groups?: ProviderGroup[], defaultProvider?: Provider): string {
	ref = ref?.trim();
	if (!ref) return '';
    const answer = modelReference({action:'resolve_display', ref, default_provider: defaultProvider});
    if (!answer) return ref;
    return answer.provider_label ? `${answer.provider_label} / ${answer.model_label}` : (answer.model_label ?? ref);
}
export function modelShortName(ref: string | null | undefined, _groups?: ProviderGroup[], defaultProvider?: Provider): string {
	ref = ref?.trim();
	if (!ref) return '';
    const answer = modelReference({action:'resolve_display', ref, default_provider: defaultProvider});
    const name = answer?.model_label ?? ref;
    const slash = name.indexOf('/');
    return slash === -1 ? name : name.slice(slash + 1);
}
export type PickerSelection = {
    groups: ProviderGroup[];
    selected: {group: ProviderGroup; model: ModelOption} | null;
    notInList: boolean;
};
export function pickerSelection(providerGroups: ProviderGroup[], selectedModel: string): PickerSelection {
    const groups = providerGroups.filter((group) => group.models.length > 0);
    for (const group of groups) {
        const model = group.models.find((item) => item.id === selectedModel || item.qualified_id === selectedModel);
        if (model) return {groups, selected:{group, model}, notInList:false};
    }
    return {groups, selected:null, notInList:selectedModel.trim() !== ''};
}

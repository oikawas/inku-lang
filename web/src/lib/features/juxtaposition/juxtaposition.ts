/**
 * Juxtaposition: a sentence from the author's other works, added after a work's
 * description. The server offers four; the author chooses one, and the work is
 * redrawn from the longer description through the ordinary description edit.
 */

export type JuxtapositionChoice = {
	sentence: string;
	reason: string;
	history_ids: string[];
	rank: number;
	/** Where the sentence stood in the shuffled list the model read: 0 the head, 1 the tail. */
	position: number;
};

export type JuxtapositionResult = { choices: JuxtapositionChoice[]; candidates: number; model: string };

const SENTENCE_END = /[。！？」』.!?]$/;
const JAPANESE = /[぀-ヿ㐀-鿿]/;

/** The description with the sentence after it. A description that ends without a
 *  stop -- a poem, or one ending in a label -- gets one, so the two do not run on. */
export function joinJuxtaposition(text: string, sentence: string): string {
	const base = text.trim();
	const added = sentence.trim();
	if (!base || !added) return base || added;
	const japanese = JAPANESE.test(base);
	if (SENTENCE_END.test(base)) return japanese ? base + added : `${base} ${added}`;
	return japanese ? `${base}。${added}` : `${base}. ${added}`;
}

/** What the child records. The server reads `sentence` back from the lineage so
 *  that the same sentence is not offered again further down it. */
export function juxtapositionMetadata(choice: JuxtapositionChoice, result: JuxtapositionResult): { juxtaposition: Record<string, unknown> } {
	return {
		juxtaposition: {
			sentence: choice.sentence,
			history_ids: [...choice.history_ids],
			rank: choice.rank,
			reason: choice.reason,
			position: choice.position,
			candidates: result.candidates,
			model: result.model
		}
	};
}

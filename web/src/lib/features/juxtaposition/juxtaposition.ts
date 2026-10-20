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
	/** The work's description with the sentence after it, joined by the shared core's rule
	 *  (a description that ends without a stop gets one), labels and all. */
	joined: string;
};

export type JuxtapositionResult = { choices: JuxtapositionChoice[]; candidates: number; model: string };

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

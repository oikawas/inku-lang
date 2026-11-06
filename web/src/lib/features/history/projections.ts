export type HistoryStarProjection = {
	id?: string;
	starred?: boolean;
	note?: string | null;
};

export type HistoryForRevisionProjection = {
	id?: string;
	for_revision?: boolean;
};

export type HistoryForShareProjection = {
	id?: string;
	for_share?: boolean;
	share_group_id?: string | null;
};

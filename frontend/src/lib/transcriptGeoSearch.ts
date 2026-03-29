export const DEFAULT_TRANSCRIPT_MAP_CENTER = {
	lat: 41.8781,
	lng: -87.6298,
};

export const DEFAULT_TRANSCRIPT_MAP_ZOOM = 10;

export const DEFAULT_TRANSCRIPT_MAP_BOUNDING_BOX =
	"41.45,-88.05,42.1,-87.35";

export interface TranscriptBoundsLike {
	getSouth: () => number;
	getWest: () => number;
	getNorth: () => number;
	getEast: () => number;
}

export function formatInsideBoundingBox(bounds: TranscriptBoundsLike): string {
	return [
		bounds.getSouth(),
		bounds.getWest(),
		bounds.getNorth(),
		bounds.getEast(),
	].join(",");
}

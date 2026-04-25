function parseNumber(value: string | undefined): number | null {
	if (!value) {
		return null;
	}

	const parsed = Number.parseFloat(value);
	return Number.isFinite(parsed) ? parsed : null;
}

function parseLatLng(value: string | undefined): { lat: number; lng: number } | null {
	if (!value) {
		return null;
	}

	const [latRaw, lngRaw] = value.split(",", 2).map((part) => part.trim());
	const lat = parseNumber(latRaw);
	const lng = parseNumber(lngRaw);
	if (lat === null || lng === null) {
		return null;
	}

	return { lat, lng };
}

function parseBoundingBox(value: string | undefined): string | null {
	if (!value) {
		return null;
	}

	const parts = value.split(",").map((part) => part.trim());
	if (parts.length !== 4) {
		return null;
	}

	const numeric = parts.map((part) => parseNumber(part));
	if (numeric.some((entry) => entry === null)) {
		return null;
	}

	return numeric.join(",");
}

const DEFAULT_CENTER_FALLBACK = {
	lat: 39.8283,
	lng: -98.5795,
};

const DEFAULT_ZOOM_FALLBACK = 4;

const DEFAULT_BOUNDING_BOX_FALLBACK =
	"24.396308,-124.848974,49.384358,-66.885444";

export const DEFAULT_TRANSCRIPT_MAP_CENTER =
	parseLatLng(import.meta.env.VITE_TRANSCRIPT_MAP_CENTER) ??
	DEFAULT_CENTER_FALLBACK;

export const DEFAULT_TRANSCRIPT_MAP_ZOOM =
	parseNumber(import.meta.env.VITE_TRANSCRIPT_MAP_ZOOM) ?? DEFAULT_ZOOM_FALLBACK;

export const DEFAULT_TRANSCRIPT_MAP_BOUNDING_BOX =
	parseBoundingBox(import.meta.env.VITE_TRANSCRIPT_MAP_BOUNDING_BOX) ??
	DEFAULT_BOUNDING_BOX_FALLBACK;

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

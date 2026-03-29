import { unescape as unescapeHtml } from "instantsearch.js/es/lib/utils";
import moment from "moment";

import { buildScannerSearchUrl } from "@/lib/searchState";

export type TranscriptSearchSource = {
	filter_link: string;
	src: string | number;
	label: string;
	tag?: string;
	address?: string;
};

export type TranscriptSearchSegment = [TranscriptSearchSource | null, string];

export type TranscriptHighlightResult = {
	transcript: {
		value: string;
	};
	raw_transcript: {
		value: string;
	};
};

export type TranscriptHit = Record<string, unknown> & {
	_highlightResult: TranscriptHighlightResult;
	__position?: number;
	audio_type: string;
	call_length: number;
	encrypted?: number;
	_geo?: {
		lat: number;
		lng: number;
	};
	contextUrl?: string;
	geo_formatted_address?: string;
	highlighted_transcript?: TranscriptSearchSegment[];
	id: string | number;
	json?: string;
	objectID?: string | number;
	permalink?: string;
	raw_audio_url: string;
	raw_metadata: string | Record<string, unknown>;
	raw_transcript: string | TranscriptSearchSegment[];
	relative_time?: string;
	short_name: string;
	start_time: number;
	start_time_ms?: number;
	start_time_string?: string;
	talkgroup: string | number;
	talkgroup_description: string;
	talkgroup_group: string;
	talkgroup_group_tag: string;
	talkgroup_group_tag_color?: string;
	talkgroup_tag: string;
	time_warning?: string;
};

export type TranscriptRenderedHit = Omit<
	TranscriptHit,
	| "highlighted_transcript"
	| "raw_metadata"
	| "raw_transcript"
	| "talkgroup_group_tag_color"
> & {
	highlighted_transcript: TranscriptSearchSegment[];
	raw_metadata: Record<string, unknown> & { encrypted?: number };
	raw_transcript: TranscriptSearchSegment[];
	talkgroup_group_tag_color: string;
};

export function buildRangeWindow(
	startTime: number,
	beforeSeconds: number,
	afterSeconds: number,
): string {
	return `${startTime - beforeSeconds}:${startTime + afterSeconds}`;
}

export function parseSelectedHitId(hash: string): string | undefined {
	const match = /^#hit-(.+)$/.exec(hash);
	return match ? match[1] : undefined;
}

function normalizeTranscriptLineBreaks(value: string): string {
	return value.replaceAll("\\n", "<br>").replaceAll("\n", "<br>");
}

export function getTranscriptHitGeoPoint(
	hit: Pick<TranscriptHit, "_geo">,
): { lat: number; lng: number } | undefined {
	if (!hit._geo) {
		return undefined;
	}

	const { lat, lng } = hit._geo;
	if (!Number.isFinite(lat) || !Number.isFinite(lng)) {
		return undefined;
	}

	return {
		lat,
		lng,
	};
}

export function createTranscriptHitTransformer({
	indexName,
	hitsPerPage,
	sortBy,
}: {
	indexName: string;
	hitsPerPage: number;
	sortBy: string;
}): (items: TranscriptHit[]) => TranscriptRenderedHit[] {
	return (items: TranscriptHit[]): TranscriptRenderedHit[] => {
		items.forEach((hit) => {
			const rawTranscript = JSON.parse(
				hit.raw_transcript as string,
			) as TranscriptSearchSegment[];
			const rawMetadata = JSON.parse(hit.raw_metadata as string) as Record<
				string,
				unknown
			> & {
				encrypted?: number;
			};

			hit.raw_transcript = rawTranscript;
			hit.raw_metadata = rawMetadata;

			const {
				_highlightResult,
				__position: _position,
				raw_metadata: _rawMetadata,
				...hitClone
			} = hit;
			hit.json = JSON.stringify(hitClone, null, 2);

			hit.objectID = hit.id;

			hit._highlightResult.transcript.value = unescapeHtml(
				hit._highlightResult.transcript.value,
			).trim();

			let highlightedTranscript: TranscriptSearchSegment[];
			try {
				highlightedTranscript = JSON.parse(
					unescapeHtml(hit._highlightResult.raw_transcript.value),
				) as TranscriptSearchSegment[];
			} catch (error) {
				console.log(error);
				highlightedTranscript = rawTranscript;
			}
			hit.highlighted_transcript = highlightedTranscript;

			if (hit.audio_type === "digital tdma") {
				hit.audio_type = "digital";
			}
			hit.audio_type =
				hit.audio_type.charAt(0).toUpperCase() + hit.audio_type.slice(1);

			switch (hit.talkgroup_group_tag) {
				case "Law Dispatch":
				case "Law Tac":
				case "Law Talk":
				case "Security":
					hit.talkgroup_group_tag_color = "primary";
					break;
				case "Fire Dispatch":
				case "Fire-Tac":
				case "Fire-Talk":
				case "EMS Dispatch":
				case "EMS-Tac":
				case "EMS-Talk":
					hit.talkgroup_group_tag_color = "danger";
					break;
				case "Public Works":
				case "Utilities":
					hit.talkgroup_group_tag_color = "success";
					break;
				case "Multi-Tac":
				case "Emergency Ops":
					hit.talkgroup_group_tag_color = "warning";
					break;
				default:
					hit.talkgroup_group_tag_color = "secondary";
			}

			let startTime = moment.unix(hit.start_time);
			if (hit.short_name === "chi_cpd") {
				if (rawMetadata.encrypted === 1) {
					hit.time_warning = ` - delayed until ${startTime
						.toDate()
						.toLocaleTimeString()}`;
					startTime = startTime.subtract(30, "minutes");
					hit.encrypted = 1;
				}
			}
			hit.start_time_ms = hit.start_time * 1000 + 1;
			hit.start_time_string = startTime.toDate().toLocaleString();
			hit.relative_time = startTime.fromNow();
			hit.permalink = buildScannerSearchUrl({
				indexName,
				hitsPerPage,
				sortBy,
				scope: {
					refinementList: {
						talkgroup_tag: [hit.talkgroup_tag],
					},
					range: {
						start_time: `${hit.start_time}:${hit.start_time}`,
					},
				},
			});
			hit.contextUrl = buildScannerSearchUrl({
				indexName,
				hitsPerPage,
				sortBy,
				callId: String(hit.id),
				scope: {
					refinementList: {
						talkgroup_tag: [hit.talkgroup_tag],
					},
					range: {
						start_time: buildRangeWindow(hit.start_time, 20 * 60, 10 * 60),
					},
				},
			});

			for (let index = 0; index < rawTranscript.length; index += 1) {
				const segment = rawTranscript[index];
				const highlightedSegment = highlightedTranscript[index] ?? segment;
				const src = segment[0];
				const highlightedSource = highlightedSegment[0];
				if (src && highlightedSource) {
					const hasTag = Boolean(highlightedSource.tag?.length);
					const refinementKey = hasTag ? "units" : "radios";
					const refinementValue = hasTag
						? highlightedSource.tag
						: String(src.src);
					src.filter_link = buildScannerSearchUrl({
						indexName,
						hitsPerPage,
						sortBy,
						scope: {
							refinementList: {
								[refinementKey]: [refinementValue],
							},
						},
					});
					src.label = hasTag ? highlightedSource.tag ?? String(src.src) : String(src.src);
				}
				segment[1] = normalizeTranscriptLineBreaks(
					highlightedSegment[1] ?? segment[1],
				);
			}
		});

		return items as TranscriptRenderedHit[];
	};
}

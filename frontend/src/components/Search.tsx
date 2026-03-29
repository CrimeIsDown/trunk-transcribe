"use client";

import { instantMeiliSearch } from "@meilisearch/instant-meilisearch";
import type { UiState } from "instantsearch.js";
import { history } from "instantsearch.js/es/lib/routers";
import { simple } from "instantsearch.js/es/lib/stateMappings";
import { unescape as unescapeHtml } from "instantsearch.js/es/lib/utils";
import moment from "moment";
import { useEffect, useState } from "react";
import { Accordion, Button, Col, Collapse, Row } from "react-bootstrap";
import { FaCalendar, FaFilter, FaRedo } from "react-icons/fa";
import {
	ClearRefinements,
	CurrentRefinements,
	HierarchicalMenu,
	Hits,
	HitsPerPage,
	InstantSearch,
	Pagination,
	RefinementList,
	SearchBox,
	SortBy,
	Stats,
	useInstantSearch,
	useRange,
	useRefinementList,
} from "react-instantsearch";
import {
	buildScannerSearchUrl,
	epochSecondsToLocalDateTimeValue,
	toEpochSeconds,
} from "@/lib/searchState";
import {
	transformCurrentRefinements,
	transformHierarchyMenuItems,
	transformSystemRefinementItems,
} from "@/lib/transcriptSearchLabels";
import SearchAnalysisPanel from "./chat/SearchAnalysisPanel";
import { Hit as HitComponent } from "./Hit";

type SearchTranscriptSource = {
	filter_link: string;
	src: string | number;
	label: string;
	tag?: string;
	address?: string;
};

type SearchTranscriptSegment = [SearchTranscriptSource | null, string];

type SearchHighlightResult = {
	transcript: {
		value: string;
	};
	raw_transcript: {
		value: string;
	};
};

type SearchHit = Record<string, unknown> & {
	_highlightResult: SearchHighlightResult;
	__position?: number;
	audio_type: string;
	call_length: number;
	encrypted?: number;
	contextUrl?: string;
	geo_formatted_address?: string;
	highlighted_transcript?: SearchTranscriptSegment[];
	id: string | number;
	json?: string;
	objectID?: string | number;
	permalink?: string;
	raw_audio_url: string;
	raw_metadata: string | Record<string, unknown>;
	raw_transcript: string | SearchTranscriptSegment[];
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

type SearchRenderedHit = Omit<
	SearchHit,
	| "highlighted_transcript"
	| "raw_metadata"
	| "raw_transcript"
	| "talkgroup_group_tag_color"
> & {
	highlighted_transcript: SearchTranscriptSegment[];
	raw_metadata: Record<string, unknown> & { encrypted?: number };
	raw_transcript: SearchTranscriptSegment[];
	talkgroup_group_tag_color: string;
};

function buildRangeWindow(
	startTime: number,
	beforeSeconds: number,
	afterSeconds: number,
): string {
	return `${startTime - beforeSeconds}:${startTime + afterSeconds}`;
}

function parseSelectedHitId(hash: string): string | undefined {
	const match = /^#hit-(.+)$/.exec(hash);
	return match ? match[1] : undefined;
}

function createTransformItems({
	indexName,
	hitsPerPage,
	sortBy,
}: {
	indexName: string;
	hitsPerPage: number;
	sortBy: string;
}): (items: SearchHit[]) => SearchRenderedHit[] {
	return (items: SearchHit[]): SearchRenderedHit[] => {
		items.forEach((hit) => {
			const rawTranscript = JSON.parse(
				hit.raw_transcript as string,
			) as SearchTranscriptSegment[];
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

			// Needed since react-instantsearch depends on objectID for setting the key
			hit.objectID = hit.id;

			hit._highlightResult.transcript.value = unescapeHtml(
				hit._highlightResult.transcript.value,
			).trim();

			let highlightedTranscript: SearchTranscriptSegment[];
			try {
				highlightedTranscript = JSON.parse(
					unescapeHtml(hit._highlightResult.raw_transcript.value),
				) as SearchTranscriptSegment[];
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

			let start_time = moment.unix(hit.start_time);
			if (hit.short_name === "chi_cpd") {
				if (rawMetadata.encrypted === 1) {
					hit.time_warning = ` - delayed until ${start_time
						.toDate()
						.toLocaleTimeString()}`;
					start_time = start_time.subtract(30, "minutes");
					hit.encrypted = 1;
				}
			}
			hit.start_time_ms = hit.start_time * 1000 + 1; // Add 1 since OpenMHz shows calls older than the specified time, and we want to include the current one
			hit.start_time_string = start_time.toDate().toLocaleString();
			hit.relative_time = start_time.fromNow();
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

			// Apply highlights
			for (let i = 0; i < rawTranscript.length; i++) {
				const segment = rawTranscript[i];
				const highlightedSegment = highlightedTranscript[i] ?? segment;
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
					if (hasTag) {
						src.label = highlightedSource.tag ?? String(src.src);
					} else {
						src.label = String(src.src);
					}
				}
				// Show newlines properly
				segment[1] = (highlightedSegment[1] ?? segment[1]).replaceAll(
					"\n",
					"<br>",
				);
			}
		});

		return items as SearchRenderedHit[];
	};
}

const hostUrl = import.meta.env.VITE_MEILI_URL || "http://localhost:7700";
const apiKey = import.meta.env.VITE_MEILI_MASTER_KEY || "testing";
const indexName = import.meta.env.VITE_MEILI_INDEX || "calls";
const AUTO_REFRESH_INTERVAL_MS = 10_000;

function buildDefaultIndexUiState(indexName: string) {
	return {
		sortBy: `${indexName}:start_time:desc`,
	};
}

function buildChicagoOnlyIndexUiState(indexName: string) {
	return {
		...buildDefaultIndexUiState(indexName),
		refinementList: {
			short_name: ["chi_cpd", "chi_cfd", "chi_oemc"],
		},
	};
}

function VirtualRefinementList({ attribute }: { attribute: string }) {
	useRefinementList({
		attribute,
		operator: "or",
	});

	return null;
}

function transformCurrentRefinementItems(
	items: Parameters<typeof transformCurrentRefinements>[0],
) {
	return transformCurrentRefinements(items);
}

function transformHierarchyMenuListItems(
	items: Parameters<typeof transformHierarchyMenuItems>[0],
) {
	return transformHierarchyMenuItems(items);
}

function transformSystemRefinementListItems(
	items: Parameters<typeof transformSystemRefinementItems>[0],
) {
	return transformSystemRefinementItems(items);
}

function CallTimeRangeFilter() {
	const { start, refine } = useRange({
		attribute: "start_time",
	});

	const [minValue, setMinValue] = useState("");
	const [maxValue, setMaxValue] = useState("");

	useEffect(() => {
		setMinValue(epochSecondsToLocalDateTimeValue(start[0]));
	}, [start[0]]);

	useEffect(() => {
		setMaxValue(epochSecondsToLocalDateTimeValue(start[1]));
	}, [start[1]]);

	const updateRange = (nextMinValue: string, nextMaxValue: string) => {
		const nextMin = toEpochSeconds(nextMinValue);
		const nextMax = toEpochSeconds(nextMaxValue);
		refine([nextMin, nextMax]);
	};

	return (
		<Row>
			<Col>
				<label htmlFor="minStartTime">From Time</label>
				<div className="input-group date">
					<input
						type="datetime-local"
						id="minStartTime"
						className="form-control"
						value={minValue}
						onChange={(event) => {
							const nextValue = event.target.value;
							setMinValue(nextValue);
							updateRange(nextValue, maxValue);
						}}
					/>
					<span className="input-group-text">
						<FaCalendar />
					</span>
				</div>
			</Col>
			<Col>
				<label htmlFor="maxStartTime">To Time</label>
				<div className="input-group date">
					<input
						type="datetime-local"
						id="maxStartTime"
						className="form-control"
						value={maxValue}
						onChange={(event) => {
							const nextValue = event.target.value;
							setMaxValue(nextValue);
							updateRange(minValue, nextValue);
						}}
					/>
					<span className="input-group-text">
						<FaCalendar />
					</span>
				</div>
			</Col>
		</Row>
	);
}

function TranscriptSearchResults({
	indexName,
	selectedHitId,
}: {
	indexName: string;
	selectedHitId?: string;
}) {
	const { indexUiState, results } = useInstantSearch<UiState>();
	const indexState = (indexUiState || {}) as Record<string, unknown>;
	const sortBy =
		typeof indexState.sortBy === "string" && indexState.sortBy
			? indexState.sortBy
			: `${indexName}:start_time:desc`;
	const hitsPerPage =
		typeof indexState.hitsPerPage === "number" &&
		Number.isFinite(indexState.hitsPerPage)
			? indexState.hitsPerPage
			: 60;

	const transformItems = createTransformItems({
		indexName,
		hitsPerPage,
		sortBy,
	});

	useEffect(() => {
		if (!selectedHitId || !results?.hits?.length) {
			return undefined;
		}

		const timer = window.setTimeout(() => {
			const element = document.getElementById(`hit-${selectedHitId}`);
			if (element) {
				element.scrollIntoView({ behavior: "smooth", block: "start" });
			}
		}, 0);

		return () => window.clearTimeout(timer);
	}, [results?.hits, selectedHitId]);

	const HitWithSelection = ({ hit }: { hit: SearchRenderedHit }) => (
		<HitComponent hit={hit} selected={String(hit.id) === selectedHitId} />
	);

	return (
		<>
			<SearchAnalysisPanel indexName={indexName} />
			<CurrentRefinements transformItems={transformCurrentRefinementItems} />
			<Stats />
			<Hits hitComponent={HitWithSelection} transformItems={transformItems} />
			<Pagination className="mt-3" />
		</>
	);
}

function SearchToolbarActions({ indexName }: { indexName: string }) {
	const { refresh, setUiState } = useInstantSearch<UiState>();
	const [autoRefreshEnabled, setAutoRefreshEnabled] = useState(false);

	useEffect(() => {
		if (!autoRefreshEnabled) {
			return undefined;
		}

		refresh();
		const intervalId = window.setInterval(() => {
			refresh();
		}, AUTO_REFRESH_INTERVAL_MS);

		return () => {
			window.clearInterval(intervalId);
		};
	}, [autoRefreshEnabled, refresh]);

	const applyIndexUiState = (nextIndexUiState: Record<string, unknown>) => {
		setUiState((currentUiState) => ({
			...currentUiState,
			[indexName]: nextIndexUiState,
		}));
	};

	return (
		<>
			<Button
				type="button"
				size="sm"
				variant="outline-secondary"
				onClick={() => {
					refresh();
				}}
			>
				<FaRedo className="me-1" />
				Refresh
			</Button>
			<Button
				type="button"
				size="sm"
				variant="outline-primary"
				onClick={() => {
					applyIndexUiState(buildDefaultIndexUiState(indexName));
				}}
			>
				Default filters
			</Button>
			<Button
				type="button"
				size="sm"
				variant="outline-primary"
				onClick={() => {
					applyIndexUiState(buildChicagoOnlyIndexUiState(indexName));
				}}
			>
				Chicago only
			</Button>
			<Button
				type="button"
				size="sm"
				variant={autoRefreshEnabled ? "primary" : "outline-secondary"}
				aria-pressed={autoRefreshEnabled}
				onClick={() => {
					setAutoRefreshEnabled((currentValue) => !currentValue);
				}}
			>
				Auto-Refresh
			</Button>
		</>
	);
}

const SearchComponent = () => {
	const searchClient = instantMeiliSearch(hostUrl, apiKey).searchClient;

	const [filtersOpen, setFiltersOpen] = useState(true);
	const [selectedHitId, setSelectedHitId] = useState<string | undefined>(() =>
		typeof window === "undefined"
			? undefined
			: parseSelectedHitId(window.location.hash),
	);

	let timer: ReturnType<typeof setTimeout>;
	const queryHook = (query: string, refine: (nextQuery: string) => void) => {
		clearTimeout(timer);
		timer = setTimeout(() => refine(query), 500);
	};

	const routing = {
		router: history({
			windowTitle: (routeState) => {
				const indexState = routeState[indexName] || {};

				if (!indexState.query) {
					return "Search Scanner Transcripts";
				}

				return `${indexState.query} - Search Scanner Transcripts`;
			},
			parseURL: ({ qsModule, location }): UiState => {
				const routeState = qsModule.parse(location.search.slice(1), {
					arrayLimit: 99,
				}) as unknown as UiState;
				if (!Object.keys(routeState).length) {
					const defaultSort = `${indexName}:start_time:desc`;
					return {
						[indexName]: {
							sortBy: defaultSort,
						},
					};
				}
				return routeState;
			},
			cleanUrlOnDispose: false,
		}),
		stateMapping: simple(),
	};

	useEffect(() => {
		const syncSelectedHitId = () => {
			setSelectedHitId(parseSelectedHitId(window.location.hash));
		};

		syncSelectedHitId();
		window.addEventListener("hashchange", syncSelectedHitId);

		return () => window.removeEventListener("hashchange", syncSelectedHitId);
	}, []);

	return (
		<InstantSearch
			searchClient={searchClient}
			indexName={indexName}
			routing={routing}
			future={{ preserveSharedStateOnUnmount: true }}
		>
			<VirtualRefinementList attribute="talkgroup_description" />
			<h1>Call Transcript Search</h1>
			<Row className="mb-2">
				<Col lg={3} className="d-none d-lg-block">
					<h2 className="fs-4">Filters</h2>
				</Col>
				<Col>
					<Row>
						<SearchBox
							className="col-lg mb-2 mb-lg-0"
							classNames={{ input: "form-control" }}
							queryHook={queryHook}
						/>
						<SortBy
							className="col-lg-auto col"
							items={[
								{
									label: "Newest First",
									value: `${indexName}:start_time:desc`,
								},
								{ label: "Oldest First", value: `${indexName}:start_time:asc` },
								{ label: "Relevance", value: indexName },
							]}
						/>
						<HitsPerPage
							className="col-lg-auto col"
							items={[
								{ label: "20 per page", value: 20, default: true },
								{ label: "40 per page", value: 40 },
								{ label: "60 per page", value: 60 },
							]}
						/>
						<div
							id="option-buttons"
							className="col-md-auto d-flex justify-content-end flex-wrap gap-2"
						>
							<SearchToolbarActions indexName={indexName} />
							<Button
								onClick={() => setFiltersOpen(!filtersOpen)}
								type="button"
								variant="primary"
								className="d-lg-none"
								aria-controls="filters"
							>
								<span className="visually-hidden">Filters</span>
								<FaFilter />
							</Button>
						</div>
					</Row>
				</Col>
			</Row>
			<Row>
				<Col className="search-panel__filters" lg={3}>
					<Collapse in={filtersOpen}>
						<div id="filters">
							<h2 id="filtersHeading" className="d-lg-none">
								Filters
							</h2>
							<Row className="mb-4">
								<ClearRefinements
									translations={{
										resetButtonText: "Clear Filters",
									}}
								/>
							</Row>
							<Accordion
								defaultActiveKey={["0", "1", "2", "3", "4"]}
								flush
								alwaysOpen
							>
								<Accordion.Item eventKey="0">
									<Accordion.Header>
										System / Department / Talkgroup
									</Accordion.Header>
									<Accordion.Body>
								<HierarchicalMenu
									attributes={[
										"talkgroup_hierarchy.lvl0",
										"talkgroup_hierarchy.lvl1",
										"talkgroup_hierarchy.lvl2",
									]}
									transformItems={transformHierarchyMenuListItems}
								/>
							</Accordion.Body>
						</Accordion.Item>

								<Accordion.Item eventKey="1">
									<Accordion.Header>Radio System</Accordion.Header>
									<Accordion.Body>
										<RefinementList
											attribute="short_name"
											operator="or"
											showMore={true}
											showMoreLimit={60}
											searchable={true}
											classNames={{
												label: "form-check-label",
												checkbox: "form-check-input",
												item: "form-check",
												count: "ms-1",
											}}
											transformItems={transformSystemRefinementListItems}
										/>
									</Accordion.Body>
								</Accordion.Item>

								<Accordion.Item eventKey="2">
									<Accordion.Header>Departments</Accordion.Header>
									<Accordion.Body>
										<RefinementList
											attribute="talkgroup_group"
											operator="or"
											showMore={true}
											showMoreLimit={60}
											searchable={true}
											classNames={{
												label: "form-check-label",
												checkbox: "form-check-input",
												item: "form-check",
												count: "ms-1",
											}}
										/>
									</Accordion.Body>
								</Accordion.Item>

								<Accordion.Item eventKey="3">
									<Accordion.Header>Talkgroups</Accordion.Header>
									<Accordion.Body>
										<RefinementList
											attribute="talkgroup_tag"
											operator="or"
											showMore={true}
											showMoreLimit={60}
											searchable={true}
											classNames={{
												label: "form-check-label",
												checkbox: "form-check-input",
												item: "form-check",
												count: "ms-1",
											}}
										/>
									</Accordion.Body>
								</Accordion.Item>

								<Accordion.Item eventKey="4">
									<Accordion.Header>Talkgroup Type</Accordion.Header>
									<Accordion.Body>
										<RefinementList
											attribute="talkgroup_group_tag"
											operator="or"
											showMore={true}
											showMoreLimit={60}
											searchable={true}
											classNames={{
												label: "form-check-label",
												checkbox: "form-check-input",
												item: "form-check",
												count: "ms-1",
											}}
										/>
									</Accordion.Body>
								</Accordion.Item>

								<Accordion.Item eventKey="5">
									<Accordion.Header>Units</Accordion.Header>
									<Accordion.Body>
										<RefinementList
											attribute="units"
											operator="or"
											showMore={true}
											showMoreLimit={60}
											searchable={true}
											classNames={{
												label: "form-check-label",
												checkbox: "form-check-input",
												item: "form-check",
												count: "ms-1",
											}}
										/>
									</Accordion.Body>
								</Accordion.Item>

								<Accordion.Item eventKey="6">
									<Accordion.Header>Radio IDs</Accordion.Header>
									<Accordion.Body>
										<RefinementList
											attribute="radios"
											operator="or"
											showMore={true}
											showMoreLimit={60}
											searchable={true}
											classNames={{
												label: "form-check-label",
												checkbox: "form-check-input",
												item: "form-check",
												count: "ms-1",
											}}
										/>
									</Accordion.Body>
								</Accordion.Item>

								<Accordion.Item eventKey="7">
									<Accordion.Header>Call Time</Accordion.Header>
									<Accordion.Body>
										<CallTimeRangeFilter />
									</Accordion.Body>
								</Accordion.Item>
							</Accordion>
						</div>
					</Collapse>
				</Col>
				<Col className="search-panel__results">
					<TranscriptSearchResults
						indexName={indexName}
						selectedHitId={selectedHitId}
					/>
				</Col>
			</Row>
		</InstantSearch>
	);
};

export default SearchComponent;

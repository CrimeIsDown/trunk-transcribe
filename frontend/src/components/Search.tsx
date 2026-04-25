"use client";

import { instantMeiliSearch } from "@meilisearch/instant-meilisearch";
import type { UiState } from "instantsearch.js";
import { history } from "instantsearch.js/es/lib/routers";
import { simple } from "instantsearch.js/es/lib/stateMappings";
import { useEffect, useMemo, useState } from "react";
import { Accordion, Alert, Button, Col, Collapse, Row } from "react-bootstrap";
import { FaFilter, FaRedo } from "react-icons/fa";
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
	useRefinementList,
} from "react-instantsearch";
import { extractScannerSearchScope } from "@/lib/searchState";
import {
	createTranscriptHitTransformer,
	parseSelectedHitId,
	type TranscriptRenderedHit,
} from "@/lib/transcriptHits";
import {
	buildTranscriptArchiveSearchUrl,
	clampTranscriptSearchRangeToMonth,
	getTranscriptCurrentMonthIndexName,
	getTranscriptSearchIndexNameForRange,
	getTranscriptSearchIndexNameFromLocation,
	type TranscriptSearchIndexConfig,
} from "@/lib/transcriptSearchIndex";
import {
	transformCurrentRefinements,
	transformHierarchyMenuItems,
	transformSystemRefinementItems,
} from "@/lib/transcriptSearchLabels";
import { useTranscriptSearchCredentials } from "@/hooks/useTranscriptSearchCredentials";
import { useEntitlements } from "@/providers/entitlements";
import CallTimeRangeFilter from "./CallTimeRangeFilter";
import SearchAnalysisPanel from "./chat/SearchAnalysisPanel";
import { Hit as HitComponent } from "./Hit";
import SavedTranscriptSearches from "./SavedTranscriptSearches";

const AUTO_REFRESH_INTERVAL_MS = 10_000;

function isRecord(value: unknown): value is Record<string, unknown> {
	return typeof value === "object" && value !== null && !Array.isArray(value);
}

function buildDefaultIndexUiState(indexName: string) {
	return {
		sortBy: `${indexName}:start_time:desc`,
	};
}

function parseCsvList(value: string | undefined): string[] {
	if (!value) {
		return [];
	}

	return value
		.split(",")
		.map((part) => part.trim())
		.filter(Boolean);
}

const TRANSCRIPT_SEARCH_PRESET_SHORT_NAMES = parseCsvList(
	import.meta.env.VITE_TRANSCRIPT_SEARCH_PRESET_SHORT_NAMES,
);

const TRANSCRIPT_SEARCH_PRESET_LABEL =
	typeof import.meta.env.VITE_TRANSCRIPT_SEARCH_PRESET_LABEL === "string" &&
	import.meta.env.VITE_TRANSCRIPT_SEARCH_PRESET_LABEL.trim()
		? import.meta.env.VITE_TRANSCRIPT_SEARCH_PRESET_LABEL.trim()
		: "Local only";

function buildPresetIndexUiState(indexName: string) {
	if (TRANSCRIPT_SEARCH_PRESET_SHORT_NAMES.length === 0) {
		return buildDefaultIndexUiState(indexName);
	}

	return {
		...buildDefaultIndexUiState(indexName),
		refinementList: {
			short_name: TRANSCRIPT_SEARCH_PRESET_SHORT_NAMES,
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

function remapSearchStateIndex(
	routeState: UiState,
	fromIndexName: string,
	toIndexName: string,
): UiState {
	if (fromIndexName === toIndexName) {
		return routeState;
	}

	const nextRouteState = { ...routeState } as Record<string, unknown>;
	const fromIndexState = nextRouteState[fromIndexName];
	if (!isRecord(fromIndexState)) {
		return routeState;
	}

	// Monthly indexes need the search state to live under the active month key.
	// Canonicalizing legacy base-index URLs here keeps routing and search aligned.
	const toIndexState = isRecord(nextRouteState[toIndexName])
		? (nextRouteState[toIndexName] as Record<string, unknown>)
		: {};

	nextRouteState[toIndexName] = {
		...toIndexState,
		...fromIndexState,
	};
	delete nextRouteState[fromIndexName];
	return nextRouteState as UiState;
}

function TranscriptArchiveIndexNotice({
	baseIndexName,
	indexName,
	splitByMonth,
}: {
	baseIndexName: string;
	indexName: string;
	splitByMonth: boolean;
}) {
	const { indexUiState } = useInstantSearch<UiState>();
	const archiveIndexConfig: TranscriptSearchIndexConfig = useMemo(
		() => ({
			baseIndexName,
			splitByMonth,
		}),
		[baseIndexName, splitByMonth],
	);
	const currentMonthIndexName = useMemo(
		() => getTranscriptCurrentMonthIndexName(archiveIndexConfig),
		[archiveIndexConfig],
	);
	const indexState = (indexUiState || {}) as Record<string, unknown>;
	const searchScope = useMemo(
		() => extractScannerSearchScope(indexState),
		[indexState],
	);
	const searchUiState = useMemo(
		() => ({
			hitsPerPage:
				typeof indexState.hitsPerPage === "number" &&
				Number.isFinite(indexState.hitsPerPage)
					? indexState.hitsPerPage
					: undefined,
			sortBy:
				typeof indexState.sortBy === "string" && indexState.sortBy
					? indexState.sortBy
					: undefined,
		}),
		[indexState],
	);
	const searchRange = searchScope.range?.start_time;
	const nextIndexName = searchRange
		? getTranscriptSearchIndexNameForRange(
				searchScope.range,
				archiveIndexConfig,
			)
		: undefined;
	const shouldRedirect =
		splitByMonth && Boolean(searchRange) && nextIndexName !== indexName;
	const shouldShowArchiveBanner =
		splitByMonth && indexName !== currentMonthIndexName && !searchRange;

	useEffect(() => {
		if (!shouldRedirect || typeof window === "undefined") {
			return;
		}

		const nextUrl = buildTranscriptArchiveSearchUrl({
			currentIndexName: indexName,
			nextIndexName: nextIndexName || currentMonthIndexName,
			scope: {
				...searchScope,
				range: {
					start_time: clampTranscriptSearchRangeToMonth(searchRange),
				},
			},
			hitsPerPage: searchUiState.hitsPerPage,
			sortBy: searchUiState.sortBy,
			hash: window.location.hash,
		});

		window.location.replace(nextUrl);
	}, [
		currentMonthIndexName,
		indexName,
		nextIndexName,
		searchRange,
		searchScope,
		searchUiState.hitsPerPage,
		searchUiState.sortBy,
		shouldRedirect,
	]);

	if (!shouldShowArchiveBanner) {
		return null;
	}

	return (
		<Alert variant="warning" className="mb-3">
			<div className="d-flex flex-column flex-lg-row justify-content-between gap-2">
				<div>
					<div className="fw-semibold">Archive month selected</div>
					<div className="small">
						Showing {indexName}. The latest month is {currentMonthIndexName}.
					</div>
				</div>
				<Button
					type="button"
					size="sm"
					variant="outline-dark"
					onClick={() => {
						if (typeof window === "undefined") {
							return;
						}

						const nextUrl = buildTranscriptArchiveSearchUrl({
							currentIndexName: indexName,
							nextIndexName: currentMonthIndexName,
							scope: searchScope,
							hitsPerPage: searchUiState.hitsPerPage,
							sortBy: searchUiState.sortBy,
							hash: window.location.hash,
						});

						window.location.replace(nextUrl);
					}}
				>
					Go to latest month
				</Button>
			</div>
		</Alert>
	);
}

function TranscriptSearchResults({
	indexName,
	selectedHitId,
}: {
	indexName: string;
	selectedHitId?: string;
}) {
	const entitlements = useEntitlements();
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

	const transformItems = createTranscriptHitTransformer({
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
			{entitlements.canUseAssistant() ? (
				<SearchAnalysisPanel indexName={indexName} />
			) : (
				<Alert variant="secondary" className="mb-3">
					AI analysis is not available for this account.
				</Alert>
			)}
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
			{TRANSCRIPT_SEARCH_PRESET_SHORT_NAMES.length > 0 ? (
				<Button
					type="button"
					size="sm"
					variant="outline-primary"
					onClick={() => {
						applyIndexUiState(buildPresetIndexUiState(indexName));
					}}
				>
					{TRANSCRIPT_SEARCH_PRESET_LABEL}
				</Button>
			) : null}
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
	const { credentials, error, isLoading } = useTranscriptSearchCredentials();
	const entitlements = useEntitlements();
	const archiveIndexConfig = useMemo<TranscriptSearchIndexConfig | null>(() => {
		if (!credentials) {
			return null;
		}

		return {
			baseIndexName: credentials.baseIndexName,
			splitByMonth: credentials.splitByMonth,
		};
	}, [credentials]);
	const searchClient = useMemo(() => {
		if (!credentials) {
			return null;
		}

		return instantMeiliSearch(credentials.hostUrl, credentials.apiKey)
			.searchClient;
	}, [credentials]);
	const searchLocationSearch =
		typeof window === "undefined" ? "" : window.location.search;
	const indexName =
		archiveIndexConfig === null
			? ""
			: getTranscriptSearchIndexNameFromLocation(
					searchLocationSearch,
					archiveIndexConfig,
				);

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

	if (isLoading) {
		return (
			<Alert variant="secondary" className="m-3">
				Loading transcript search…
			</Alert>
		);
	}

	if (!credentials || !archiveIndexConfig || !searchClient) {
		return (
			<Alert variant="danger" className="m-3">
				Failed to load search credentials.
				{error ? <div className="small mt-2">{error.message}</div> : null}
			</Alert>
		);
	}

	if (!entitlements.canSearchTranscripts()) {
		return (
			<Alert variant="warning" className="m-3">
				Transcript search is not available for this account.
			</Alert>
		);
	}

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

				if (credentials.splitByMonth && Object.keys(routeState).length) {
					return remapSearchStateIndex(
						routeState,
						credentials.baseIndexName,
						indexName,
					);
				}

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
								defaultActiveKey={["0", "1", "2", "3", "4", "5", "6", "7", "8"]}
								flush
								alwaysOpen
							>
								<Accordion.Item eventKey="0">
									<Accordion.Header>Saved Searches</Accordion.Header>
									<Accordion.Body>
										<SavedTranscriptSearches indexName={indexName} />
									</Accordion.Body>
								</Accordion.Item>

								<Accordion.Item eventKey="1">
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

								<Accordion.Item eventKey="2">
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

								<Accordion.Item eventKey="3">
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

								<Accordion.Item eventKey="4">
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

								<Accordion.Item eventKey="5">
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

								<Accordion.Item eventKey="6">
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

								<Accordion.Item eventKey="7">
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

								<Accordion.Item eventKey="8">
									<Accordion.Header>Call Time</Accordion.Header>
									<Accordion.Body>
										<CallTimeRangeFilter
											archiveConfig={archiveIndexConfig}
											archiveDepthDays={entitlements.archiveDepthDays()}
										/>
									</Accordion.Body>
								</Accordion.Item>
							</Accordion>
						</div>
					</Collapse>
				</Col>
				<Col className="search-panel__results">
					<TranscriptArchiveIndexNotice
						baseIndexName={credentials.baseIndexName}
						indexName={indexName}
						splitByMonth={credentials.splitByMonth}
					/>
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

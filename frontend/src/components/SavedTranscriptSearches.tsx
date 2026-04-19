"use client";

import type { UiState } from "instantsearch.js";
import { useEffect, useMemo, useState } from "react";
import { Badge, Button, ListGroup } from "react-bootstrap";
import { useInstantSearch } from "react-instantsearch";

import {
	buildTranscriptSavedSearchUrl,
	deleteTranscriptSavedSearchEntry,
	describeTranscriptSavedSearchState,
	extractTranscriptSavedSearchState,
	upsertTranscriptSavedSearchEntry,
	type TranscriptSavedSearchEntry,
} from "@/lib/transcriptSavedSearches";
import { useSavedSearchStore } from "@/providers/savedSearchStore";

function formatSavedSearchTimestamp(timestamp: string): string {
	const parsed = new Date(timestamp);
	return Number.isNaN(parsed.getTime()) ? timestamp : parsed.toLocaleString();
}

export default function SavedTranscriptSearches({
	indexName,
}: {
	indexName: string;
}) {
	const { indexUiState, setUiState } = useInstantSearch<UiState>();
	const savedSearchStore = useSavedSearchStore();
	const [savedSearches, setSavedSearches] = useState<
		TranscriptSavedSearchEntry[]
	>([]);

	useEffect(() => {
		let isActive = true;
		savedSearchStore
			.list()
			.then((entries) => {
				if (isActive) {
					setSavedSearches(entries);
				}
			})
			.catch((error) => {
				console.error("Failed to load saved searches", error);
			});

		return () => {
			isActive = false;
		};
	}, [savedSearchStore]);

	const currentState = useMemo(
		() =>
			extractTranscriptSavedSearchState(
				(indexUiState || {}) as Record<string, unknown>,
			),
		[indexUiState],
	);

	const currentStateSignature = useMemo(
		() => JSON.stringify(currentState),
		[currentState],
	);

	const saveCurrentSearch = async () => {
		if (typeof window === "undefined") {
			return;
		}

		const defaultName = currentState.query || "Untitled search";
		const name = window.prompt(
			"Enter a name for this saved search",
			defaultName,
		);
		if (!name || !name.trim()) {
			return;
		}

		try {
			const created = await savedSearchStore.create(
				name,
				currentState,
				indexName,
			);
			setSavedSearches((currentEntries) =>
				upsertTranscriptSavedSearchEntry(currentEntries, created),
			);
		} catch (error) {
			console.error("Failed to create saved search", error);
		}
	};

	const openSavedSearch = (entry: TranscriptSavedSearchEntry) => {
		setUiState((currentUiState) => ({
			...currentUiState,
			[indexName]: {
				...entry.state,
			},
		}));
	};

	const updateSavedSearch = async (entry: TranscriptSavedSearchEntry) => {
		const shouldUpdate =
			typeof window === "undefined"
				? true
				: window.confirm(
						`Update "${entry.name}" with the current search state?`,
					);

		if (!shouldUpdate) {
			return;
		}

		try {
			const updated = await savedSearchStore.update(
				entry.id,
				currentState,
				indexName,
			);
			setSavedSearches((currentEntries) =>
				upsertTranscriptSavedSearchEntry(currentEntries, updated),
			);
		} catch (error) {
			console.error("Failed to update saved search", error);
		}
	};

	const removeSavedSearch = async (entry: TranscriptSavedSearchEntry) => {
		const shouldDelete =
			typeof window === "undefined"
				? true
				: window.confirm(`Delete saved search "${entry.name}"?`);

		if (!shouldDelete) {
			return;
		}

		try {
			await savedSearchStore.remove(entry.id);
			setSavedSearches((currentEntries) =>
				deleteTranscriptSavedSearchEntry(currentEntries, entry.id),
			);
		} catch (error) {
			console.error("Failed to remove saved search", error);
		}
	};

	return (
		<div className="saved-searches-panel">
			<div className="d-flex flex-wrap justify-content-between align-items-start gap-2 mb-3">
				<div>
					<div className="fw-semibold">Saved Searches</div>
					<div className="text-muted small">
						Save and reopen the current transcript search state from this
						browser.
					</div>
				</div>
				<Button
					type="button"
					size="sm"
					variant="outline-primary"
					onClick={saveCurrentSearch}
				>
					Save current search
				</Button>
			</div>

			{savedSearches.length === 0 ? (
				<div className="text-muted small">No saved searches yet.</div>
			) : (
				<ListGroup className="saved-searches-list">
					{savedSearches.map((entry) => {
						const summary = describeTranscriptSavedSearchState(entry.state);
						const isActive =
							JSON.stringify(entry.state) === currentStateSignature;
						const openUrl = buildTranscriptSavedSearchUrl(
							indexName,
							entry.state,
						);

						return (
							<ListGroup.Item
								key={entry.id}
								className="d-flex flex-column gap-2"
								active={isActive}
							>
								<div className="d-flex flex-wrap justify-content-between align-items-start gap-2">
									<div>
										<a
											href={openUrl}
											className={`fw-semibold text-decoration-none ${
												isActive ? "text-white" : "text-body"
											}`}
											onClick={(event) => {
												event.preventDefault();
												openSavedSearch(entry);
											}}
										>
											{entry.name}
										</a>
										<div
											className={`small ${isActive ? "text-white-50" : "text-muted"}`}
										>
											Updated {formatSavedSearchTimestamp(entry.updatedAt)}
										</div>
									</div>

									<div className="d-flex flex-wrap gap-2">
										<Button
											type="button"
											size="sm"
											variant={isActive ? "light" : "outline-primary"}
											onClick={() => {
												openSavedSearch(entry);
											}}
										>
											Open
										</Button>
										<Button
											type="button"
											size="sm"
											variant={isActive ? "light" : "outline-secondary"}
											onClick={() => {
												updateSavedSearch(entry);
											}}
										>
											Update
										</Button>
										<Button
											type="button"
											size="sm"
											variant={isActive ? "light" : "outline-danger"}
											onClick={() => {
												removeSavedSearch(entry);
											}}
										>
											Delete
										</Button>
									</div>
								</div>

								{summary.length > 0 ? (
									<div
										className={`small ${isActive ? "text-white-50" : "text-muted"}`}
									>
										{summary.map((item) => (
											<Badge
												bg={isActive ? "light" : "secondary"}
												text={isActive ? "dark" : "light"}
												className="me-1 mb-1"
												key={item}
											>
												{item}
											</Badge>
										))}
									</div>
								) : null}
							</ListGroup.Item>
						);
					})}
				</ListGroup>
			)}
		</div>
	);
}

import { createContext, useContext, type ReactNode } from "react";

import {
	parseScannerSearchUrl,
	type ScannerSearchUiState,
} from "@/lib/searchState";
import {
	buildTranscriptSavedSearchUrl,
	createTranscriptSavedSearchEntryFromState,
	deleteTranscriptSavedSearchEntry,
	loadTranscriptSavedSearches,
	persistTranscriptSavedSearches,
	updateTranscriptSavedSearchEntryFromState,
	upsertTranscriptSavedSearchEntry,
	type TranscriptSavedSearchEntry,
} from "@/lib/transcriptSavedSearches";

export type SavedSearchStore = {
	list: () => Promise<TranscriptSavedSearchEntry[]>;
	create: (
		name: string,
		state: ScannerSearchUiState,
		indexName?: string,
	) => Promise<TranscriptSavedSearchEntry>;
	update: (
		id: string,
		state: ScannerSearchUiState,
		indexName?: string,
	) => Promise<TranscriptSavedSearchEntry>;
	remove: (id: string) => Promise<void>;
};

export type SavedSearchStorage = Parameters<
	typeof loadTranscriptSavedSearches
>[0];

export function createLocalStorageSavedSearchStore(
	storage?: SavedSearchStorage,
): SavedSearchStore {
	return {
		async list() {
			return loadTranscriptSavedSearches(storage);
		},

		async create(name, state, _indexName) {
			const entries = loadTranscriptSavedSearches(storage);
			const created = createTranscriptSavedSearchEntryFromState(name, state);
			persistTranscriptSavedSearches([...entries, created], storage);
			return created;
		},

		async update(id, state, _indexName) {
			const entries = loadTranscriptSavedSearches(storage);
			const existing = entries.find((entry) => entry.id === id);
			if (!existing) {
				throw new Error(`Saved search not found: ${id}`);
			}

			const updated = updateTranscriptSavedSearchEntryFromState(
				existing,
				state,
			);
			persistTranscriptSavedSearches(
				upsertTranscriptSavedSearchEntry(entries, updated),
				storage,
			);
			return updated;
		},

		async remove(id) {
			const entries = loadTranscriptSavedSearches(storage);
			persistTranscriptSavedSearches(
				deleteTranscriptSavedSearchEntry(entries, id),
				storage,
			);
		},
	};
}

type SirensSavedSearch = {
	id: number | string;
	name: string;
	url: string;
	created_at?: string;
	updated_at?: string;
};

function trimTrailingSlash(value: string): string {
	return value.endsWith("/") ? value.slice(0, -1) : value;
}

function getXsrfToken(): string | null {
	if (typeof document === "undefined") {
		return null;
	}

	const tokenCookie = document.cookie
		.split("; ")
		.find((row) => row.startsWith("XSRF-TOKEN="))
		?.split("=")[1];

	return tokenCookie ? decodeURIComponent(tokenCookie) : null;
}

function sortEntries(
	entries: TranscriptSavedSearchEntry[],
): TranscriptSavedSearchEntry[] {
	return [...entries].sort((left, right) =>
		right.updatedAt.localeCompare(left.updatedAt),
	);
}

function toTranscriptSavedSearchEntry(
	value: SirensSavedSearch,
): TranscriptSavedSearchEntry | null {
	const parsed = parseScannerSearchUrl(value.url);
	if (!parsed) {
		return null;
	}

	const now = new Date().toISOString();
	return {
		id: String(value.id),
		name: value.name,
		state: parsed.state,
		createdAt: value.created_at || now,
		updatedAt: value.updated_at || value.created_at || now,
	};
}

async function readSirensJson(response: Response): Promise<unknown> {
	const contentType = response.headers.get("Content-Type") || "";
	if (contentType.includes("application/json")) {
		return response.json();
	}
	return response.text();
}

export function createSirensBackendSavedSearchStore({
	apiBaseUrl,
}: {
	apiBaseUrl: string;
}): SavedSearchStore {
	const baseUrl = trimTrailingSlash(apiBaseUrl);

	return {
		async list() {
			const response = await fetch(`${baseUrl}/api/savedSearches`, {
				credentials: "include",
				headers: {
					Accept: "application/json",
				},
			});
			if (!response.ok) {
				throw new Error(`Failed to load saved searches (${response.status})`);
			}

			const payload = await response.json();
			const entries = Array.isArray(payload)
				? payload
						.map((item) =>
							toTranscriptSavedSearchEntry(item as SirensSavedSearch),
						)
						.filter(
							(entry): entry is TranscriptSavedSearchEntry => entry !== null,
						)
				: [];

			return sortEntries(entries);
		},

		async create(name, state, indexName) {
			const xsrfToken = getXsrfToken();
			const url = buildTranscriptSavedSearchUrl(
				indexName || import.meta.env.VITE_MEILI_INDEX || "calls",
				state,
			);

			const response = await fetch(`${baseUrl}/api/savedSearches`, {
				method: "POST",
				credentials: "include",
				headers: {
					Accept: "application/json",
					"Content-Type": "application/json",
					...(xsrfToken ? { "X-XSRF-TOKEN": xsrfToken } : {}),
				},
				body: JSON.stringify({
					name,
					url,
				}),
			});
			if (!response.ok) {
				const detail = await readSirensJson(response);
				throw new Error(
					`Failed to create saved search (${response.status}): ${JSON.stringify(detail)}`,
				);
			}

			const payload = (await response.json()) as SirensSavedSearch;
			const entry = toTranscriptSavedSearchEntry(payload);
			if (!entry) {
				throw new Error("Saved search was created but could not be parsed");
			}
			return entry;
		},

		async update(id, state, indexName) {
			const xsrfToken = getXsrfToken();
			const url = buildTranscriptSavedSearchUrl(
				indexName || import.meta.env.VITE_MEILI_INDEX || "calls",
				state,
			);

			const response = await fetch(`${baseUrl}/api/savedSearches/${id}`, {
				method: "PATCH",
				credentials: "include",
				headers: {
					Accept: "application/json",
					"Content-Type": "application/json",
					...(xsrfToken ? { "X-XSRF-TOKEN": xsrfToken } : {}),
				},
				body: JSON.stringify({
					url,
				}),
			});
			if (!response.ok) {
				const detail = await readSirensJson(response);
				throw new Error(
					`Failed to update saved search (${response.status}): ${JSON.stringify(detail)}`,
				);
			}

			const payload = (await response.json()) as SirensSavedSearch;
			const entry = toTranscriptSavedSearchEntry(payload);
			if (!entry) {
				throw new Error("Saved search was updated but could not be parsed");
			}
			return entry;
		},

		async remove(id) {
			const xsrfToken = getXsrfToken();
			const response = await fetch(`${baseUrl}/api/savedSearches/${id}`, {
				method: "DELETE",
				credentials: "include",
				headers: {
					Accept: "application/json",
					...(xsrfToken ? { "X-XSRF-TOKEN": xsrfToken } : {}),
				},
			});
			if (!response.ok) {
				const detail = await readSirensJson(response);
				throw new Error(
					`Failed to delete saved search (${response.status}): ${JSON.stringify(detail)}`,
				);
			}
		},
	};
}

const defaultSavedSearchStore = createLocalStorageSavedSearchStore();

const SavedSearchStoreContext = createContext<SavedSearchStore>(
	defaultSavedSearchStore,
);

export function SavedSearchStoreProvider({
	children,
	store,
}: {
	children: ReactNode;
	store?: SavedSearchStore;
}) {
	return (
		<SavedSearchStoreContext.Provider value={store ?? defaultSavedSearchStore}>
			{children}
		</SavedSearchStoreContext.Provider>
	);
}

export function useSavedSearchStore(): SavedSearchStore {
	return useContext(SavedSearchStoreContext);
}

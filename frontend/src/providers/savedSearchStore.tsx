import { createContext, useContext, type ReactNode } from "react";

import type { ScannerSearchUiState } from "@/lib/searchState";
import {
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
	) => Promise<TranscriptSavedSearchEntry>;
	update: (
		id: string,
		state: ScannerSearchUiState,
	) => Promise<TranscriptSavedSearchEntry>;
	remove: (id: string) => Promise<void>;
};

export type SavedSearchStorage = Parameters<typeof loadTranscriptSavedSearches>[0];

export function createLocalStorageSavedSearchStore(
	storage?: SavedSearchStorage,
): SavedSearchStore {
	return {
		async list() {
			return loadTranscriptSavedSearches(storage);
		},

		async create(name, state) {
			const entries = loadTranscriptSavedSearches(storage);
			const created = createTranscriptSavedSearchEntryFromState(name, state);
			persistTranscriptSavedSearches([...entries, created], storage);
			return created;
		},

		async update(id, state) {
			const entries = loadTranscriptSavedSearches(storage);
			const existing = entries.find((entry) => entry.id === id);
			if (!existing) {
				throw new Error(`Saved search not found: ${id}`);
			}

			const updated = updateTranscriptSavedSearchEntryFromState(existing, state);
			persistTranscriptSavedSearches(
				upsertTranscriptSavedSearchEntry(entries, updated),
				storage,
			);
			return updated;
		},

		async remove(id) {
			const entries = loadTranscriptSavedSearches(storage);
			persistTranscriptSavedSearches(deleteTranscriptSavedSearchEntry(entries, id), storage);
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


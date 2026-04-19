import { createContext, useContext, type ReactNode } from "react";

export type TranscriptSearchCredentials = {
	hostUrl: string;
	apiKey: string;
	baseIndexName: string;
	splitByMonth: boolean;
};

export type SearchCredentialProvider = {
	getTranscriptSearchCredentials: () => Promise<TranscriptSearchCredentials>;
};

function trimTrailingSlash(value: string): string {
	return value.endsWith("/") ? value.slice(0, -1) : value;
}

export function createEnvSearchCredentialProvider(): SearchCredentialProvider {
	return {
		async getTranscriptSearchCredentials() {
			return {
				hostUrl: import.meta.env.VITE_MEILI_URL || "http://localhost:7700",
				apiKey: import.meta.env.VITE_MEILI_MASTER_KEY || "testing",
				baseIndexName: import.meta.env.VITE_MEILI_INDEX || "calls",
				splitByMonth:
					import.meta.env.VITE_MEILI_INDEX_SPLIT_BY_MONTH === "true",
			};
		},
	};
}

export function createSirensBackendSearchCredentialProvider({
	apiBaseUrl,
}: {
	apiBaseUrl: string;
}): SearchCredentialProvider {
	const baseUrl = trimTrailingSlash(apiBaseUrl);

	let cachedApiKey: string | null = null;
	let inflight: Promise<string> | null = null;

	async function fetchApiKey(): Promise<string> {
		if (cachedApiKey) {
			return cachedApiKey;
		}

		if (!inflight) {
			inflight = fetch(`${baseUrl}/api/search-key`, {
				credentials: "include",
				headers: {
					Accept: "application/json",
				},
			})
				.then(async (response) => {
					if (!response.ok) {
						throw new Error(`Failed to fetch search key (${response.status})`);
					}

					const payload = (await response.json()) as { meilisearch?: unknown };
					const apiKey = payload?.meilisearch;
					if (typeof apiKey !== "string" || !apiKey) {
						throw new Error(
							"Search key response did not include meilisearch key",
						);
					}

					cachedApiKey = apiKey;
					return apiKey;
				})
				.finally(() => {
					inflight = null;
				});
		}

		return inflight;
	}

	return {
		async getTranscriptSearchCredentials() {
			const apiKey = await fetchApiKey();

			return {
				hostUrl: import.meta.env.VITE_MEILI_URL || "http://localhost:7700",
				apiKey,
				baseIndexName: import.meta.env.VITE_MEILI_INDEX || "calls",
				splitByMonth:
					import.meta.env.VITE_MEILI_INDEX_SPLIT_BY_MONTH === "true",
			};
		},
	};
}

const defaultSearchCredentialProvider = (() => {
	const sirensApiBaseUrl = import.meta.env.VITE_SIRENS_API_BASE_URL;
	const explicitApiKey = import.meta.env.VITE_MEILI_MASTER_KEY;
	if (sirensApiBaseUrl && !explicitApiKey) {
		return createSirensBackendSearchCredentialProvider({
			apiBaseUrl: sirensApiBaseUrl,
		});
	}

	return createEnvSearchCredentialProvider();
})();

const SearchCredentialContext = createContext<SearchCredentialProvider>(
	defaultSearchCredentialProvider,
);

export function SearchCredentialsProvider({
	children,
	provider,
}: {
	children: ReactNode;
	provider?: SearchCredentialProvider;
}) {
	return (
		<SearchCredentialContext.Provider
			value={provider ?? defaultSearchCredentialProvider}
		>
			{children}
		</SearchCredentialContext.Provider>
	);
}

export function useSearchCredentialProvider(): SearchCredentialProvider {
	return useContext(SearchCredentialContext);
}

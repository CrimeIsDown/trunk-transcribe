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

export function createEnvSearchCredentialProvider(): SearchCredentialProvider {
	return {
		async getTranscriptSearchCredentials() {
			return {
				hostUrl: import.meta.env.VITE_MEILI_URL || "http://localhost:7700",
				apiKey: import.meta.env.VITE_MEILI_MASTER_KEY || "testing",
				baseIndexName: import.meta.env.VITE_MEILI_INDEX || "calls",
				splitByMonth: import.meta.env.VITE_MEILI_INDEX_SPLIT_BY_MONTH === "true",
			};
		},
	};
}

const defaultSearchCredentialProvider = createEnvSearchCredentialProvider();

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


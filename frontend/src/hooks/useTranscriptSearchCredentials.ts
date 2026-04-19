import { useCallback, useEffect, useState } from "react";

import {
	useSearchCredentialProvider,
	type TranscriptSearchCredentials,
} from "@/providers/searchCredentials";

export type UseTranscriptSearchCredentialsResult = {
	credentials: TranscriptSearchCredentials | null;
	error: Error | null;
	isLoading: boolean;
	refresh: () => void;
};

function asError(error: unknown): Error {
	return error instanceof Error ? error : new Error(String(error));
}

export function useTranscriptSearchCredentials(): UseTranscriptSearchCredentialsResult {
	const provider = useSearchCredentialProvider();
	const [credentials, setCredentials] = useState<TranscriptSearchCredentials | null>(
		null,
	);
	const [error, setError] = useState<Error | null>(null);
	const [refreshToken, setRefreshToken] = useState(0);

	const refresh = useCallback(() => {
		setRefreshToken((value) => value + 1);
	}, []);

	useEffect(() => {
		let isActive = true;
		setError(null);

		provider
			.getTranscriptSearchCredentials()
			.then((nextCredentials) => {
				if (!isActive) {
					return;
				}
				setCredentials(nextCredentials);
			})
			.catch((caught) => {
				if (!isActive) {
					return;
				}
				setError(asError(caught));
			});

		return () => {
			isActive = false;
		};
	}, [provider, refreshToken]);

	return {
		credentials,
		error,
		isLoading: !credentials && !error,
		refresh,
	};
}


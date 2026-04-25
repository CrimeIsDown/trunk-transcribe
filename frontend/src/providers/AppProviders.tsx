import { useMemo, type ReactNode } from "react";

import { AuthProvider } from "./auth";
import { EntitlementsProvider } from "./entitlements";
import { NotificationsProvider } from "./notifications";
import {
	SavedSearchStoreProvider,
	createSirensBackendSavedSearchStore,
} from "./savedSearchStore";
import { SearchCredentialsProvider } from "./searchCredentials";
import { ViewerProvider } from "./viewer";

export function AppProviders({ children }: { children: ReactNode }) {
	const sirensApiBaseUrl = import.meta.env.VITE_SIRENS_API_BASE_URL;
	const savedSearchStore = useMemo(() => {
		if (!sirensApiBaseUrl) {
			return undefined;
		}

		return createSirensBackendSavedSearchStore({
			apiBaseUrl: sirensApiBaseUrl,
		});
	}, [sirensApiBaseUrl]);

	return (
		<AuthProvider>
			<ViewerProvider>
				<EntitlementsProvider>
					<SearchCredentialsProvider>
						<SavedSearchStoreProvider store={savedSearchStore}>
							<NotificationsProvider>{children}</NotificationsProvider>
						</SavedSearchStoreProvider>
					</SearchCredentialsProvider>
				</EntitlementsProvider>
			</ViewerProvider>
		</AuthProvider>
	);
}

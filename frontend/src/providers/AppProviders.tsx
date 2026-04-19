import type { ReactNode } from "react";

import { AuthProvider } from "./auth";
import { EntitlementsProvider } from "./entitlements";
import { NotificationsProvider } from "./notifications";
import { SavedSearchStoreProvider } from "./savedSearchStore";
import { SearchCredentialsProvider } from "./searchCredentials";
import { ViewerProvider } from "./viewer";

export function AppProviders({ children }: { children: ReactNode }) {
	return (
		<AuthProvider>
			<ViewerProvider>
				<EntitlementsProvider>
					<SearchCredentialsProvider>
						<SavedSearchStoreProvider>
							<NotificationsProvider>{children}</NotificationsProvider>
						</SavedSearchStoreProvider>
					</SearchCredentialsProvider>
				</EntitlementsProvider>
			</ViewerProvider>
		</AuthProvider>
	);
}


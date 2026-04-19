import { createContext, useContext, type ReactNode } from "react";

export type EntitlementsService = {
	canSearchTranscripts: () => boolean;
	canCreateAlerts: () => boolean;
};

const defaultEntitlementsService: EntitlementsService = {
	canSearchTranscripts: () => true,
	canCreateAlerts: () => false,
};

const EntitlementsContext = createContext<EntitlementsService>(
	defaultEntitlementsService,
);

export function EntitlementsProvider({
	children,
	service,
}: {
	children: ReactNode;
	service?: EntitlementsService;
}) {
	return (
		<EntitlementsContext.Provider
			value={service ?? defaultEntitlementsService}
		>
			{children}
		</EntitlementsContext.Provider>
	);
}

export function useEntitlements(): EntitlementsService {
	return useContext(EntitlementsContext);
}


import { createContext, useContext, type ReactNode } from "react";

export type Viewer = {
	id: string;
	displayName?: string;
	email?: string;
};

export type ViewerProvider = {
	viewer: Viewer | null;
	refresh: () => Promise<void>;
};

const defaultViewerProvider: ViewerProvider = {
	viewer: null,
	async refresh() {},
};

const ViewerContext = createContext<ViewerProvider>(defaultViewerProvider);

export function ViewerProvider({
	children,
	provider,
}: {
	children: ReactNode;
	provider?: ViewerProvider;
}) {
	return (
		<ViewerContext.Provider value={provider ?? defaultViewerProvider}>
			{children}
		</ViewerContext.Provider>
	);
}

export function useViewer(): ViewerProvider {
	return useContext(ViewerContext);
}


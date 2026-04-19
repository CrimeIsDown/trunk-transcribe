import { createContext, useContext, type ReactNode } from "react";

export type AuthStatus = "anonymous" | "authenticated" | "loading";

export type AuthProvider = {
	status: AuthStatus;
	getAccessToken: () => Promise<string | null>;
	signIn: () => Promise<void>;
	signOut: () => Promise<void>;
};

const defaultAuthProvider: AuthProvider = {
	status: "anonymous",
	async getAccessToken() {
		return null;
	},
	async signIn() {},
	async signOut() {},
};

const AuthContext = createContext<AuthProvider>(defaultAuthProvider);

export function AuthProvider({
	children,
	provider,
}: {
	children: ReactNode;
	provider?: AuthProvider;
}) {
	return (
		<AuthContext.Provider value={provider ?? defaultAuthProvider}>
			{children}
		</AuthContext.Provider>
	);
}

export function useAuth(): AuthProvider {
	return useContext(AuthContext);
}


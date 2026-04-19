import { createContext, useContext, type ReactNode } from "react";

export type NotificationLevel = "info" | "success" | "warning" | "error";

export type NotificationStore = {
	notify: (level: NotificationLevel, message: string) => void;
};

const defaultNotificationStore: NotificationStore = {
	notify: () => {},
};

const NotificationContext = createContext<NotificationStore>(
	defaultNotificationStore,
);

export function NotificationsProvider({
	children,
	store,
}: {
	children: ReactNode;
	store?: NotificationStore;
}) {
	return (
		<NotificationContext.Provider value={store ?? defaultNotificationStore}>
			{children}
		</NotificationContext.Provider>
	);
}

export function useNotifications(): NotificationStore {
	return useContext(NotificationContext);
}


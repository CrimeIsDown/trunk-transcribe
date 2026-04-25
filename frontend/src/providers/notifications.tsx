import { createContext, useContext, type ReactNode } from "react";

export type NotificationLevel = "info" | "success" | "warning" | "error";

export type NotificationChannel = {
	id: string;
	service: string;
	path: string;
	createdAt?: string;
	updatedAt?: string;
};

export type TranscriptSubscriptionLocation = {
	address?: string;
	radius?: number;
	travelTime?: number;
	geo?: {
		lat: number;
		lng: number;
	};
};

export type TranscriptSubscription = {
	id: string;
	name: string;
	enabled: boolean;
	topic: string;
	keywords: string[];
	ignoreKeywords: string[];
	location: TranscriptSubscriptionLocation | null;
	notificationChannelIds: string[];
	createdAt?: string;
	updatedAt?: string;
};

export type AvailableTalkgroup = {
	id: number;
	label: string;
	system: string;
	value: string;
};

export type AvailableTalkgroupGroup = {
	id: number;
	group: string;
	talkgroups: AvailableTalkgroup[];
};

export type AvailableTalkgroupSystem = {
	id: number;
	group: string;
	talkgroups: AvailableTalkgroupGroup[];
};

export type CreateNotificationChannelInput = {
	service: string;
	path: string;
};

export type UpdateNotificationChannelInput = Partial<CreateNotificationChannelInput>;

export type CreateTranscriptSubscriptionInput = {
	name: string;
	enabled: boolean;
	topic: string;
	keywords?: string[];
	ignoreKeywords?: string[];
	location?: TranscriptSubscriptionLocation | null;
	notificationChannelIds: string[];
};

export type UpdateTranscriptSubscriptionInput = Partial<CreateTranscriptSubscriptionInput>;

export type NotificationStore = {
	notify: (level: NotificationLevel, message: string) => void;
	listNotificationChannels: () => Promise<NotificationChannel[]>;
	createNotificationChannel: (
		input: CreateNotificationChannelInput,
	) => Promise<NotificationChannel>;
	updateNotificationChannel: (
		id: string,
		input: UpdateNotificationChannelInput,
	) => Promise<NotificationChannel>;
	removeNotificationChannel: (id: string) => Promise<void>;
	listTranscriptSubscriptions: () => Promise<TranscriptSubscription[]>;
	createTranscriptSubscription: (
		input: CreateTranscriptSubscriptionInput,
	) => Promise<TranscriptSubscription>;
	updateTranscriptSubscription: (
		id: string,
		input: UpdateTranscriptSubscriptionInput,
	) => Promise<TranscriptSubscription>;
	removeTranscriptSubscription: (id: string) => Promise<void>;
	listAvailableTalkgroups: () => Promise<AvailableTalkgroupSystem[]>;
};

function isRecord(value: unknown): value is Record<string, unknown> {
	return typeof value === "object" && value !== null && !Array.isArray(value);
}

function trimTrailingSlash(value: string): string {
	return value.endsWith("/") ? value.slice(0, -1) : value;
}

function getXsrfToken(): string | null {
	if (typeof document === "undefined") {
		return null;
	}

	const tokenCookie = document.cookie
		.split("; ")
		.find((row) => row.startsWith("XSRF-TOKEN="))
		?.split("=")[1];

	return tokenCookie ? decodeURIComponent(tokenCookie) : null;
}

async function readSirensJson(response: Response): Promise<unknown> {
	const contentType = response.headers.get("Content-Type") || "";
	if (contentType.includes("application/json")) {
		return response.json();
	}
	return response.text();
}

function parseStringArray(value: unknown): string[] {
	if (Array.isArray(value)) {
		return value
			.map((item) => (typeof item === "string" ? item.trim() : ""))
			.filter(Boolean);
	}

	if (typeof value === "string" && value.trim()) {
		try {
			const parsed = JSON.parse(value);
			return parseStringArray(parsed);
		} catch {
			return [value.trim()];
		}
	}

	return [];
}

function parseLocation(
	value: unknown,
): TranscriptSubscriptionLocation | null {
	if (!value) {
		return null;
	}

	if (typeof value === "string") {
		try {
			return parseLocation(JSON.parse(value));
		} catch {
			return null;
		}
	}

	if (!isRecord(value)) {
		return null;
	}

	const address = typeof value.address === "string" ? value.address : undefined;
	const radius = typeof value.radius === "number" ? value.radius : undefined;
	const travelTime =
		typeof value.travel_time === "number"
			? value.travel_time
			: typeof value.travelTime === "number"
				? value.travelTime
				: undefined;
	const geoCandidate = value.geo;
	const geo =
		isRecord(geoCandidate) &&
		typeof geoCandidate.lat === "number" &&
		typeof geoCandidate.lng === "number"
			? { lat: geoCandidate.lat, lng: geoCandidate.lng }
			: null;

	return {
		...(address ? { address } : {}),
		...(radius !== undefined ? { radius } : {}),
		...(travelTime !== undefined ? { travelTime } : {}),
		...(geo ? { geo } : {}),
	};
}

function parseNotificationChannel(value: unknown): NotificationChannel | null {
	if (!isRecord(value)) {
		return null;
	}

	const id = value.id;
	const service = value.service;
	const path = value.path;
	if (
		(typeof id !== "number" && typeof id !== "string") ||
		typeof service !== "string" ||
		typeof path !== "string"
	) {
		return null;
	}

	const createdAt =
		typeof value.created_at === "string"
			? value.created_at
			: typeof value.createdAt === "string"
				? value.createdAt
				: undefined;
	const updatedAt =
		typeof value.updated_at === "string"
			? value.updated_at
			: typeof value.updatedAt === "string"
				? value.updatedAt
				: undefined;

	return {
		id: String(id),
		service,
		path,
		...(createdAt ? { createdAt } : {}),
		...(updatedAt ? { updatedAt } : {}),
	};
}

function parseTranscriptSubscription(
	value: unknown,
): TranscriptSubscription | null {
	if (!isRecord(value)) {
		return null;
	}

	const id = value.id;
	const name = value.name;
	const topic = value.topic;
	const enabled =
		typeof value.enabled === "boolean"
			? value.enabled
			: typeof value.enabled === "number"
				? value.enabled > 0
				: true;

	if (
		(typeof id !== "number" && typeof id !== "string") ||
		typeof name !== "string" ||
		typeof topic !== "string"
	) {
		return null;
	}

	const createdAt =
		typeof value.created_at === "string"
			? value.created_at
			: typeof value.createdAt === "string"
				? value.createdAt
				: undefined;
	const updatedAt =
		typeof value.updated_at === "string"
			? value.updated_at
			: typeof value.updatedAt === "string"
				? value.updatedAt
				: undefined;

	const notificationChannelIds = parseStringArray(
		value.notification_channels ?? value.notificationChannelIds,
	).map(String);

	return {
		id: String(id),
		name: name.trim(),
		enabled,
		topic: topic.trim(),
		keywords: parseStringArray(value.keywords),
		ignoreKeywords: parseStringArray(
			value.ignore_keywords ?? value.ignoreKeywords,
		),
		location: parseLocation(value.location),
		notificationChannelIds,
		...(createdAt ? { createdAt } : {}),
		...(updatedAt ? { updatedAt } : {}),
	};
}

function parseAvailableTalkgroups(
	value: unknown,
): AvailableTalkgroupSystem[] {
	if (!Array.isArray(value)) {
		return [];
	}

	return value
		.map((system) => {
			if (!isRecord(system)) {
				return null;
			}

			const id = system.id;
			const group = system.group;
			const talkgroups = system.talkgroups;
			if (typeof id !== "number" || typeof group !== "string" || !Array.isArray(talkgroups)) {
				return null;
			}

			const parsedGroups = talkgroups
				.map((groupValue) => {
					if (!isRecord(groupValue)) {
						return null;
					}

					const groupId = groupValue.id;
					const groupName = groupValue.group;
					const groupTalkgroups = groupValue.talkgroups;
					if (
						typeof groupId !== "number" ||
						typeof groupName !== "string" ||
						!Array.isArray(groupTalkgroups)
					) {
						return null;
					}

					const parsedTalkgroups = groupTalkgroups
						.map((tg) => {
							if (!isRecord(tg)) {
								return null;
							}

							const tgId = tg.id;
							const label = tg.label;
							const systemName = tg.system;
							const tgValue = tg.value;
							if (
								typeof tgId !== "number" ||
								typeof label !== "string" ||
								typeof systemName !== "string" ||
								typeof tgValue !== "string"
							) {
								return null;
							}

							return {
								id: tgId,
								label,
								system: systemName,
								value: tgValue,
							} satisfies AvailableTalkgroup;
						})
						.filter((tg): tg is AvailableTalkgroup => tg !== null);

					return {
						id: groupId,
						group: groupName,
						talkgroups: parsedTalkgroups,
					} satisfies AvailableTalkgroupGroup;
				})
				.filter((entry): entry is AvailableTalkgroupGroup => entry !== null);

			return {
				id,
				group,
				talkgroups: parsedGroups,
			} satisfies AvailableTalkgroupSystem;
		})
		.filter((system): system is AvailableTalkgroupSystem => system !== null);
}

function createNoopNotificationStore(): NotificationStore {
	return {
		notify: () => {},
		async listNotificationChannels() {
			return [];
		},
		async createNotificationChannel() {
			throw new Error("Notification channels are not configured for this app.");
		},
		async updateNotificationChannel() {
			throw new Error("Notification channels are not configured for this app.");
		},
		async removeNotificationChannel() {
			throw new Error("Notification channels are not configured for this app.");
		},
		async listTranscriptSubscriptions() {
			return [];
		},
		async createTranscriptSubscription() {
			throw new Error("Transcript subscriptions are not configured for this app.");
		},
		async updateTranscriptSubscription() {
			throw new Error("Transcript subscriptions are not configured for this app.");
		},
		async removeTranscriptSubscription() {
			throw new Error("Transcript subscriptions are not configured for this app.");
		},
		async listAvailableTalkgroups() {
			return [];
		},
	};
}

export function createSirensBackendNotificationStore({
	apiBaseUrl,
}: {
	apiBaseUrl: string;
}): NotificationStore {
	const baseUrl = trimTrailingSlash(apiBaseUrl);

	return {
		notify: () => {},

		async listNotificationChannels() {
			const response = await fetch(`${baseUrl}/api/notificationChannels`, {
				credentials: "include",
				headers: {
					Accept: "application/json",
				},
			});
			if (!response.ok) {
				throw new Error(
					`Failed to load notification channels (${response.status})`,
				);
			}

			const payload = await response.json();
			return Array.isArray(payload)
				? payload
						.map(parseNotificationChannel)
						.filter((channel): channel is NotificationChannel => channel !== null)
				: [];
		},

		async createNotificationChannel(input) {
			const xsrfToken = getXsrfToken();
			const response = await fetch(`${baseUrl}/api/notificationChannels`, {
				method: "POST",
				credentials: "include",
				headers: {
					Accept: "application/json",
					"Content-Type": "application/json",
					...(xsrfToken ? { "X-XSRF-TOKEN": xsrfToken } : {}),
				},
				body: JSON.stringify({
					service: input.service,
					path: input.path,
				}),
			});
			if (!response.ok) {
				const detail = await readSirensJson(response);
				throw new Error(
					`Failed to create notification channel (${response.status}): ${JSON.stringify(detail)}`,
				);
			}

			const payload = await response.json();
			const channel = parseNotificationChannel(payload);
			if (!channel) {
				throw new Error("Notification channel was created but could not be parsed.");
			}
			return channel;
		},

		async updateNotificationChannel(id, input) {
			const xsrfToken = getXsrfToken();
			const response = await fetch(`${baseUrl}/api/notificationChannels/${id}`, {
				method: "PATCH",
				credentials: "include",
				headers: {
					Accept: "application/json",
					"Content-Type": "application/json",
					...(xsrfToken ? { "X-XSRF-TOKEN": xsrfToken } : {}),
				},
				body: JSON.stringify({
					...(input.service ? { service: input.service } : {}),
					...(input.path ? { path: input.path } : {}),
				}),
			});
			if (!response.ok) {
				const detail = await readSirensJson(response);
				throw new Error(
					`Failed to update notification channel (${response.status}): ${JSON.stringify(detail)}`,
				);
			}

			const payload = await response.json();
			const channel = parseNotificationChannel(payload);
			if (!channel) {
				throw new Error("Notification channel was updated but could not be parsed.");
			}
			return channel;
		},

		async removeNotificationChannel(id) {
			const xsrfToken = getXsrfToken();
			const response = await fetch(`${baseUrl}/api/notificationChannels/${id}`, {
				method: "DELETE",
				credentials: "include",
				headers: {
					Accept: "application/json",
					...(xsrfToken ? { "X-XSRF-TOKEN": xsrfToken } : {}),
				},
			});
			if (!response.ok) {
				const detail = await readSirensJson(response);
				throw new Error(
					`Failed to delete notification channel (${response.status}): ${JSON.stringify(detail)}`,
				);
			}
		},

		async listTranscriptSubscriptions() {
			const response = await fetch(`${baseUrl}/api/transcriptSubscriptions`, {
				credentials: "include",
				headers: {
					Accept: "application/json",
				},
			});
			if (!response.ok) {
				throw new Error(
					`Failed to load transcript subscriptions (${response.status})`,
				);
			}

			const payload = await response.json();
			return Array.isArray(payload)
				? payload
						.map(parseTranscriptSubscription)
						.filter(
							(sub): sub is TranscriptSubscription => sub !== null,
						)
				: [];
		},

		async createTranscriptSubscription(input) {
			const xsrfToken = getXsrfToken();
			const response = await fetch(`${baseUrl}/api/transcriptSubscriptions`, {
				method: "POST",
				credentials: "include",
				headers: {
					Accept: "application/json",
					"Content-Type": "application/json",
					...(xsrfToken ? { "X-XSRF-TOKEN": xsrfToken } : {}),
				},
				body: JSON.stringify({
					name: input.name,
					enabled: input.enabled,
					topic: input.topic,
					...(input.keywords ? { keywords: input.keywords } : {}),
					...(input.ignoreKeywords
						? { ignore_keywords: input.ignoreKeywords }
						: {}),
					...(input.location ? { location: input.location } : {}),
					notification_channels: input.notificationChannelIds,
				}),
			});
			if (!response.ok) {
				const detail = await readSirensJson(response);
				throw new Error(
					`Failed to create transcript subscription (${response.status}): ${JSON.stringify(detail)}`,
				);
			}

			const payload = await response.json();
			const subscription = parseTranscriptSubscription(payload);
			if (!subscription) {
				throw new Error(
					"Transcript subscription was created but could not be parsed.",
				);
			}

			return {
				...subscription,
				notificationChannelIds:
					subscription.notificationChannelIds.length > 0
						? subscription.notificationChannelIds
						: input.notificationChannelIds.map(String),
			};
		},

		async updateTranscriptSubscription(id, input) {
			const xsrfToken = getXsrfToken();
			const response = await fetch(`${baseUrl}/api/transcriptSubscriptions/${id}`, {
				method: "PATCH",
				credentials: "include",
				headers: {
					Accept: "application/json",
					"Content-Type": "application/json",
					...(xsrfToken ? { "X-XSRF-TOKEN": xsrfToken } : {}),
				},
				body: JSON.stringify({
					...(input.name ? { name: input.name } : {}),
					...(input.enabled !== undefined ? { enabled: input.enabled } : {}),
					...(input.topic ? { topic: input.topic } : {}),
					...(input.notificationChannelIds
						? { notification_channels: input.notificationChannelIds }
						: {}),
				}),
			});
			if (!response.ok) {
				const detail = await readSirensJson(response);
				throw new Error(
					`Failed to update transcript subscription (${response.status}): ${JSON.stringify(detail)}`,
				);
			}

			const payload = await response.json();
			const subscription = parseTranscriptSubscription(payload);
			if (!subscription) {
				throw new Error(
					"Transcript subscription was updated but could not be parsed.",
				);
			}

			return {
				...subscription,
				notificationChannelIds:
					subscription.notificationChannelIds.length > 0
						? subscription.notificationChannelIds
						: input.notificationChannelIds?.map(String) ?? [],
			};
		},

		async removeTranscriptSubscription(id) {
			const xsrfToken = getXsrfToken();
			const response = await fetch(`${baseUrl}/api/transcriptSubscriptions/${id}`, {
				method: "DELETE",
				credentials: "include",
				headers: {
					Accept: "application/json",
					...(xsrfToken ? { "X-XSRF-TOKEN": xsrfToken } : {}),
				},
			});
			if (!response.ok) {
				const detail = await readSirensJson(response);
				throw new Error(
					`Failed to delete transcript subscription (${response.status}): ${JSON.stringify(detail)}`,
				);
			}
		},

		async listAvailableTalkgroups() {
			const response = await fetch(`${baseUrl}/api/searchTalkgroups`, {
				credentials: "include",
				headers: {
					Accept: "application/json",
				},
			});
			if (!response.ok) {
				throw new Error(
					`Failed to load available talkgroups (${response.status})`,
				);
			}

			const payload = await response.json();
			return parseAvailableTalkgroups(payload);
		},
	};
}

const defaultNotificationStore: NotificationStore = (() => {
	const sirensApiBaseUrl = import.meta.env.VITE_SIRENS_API_BASE_URL;
	if (sirensApiBaseUrl) {
		return createSirensBackendNotificationStore({
			apiBaseUrl: sirensApiBaseUrl,
		});
	}

	return createNoopNotificationStore();
})();

const NotificationContext = createContext<NotificationStore>(defaultNotificationStore);

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

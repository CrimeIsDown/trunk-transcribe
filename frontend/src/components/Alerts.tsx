"use client";

import { useEffect, useMemo, useState } from "react";
import {
	Alert,
	Badge,
	Button,
	Col,
	Form,
	Modal,
	Row,
	Spinner,
	Table,
} from "react-bootstrap";

import type { ScannerSearchUiState } from "@/lib/searchState";
import {
	describeTranscriptSavedSearchState,
	type TranscriptSavedSearchEntry,
} from "@/lib/transcriptSavedSearches";
import { useAuth } from "@/providers/auth";
import { useEntitlements } from "@/providers/entitlements";
import type {
	AvailableTalkgroupSystem,
	CreateTranscriptSubscriptionInput,
	NotificationChannel,
	TranscriptSubscription,
	UpdateNotificationChannelInput,
	UpdateTranscriptSubscriptionInput,
} from "@/providers/notifications";
import { useNotifications } from "@/providers/notifications";
import { useSavedSearchStore } from "@/providers/savedSearchStore";

function parseCsv(input: string): string[] {
	return input
		.split(",")
		.map((value) => value.trim())
		.filter(Boolean);
}

type FlattenedTalkgroup = {
	label: string;
	group: string;
	value: string;
	systemId: string;
};

function flattenTalkgroups(systems: AvailableTalkgroupSystem[]): FlattenedTalkgroup[] {
	return systems.flatMap((system) =>
		system.talkgroups.flatMap((group) =>
			group.talkgroups.flatMap((talkgroup) => {
				const systemId = talkgroup.value.split("@")[1] ?? "";
				return systemId
					? [
							{
								label: talkgroup.label,
								group: group.group,
								value: talkgroup.value,
								systemId,
							},
						]
					: [];
			}),
		),
	);
}

function deriveTopicFromSearchState(
	state: ScannerSearchUiState,
	availableTalkgroups: AvailableTalkgroupSystem[],
): string | null {
	const systemIds = state.refinementList?.short_name ?? [];
	const talkgroupLabels = state.refinementList?.talkgroup_tag ?? [];
	const groupLabels = state.refinementList?.talkgroup_group ?? [];

	const talkgroups = flattenTalkgroups(availableTalkgroups);
	const scopedBySystem = (entry: FlattenedTalkgroup): boolean =>
		systemIds.length === 0 || systemIds.includes(entry.systemId);

	const topicsFromTalkgroups = talkgroupLabels.length
		? Array.from(
				new Set(
					talkgroups
						.filter(scopedBySystem)
						.filter((entry) => talkgroupLabels.includes(entry.label))
						.map((entry) => entry.value),
				),
			)
		: [];

	if (topicsFromTalkgroups.length > 0) {
		return topicsFromTalkgroups.join("|");
	}

	const topicsFromGroups = groupLabels.length
		? Array.from(
				new Set(
					talkgroups
						.filter(scopedBySystem)
						.filter((entry) => groupLabels.includes(entry.group))
						.map((entry) => entry.value),
				),
			)
		: [];

	if (topicsFromGroups.length > 0) {
		return topicsFromGroups.join("|");
	}

	if (systemIds.length > 0) {
		return systemIds.length === 1
			? `.*@${systemIds[0]}`
			: `.*@(${systemIds.join("|")})`;
	}

	return null;
}

export default function Alerts() {
	const auth = useAuth();
	const entitlements = useEntitlements();
	const notifications = useNotifications();
	const savedSearchStore = useSavedSearchStore();

	const canCreateAlerts = entitlements.canCreateAlerts();

	const [channels, setChannels] = useState<NotificationChannel[]>([]);
	const [subscriptions, setSubscriptions] = useState<TranscriptSubscription[]>([]);
	const [savedSearches, setSavedSearches] = useState<TranscriptSavedSearchEntry[]>([]);
	const [talkgroups, setTalkgroups] = useState<AvailableTalkgroupSystem[]>([]);

	const [loadError, setLoadError] = useState<string | null>(null);
	const [isLoading, setIsLoading] = useState(false);

	const [channelForm, setChannelForm] = useState({
		service: "tgram",
		path: "",
	});
	const [subscriptionForm, setSubscriptionForm] = useState<{
		name: string;
		enabled: boolean;
		topic: string;
		keywordsCsv: string;
		ignoreKeywordsCsv: string;
		notificationChannelIds: string[];
	}>({
		name: "",
		enabled: true,
		topic: "",
		keywordsCsv: "",
		ignoreKeywordsCsv: "",
		notificationChannelIds: [],
	});

	const [selectedSavedSearchId, setSelectedSavedSearchId] = useState<string>("");

	const [editingChannel, setEditingChannel] = useState<NotificationChannel | null>(null);
	const [editingSubscription, setEditingSubscription] = useState<TranscriptSubscription | null>(
		null,
	);
	const [isSaving, setIsSaving] = useState(false);
	const [actionError, setActionError] = useState<string | null>(null);

	const selectedSavedSearch = useMemo(
		() => savedSearches.find((entry) => entry.id === selectedSavedSearchId) ?? null,
		[savedSearches, selectedSavedSearchId],
	);

	async function refresh() {
		setIsLoading(true);
		setLoadError(null);

		try {
			const [nextChannels, nextSubscriptions, nextSavedSearches] = await Promise.all([
				notifications.listNotificationChannels(),
				notifications.listTranscriptSubscriptions(),
				savedSearchStore.list(),
			]);
			setChannels(nextChannels);
			setSubscriptions(nextSubscriptions);
			setSavedSearches(nextSavedSearches);

			try {
				const nextTalkgroups = await notifications.listAvailableTalkgroups();
				setTalkgroups(nextTalkgroups);
			} catch {
				// Talkgroup metadata is helpful for prefill but shouldn't block core alert CRUD.
			}
		} catch (error) {
			setLoadError(error instanceof Error ? error.message : String(error));
		} finally {
			setIsLoading(false);
		}
	}

	useEffect(() => {
		if (auth.status !== "authenticated") {
			return;
		}

		void refresh();
		// eslint-disable-next-line react-hooks/exhaustive-deps
	}, [auth.status]);

	const isActionsEnabled = auth.status === "authenticated" && canCreateAlerts;

	return (
		<div className="container-fluid py-3">
			<Row className="align-items-center mb-3">
				<Col>
					<h1 className="mb-0">Alerts</h1>
					<div className="text-muted small">
						Create notification channels and subscribe to transcript topics.
					</div>
				</Col>
				<Col xs="auto">
					<Button
						type="button"
						variant="outline-secondary"
						disabled={auth.status !== "authenticated" || isLoading}
						onClick={() => void refresh()}
					>
						Refresh
					</Button>
				</Col>
			</Row>

			{auth.status === "anonymous" ? (
				<Alert variant="info">
					<div className="d-flex flex-column flex-md-row align-items-start align-items-md-center justify-content-between gap-2">
						<div>
							<div className="fw-semibold">Sign in to manage alerts</div>
							<div className="small">
								Alerts are a Sirens feature. Sign in to create channels and
								subscriptions.
							</div>
						</div>
						<Button type="button" onClick={() => void auth.signIn()}>
							Sign in
						</Button>
					</div>
				</Alert>
			) : null}

			{auth.status === "authenticated" && !canCreateAlerts ? (
				<Alert variant="warning">
					<div className="fw-semibold">Alerts are not enabled for this account.</div>
					<div className="small">
						If you think this is a mistake, refresh or contact support.
					</div>
				</Alert>
			) : null}

			{loadError ? (
				<Alert variant="danger">
					<div className="fw-semibold">Failed to load alerts data</div>
					<div className="small mt-1">{loadError}</div>
				</Alert>
			) : null}

			{isLoading ? (
				<Alert variant="secondary">
					<Spinner animation="border" size="sm" className="me-2" />
					Loading alerts…
				</Alert>
			) : null}

			{actionError ? (
				<Alert variant="danger" onClose={() => setActionError(null)} dismissible>
					{actionError}
				</Alert>
			) : null}

			<Row className="g-4">
				<Col lg={5}>
					<div className="border rounded p-3 bg-white">
						<div className="d-flex align-items-center justify-content-between mb-2">
							<div className="fw-semibold">Notification Channels</div>
							<Badge bg="secondary">{channels.length}</Badge>
						</div>

						<Form
							onSubmit={(event) => {
								event.preventDefault();
								if (!isActionsEnabled) {
									return;
								}

								setIsSaving(true);
								setActionError(null);
								void notifications
									.createNotificationChannel({
										service: channelForm.service,
										path: channelForm.path,
									})
									.then((created) => {
										setChannels((prev) => [...prev, created]);
										setChannelForm((prev) => ({ ...prev, path: "" }));
									})
									.catch((error) => {
										setActionError(
											error instanceof Error ? error.message : String(error),
										);
									})
									.finally(() => setIsSaving(false));
							}}
						>
							<Row className="g-2 align-items-end">
								<Col xs={4}>
									<Form.Label>Service</Form.Label>
									<Form.Select
										disabled={!isActionsEnabled || isSaving}
										value={channelForm.service}
										onChange={(event) =>
											setChannelForm((prev) => ({
												...prev,
												service: event.target.value,
											}))
										}
									>
										<option value="tgram">Telegram</option>
										<option value="ntfy">ntfy</option>
										<option value="mailgun">Mailgun</option>
										<option value="sns">AWS SNS</option>
										<option value="ses">AWS SES</option>
									</Form.Select>
								</Col>
								<Col>
									<Form.Label>Path</Form.Label>
									<Form.Control
										disabled={!isActionsEnabled || isSaving}
										value={channelForm.path}
										placeholder="Channel identifier, email, topic, etc"
										onChange={(event) =>
											setChannelForm((prev) => ({
												...prev,
												path: event.target.value,
											}))
										}
									/>
								</Col>
								<Col xs="auto">
									<Button
										type="submit"
										disabled={!isActionsEnabled || isSaving || !channelForm.path.trim()}
									>
										Add
									</Button>
								</Col>
							</Row>
						</Form>

						<div className="mt-3">
							<Table size="sm" responsive bordered>
								<thead>
									<tr>
										<th>Service</th>
										<th>Path</th>
										<th style={{ width: "1%" }}>Actions</th>
									</tr>
								</thead>
								<tbody>
									{channels.length === 0 ? (
										<tr>
											<td colSpan={3} className="text-muted text-center">
												No channels configured yet.
											</td>
										</tr>
									) : (
										channels.map((channel) => (
											<tr key={channel.id}>
												<td>{channel.service}</td>
												<td className="text-break">{channel.path}</td>
												<td className="text-nowrap">
													<Button
														size="sm"
														variant="outline-primary"
														className="me-2"
														disabled={!isActionsEnabled || isSaving}
														onClick={() => setEditingChannel(channel)}
													>
														Edit
													</Button>
													<Button
														size="sm"
														variant="outline-danger"
														disabled={!isActionsEnabled || isSaving}
														onClick={() => {
															setIsSaving(true);
															setActionError(null);
															void notifications
																.removeNotificationChannel(channel.id)
																.then(() =>
																	setChannels((prev) =>
																		prev.filter((entry) => entry.id !== channel.id),
																	),
																)
																.catch((error) =>
																	setActionError(
																		error instanceof Error
																			? error.message
																			: String(error),
																	),
																)
																.finally(() => setIsSaving(false));
														}}
													>
														Delete
													</Button>
												</td>
											</tr>
										))
									)}
								</tbody>
							</Table>
						</div>
					</div>
				</Col>

				<Col lg={7}>
					<div className="border rounded p-3 bg-white">
						<div className="d-flex align-items-center justify-content-between mb-2">
							<div className="fw-semibold">Transcript Subscriptions</div>
							<Badge bg="secondary">{subscriptions.length}</Badge>
						</div>

						<div className="border rounded p-2 mb-3 bg-body-tertiary">
							<div className="fw-semibold mb-2">Create Alert From Saved Search</div>
							<Row className="g-2 align-items-end">
								<Col>
									<Form.Label>Saved Search</Form.Label>
									<Form.Select
										value={selectedSavedSearchId}
										disabled={auth.status !== "authenticated" || isSaving}
										onChange={(event) => setSelectedSavedSearchId(event.target.value)}
									>
										<option value="">Select a saved search…</option>
										{savedSearches.map((entry) => (
											<option key={entry.id} value={entry.id}>
												{entry.name}
											</option>
										))}
									</Form.Select>
								</Col>
								<Col xs="auto">
									<Button
										type="button"
										variant="outline-primary"
										disabled={
											!isActionsEnabled ||
											isSaving ||
											!selectedSavedSearch ||
											talkgroups.length === 0
										}
										onClick={() => {
											if (!selectedSavedSearch) {
												return;
											}

											const derivedTopic = deriveTopicFromSearchState(
												selectedSavedSearch.state,
												talkgroups,
											);
											setSubscriptionForm((prev) => ({
												...prev,
												name: selectedSavedSearch.name,
												topic: derivedTopic ?? prev.topic,
												keywordsCsv: selectedSavedSearch.state.query ?? prev.keywordsCsv,
											}));
										}}
									>
										Prefill
									</Button>
								</Col>
							</Row>
							{selectedSavedSearch ? (
								<div className="small text-muted mt-2">
									{describeTranscriptSavedSearchState(selectedSavedSearch.state).length === 0
										? "This saved search has no active filters."
										: describeTranscriptSavedSearchState(selectedSavedSearch.state).join(" · ")}
								</div>
							) : null}
							{talkgroups.length === 0 ? (
								<div className="small text-muted mt-2">
									Talkgroup metadata is unavailable, so we can’t derive topics from search
									state yet.
								</div>
							) : null}
						</div>

						<Form
							onSubmit={(event) => {
								event.preventDefault();
								if (!isActionsEnabled) {
									return;
								}

								const payload: CreateTranscriptSubscriptionInput = {
									name: subscriptionForm.name,
									enabled: subscriptionForm.enabled,
									topic: subscriptionForm.topic,
									keywords: subscriptionForm.keywordsCsv
										? parseCsv(subscriptionForm.keywordsCsv)
										: undefined,
									ignoreKeywords: subscriptionForm.ignoreKeywordsCsv
										? parseCsv(subscriptionForm.ignoreKeywordsCsv)
										: undefined,
									notificationChannelIds: subscriptionForm.notificationChannelIds,
								};

								setIsSaving(true);
								setActionError(null);
								void notifications
									.createTranscriptSubscription(payload)
									.then((created) => {
										setSubscriptions((prev) => [...prev, created]);
										setSubscriptionForm((prev) => ({
											...prev,
											name: "",
											topic: "",
											keywordsCsv: "",
											ignoreKeywordsCsv: "",
										}));
									})
									.catch((error) => {
										setActionError(
											error instanceof Error ? error.message : String(error),
										);
									})
									.finally(() => setIsSaving(false));
							}}
						>
							<Row className="g-2">
								<Col md={6}>
									<Form.Label>Name</Form.Label>
									<Form.Control
										disabled={!isActionsEnabled || isSaving}
										value={subscriptionForm.name}
										onChange={(event) =>
											setSubscriptionForm((prev) => ({
												...prev,
												name: event.target.value,
											}))
										}
										placeholder="e.g. Night OEMC hits"
									/>
								</Col>
								<Col md={3}>
									<Form.Label>Enabled</Form.Label>
									<Form.Check
										type="switch"
										disabled={!isActionsEnabled || isSaving}
										checked={subscriptionForm.enabled}
										onChange={(event) =>
											setSubscriptionForm((prev) => ({
												...prev,
												enabled: event.target.checked,
											}))
										}
										label={subscriptionForm.enabled ? "On" : "Off"}
									/>
								</Col>
								<Col md={3}>
									<Form.Label>Destinations</Form.Label>
									<Form.Select
										disabled={!isActionsEnabled || isSaving}
										multiple
										value={subscriptionForm.notificationChannelIds}
										onChange={(event) => {
											const selected = Array.from(event.target.selectedOptions).map(
												(option) => option.value,
											);
											setSubscriptionForm((prev) => ({
												...prev,
												notificationChannelIds: selected,
											}));
										}}
									>
										{channels.map((channel) => (
											<option key={channel.id} value={channel.id}>
												{channel.service}: {channel.path}
											</option>
										))}
									</Form.Select>
									<div className="small text-muted">
										Hold Ctrl/Cmd to pick multiple channels.
									</div>
								</Col>
							</Row>

							<Row className="g-2 mt-1">
								<Col>
									<Form.Label>Topic (talkgroup@system or regex)</Form.Label>
									<Form.Control
										disabled={!isActionsEnabled || isSaving}
										value={subscriptionForm.topic}
										onChange={(event) =>
											setSubscriptionForm((prev) => ({
												...prev,
												topic: event.target.value,
											}))
										}
										placeholder="e.g. 14@chi_cpd"
									/>
								</Col>
							</Row>

							<Row className="g-2 mt-1">
								<Col md={6}>
									<Form.Label>Keywords (comma-separated)</Form.Label>
									<Form.Control
										disabled={!isActionsEnabled || isSaving}
										value={subscriptionForm.keywordsCsv}
										onChange={(event) =>
											setSubscriptionForm((prev) => ({
												...prev,
												keywordsCsv: event.target.value,
											}))
										}
										placeholder="e.g. shots fired, pursuit"
									/>
								</Col>
								<Col md={6}>
									<Form.Label>Ignore Keywords (comma-separated)</Form.Label>
									<Form.Control
										disabled={!isActionsEnabled || isSaving}
										value={subscriptionForm.ignoreKeywordsCsv}
										onChange={(event) =>
											setSubscriptionForm((prev) => ({
												...prev,
												ignoreKeywordsCsv: event.target.value,
											}))
										}
										placeholder="e.g. test, drill"
									/>
								</Col>
							</Row>

							<div className="mt-2 d-flex justify-content-end">
								<Button
									type="submit"
									disabled={
										!isActionsEnabled ||
										isSaving ||
										!subscriptionForm.name.trim() ||
										!subscriptionForm.topic.trim() ||
										subscriptionForm.notificationChannelIds.length === 0
									}
								>
									Create Alert
								</Button>
							</div>
						</Form>

						<div className="mt-3">
							<Table size="sm" responsive bordered>
								<thead>
									<tr>
										<th>Name</th>
										<th>Topic</th>
										<th>Destinations</th>
										<th>Enabled</th>
										<th style={{ width: "1%" }}>Actions</th>
									</tr>
								</thead>
								<tbody>
									{subscriptions.length === 0 ? (
										<tr>
											<td colSpan={5} className="text-muted text-center">
												No subscriptions configured yet.
											</td>
										</tr>
									) : (
										subscriptions.map((subscription) => (
											<tr key={subscription.id}>
												<td className="text-break">
													<div className="fw-semibold">{subscription.name}</div>
													{subscription.keywords.length > 0 ? (
														<div className="small text-muted">
															Keywords: {subscription.keywords.join(", ")}
														</div>
													) : null}
													{subscription.ignoreKeywords.length > 0 ? (
														<div className="small text-muted">
															Ignore: {subscription.ignoreKeywords.join(", ")}
														</div>
													) : null}
												</td>
												<td className="text-break">
													<code>{subscription.topic}</code>
												</td>
												<td>
													{subscription.notificationChannelIds.length === 0 ? (
														<span className="text-muted">None</span>
													) : (
														subscription.notificationChannelIds.length
													)}
												</td>
												<td>{subscription.enabled ? "On" : "Off"}</td>
												<td className="text-nowrap">
													<Button
														size="sm"
														variant="outline-primary"
														className="me-2"
														disabled={!isActionsEnabled || isSaving}
														onClick={() => setEditingSubscription(subscription)}
													>
														Edit
													</Button>
													<Button
														size="sm"
														variant="outline-secondary"
														className="me-2"
														disabled={!isActionsEnabled || isSaving}
														onClick={() => {
															setIsSaving(true);
															setActionError(null);
															void notifications
																.updateTranscriptSubscription(subscription.id, {
																	enabled: !subscription.enabled,
																})
																.then((updated) =>
																	setSubscriptions((prev) =>
																		prev.map((entry) =>
																			entry.id === subscription.id ? updated : entry,
																		),
																	),
																)
																.catch((error) =>
																	setActionError(
																		error instanceof Error
																			? error.message
																			: String(error),
																	),
																)
																.finally(() => setIsSaving(false));
														}}
													>
														Toggle
													</Button>
													<Button
														size="sm"
														variant="outline-danger"
														disabled={!isActionsEnabled || isSaving}
														onClick={() => {
															setIsSaving(true);
															setActionError(null);
															void notifications
																.removeTranscriptSubscription(subscription.id)
																.then(() =>
																	setSubscriptions((prev) =>
																		prev.filter((entry) => entry.id !== subscription.id),
																	),
																)
																.catch((error) =>
																	setActionError(
																		error instanceof Error
																			? error.message
																			: String(error),
																	),
																)
																.finally(() => setIsSaving(false));
														}}
													>
														Delete
													</Button>
												</td>
											</tr>
										))
									)}
								</tbody>
							</Table>
						</div>
					</div>
				</Col>
			</Row>

			<Modal show={Boolean(editingChannel)} onHide={() => setEditingChannel(null)}>
				<Modal.Header closeButton>
					<Modal.Title>Edit Channel</Modal.Title>
				</Modal.Header>
				{editingChannel ? (
					<EditChannelForm
						channel={editingChannel}
						disabled={!isActionsEnabled || isSaving}
						onCancel={() => setEditingChannel(null)}
						onSave={(patch) => {
							setIsSaving(true);
							setActionError(null);
							void notifications
								.updateNotificationChannel(editingChannel.id, patch)
								.then((updated) => {
									setChannels((prev) =>
										prev.map((entry) =>
											entry.id === updated.id ? updated : entry,
										),
									);
									setEditingChannel(null);
								})
								.catch((error) =>
									setActionError(
										error instanceof Error ? error.message : String(error),
									),
								)
								.finally(() => setIsSaving(false));
						}}
					/>
				) : null}
			</Modal>

			<Modal
				show={Boolean(editingSubscription)}
				onHide={() => setEditingSubscription(null)}
				size="lg"
			>
				<Modal.Header closeButton>
					<Modal.Title>Edit Subscription</Modal.Title>
				</Modal.Header>
				{editingSubscription ? (
					<EditSubscriptionForm
						subscription={editingSubscription}
						channels={channels}
						disabled={!isActionsEnabled || isSaving}
						onCancel={() => setEditingSubscription(null)}
						onSave={(patch) => {
							setIsSaving(true);
							setActionError(null);
							void notifications
								.updateTranscriptSubscription(editingSubscription.id, patch)
								.then((updated) => {
									setSubscriptions((prev) =>
										prev.map((entry) =>
											entry.id === updated.id ? updated : entry,
										),
									);
									setEditingSubscription(null);
								})
								.catch((error) =>
									setActionError(
										error instanceof Error ? error.message : String(error),
									),
								)
								.finally(() => setIsSaving(false));
						}}
					/>
				) : null}
			</Modal>
		</div>
	);
}

function EditChannelForm({
	channel,
	disabled,
	onSave,
	onCancel,
}: {
	channel: NotificationChannel;
	disabled: boolean;
	onSave: (patch: UpdateNotificationChannelInput) => void;
	onCancel: () => void;
}) {
	const [service, setService] = useState(channel.service);
	const [path, setPath] = useState(channel.path);

	return (
		<Form
			onSubmit={(event) => {
				event.preventDefault();
				onSave({
					service,
					path,
				});
			}}
		>
			<Modal.Body>
				<Row className="g-2">
					<Col md={4}>
						<Form.Label>Service</Form.Label>
						<Form.Control
							value={service}
							disabled={disabled}
							onChange={(event) => setService(event.target.value)}
						/>
					</Col>
					<Col md={8}>
						<Form.Label>Path</Form.Label>
						<Form.Control
							value={path}
							disabled={disabled}
							onChange={(event) => setPath(event.target.value)}
						/>
					</Col>
				</Row>
			</Modal.Body>
			<Modal.Footer>
				<Button type="button" variant="outline-secondary" onClick={onCancel}>
					Cancel
				</Button>
				<Button type="submit" disabled={disabled || !service.trim() || !path.trim()}>
					Save
				</Button>
			</Modal.Footer>
		</Form>
	);
}

function EditSubscriptionForm({
	subscription,
	channels,
	disabled,
	onSave,
	onCancel,
}: {
	subscription: TranscriptSubscription;
	channels: NotificationChannel[];
	disabled: boolean;
	onSave: (patch: UpdateTranscriptSubscriptionInput) => void;
	onCancel: () => void;
}) {
	const [name, setName] = useState(subscription.name);
	const [topic, setTopic] = useState(subscription.topic);
	const [enabled, setEnabled] = useState(subscription.enabled);
	const [destinationIds, setDestinationIds] = useState<string[]>(
		subscription.notificationChannelIds,
	);

	const isValid = Boolean(name.trim() && topic.trim() && destinationIds.length > 0);

	return (
		<Form
			onSubmit={(event) => {
				event.preventDefault();
				if (!isValid) {
					return;
				}

				onSave({
					name,
					topic,
					enabled,
					notificationChannelIds: destinationIds,
				});
			}}
		>
			<Modal.Body>
				<Row className="g-2">
					<Col md={6}>
						<Form.Label>Name</Form.Label>
						<Form.Control
							value={name}
							disabled={disabled}
							onChange={(event) => setName(event.target.value)}
						/>
					</Col>
					<Col md={3}>
						<Form.Label>Enabled</Form.Label>
						<Form.Check
							type="switch"
							checked={enabled}
							disabled={disabled}
							onChange={(event) => setEnabled(event.target.checked)}
							label={enabled ? "On" : "Off"}
						/>
					</Col>
					<Col md={3}>
						<Form.Label>Destinations</Form.Label>
						<Form.Select
							disabled={disabled}
							multiple
							value={destinationIds}
							onChange={(event) => {
								const selected = Array.from(event.target.selectedOptions).map(
									(option) => option.value,
								);
								setDestinationIds(selected);
							}}
						>
							{channels.map((channel) => (
								<option key={channel.id} value={channel.id}>
									{channel.service}: {channel.path}
								</option>
							))}
						</Form.Select>
					</Col>
				</Row>

				<Row className="g-2 mt-1">
					<Col>
						<Form.Label>Topic</Form.Label>
						<Form.Control
							value={topic}
							disabled={disabled}
							onChange={(event) => setTopic(event.target.value)}
						/>
						<div className="small text-muted">
							Keyword and location filters are set at creation time today.
						</div>
					</Col>
				</Row>
			</Modal.Body>
			<Modal.Footer>
				<Button type="button" variant="outline-secondary" onClick={onCancel}>
					Cancel
				</Button>
				<Button type="submit" disabled={disabled || !isValid}>
					Save
				</Button>
			</Modal.Footer>
		</Form>
	);
}


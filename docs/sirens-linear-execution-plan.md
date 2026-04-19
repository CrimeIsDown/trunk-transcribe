# Sirens Linear Execution Plan

Last updated: 2026-04-18

## Scope

This document captures the recommended execution order for the open Linear work in the `CrimeIsDown` team's `Sirens` project that applies to `trunk-transcribe`.

The intent is to sequence the current Sirens integration tranche so architecture decisions land before interface work, and interface work lands before product-specific integrations.

## Current repo context

The current tranche is concentrated in the shared frontend:

- `frontend/src/components/Search.tsx`
- `frontend/src/components/TranscriptMap.tsx`
- `frontend/src/components/SavedTranscriptSearches.tsx`
- `frontend/src/lib/transcriptSavedSearches.ts`

These files currently carry the main assumptions that need to be pushed behind reusable interfaces:

- env-backed search credentials
- browser-local saved searches
- no authenticated viewer/capabilities bootstrap
- no notification abstraction

## Planning principles

This ordering is based on four rules:

1. Decide topology before building too much against an accidental app boundary.
2. Introduce shared abstractions before adding Sirens-only adapters.
3. Land lower-risk adapter work before higher-complexity user-state and alerts work.
4. Keep Chicago-specific cleanup from blocking core commercial integration work.

## Recommended execution order

### 0. Triage the still-open search parent

#### `CRI-42` Port over transcript search

Status:
- `In Progress`

Why first:
- Its child parity tasks appear to have already been completed.
- This looks like an issue hygiene problem more than a large remaining implementation.
- It should be closed, split, or refreshed before more Sirens platform work starts so the project state is accurate.

Expected output:
- confirm whether `CRI-42` is actually done
- if not done, create follow-up tickets for concrete missing gaps
- close or re-scope the parent issue

### 1. Make the topology decision

#### `CRI-69` Decide and document frontend app topology for `crimeisdown.com` and `sirens.app`

Status:
- `Backlog`

Why this comes first:
- The rest of the Sirens tranche assumes some frontend ownership model.
- Without this decision, it is easy to overbuild inside `trunk-transcribe` or to introduce abstractions that fit the wrong deployment model.

Decision to produce:
- whether Sirens remains a mode within the existing frontend
- whether Sirens moves to a separate private frontend
- or whether the team uses a hybrid approach where shared packages stay here and product composition moves elsewhere later

Expected output:
- architecture decision record in `docs/`
- explicit statement of what remains shared/open
- explicit statement of what is private/product-specific

Exit criteria:
- follow-up tickets can reference a stable topology assumption

### 2. Establish provider boundaries in the shared frontend

#### `CRI-63` Introduce frontend providers for auth, entitlements, saved searches, notifications, and search credentials

Status:
- `Backlog`

Why this is foundational:
- This is the abstraction layer that all later Sirens integrations should plug into.
- It prevents one-off direct integrations in `Search.tsx`, `TranscriptMap.tsx`, and saved-search UI code.

Target interfaces:
- `AuthProvider`
- `ViewerProvider`
- `EntitlementsService`
- `SavedSearchStore`
- `NotificationStore`
- `SearchCredentialProvider`

Default implementations to preserve current behavior:
- anonymous/no-op auth
- open/shared entitlements
- `localStorage` saved searches
- env-backed search credentials
- no-op notifications

Expected output:
- shared components depend on interfaces rather than direct storage or env assumptions
- current OSS behavior stays intact
- Sirens adapters can be added without rewriting search and map components

Primary code areas:
- `frontend/src/components/Search.tsx`
- `frontend/src/components/TranscriptMap.tsx`
- `frontend/src/components/SavedTranscriptSearches.tsx`
- `frontend/src/lib/transcriptSavedSearches.ts`

### 3. Add viewer and capability bootstrap

#### `CRI-65` Add a generic viewer and capabilities bootstrap contract for Sirens

Status:
- `Backlog`

Why this comes immediately after `CRI-63`:
- It gives the new provider model an actual authenticated contract to carry.
- It is the cleanest way to gate premium behavior without leaking Patreon-specific logic into the shared frontend.

Target contract shape:
- `canSearchTranscripts`
- `canCreateAlerts`
- `canUseAssistant`
- `archiveDepthDays`
- `canExportAudio`

Expected output:
- frontend feature gating becomes capability-based
- backend tier logic stays private to the backend
- later Sirens adapters have a stable account-aware bootstrap model

Can overlap with `CRI-63`:
- yes, but final API shape should be finalized only after the provider model is clear

### 4. Prove the adapter pattern with saved searches

#### `CRI-64` Replace browser-only saved searches with a pluggable store and Sirens backend adapter

Status:
- `Backlog`

Why this comes before search credentials and notifications:
- It is the cleanest first adapter on top of the provider model.
- It exercises authenticated user state without immediately taking on the complexity of alerts.
- It reduces uncertainty in the frontend normalization layer.

Expected output:
- shared frontend uses `SavedSearchStore`
- `localStorage` remains the default OSS/shared adapter
- Sirens can use backend CRUD without a separate UI path

Primary code areas:
- `frontend/src/components/SavedTranscriptSearches.tsx`
- `frontend/src/lib/transcriptSavedSearches.ts`
- any provider wiring added in `CRI-63`

Notes:
- This should align with `CRI-65` where authenticated vs anonymous behavior matters.
- It does not need to wait on notifications work.

### 5. Replace browser search credentials with scoped backend-issued credentials

#### `CRI-66` Use private backend-issued scoped search credentials in Sirens search and map flows

Status:
- `Backlog`

Why this follows `CRI-63` and `CRI-65`:
- It needs the `SearchCredentialProvider` abstraction from `CRI-63`.
- It should use the viewer/capabilities contract from `CRI-65` to handle access failures and premium gating correctly.

Why it is high priority:
- This removes the need to ship privileged env-configured search credentials for premium flows.
- It directly improves separation between open/shared mode and authenticated Sirens mode.

Expected output:
- `Search.tsx` and `TranscriptMap.tsx` request credentials through a provider
- Sirens uses temporary scoped keys from the private backend
- open/shared mode retains env-backed fallback behavior

Primary code areas:
- `frontend/src/components/Search.tsx`
- `frontend/src/components/TranscriptMap.tsx`

### 6. Integrate notifications and transcript subscriptions

#### `CRI-67` Integrate notification channels and transcript subscriptions into the Sirens frontend

Status:
- `Backlog`

Why this follows the prior work:
- It depends on the provider boundary from `CRI-63`.
- It should consume capability/bootstrap information from `CRI-65`.
- It will likely benefit from patterns already established in `CRI-64`, since both are frontend-to-backend user-state integrations.

Why this is later than saved searches:
- Notifications have more product and UX ambiguity.
- The issue explicitly includes alert creation from search state, map state, or both.
- It will touch more flows and should build on already-proven adapter patterns.

Expected output:
- CRUD for notification channels through the private backend
- CRUD for transcript subscriptions through the private backend
- alert creation from normalized search/map state
- feature naming aligned around `Alerts` in `sirens.app`

Primary code areas:
- provider layer introduced in `CRI-63`
- shared search and map state flow
- any alert creation UI introduced in the frontend

### 7. Clean up Chicago-specific product behavior in parallel

#### `CRI-68` Separate Chicago-specific product behavior from shared transcript-search core

Status:
- `Backlog`

Why this is parallel work rather than a blocker:
- It is important boundary cleanup, but the ticket itself says it should not block the provider-backed commercial integrations.
- Its best shape depends somewhat on the topology decision in `CRI-69`.

Recommended timing:
- start after `CRI-69`
- schedule as a parallel cleanup lane while `CRI-64` through `CRI-67` proceed

Expected output:
- inventory of Chicago-specific assumptions
- configuration-driven or app-composed replacements for those assumptions
- shared search and map components become city-agnostic by default

Likely targets:
- presets
- copy
- default market assumptions
- any public-site-only behavior currently embedded in shared components

## Dependency graph summary

Required ordering:

- `CRI-69` before major implementation in the current Sirens tranche
- `CRI-63` before `CRI-64`
- `CRI-63` before `CRI-66`
- `CRI-63` before `CRI-67`
- `CRI-65` before `CRI-66`
- `CRI-65` before `CRI-67`

Recommended but not strictly blocking:

- `CRI-65` should be shaped alongside the provider model from `CRI-63`
- `CRI-64` should land before `CRI-67` to establish the frontend pattern for backend-backed user state
- `CRI-68` should be informed by `CRI-69`

## Suggested implementation phases

### Phase 1: Decision and issue hygiene

Tickets:
- `CRI-42`
- `CRI-69`

Goal:
- make the project state accurate
- remove ambiguity about frontend ownership and repo boundaries

### Phase 2: Shared interfaces

Tickets:
- `CRI-63`
- `CRI-65`

Goal:
- create stable frontend seams for authenticated Sirens behavior

### Phase 3: First product integrations

Tickets:
- `CRI-64`
- `CRI-66`

Goal:
- prove the adapter model with saved searches
- move premium search access onto scoped backend credentials

### Phase 4: Alerts and stateful premium workflows

Tickets:
- `CRI-67`

Goal:
- connect search and map state to backend-backed alerts and subscriptions

### Phase 5: Shared-core cleanup

Tickets:
- `CRI-68`

Goal:
- make the shared frontend city-agnostic and product-agnostic by composition

## Deprioritized backlog for this tranche

These open `Sirens` tickets are not on the immediate dependency path and should not interrupt the current integration tranche unless priorities change:

### `CRI-24` New OpenAI Models - Enhancement Request

Why later:
- useful and user-facing, but orthogonal to the current Sirens frontend boundary work

When to pull forward:
- if OpenAI model compatibility is currently blocking deployments or user adoption

### `CRI-17` Improve geocoding accuracy

Why later:
- important bug, but not part of the current architecture and provider tranche

When to pull forward:
- if map accuracy is currently causing visible product errors

### `CRI-50` Send update to patrons

Why later:
- communication task, not a technical blocker

When to do it:
- after at least one or two visible Sirens integration items have landed

### `CRI-51` Train a transcription AI model

Why later:
- research-heavy and not dependent on the current frontend integration work

### `CRI-47` CrimeIsDown app - take a picture of police, find out what is going on

Why later:
- large product exploration item with no current dependency on the tranche above

### `CRI-48` AI generated newsletter on police/fire incidents

Why later:
- product expansion idea that should wait until the shared/core and Sirens boundaries are cleaner

## Recommended next ticket to execute

If implementation starts immediately, the next ticket should be:

1. `CRI-69` if the topology decision is still unresolved
2. `CRI-63` immediately after that decision is documented

If the topology decision is already effectively known but undocumented, write it down first and then begin `CRI-63` in the same work window.

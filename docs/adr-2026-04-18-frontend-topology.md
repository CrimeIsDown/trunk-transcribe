# ADR: Frontend Topology for `crimeisdown.com` and `sirens.app`

Date: 2026-04-18  
Status: Accepted

## Context

We have two distinct product surfaces:

- `crimeisdown.com`: public-facing site (map, audio, guide, etc).
- `sirens.app`: premium transcript search + map + alerts.

Historically, `crimeisdown.com` shipped transcript routes (`/transcripts/search`, `/transcripts/map`, `/transcripts/notifications`) as part of the public frontend.

The current direction for the v4 public-site rewrite is to *remove* transcript UI from the public site and instead redirect transcript routes to `sirens.app`. That implies `sirens.app` should own transcript UX independently of the public-site shell.

At the same time, the `trunk-transcribe` repo contains the current transcript search/map UI implementation (React), and the open Sirens Linear tranche requires introducing stable provider/adapter seams in that UI before wiring in authenticated Sirens behavior.

## Decision

Adopt a two-frontend topology:

- The public site remains a separate frontend codebase (Astro) and does not embed transcript search UX.
- `sirens.app` is implemented as a separate frontend app and becomes the canonical home for transcript search, map, saved searches, and alerts.

For the current tranche, we treat `trunk-transcribe/frontend` as the `sirens.app` codebase (and the shared transcript UI surface), with a strong emphasis on preserving an anonymous/open default mode via adapters so the repo remains usable outside the commercial Sirens deployment.

## What Stays Shared/Open vs Private

Shared/open (lives in `trunk-transcribe/frontend`, with default adapters):

- transcript search + transcript map UI
- normalized search/map state shaping
- provider interfaces for auth, viewer/capabilities, entitlements, notifications, saved searches, and search credentials
- default adapters:
  - anonymous/no-op auth
  - open/shared entitlements
  - `localStorage` saved searches
  - env-backed search credentials
  - no-op notifications

Private/Sirens-specific (implemented as adapters behind the shared interfaces):

- authenticated viewer bootstrap and capability gating
- backend-backed saved searches
- backend-issued scoped search credentials
- backend-backed notifications/channels and transcript subscriptions (alerts)

## Consequences

- The Sirens tranche work (`CRI-63` .. `CRI-67`) proceeds inside `trunk-transcribe/frontend` without being blocked by public-site route parity work.
- Public-site work can evolve independently (including navigation and shell) while keeping transcript routing stable via redirects to `sirens.app`.
- Provider boundaries become the primary seam between open/shared behavior and Sirens-only product integrations, reducing the risk of leaking commercial assumptions into shared components.

## Alternatives Considered

1. **Sirens as a mode inside the public-site frontend**
   - Rejected: v4 public-site parity explicitly removes transcript UI from the public shell and redirects to `sirens.app`.
2. **Separate private Sirens frontend repo**
   - Deferred: possible later, but the current code and Linear tranche are already concentrated in `trunk-transcribe/frontend`. We can revisit extraction once provider seams exist and the surface stabilizes.
3. **Monorepo with shared packages + multiple frontends**
   - Deferred: attractive long-term, but it is premature before the provider model (`CRI-63`) lands and the Sirens adapters (`CRI-64` .. `CRI-67`) prove what truly needs to be shared.


# CrimeIsDown Website Product Spec

## Document Status

- Status: Draft
- Date: 2026-03-16
- Scope: Public `crimeisdown.com` site and premium `sirens.app` product split
- Exclusions: `Directive Changes` is removed entirely from the new site structure

## Product Summary

CrimeIsDown should stop behaving like a flat directory of unrelated tools and instead guide users through the primary job to be done:

`I heard sirens. What is happening near me?`

The updated product structure should separate the free public utility from the premium investigative workflow.

- `crimeisdown.com` is the free public front door for Chicago scanner context.
- `sirens.app` is the premium workflow for searchable transcripts, incident analysis, saved alerts, and AI assistance.

This split keeps the public site focused and easier to understand while preserving room for a much more powerful premium experience.

## Goals

### Primary Goals

1. Make location the default entry point for new visitors.
2. Reduce top-level navigation complexity.
3. Keep the public site free, useful, and easy to understand.
4. Move advanced search and premium workflows into `sirens.app`.
5. Increase clarity around what each property is for.

### Secondary Goals

1. Improve conversion from public-site visitors to premium Sirens users.
2. Consolidate scanner reference tools into a single coherent section.
3. Reduce homepage clutter and historical digressions above the fold.

## Non-Goals

1. Rebuilding the backend architecture in this phase.
2. Specifying visual design in pixel-level detail.
3. Preserving the old `Directive Changes` feature or route.
4. Keeping every current page as a top-level navigation item.

## Target Users

### Public Site Users

- Chicago residents who hear sirens and want quick context
- Scanner hobbyists who need boundaries, channels, and definitions
- Journalists who need fast area and radio context
- Casual visitors who want to listen live

### Premium Users

- Journalists and newsroom staff
- Power users and heavy scanner listeners
- Researchers tracking patterns over time
- Users who want saved searches, alerts, and transcript search

## Core Product Positioning

### crimeisdown.com

Public utility for:

- finding scanner context by address
- listening live
- understanding scanner terms and codes
- learning how Chicago public safety radio is organized

### sirens.app

Premium workflow for:

- transcript search
- incident map
- saved searches
- notifications and newsletters
- AI-assisted interpretation and follow-up questions

## Site Principles

1. Start with place, not tools.
2. Keep free and premium boundaries obvious.
3. Put user goals in navigation labels.
4. Keep advanced controls off first-touch experiences.
5. Group support tools together instead of scattering them across pages.

## Information Architecture

## crimeisdown.com Sitemap

1. `/` Home
2. `/area` Find My Area
3. `/listen` Listen Live
4. `/listen/archives` Audio Archives
5. `/reference` Scanner Reference
6. `/reference/radio-ids` Radio ID Lookup
7. `/reference/ucr-codes` UCR Code Lookup
8. `/reference/guide` Scanner Guide
9. `/about` About CrimeIsDown
10. `/support` Support

## sirens.app Sitemap

1. `/` Premium Home
2. `/search` Transcript Search
3. `/map` Incident Map
4. `/alerts` Alerts and Newsletters
5. `/assistant` Scanner AI Assistant
6. `/account` Account

## Primary Navigation

### crimeisdown.com

- Find My Area
- Listen
- Reference
- Sirens
- About

### sirens.app

- Search
- Map
- Alerts
- Assistant
- Account

## Global Content Strategy

### Content to Remove

- `Directive Changes` route
- `Directive Changes` navigation item
- homepage references that treat all tools as equally important

### Content to Move Below the Fold or Into About

- mission/history narrative
- long-form explanation of the CrimeIsDown name
- donation explanations
- partner/source acknowledgements

### Content to Elevate

- location search
- live listening
- reference tools
- premium upgrade path

## Functional Requirements

## Shared Requirements

1. Navigation must clearly distinguish free public tools from premium Sirens features.
2. All pages should include a persistent CTA to `Find My Area`.
3. All pages should include a persistent CTA to `Open Sirens` where premium features are mentioned.
4. Mobile layouts should prioritize the primary task on first viewport load.

## crimeisdown.com Requirements

1. Users can search for an address or place and see Chicago-specific boundary/context data.
2. Users can listen to live scanner audio with minimal friction.
3. Users can browse or search reference material without authentication.
4. Users can discover premium features without being forced into them on basic tasks.

## sirens.app Requirements

1. Users can search transcripts by location, time, channel, and agency.
2. Users can view search results on a map.
3. Users can save searches and configure alerts.
4. Users can ask AI follow-up questions using scanner-specific context.

## Conversion Requirements

1. The public site should frame Sirens as the deeper layer, not as the default starting point.
2. Premium promotion should appear:
   - on the homepage
   - after area lookups
   - on the listen page near archives and transcripts
   - on the reference page where deeper analysis is likely useful

## Route-by-Route Wireframe Outline

## crimeisdown.com

### `/` Home

#### Purpose

Give first-time visitors an immediate answer path and explain the free/premium split.

#### Primary User Questions

- I heard sirens. Where do I start?
- What can I do for free here?
- When should I use Sirens?

#### Wireframe Sections

1. Header
   - Logo
   - Nav: Find My Area, Listen, Reference, Sirens, About
   - Optional support link in utility area
2. Hero
   - Headline: `Heard sirens in Chicago? Start with your location.`
   - Subhead
   - Address search field
   - Primary CTA: `Find My Area`
   - Secondary CTA: `Listen Live`
3. Quick Actions Row
   - Find My Area card
   - Listen Live card
   - Reference Tools card
   - Search Transcripts card with premium badge
4. How It Works
   - Step 1: Search your address
   - Step 2: Listen or look things up
   - Step 3: Go deeper in Sirens
5. Premium Promo Band
   - Short value statement
   - CTA to Sirens
6. Trust / Source Strip
   - Brief note on public data and scanner resources
7. Footer
   - About
   - Support
   - Contact

#### Key Content

- Keep copy short and action-oriented.
- Do not place historical essays above the main CTA.

### `/area` Find My Area

#### Purpose

Make address-based context the main public experience.

#### Primary User Questions

- What area am I in?
- Which police district and beat cover this address?
- Which channels should I listen to?

#### Wireframe Sections

1. Page Header
   - Headline: `Find the scanner context for any Chicago address`
   - Supporting line
2. Search Module
   - Address/place input
   - CTA: `Search`
   - Optional current-location button later
3. Results Summary Card
   - Neighborhood
   - Community area
   - Ward
   - Police district
   - Beat
4. Recommended Channels Card
   - Primary channels
   - Secondary channels
   - CTA: `Listen Live`
5. Map Module
   - Boundary layers
   - Address pin
   - Layer toggles
6. Nearby Activity Module
   - Demo nearby incidents or explanatory placeholder
   - CTA: `Search Nearby Activity in Sirens`
7. Next Steps Row
   - Listen Live
   - Open Reference
   - Open Sirens

#### Notes

- This is the single most important page after the homepage.
- It should be optimized for mobile first.

### `/listen` Listen Live

#### Purpose

Give users an obvious place to hear current radio traffic without burying them in archive and pricing detail.

#### Primary User Questions

- How do I listen right now?
- What is the main feed?
- Where are the advanced audio options?

#### Wireframe Sections

1. Page Header
   - Headline: `Listen to Chicago scanner audio`
   - Supporting text
2. Main Live Player
   - Primary stream/player
   - Short description of coverage
3. Main Feed Module
   - YouTube feed embed
   - CTA: `Watch on YouTube`
4. Recommended Sources Module
   - OpenMHz links
   - Broadcastify links
   - Other specialty sources
5. Audio Tools Module
   - CTA card to `Audio Archives`
   - CTA card to `Find My Area`
   - CTA card to `Reference`
6. Premium Promo Module
   - `Need searchable history? Use Sirens transcript search.`

#### Notes

- Archive downloads and pricing should not dominate this page.
- This page is for live listening first.

### `/listen/archives` Audio Archives

#### Purpose

Separate archive lookup from live listening so both experiences are easier to scan.

#### Primary User Questions

- Can I search older recordings?
- What is free vs paid?
- How do I export or download audio?

#### Wireframe Sections

1. Page Header
   - Headline: `Search scanner archives`
   - Supporting text
2. Archive Search Module
   - Date/time input
   - Channel/system selectors
   - Search CTA
3. Export / Download Module
   - Clip export tools
   - Download limits summary
4. Access / Membership Module
   - Clear free vs paid comparison
   - CTA to Patreon or Sirens depending product choice
5. Alternate Paths Row
   - Listen Live
   - Find My Area
   - Search Transcripts in Sirens

#### Notes

- This is a utility page, not a top-level nav item.

### `/reference` Scanner Reference

#### Purpose

Create one home for all interpretation tools.

#### Primary User Questions

- What does that code mean?
- Who is unit 1234?
- Where do I learn scanner terminology?

#### Wireframe Sections

1. Page Header
   - Headline: `Scanner reference tools`
   - Supporting text
2. Tool Cards
   - Radio ID Lookup
   - UCR Code Lookup
   - Scanner Guide
3. Quick Search Strip
   - Inline radio ID search
   - Inline UCR search
4. Learn the Basics Section
   - Intro paragraph
   - CTA to Scanner Guide
5. Premium Assistant Promo
   - `Need help interpreting a call? Ask the Sirens assistant.`

#### Notes

- Reference should be a coherent destination, not a scattered collection.

### `/reference/radio-ids` Radio ID Lookup

#### Purpose

Provide a dedicated deep link for radio identifier lookup.

#### Wireframe Sections

1. Header
2. Search input
3. Result table
4. Related links
   - Scanner Guide
   - UCR Codes
   - Sirens Assistant

### `/reference/ucr-codes` UCR Code Lookup

#### Purpose

Provide a dedicated deep link for UCR code lookup.

#### Wireframe Sections

1. Header
2. Search input
3. Result table
4. Related links
   - Radio IDs
   - Scanner Guide
   - Sirens Assistant

### `/reference/guide` Scanner Guide

#### Purpose

Provide readable orientation for scanner terminology and Chicago-specific context.

#### Wireframe Sections

1. Header
2. Guide overview
3. Embedded guide content or migrated native content
4. Related tools sidebar or cards
   - Radio IDs
   - UCR Codes
   - Sirens Assistant

#### Notes

- Long term, move away from a Google Docs embed to native site content.

### `/about` About CrimeIsDown

#### Purpose

Hold the history, mission, and source material that should not crowd the homepage.

#### Wireframe Sections

1. Header
2. What this site does
3. What stays free
4. What moved to Sirens
5. Sources and acknowledgements
6. Contact

### `/support` Support

#### Purpose

Keep funding asks off the homepage while still making them easy to find.

#### Wireframe Sections

1. Header
2. Why support matters
3. Patreon CTA
4. PayPal CTA
5. Optional infrastructure/mission summary

## sirens.app

### `/` Premium Home

#### Purpose

Serve as the premium landing page with a search-first workflow.

#### Wireframe Sections

1. Header
2. Hero with location input
3. Search nearby CTA
4. Feature cards
   - Transcript Search
   - Incident Map
   - Alerts
   - Assistant
5. Pricing/access summary

### `/search` Transcript Search

#### Purpose

Search transcripts with a simpler entry point than the current advanced-first UI.

#### Wireframe Sections

1. Header
2. Simple search mode
   - location
   - time
   - agency
3. Results list
4. Advanced filters drawer
5. Saved search CTA
6. Ask Assistant CTA

### `/map` Incident Map

#### Purpose

Show results spatially for premium users.

#### Wireframe Sections

1. Header
2. Search summary
3. Map
4. Result drawer/list
5. Related actions
   - Save search
   - Open assistant

### `/alerts` Alerts and Newsletters

#### Purpose

Turn useful searches into subscriptions.

#### Wireframe Sections

1. Header
2. Saved searches list
3. New alert form
4. Delivery settings
5. Newsletter presets

### `/assistant` Scanner AI Assistant

#### Purpose

Help users interpret terminology, summarize incidents, and ask follow-up questions.

#### Wireframe Sections

1. Header
2. Prompt input
3. Suggested prompts
4. Conversation area
5. Linked context/results rail

### `/account` Account

#### Purpose

Provide account, plan, and preferences management.

#### Wireframe Sections

1. Header
2. Membership/access summary
3. Saved search count
4. Notification settings
5. Linked public-site tools

## Detailed Page Copy

## crimeisdown.com Copy

### Home

#### Hero

- Headline: `Heard sirens in Chicago? Start with your location.`
- Subhead: `Find the police district, beat, neighborhood, and scanner channels for any Chicago address. Then listen live or jump into deeper search tools.`
- Primary CTA: `Find My Area`
- Secondary CTA: `Listen Live`

#### Quick Actions

- Find My Area: `Enter an address to see the district, beat, community area, and the scanner channels most likely carrying traffic nearby.`
- Listen Live: `Tune into live Chicago scanner audio, watch the general feed, and follow active radio traffic.`
- Use Reference Tools: `Look up radio IDs, UCR codes, and scanner terminology when you hear something you do not recognize.`
- Search Transcripts: `Need searchable call history and AI-assisted analysis? Use the premium Sirens platform.`

#### How It Works

- Step 1: `Search your address`
- Step 1 Copy: `Get the local map context and the channels that matter.`
- Step 2: `Listen or look things up`
- Step 2 Copy: `Use live audio and scanner reference tools to understand what you are hearing.`
- Step 3: `Go deeper if needed`
- Step 3 Copy: `Use Sirens for transcript search, incident mapping, and alerts.`

#### Premium Promo

- Heading: `Need faster answers?`
- Copy: `Sirens adds searchable transcripts, incident mapping, and saved alerts for journalists, researchers, and power users.`
- CTA: `Open Sirens`

### Find My Area

- Headline: `Find the scanner context for any Chicago address`
- Subhead: `See where an address sits in Chicago and which public safety channels are most relevant nearby.`
- Input Placeholder: `Enter an address or place name`

#### Results Labels

- `Location Summary`
- `Recommended Channels`
- `Map Context`
- `Nearby Activity`

#### Supporting Copy

- `This address is in [Neighborhood], Community Area [X], Ward [X], Police District [X], and Beat [X].`
- `Start with these channels to hear traffic most likely related to this area.`
- `View nearby boundaries and switch between district, beat, ward, and neighborhood layers.`
- `Need more than map context? Search nearby activity in Sirens.`

### Listen

- Headline: `Listen to Chicago scanner audio`
- Subhead: `Follow live public safety radio traffic, watch the main stream, or jump to archives and external sources.`

#### Section Copy

- `Start with the live scanner player for active Chicago-area radio traffic.`
- `Watch the general #ChicagoScanner feed on YouTube for a broader citywide mix.`
- `Need older audio? Search archive recordings by time and channel.`
- `Use OpenMHz, Broadcastify, and specialty feeds when you want more coverage.`
- `Need searchable history? Use Sirens transcript search.`

### Audio Archives

- Headline: `Search scanner archives`
- Subhead: `Look up past recordings by date, time, and channel.`
- Membership Copy: `Free access covers basic archive lookup. Expanded download and export limits are available through paid access.`

### Reference

- Headline: `Scanner reference tools`
- Subhead: `Decode what you are hearing on Chicago public safety radio.`

#### Card Copy

- Radio IDs: `Look up unit and radio identifiers to understand who is talking.`
- UCR Codes: `Translate incident reporting codes into plain language.`
- Scanner Guide: `Learn scanner terms, Chicago-specific shorthand, and common dispatch patterns.`

### About

- Headline: `About CrimeIsDown`
- Subhead: `CrimeIsDown helps Chicago scanner listeners understand where things are happening and what they are hearing.`

#### Section Copy

- `CrimeIsDown is built for residents, journalists, hobbyists, and anyone trying to make sense of Chicago scanner traffic quickly.`
- `The public site focuses on location context, live listening, and reference tools.`
- `Advanced transcript search, AI workflows, and alerts live in Sirens.`
- `Mapping and reference data come from public datasets and scanner community resources.`

### Support

- Headline: `Support CrimeIsDown`
- Copy: `Support keeps the public tools online and helps fund the infrastructure behind Chicago scanner coverage.`
- CTA 1: `Support on Patreon`
- CTA 2: `Donate with PayPal`

## sirens.app Copy

### Premium Home

- Headline: `I heard sirens near...`
- Subhead: `Search scanner transcripts, map incidents, and get faster answers from live Chicago radio traffic.`
- Input Placeholder: `Enter an address, neighborhood, or landmark`
- Primary CTA: `Search Nearby Activity`

#### Feature Copy

- Transcript Search: `Search recent radio traffic by location, time, agency, and channel.`
- Incident Map: `See calls and related activity on a map instead of piecing it together manually.`
- AI Assistant: `Ask follow-up questions about scanner terminology, calls, and patterns in the results.`
- Alerts: `Save searches and get updates for the places and topics you care about.`

## User Flows

### Flow 1: Heard Sirens, Wants Quick Context

1. User lands on `crimeisdown.com/`
2. User enters address
3. User reaches `/area`
4. User checks district/beat/channel suggestions
5. User clicks `Listen Live` or `Open Sirens`

### Flow 2: Curious Scanner Listener

1. User lands on `/listen`
2. User starts live audio
3. User hears unfamiliar term
4. User opens `/reference`
5. User looks up code or terminology

### Flow 3: Journalist Needs Searchable Context

1. User lands on `crimeisdown.com/`
2. User sees premium prompt
3. User opens `sirens.app/search`
4. User filters by location and time
5. User saves search or creates alert

## Implementation Guidance

### Public Site Priorities

1. Rework homepage around address-first hero.
2. Build `/area` as the flagship experience.
3. Split live listening and archives into separate routes.
4. Consolidate all lookup tools under `/reference`.
5. Remove `Directive Changes` completely from routes, nav, and content.

### Premium Priorities

1. Replace advanced-first transcript search entry with a simpler starter mode.
2. Keep advanced filters available, but secondary.
3. Make saved alerts a first-class premium feature.

## Success Metrics

1. Increased clickthrough from homepage to `/area`
2. Reduced bounce rate from homepage
3. Increased clicks from public site to Sirens
4. Increased completion of key flows:
   - address search
   - live listen start
   - reference lookup
   - premium search start

## Open Questions

1. Will archive access remain on `crimeisdown.com`, or eventually move into Sirens?
2. Will premium access continue to be Patreon-authenticated, or migrate to a first-party account model?
3. Should the public site expose a lightweight nearby-activity preview, or reserve all such results for Sirens?
4. Should the scanner guide remain an embed in the short term, or be migrated immediately into native content?

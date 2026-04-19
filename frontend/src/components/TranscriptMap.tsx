'use client'

import { instantMeiliSearch } from '@meilisearch/instant-meilisearch'
import type { UiState } from 'instantsearch.js'
import { history } from 'instantsearch.js/es/lib/routers'
import { simple } from 'instantsearch.js/es/lib/stateMappings'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { useEffect, useMemo, useRef, useState } from 'react'
import { Alert, Badge, Col, Row } from 'react-bootstrap'
import {
  ClearRefinements,
  CurrentRefinements,
  HitsPerPage,
  InstantSearch,
  Pagination,
  RefinementList,
  SearchBox,
  SortBy,
  Stats,
  useInstantSearch,
  useRefinementList,
} from 'react-instantsearch'

import { extractTranscriptGeoPoint } from '@/lib/transcriptGeo'
import { extractScannerSearchScope } from '@/lib/searchState'
import {
  createTranscriptHitTransformer,
  type TranscriptRenderedHit,
} from '@/lib/transcriptHits'
import {
  DEFAULT_TRANSCRIPT_MAP_CENTER,
  DEFAULT_TRANSCRIPT_MAP_BOUNDING_BOX,
  DEFAULT_TRANSCRIPT_MAP_ZOOM,
  formatInsideBoundingBox,
} from '@/lib/transcriptGeoSearch'
import {
  getTranscriptSearchIndexNameFromLocation,
  type TranscriptSearchIndexConfig,
} from '@/lib/transcriptSearchIndex'
import {
  transformCurrentRefinements,
  transformSystemRefinementItems,
} from '@/lib/transcriptSearchLabels'
import { useTranscriptSearchCredentials } from '@/hooks/useTranscriptSearchCredentials'
import CallTimeRangeFilter from './CallTimeRangeFilter'
import { Hit as HitComponent } from './Hit'

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function remapSearchStateIndex(
  routeState: UiState,
  fromIndexName: string,
  toIndexName: string,
): UiState {
  if (fromIndexName === toIndexName) {
    return routeState
  }

  const nextRouteState = { ...routeState } as Record<string, unknown>
  const fromIndexState = nextRouteState[fromIndexName]
  if (!isRecord(fromIndexState)) {
    return routeState
  }

  const toIndexState = isRecord(nextRouteState[toIndexName])
    ? (nextRouteState[toIndexName] as Record<string, unknown>)
    : {}

  nextRouteState[toIndexName] = {
    ...toIndexState,
    ...fromIndexState,
  }
  delete nextRouteState[fromIndexName]
  return nextRouteState as UiState
}

function buildDefaultIndexUiState(indexName: string) {
  return {
    sortBy: `${indexName}:start_time:desc`,
  }
}

function transformCurrentRefinementItems(
  items: Parameters<typeof transformCurrentRefinements>[0],
) {
  return transformCurrentRefinements(items)
}

function transformSystemRefinementListItems(
  items: Parameters<typeof transformSystemRefinementItems>[0],
) {
  return transformSystemRefinementItems(items)
}

function VirtualRefinementList({ attribute }: { attribute: string }) {
  useRefinementList({
    attribute,
    operator: 'or',
  })

  return null
}

function TranscriptGeoMap({ hits }: { hits: TranscriptRenderedHit[] }) {
  const elementRef = useRef<HTMLDivElement | null>(null)
  const mapRef = useRef<L.Map | null>(null)
  const markersRef = useRef<L.LayerGroup | null>(null)
  const [boundingBox, setBoundingBox] = useState(
    DEFAULT_TRANSCRIPT_MAP_BOUNDING_BOX,
  )

  useEffect(() => {
    if (!elementRef.current || mapRef.current) {
      return undefined
    }

    const map = L.map(elementRef.current, {
      scrollWheelZoom: false,
    }).setView(
      [DEFAULT_TRANSCRIPT_MAP_CENTER.lat, DEFAULT_TRANSCRIPT_MAP_CENTER.lng],
      DEFAULT_TRANSCRIPT_MAP_ZOOM,
    )

    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution:
        '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    }).addTo(map)

    const updateBoundingBox = () => {
      setBoundingBox(formatInsideBoundingBox(map.getBounds()))
    }

    markersRef.current = L.layerGroup().addTo(map)
    map.on('moveend zoomend', updateBoundingBox)
    updateBoundingBox()
    mapRef.current = map

    return () => {
      map.off('moveend zoomend', updateBoundingBox)
      markersRef.current?.clearLayers()
      map.remove()
      mapRef.current = null
      markersRef.current = null
    }
  }, [])

  useEffect(() => {
    const map = mapRef.current
    const markers = markersRef.current
    if (!map || !markers) {
      return
    }

    markers.clearLayers()
    const geoHits = hits
      .map((hit) => ({
        hit,
        point: extractTranscriptGeoPoint(hit as Record<string, unknown>),
      }))
      .filter(
        (
          entry,
        ): entry is {
          hit: TranscriptRenderedHit
          point: NonNullable<ReturnType<typeof extractTranscriptGeoPoint>>
        } => Boolean(entry.point),
      )

    if (geoHits.length === 0) {
      map.setView(
        [DEFAULT_TRANSCRIPT_MAP_CENTER.lat, DEFAULT_TRANSCRIPT_MAP_CENTER.lng],
        DEFAULT_TRANSCRIPT_MAP_ZOOM,
      )
      return
    }

    const bounds = L.latLngBounds([])
    geoHits.forEach(({ hit, point }) => {
      const marker = L.circleMarker([point.lat, point.lng], {
        radius: 7,
        color: '#0d6efd',
        weight: 2,
        fillColor: '#0d6efd',
        fillOpacity: 0.7,
      }).addTo(markers)

      const popup = document.createElement('div')
      popup.className = 'transcript-map-popup'
      const title = document.createElement('a')
      title.href = hit.permalink
      title.textContent = `${hit.talkgroup_description} (${hit.talkgroup_tag})`
      title.className = 'fw-semibold text-decoration-none'
      popup.appendChild(title)

      if (point.address) {
        const address = document.createElement('div')
        address.className = 'small text-muted'
        address.textContent = point.address
        popup.appendChild(address)
      }

      const timestamp = document.createElement('div')
      timestamp.className = 'small'
      timestamp.textContent = hit.start_time_string
      popup.appendChild(timestamp)

      marker.bindPopup(popup)
      bounds.extend([point.lat, point.lng])
    })

    map.fitBounds(bounds, {
      padding: [24, 24],
      maxZoom: 14,
    })
  }, [hits])

  return (
    <>
      <div
        ref={elementRef}
        className="transcript-map ais-GeoSearch-map rounded border bg-body-tertiary"
        aria-label="Transcript map"
      />
      <div className="small text-muted mt-2">
        Bounding box: <code>{boundingBox}</code>
      </div>
    </>
  )
}

function TranscriptMapResults({ indexName }: { indexName: string }) {
  const { indexUiState, results } = useInstantSearch<UiState>()
  const indexState = (indexUiState || {}) as Record<string, unknown>
  const sortBy =
    typeof indexState.sortBy === 'string' && indexState.sortBy
      ? indexState.sortBy
      : `${indexName}:start_time:desc`
  const hitsPerPage =
    typeof indexState.hitsPerPage === 'number' &&
    Number.isFinite(indexState.hitsPerPage)
      ? indexState.hitsPerPage
      : 30

  const transformItems = useMemo(
    () =>
      createTranscriptHitTransformer({
        indexName,
        hitsPerPage,
        sortBy,
      }),
    [hitsPerPage, indexName, sortBy],
  )

  const hits = useMemo(
    () =>
      transformItems(
        ((results?.hits || []) as TranscriptRenderedHit[]).map((hit) => ({
          ...hit,
        })),
      ),
    [results?.hits, transformItems],
  )

  const geoHits = useMemo(
    () => hits.filter((hit) => extractTranscriptGeoPoint(hit as Record<string, unknown>)),
    [hits],
  )

  return (
    <>
      <Row className="mb-3">
        <Col lg={7}>
          <TranscriptGeoMap hits={hits} />
        </Col>
        <Col lg={5}>
          <div className="d-flex align-items-center justify-content-between mb-2">
            <div className="fw-semibold">Map Results</div>
            <Badge bg="secondary">{geoHits.length} mapped</Badge>
          </div>
          <Stats />
          <div className="mt-2">
            {hits.map((hit) => (
              <HitComponent key={hit.id} hit={hit} />
            ))}
          </div>
          <Pagination className="mt-3" />
        </Col>
      </Row>
    </>
  )
}

export default function TranscriptMap() {
  const { credentials, error, isLoading } = useTranscriptSearchCredentials()
  const archiveIndexConfig = useMemo<TranscriptSearchIndexConfig | null>(() => {
    if (!credentials) {
      return null
    }

    return {
      baseIndexName: credentials.baseIndexName,
      splitByMonth: credentials.splitByMonth,
    }
  }, [credentials])
  const searchClient = useMemo(() => {
    if (!credentials) {
      return null
    }

    return instantMeiliSearch(credentials.hostUrl, credentials.apiKey).searchClient
  }, [credentials])
  const searchLocationSearch =
    typeof window === 'undefined' ? '' : window.location.search
  const indexName =
    archiveIndexConfig === null
      ? ''
      : getTranscriptSearchIndexNameFromLocation(
          searchLocationSearch,
          archiveIndexConfig,
        )

  if (isLoading) {
    return (
      <Alert variant="secondary" className="m-3">
        Loading transcript map…
      </Alert>
    )
  }

  if (!credentials || !archiveIndexConfig || !searchClient) {
    return (
      <Alert variant="danger" className="m-3">
        Failed to load search credentials.
        {error ? <div className="small mt-2">{error.message}</div> : null}
      </Alert>
    )
  }

  const routing = {
    router: history({
      windowTitle: (routeState) => {
        const indexState = routeState[indexName] || {}

        if (!indexState.query) {
          return 'Transcript Map'
        }

        return `${indexState.query} - Transcript Map`
      },
      parseURL: ({ qsModule, location }): UiState => {
        const routeState = qsModule.parse(location.search.slice(1), {
          arrayLimit: 99,
        }) as unknown as UiState

        if (credentials.splitByMonth && Object.keys(routeState).length) {
          return remapSearchStateIndex(
            routeState,
            credentials.baseIndexName,
            indexName,
          )
        }

        if (!Object.keys(routeState).length) {
          return {
            [indexName]: buildDefaultIndexUiState(indexName),
          }
        }

        return routeState
      },
      cleanUrlOnDispose: false,
    }),
    stateMapping: simple(),
  }

  return (
    <InstantSearch
      key={indexName}
      searchClient={searchClient}
      indexName={indexName}
      routing={routing}
      future={{ preserveSharedStateOnUnmount: true }}
    >
      <VirtualRefinementList attribute="talkgroup_description" />
      <h1>Transcript Map</h1>
      <Row className="mb-2">
        <Col lg={3} className="d-none d-lg-block">
          <h2 className="fs-4">Filters</h2>
        </Col>
        <Col>
          <Row>
            <SearchBox
              className="col-lg mb-2 mb-lg-0"
              classNames={{ input: 'form-control' }}
            />
            <SortBy
              className="col-lg-auto col"
              items={[
                {
                  label: 'Newest First',
                  value: `${indexName}:start_time:desc`,
                },
                { label: 'Oldest First', value: `${indexName}:start_time:asc` },
                { label: 'Relevance', value: indexName },
              ]}
            />
            <HitsPerPage
              className="col-lg-auto col"
              items={[
                { label: '20 per page', value: 20, default: true },
                { label: '40 per page', value: 40 },
                { label: '60 per page', value: 60 },
              ]}
            />
          </Row>
        </Col>
      </Row>
      <Row>
        <Col className="search-panel__filters" lg={3}>
          <ClearRefinements
            translations={{
              resetButtonText: 'Clear Filters',
            }}
          />
          <div className="mt-3">
            <RefinementList
              attribute="short_name"
              operator="or"
              showMore={true}
              showMoreLimit={60}
              searchable={true}
              classNames={{
                label: 'form-check-label',
                checkbox: 'form-check-input',
                item: 'form-check',
                count: 'ms-1',
              }}
              transformItems={transformSystemRefinementListItems}
            />
          </div>
          <div className="mt-3">
            <RefinementList
              attribute="talkgroup_group"
              operator="or"
              showMore={true}
              showMoreLimit={60}
              searchable={true}
              classNames={{
                label: 'form-check-label',
                checkbox: 'form-check-input',
                item: 'form-check',
                count: 'ms-1',
              }}
            />
          </div>
          <div className="mt-3">
            <CallTimeRangeFilter archiveConfig={archiveIndexConfig} />
          </div>
        </Col>
        <Col className="search-panel__results">
          <CurrentRefinements transformItems={transformCurrentRefinementItems} />
          <Alert variant="info" className="mb-3">
            The map only shows calls with coordinates in the indexed documents.
          </Alert>
          <TranscriptMapResults indexName={indexName} />
        </Col>
      </Row>
    </InstantSearch>
  )
}

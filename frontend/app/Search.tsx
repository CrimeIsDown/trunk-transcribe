'use client';

import { usePathname, useSearchParams } from 'next/navigation';
import { UiState } from 'instantsearch.js';
import { unescape } from 'instantsearch.js/es/lib/utils';
import { history } from 'instantsearch.js/es/lib/routers';
import { simple } from 'instantsearch.js/es/lib/stateMappings';
import React, { useState } from 'react';
import { FaFilter, FaCalendar } from 'react-icons/fa';
import {
  Hits,
  SearchBox,
  RefinementList,
  CurrentRefinements,
  Stats,
  ClearRefinements,
  SortBy,
  HitsPerPage,
  Pagination,
  HierarchicalMenu,
} from 'react-instantsearch';
import { InstantSearchNext, InstantSearchNextRouting } from 'react-instantsearch-nextjs';
import { instantMeiliSearch } from '@meilisearch/instant-meilisearch';

import moment from 'moment';
import { Accordion, Button, Col, Collapse, Modal, Row } from 'react-bootstrap';
import dynamic from 'next/dynamic';
import { Hit as HitComponent } from './Hit';

function transformItems(items: any): any {
  items.map((hit: any) => {
    hit.raw_transcript = JSON.parse(hit.raw_transcript);
    hit.raw_metadata = JSON.parse(hit.raw_metadata);

    const hitClone = { ...hit };
    delete hitClone['_highlightResult'];
    delete hitClone['_snippetResult'];
    delete hitClone['__position'];
    delete hitClone['raw_metadata'];
    hit.json = JSON.stringify(hitClone, null, 2);

    // Needed since react-instantsearch depends on objectID for setting the key
    hit.objectID = hit.id;

    hit._highlightResult.transcript.value = unescape(
      hit._highlightResult.transcript.value,
    ).trim();

    try {
      hit.highlighted_transcript = JSON.parse(
        unescape(hit._highlightResult.raw_transcript.value),
      );
    } catch (e) {
      console.log(e);
      hit.highlighted_transcript = hit.raw_transcript;
    }

    if (hit.audio_type == 'digital tdma') {
      hit.audio_type = 'digital';
    }
    hit.audio_type = hit.audio_type.charAt(0).toUpperCase() + hit.audio_type.slice(1);

    switch (hit.talkgroup_group_tag) {
      case 'Law Dispatch':
      case 'Law Tac':
      case 'Law Talk':
      case 'Security':
        hit.talkgroup_group_tag_color = 'primary';
        break;
      case 'Fire Dispatch':
      case 'Fire-Tac':
      case 'Fire-Talk':
      case 'EMS Dispatch':
      case 'EMS-Tac':
      case 'EMS-Talk':
        hit.talkgroup_group_tag_color = 'danger';
        break;
      case 'Public Works':
      case 'Utilities':
        hit.talkgroup_group_tag_color = 'success';
        break;
      case 'Multi-Tac':
      case 'Emergency Ops':
        hit.talkgroup_group_tag_color = 'warning';
        break;
      default:
        hit.talkgroup_group_tag_color = 'secondary';
    }

    let start_time = moment.unix(hit.start_time);
    if (hit.short_name == 'chi_cpd') {
      if (hit.raw_metadata['encrypted'] == 1) {
        hit.time_warning = ` - delayed until ${start_time
          .toDate()
          .toLocaleTimeString()}`;
        start_time = start_time.subtract(30, 'minutes');
        hit.encrypted = true;
      }
    }
    hit.start_time_ms = hit.start_time * 1000 + 1; // Add 1 since OpenMHz shows calls older than the specified time, and we want to include the current one
    hit.start_time_string = start_time.toDate().toLocaleString();
    hit.relative_time = start_time.fromNow();

    // hit.permalink = this.search.createURL({
    //   [this.indexName]: {
    //     refinementList: {
    //       talkgroup_tag: [hit.talkgroup_tag],
    //     },
    //     range: {
    //       start_time: `${hit.start_time}:${hit.start_time}`,
    //     },
    //   },
    // });

    // hit.contextUrl =
    //   this.search.createURL(this.buildContextState(hit)).split('#')[0] +
    //   '#hit-' +
    //   hit.id;

    // Apply highlights
    for (let i = 0; i < hit.raw_transcript.length; i++) {
      const segment = hit.raw_transcript[i];
      const highlightedSegment = hit.highlighted_transcript[i];
      const src = segment[0];
      if (src) {
        src.filter_link = '#';
        if (highlightedSegment[0].tag.length > 0) {
          src.label = highlightedSegment[0].tag;
        } else {
          src.label = String(src.src);
        }
      }
      // Show newlines properly
      segment[1] = highlightedSegment[1].replaceAll('\n', '<br>');
    }
  });

  return items;
};

const hostUrl = process.env.MEILI_URL || 'http://localhost:7700';
const apiKey = process.env.MEILI_MASTER_KEY || 'testing';
const indexName = process.env.MEILI_INDEX || 'calls';

const SearchComponent = () => {
  const { searchClient } = instantMeiliSearch(hostUrl, apiKey);

  const [filtersOpen, setFiltersOpen] = useState(true);

  let timer: ReturnType<typeof setTimeout>
  const queryHook = (query: string, refine: Function) => {
    clearTimeout(timer);
    timer = setTimeout(() => refine(query), 500);
  };

  const pathname = usePathname();
  const searchParams = useSearchParams();

  const routing = {
    router: history({
      windowTitle: (routeState) => {
        const indexState = routeState[indexName] || {};

        if (!indexState.query) {
          return 'Search Scanner Transcripts';
        }

        return `${indexState.query} - Search Scanner Transcripts`;
      },
      parseURL: ({ qsModule, location }): UiState => {
        const routeState = qsModule.parse(location.search.slice(1), {
          arrayLimit: 99,
        }) as unknown as UiState;
        if (!Object.keys(routeState).length) {
          const defaultSort = `${indexName}:start_time:desc`;
          return {
            [indexName]: {
              sortBy: defaultSort,
            },
          };
        }
        return routeState;
      },
      getLocation: (): Location => {
        if (typeof window === 'undefined') {
          const url = `http://localhost:3000${pathname}?${searchParams}`;
          return new URL(url) as unknown as Location;
        }

        return window.location;
      },
      cleanUrlOnDispose: false,
    }),
    stateMapping: simple(),
  } as unknown as InstantSearchNextRouting<UiState, UiState>;

  return (
    <InstantSearchNext searchClient={searchClient} indexName={indexName} routing={routing} future={{preserveSharedStateOnUnmount: true}}>
      <h1>Call Transcript Search</h1>
      <a href="/live">View firehose</a>
      <Row className="mb-2">
        <Col lg={3} className="d-none d-lg-block">
          <h2 className="fs-4">Filters</h2>
        </Col>
        <Col>
          <Row>
            <SearchBox className="col-lg mb-2 mb-lg-0" classNames={{ input: 'form-control' }} queryHook={queryHook} />
            <SortBy className="col-lg-auto col" items={[
              { label: 'Newest First', value: `${indexName}:start_time:desc` },
              { label: 'Oldest First', value: `${indexName}:start_time:asc` },
              { label: 'Relevance', value: indexName },
            ]} />
            <HitsPerPage className="col-lg-auto col" items={[
              { label: '20 per page', value: 20, default: true },
              { label: '40 per page', value: 40 },
              { label: '60 per page', value: 60 },
            ]} />
            <div id="option-buttons" className="col-md-auto d-flex justify-content-end">
              <Button onClick={() => setFiltersOpen(!filtersOpen)} type="button" variant="primary" className="d-lg-none" aria-controls="filters">
                <span className="visually-hidden">Filters</span>
                <FaFilter />
              </Button>
            </div>
          </Row>
        </Col>
      </Row>
      <Row>
        <Col className="search-panel__filters" lg={3}>
          <Collapse in={filtersOpen}>
            <div id="filters">
              <h2 id="filtersHeading" className="d-lg-none">Filters</h2>
              <Row className="mb-4">
                <ClearRefinements
                  translations={{
                    resetButtonText: 'Clear Filters',
                  }}
                />
              </Row>
              <Accordion defaultActiveKey={["0", "1", "2", "3", "4"]} flush alwaysOpen>
                <Accordion.Item eventKey="0">
                  <Accordion.Header>System / Department / Talkgroup</Accordion.Header>
                  <Accordion.Body>
                    <HierarchicalMenu
                      attributes={[
                        'talkgroup_hierarchy.lvl0',
                        'talkgroup_hierarchy.lvl1',
                        'talkgroup_hierarchy.lvl2',
                      ]}
                    />
                  </Accordion.Body>
                </Accordion.Item>

                <Accordion.Item eventKey="1">
                  <Accordion.Header>Radio System</Accordion.Header>
                  <Accordion.Body>
                    <RefinementList attribute="short_name" operator="or" showMore={true} showMoreLimit={60} searchable={true} classNames={{ label: 'form-check-label', checkbox: 'form-check-input', item: 'form-check', count: 'ms-1' }} />
                  </Accordion.Body>
                </Accordion.Item>

                <Accordion.Item eventKey="2">
                  <Accordion.Header>Departments</Accordion.Header>
                  <Accordion.Body>
                    <RefinementList attribute="talkgroup_group" operator="or" showMore={true} showMoreLimit={60} searchable={true} classNames={{ label: 'form-check-label', checkbox: 'form-check-input', item: 'form-check', count: 'ms-1' }} />
                  </Accordion.Body>
                </Accordion.Item>

                <Accordion.Item eventKey="3">
                  <Accordion.Header>Talkgroups</Accordion.Header>
                  <Accordion.Body>
                    <RefinementList attribute="talkgroup_tag" operator="or" showMore={true} showMoreLimit={60} searchable={true} classNames={{ label: 'form-check-label', checkbox: 'form-check-input', item: 'form-check', count: 'ms-1' }} />
                  </Accordion.Body>
                </Accordion.Item>

                <Accordion.Item eventKey="4">
                  <Accordion.Header>Talkgroup Type</Accordion.Header>
                  <Accordion.Body>
                    <RefinementList attribute="talkgroup_group_tag" operator="or" showMore={true} showMoreLimit={60} searchable={true} classNames={{ label: 'form-check-label', checkbox: 'form-check-input', item: 'form-check', count: 'ms-1' }} />
                  </Accordion.Body>
                </Accordion.Item>

                <Accordion.Item eventKey="5">
                  <Accordion.Header>Units</Accordion.Header>
                  <Accordion.Body>
                    <RefinementList attribute="units" operator="or" showMore={true} showMoreLimit={60} searchable={true} classNames={{ label: 'form-check-label', checkbox: 'form-check-input', item: 'form-check', count: 'ms-1' }} />
                  </Accordion.Body>
                </Accordion.Item>

                <Accordion.Item eventKey="6">
                  <Accordion.Header>Radio IDs</Accordion.Header>
                  <Accordion.Body>
                    <RefinementList attribute="radios" operator="or" showMore={true} showMoreLimit={60} searchable={true} classNames={{ label: 'form-check-label', checkbox: 'form-check-input', item: 'form-check', count: 'ms-1' }} />
                  </Accordion.Body>
                </Accordion.Item>

                <Accordion.Item eventKey="7">
                  <Accordion.Header>Call Time</Accordion.Header>
                  <Accordion.Body>
                    <Row>
                      <Col>
                        <label htmlFor="minStartTime">From Time</label>
                        <div className="input-group date">
                          <input type="datetime-local" id="minStartTime" className="form-control" />
                          <span className="input-group-text"><FaCalendar /></span>
                        </div>
                      </Col>
                      <Col>
                        <label htmlFor="maxStartTime">To Time</label>
                        <div className="input-group date">
                          <input type="datetime-local" id="maxStartTime" className="form-control" />
                          <span className="input-group-text"><FaCalendar /></span>
                        </div>
                      </Col>
                    </Row>
                  </Accordion.Body>
                </Accordion.Item>
              </Accordion>
            </div>
          </Collapse>
        </Col>
        <Col className="search-panel__results">
          <CurrentRefinements />
          <Stats />
          <Hits hitComponent={HitComponent} transformItems={transformItems} />
          <Pagination className="mt-3" />
        </Col>
      </Row>
    </InstantSearchNext>
  );
}

export default dynamic(() => Promise.resolve(SearchComponent), { ssr: false });

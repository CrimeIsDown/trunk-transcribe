import { Hit as HitObj } from "instantsearch.js";
import { useState } from "react";
import { Button, Col, Collapse, Modal, Row } from "react-bootstrap";
import { FaLink, FaDownload, FaInfoCircle, FaMapMarkerAlt, FaFilter, FaCalendar } from 'react-icons/fa';

type HitProps = {
  hit: HitObj;
};

export function Hit({ hit }: HitProps) {
    const [show, setShow] = useState(false);
    const [detailsOpen, setDetailsOpen] = useState(false);

    const handleClose = () => setShow(false);
    const handleShow = () => setShow(true);

    return (
      <>
        <Row key={hit.id} id={`hit-${hit.id}`}>
          <Collapse in={detailsOpen}>
            <Col lg={5} className={`d-md-block order-lg-2`} id={`hit-${hit.id}-metadata-col`}>
              <p className="d-none d-md-block">
                <strong>
                  <a href={hit.permalink}><FaLink /> {hit.start_time_string}</a>
                </strong>
                <span className="ms-1 fst-italic fs-7">({hit.relative_time})</span>
              </p>
              <p>
                <span className="badge text-bg-light me-1">Duration: {hit.call_length}s</span>
                <a href={`https://openmhz.com/system/${hit.short_name}?filter-type=talkgroup&filter-code=${hit.talkgroup}&time=${hit.start_time}`} className="badge text-bg-secondary me-1" target="_blank" rel="noopener noreferrer">
                  TG {hit.talkgroup}
                </a>
                <span className="badge text-bg-secondary me-1">{hit.audio_type}</span>
                {hit.encrypted > 0 && (
                  <span className="badge text-bg-warning me-1" data-bs-toggle="tooltip" title="From an official Broadcastify.com stream of an encrypted channel">
                    Encrypted / Delayed
                  </span>
                )}
                <Button variant="light" size="sm" className="badge text-bg-light" onClick={handleShow}>
                  Raw Data
                </Button>
              </p>
              <p className="fst-italic">{hit.talkgroup_group} / <strong>{hit.talkgroup_description}</strong></p>
              <div>
                <a href={hit.raw_audio_url} className="btn btn-sm btn-primary mt-2" target="_blank" rel="noopener noreferrer">
                  <FaDownload /> Download Audio
                </a>
              </div>
            </Col>
          </Collapse>
          <Col>
            <h4 className="fs-6 mt-2">
              {/* <Button variant="success" size="sm" className="me-1">
                <FaPlay /><span className="visually-hidden">Play Audio</span>
              </Button>
              <a className="btn btn-sm btn-primary me-1" href={hit.contextUrl}>
                <FaFilter />
              </a> */}
              <Button variant="info" size="sm" className="d-md-none me-1" aria-expanded="false" aria-controls={`hit-${hit.id}-metadata-col`} onClick={() => setDetailsOpen(!detailsOpen)}>
                <FaInfoCircle /><span className="visually-hidden">More Details</span>
              </Button>
              {hit.talkgroup_tag}
              <span className={`badge text-bg-secondary ms-1 me-1`}>{hit.talkgroup_group_tag}</span>
            </h4>
            {hit.geo_formatted_address && (
              <p><span className="badge text-bg-light fs-6"><FaMapMarkerAlt /> {hit.geo_formatted_address}</span></p>
            )}
            <blockquote className="blockquote">
              {hit.raw_transcript.map((segment: any, index: number) => (
                <p key={`${hit.id}-t${index}`}>
                  {segment[0] && <a href={segment[0].filter_link} title={`Radio ID ${segment[0].src}`}>{segment[0].label}</a>}
                  {segment[0] && ': '}
                  <span dangerouslySetInnerHTML={{ __html: segment[1]}} />
                </p>
              ))}
            </blockquote>
            <div><audio id={`call-audio-${hit.id}`} className="call-audio mt-3" src={hit.raw_audio_url} controls preload="none" /></div>
          </Col>
        </Row>
        <Modal size="xl" className="metadata-modal" id={`metadata-${hit.id}`} show={show} onHide={handleClose}>
          <Modal.Header closeButton>
            <Modal.Title>Raw Result Data</Modal.Title>
          </Modal.Header>
          <Modal.Body className="modal-body">
            <pre>{hit.json}</pre>
          </Modal.Body>
        </Modal>
      </>
    );
  }
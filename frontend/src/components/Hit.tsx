import type { Hit as HitObj } from "instantsearch.js";
import { useState } from "react";
import { Button, Col, Collapse, Modal, Row } from "react-bootstrap";
import {
	FaDownload,
	FaFilter,
	FaInfoCircle,
	FaLink,
	FaMapMarkerAlt,
	FaPlay,
} from "react-icons/fa";

type HitProps = {
	hit: TranscriptHit;
	selected?: boolean;
};

type TranscriptSource = {
	filter_link: string;
	src: string | number;
	label: string;
	tag?: string;
	address?: string;
};

type TranscriptSegment = [TranscriptSource | null, string];

type TranscriptHit = HitObj & {
	id: string | number;
	call_length: number;
	encrypted?: number;
	geo_formatted_address?: string;
	contextUrl: string;
	json: string;
	permalink: string;
	raw_audio_url: string;
	raw_transcript: TranscriptSegment[];
	relative_time: string;
	short_name: string;
	start_time: number;
	start_time_string: string;
	talkgroup: string | number;
	talkgroup_description: string;
	talkgroup_group: string;
	talkgroup_group_tag: string;
	talkgroup_group_tag_color: string;
	talkgroup_tag: string;
	time_warning?: string;
};

export function Hit({ hit, selected = false }: HitProps) {
	const [show, setShow] = useState(false);
	const [detailsOpen, setDetailsOpen] = useState(false);
	const [showPlayer, setShowPlayer] = useState(false);

	const handleClose = () => setShow(false);
	const handleShow = () => setShow(true);
	const handlePlay = () => setShowPlayer(true);
	const timeWarning = hit.time_warning ? (
		<span className="ms-1 fst-italic fs-7">{hit.time_warning}</span>
	) : null;

	return (
		<>
			<Row
				key={hit.id}
				id={`hit-${hit.id}`}
				className={selected ? "selected" : undefined}
			>
				<Collapse in={detailsOpen}>
					<Col
						lg={5}
						className={`d-md-block order-lg-2`}
						id={`hit-${hit.id}-metadata-col`}
					>
						<p className="d-none d-md-block">
							<strong>
								<a href={hit.permalink}>
									<FaLink /> {hit.start_time_string}
								</a>
							</strong>
							{timeWarning}
							<span className="ms-1 fst-italic fs-7">
								({hit.relative_time})
							</span>
						</p>
						<p>
							<span className="badge text-bg-light me-1">
								Duration: {hit.call_length}s
							</span>
							<a
								href={`https://openmhz.com/system/${hit.short_name}?filter-type=talkgroup&filter-code=${hit.talkgroup}&time=${hit.start_time}`}
								className="badge text-bg-secondary me-1"
								target="_blank"
								rel="noopener noreferrer"
							>
								TG {hit.talkgroup}
							</a>
							<span className="badge text-bg-secondary me-1">
								{hit.audio_type}
							</span>
							{(hit.encrypted || 0) > 0 && (
								<span
									className="badge text-bg-warning me-1"
									data-bs-toggle="tooltip"
									title="From an official Broadcastify.com stream of an encrypted channel"
								>
									Encrypted / Delayed 30mins
								</span>
							)}
							<Button
								variant="light"
								size="sm"
								className="badge text-bg-light"
								onClick={handleShow}
							>
								Raw Data
							</Button>
						</p>
						<p className="fst-italic">
							{hit.talkgroup_group} /{" "}
							<strong>{hit.talkgroup_description}</strong>
						</p>
					</Col>
				</Collapse>
				<Col>
					<h4 className="fs-6 mt-2">
						{!showPlayer && (
							<Button
								variant="success"
								size="sm"
								className="me-1"
								onClick={handlePlay}
							>
								<FaPlay />
								<span className="visually-hidden">Play Audio</span>
							</Button>
						)}
						<Button
							variant="primary"
							size="sm"
							className="me-1"
							as="a"
							href={hit.contextUrl}
						>
							<FaFilter />
							<span className="visually-hidden">Filter to context</span>
						</Button>
						<Button
							variant="info"
							size="sm"
							className="d-md-none me-1"
							aria-expanded="false"
							aria-controls={`hit-${hit.id}-metadata-col`}
							onClick={() => setDetailsOpen(!detailsOpen)}
						>
							<FaInfoCircle />
							<span className="visually-hidden">More Details</span>
						</Button>
						{hit.talkgroup_tag}
						<span
							className={`badge text-bg-${hit.talkgroup_group_tag_color} ms-1 me-1`}
						>
							{hit.talkgroup_group_tag}
						</span>
					</h4>
					{hit.geo_formatted_address && (
						<p>
							<span className="badge text-bg-light fs-6">
								<FaMapMarkerAlt /> {hit.geo_formatted_address}
							</span>
						</p>
					)}
					<p className="d-md-none">
						<strong>
							<a href={hit.permalink}>
								<FaLink /> {hit.start_time_string}
							</a>
						</strong>
						{timeWarning}
						<span className="ms-1 fst-italic fs-7">({hit.relative_time})</span>
					</p>
					<blockquote className="blockquote">
						{hit.raw_transcript.map((segment, index) => (
							<p key={`${hit.id}-t${index}`}>
								{segment[0] && (
									<a
										href={segment[0].filter_link}
										title={`Radio ID ${segment[0].src}`}
									>
										{segment[0].label}
									</a>
								)}
								{segment[0] && ": "}
								{/* biome-ignore lint/security/noDangerouslySetInnerHtml: transcript highlights are rendered as HTML markup from the search backend */}
								<span dangerouslySetInnerHTML={{ __html: segment[1] }} />
							</p>
						))}
					</blockquote>
					{showPlayer && (
						<div className="mt-3">
							{/* biome-ignore lint/a11y/useMediaCaption: the transcript text is displayed alongside the audio playback */}
							<audio
								id={`call-audio-${hit.id}`}
								className="call-audio"
								src={hit.raw_audio_url}
								controls
								autoPlay
								preload="none"
							/>
						</div>
					)}
					<div>
						<a
							href={hit.raw_audio_url}
							className="btn btn-sm btn-primary mt-2"
							target="_blank"
							rel="noopener noreferrer"
						>
							<FaDownload /> Download Audio
						</a>
					</div>
				</Col>
			</Row>
			<Modal
				size="xl"
				className="metadata-modal"
				id={`metadata-${hit.id}`}
				show={show}
				onHide={handleClose}
			>
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

"use client";

import { useEffect, useState } from "react";
import { Col, Row } from "react-bootstrap";
import { FaCalendar } from "react-icons/fa";
import { useRange } from "react-instantsearch";

import {
	clampTranscriptSearchRangeToMonth,
	type TranscriptSearchIndexConfig,
} from "@/lib/transcriptSearchIndex";
import {
	epochSecondsToLocalDateTimeValue,
	toEpochSeconds,
} from "@/lib/searchState";

type CallTimeRangeFilterProps = {
	archiveConfig?: TranscriptSearchIndexConfig;
	archiveDepthDays?: number | null;
};

export default function CallTimeRangeFilter({
	archiveConfig,
	archiveDepthDays,
}: CallTimeRangeFilterProps) {
	const { start, refine } = useRange({
		attribute: "start_time",
	});

	const [minValue, setMinValue] = useState("");
	const [maxValue, setMaxValue] = useState("");

	useEffect(() => {
		setMinValue(epochSecondsToLocalDateTimeValue(start[0]));
	}, [start[0]]);

	useEffect(() => {
		setMaxValue(epochSecondsToLocalDateTimeValue(start[1]));
	}, [start[1]]);

	const normalizedArchiveDepthDays =
		typeof archiveDepthDays === "number" &&
		Number.isFinite(archiveDepthDays) &&
		archiveDepthDays > 0
			? Math.floor(archiveDepthDays)
			: null;

	const minAllowedEpochSeconds =
		normalizedArchiveDepthDays === null
			? undefined
			: Math.floor(Date.now() / 1000) -
				normalizedArchiveDepthDays * 24 * 60 * 60;

	const minAllowedInputValue = epochSecondsToLocalDateTimeValue(
		minAllowedEpochSeconds,
	);

	const clampEpochSeconds = (value: number | undefined): number | undefined => {
		if (value === undefined || minAllowedEpochSeconds === undefined) {
			return value;
		}

		return Math.max(value, minAllowedEpochSeconds);
	};

	const updateRange = (nextMinValue: string, nextMaxValue: string) => {
		const nextMin = clampEpochSeconds(toEpochSeconds(nextMinValue));
		let nextMax = clampEpochSeconds(toEpochSeconds(nextMaxValue));

		if (nextMin !== undefined && nextMax !== undefined && nextMax < nextMin) {
			nextMax = nextMin;
		}

		const nextRange = `${nextMin ?? ""}:${nextMax ?? ""}`;

		if (archiveConfig?.splitByMonth && nextMin !== undefined) {
			const clampedRange = clampTranscriptSearchRangeToMonth(nextRange);
			if (clampedRange) {
				const [clampedMin, clampedMax] = clampedRange.split(":", 2);
				const clampedMinValue = clampEpochSeconds(
					Number.parseInt(clampedMin || "", 10),
				);
				let clampedMaxValue = clampEpochSeconds(
					Number.parseInt(clampedMax || "", 10),
				);
				if (
					clampedMinValue !== undefined &&
					clampedMaxValue !== undefined &&
					clampedMaxValue < clampedMinValue
				) {
					clampedMaxValue = clampedMinValue;
				}
				refine([
					Number.isFinite(clampedMinValue) ? clampedMinValue : undefined,
					Number.isFinite(clampedMaxValue) ? clampedMaxValue : undefined,
				]);
			}
			return;
		}

		refine([nextMin, nextMax]);
	};

	return (
		<Row>
			<Col>
				{normalizedArchiveDepthDays !== null ? (
					<div className="text-muted small mb-2">
						Archive limited to the last {normalizedArchiveDepthDays} days.
					</div>
				) : null}
				<label htmlFor="minStartTime">From Time</label>
				<div className="input-group date">
					<input
						type="datetime-local"
						id="minStartTime"
						className="form-control"
						value={minValue}
						min={minAllowedInputValue || undefined}
						onChange={(event) => {
							const nextValue = event.target.value;
							setMinValue(nextValue);
							updateRange(nextValue, maxValue);
						}}
					/>
					<span className="input-group-text">
						<FaCalendar />
					</span>
				</div>
			</Col>
			<Col>
				<label htmlFor="maxStartTime">To Time</label>
				<div className="input-group date">
					<input
						type="datetime-local"
						id="maxStartTime"
						className="form-control"
						value={maxValue}
						min={minAllowedInputValue || undefined}
						onChange={(event) => {
							const nextValue = event.target.value;
							setMaxValue(nextValue);
							updateRange(minValue, nextValue);
						}}
					/>
					<span className="input-group-text">
						<FaCalendar />
					</span>
				</div>
			</Col>
		</Row>
	);
}

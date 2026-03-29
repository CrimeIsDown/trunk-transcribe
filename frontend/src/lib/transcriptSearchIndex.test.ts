import { describe, expect, it } from "vitest";

import {
	clampTranscriptSearchRangeToMonth,
	getTranscriptCurrentMonthIndexName,
	getTranscriptMonthRangeBounds,
	getTranscriptSearchIndexNameForRange,
	getTranscriptSearchIndexNameFromLocation,
	rewriteTranscriptSortByIndexName,
} from "./transcriptSearchIndex";

describe("transcriptSearchIndex", () => {
	const referenceDate = new Date(2024, 2, 15, 12, 0, 0);
	const marchRangeStart = Math.floor(Date.UTC(2024, 2, 15, 12, 0, 0) / 1000);
	const marchRangeEnd = Math.floor(Date.UTC(2024, 3, 5, 12, 0, 0) / 1000);
	const config = {
		baseIndexName: "calls",
		splitByMonth: true,
		referenceDate,
	};

	it("defaults to the current month when split-by-month is enabled and no index is present", () => {
		expect(getTranscriptSearchIndexNameFromLocation("", config)).toBe(
			getTranscriptCurrentMonthIndexName(config),
		);
	});

	it("canonicalizes legacy base-index urls to the current month when split-by-month is enabled", () => {
		expect(
			getTranscriptSearchIndexNameFromLocation("?calls[query]=shots", config),
		).toBe(getTranscriptCurrentMonthIndexName(config));
	});

	it("preserves explicit monthly index urls", () => {
		expect(
			getTranscriptSearchIndexNameFromLocation(
				"?calls_2024_02[query]=shots",
				config,
			),
		).toBe("calls_2024_02");
	});

	it("falls back to the base index when split-by-month is disabled", () => {
		expect(
			getTranscriptSearchIndexNameFromLocation("?calls[query]=shots", {
				baseIndexName: "calls",
				splitByMonth: false,
				referenceDate,
			}),
		).toBe("calls");
	});

	it("selects the month index from a call-time range", () => {
		expect(
			getTranscriptSearchIndexNameForRange({ start_time: `${marchRangeStart}:${
				marchRangeStart + 3600
			}` }, config),
		).toBe("calls_2024_03")
	});

	it("clamps cross-month ranges to the selected month", () => {
		const bounds = getTranscriptMonthRangeBounds(referenceDate);

		expect(clampTranscriptSearchRangeToMonth(`${marchRangeStart}:${marchRangeEnd}`)).toBe(
			`${bounds.start_time}:${bounds.end_time}`,
		);
	});

	it("rewrites sortBy prefixes when switching indexes", () => {
		expect(
			rewriteTranscriptSortByIndexName(
				"calls:start_time:desc",
				"calls_2024_03",
				"calls",
			),
		).toBe("calls_2024_03:start_time:desc");
	});
});

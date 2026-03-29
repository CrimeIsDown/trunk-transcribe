import { describe, expect, it } from "vitest";

import {
	formatHierarchyLabel,
	formatSystemLabel,
	transformCurrentRefinements,
	transformHierarchyMenuItems,
	transformSystemRefinementItems,
} from "./transcriptSearchLabels";

describe("transcriptSearchLabels", () => {
	it("maps known radio system codes to human-friendly labels", () => {
		expect(formatSystemLabel("chi_cpd")).toBe("Chicago Police Department");
		expect(formatSystemLabel("willco_p25")).toBe("Will County (P25)");
	});

	it("falls back to a readable title case label for unknown codes", () => {
		expect(formatSystemLabel("north_side")).toBe("North Side");
	});

	it("formats hierarchy paths using the mapped system label", () => {
		expect(formatHierarchyLabel("chi_cpd > Police > Main")).toBe(
			"Chicago Police Department > Police > Main",
		);
	});

	it("transforms refinement list items for systems", () => {
		expect(
			transformSystemRefinementItems([
				{ value: "chi_cpd", label: "chi_cpd", highlighted: "chi_cpd" },
			]),
		).toEqual([
			{
				value: "chi_cpd",
				label: "Chicago Police Department",
				highlighted: "Chicago Police Department",
			},
		]);
	});

	it("transforms hierarchy and current refinement labels", () => {
		const [hierarchyItem] = transformHierarchyMenuItems([
			{ value: "chi_cpd > Police", label: "chi_cpd > Police" },
		]);
		expect(hierarchyItem.label).toBe("Chicago Police Department > Police");

		const [shortNameRefinement, callTimeRefinement] =
			transformCurrentRefinements([
				{
					attribute: "short_name",
					label: "short_name",
					refinements: [{ value: "chi_cpd", label: "chi_cpd" }],
				},
				{
					attribute: "start_time",
					label: "start_time",
					refinements: [{ value: 1704153600, label: "1704153600" }],
				},
			]);

		expect(shortNameRefinement.label).toBe("System");
		expect(shortNameRefinement.refinements[0].label).toBe(
			"Chicago Police Department",
		);
		expect(callTimeRefinement.label).toBe("Call Time");
		expect(callTimeRefinement.refinements[0].label).toContain("2024");
	});
});

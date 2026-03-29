const SYSTEM_LABELS: Record<string, string> = {
	chi_cpd: "Chicago Police Department",
	chi_cfd: "Chicago Fire Department (conventional P25)",
	chi_oemc: "Chicago OEMC (trunked P25)",
	sc21102: "STARCOM21",
	chisuburbs: "Chicago Suburbs",
	willco_p25: "Will County (P25)",
};

function formatFallbackLabel(value: string): string {
	return value
		.replaceAll("_", " ")
		.replace(/\s+/g, " ")
		.trim()
		.replace(/\b\w/g, (character) => character.toUpperCase());
}

export function formatSystemLabel(value: unknown): string {
	if (typeof value !== "string") {
		return "";
	}

	const normalizedValue = value.trim();
	if (!normalizedValue) {
		return "";
	}

	return SYSTEM_LABELS[normalizedValue] ?? formatFallbackLabel(normalizedValue);
}

export function formatHierarchyLabel(value: unknown): string {
	if (typeof value !== "string") {
		return "";
	}

	const [head, ...tail] = value.split(" > ");
	const formattedHead = formatSystemLabel(head);

	return [formattedHead || head, ...tail].join(" > ");
}

function formatCallTimeLabel(value: unknown): string {
	const numericValue =
		typeof value === "number" ? value : Number.parseInt(String(value), 10);

	if (!Number.isFinite(numericValue)) {
		return String(value ?? "");
	}

	return new Date(numericValue * 1000).toLocaleString([], {
		year: "numeric",
		month: "numeric",
		day: "numeric",
		hour: "numeric",
		minute: "2-digit",
	});
}

type RefinementListItem = {
	value?: unknown;
	label?: unknown;
	highlighted?: unknown;
} & Record<string, unknown>;

type CurrentRefinement = {
	value?: unknown;
	label?: string;
} & Record<string, unknown>;

type CurrentRefinementItem = {
	attribute?: string;
	label?: string;
	refinements?: CurrentRefinement[];
} & Record<string, unknown>;

export function transformSystemRefinementItems(
	items: RefinementListItem[],
): RefinementListItem[] {
	return items.map((item) => {
		const label = formatSystemLabel(item.value);

		return {
			...item,
			label: label || item.label,
			highlighted: label || item.highlighted,
		};
	});
}

export function transformHierarchyMenuItems(
	items: RefinementListItem[],
): RefinementListItem[] {
	return items.map((item) => {
		const label = formatHierarchyLabel(item.label ?? item.value);

		return {
			...item,
			label: label || item.label,
			highlighted: label || item.highlighted,
		};
	});
}

export function transformCurrentRefinements(
	items: CurrentRefinementItem[],
): CurrentRefinementItem[] {
	return items.map((item) => {
		const nextItem = { ...item };

		switch (nextItem.attribute) {
			case "short_name":
				nextItem.label = "System";
				nextItem.refinements = nextItem.refinements?.map((refinement) => ({
					...refinement,
					label: formatSystemLabel(refinement.value),
				}));
				break;
			case "talkgroup_group":
				nextItem.label = "Department";
				break;
			case "talkgroup_tag":
				nextItem.label = "Talkgroup";
				break;
			case "talkgroup_group_tag":
				nextItem.label = "Talkgroup Type";
				break;
			case "talkgroup_hierarchy.lvl0":
			case "talkgroup_hierarchy.lvl1":
			case "talkgroup_hierarchy.lvl2":
				nextItem.label = "Sys/Dept/TG";
				nextItem.refinements = nextItem.refinements?.map((refinement) => ({
					...refinement,
					label: formatHierarchyLabel(refinement.label ?? refinement.value),
				}));
				break;
			case "start_time":
				nextItem.label = "Call Time";
				nextItem.refinements = nextItem.refinements?.map((refinement) => ({
					...refinement,
					label: formatCallTimeLabel(refinement.value),
				}));
				break;
			default:
				break;
		}

		return nextItem;
	});
}

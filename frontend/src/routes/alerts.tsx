import { createFileRoute } from "@tanstack/react-router";
import Container from "react-bootstrap/Container";

import Alerts from "../components/Alerts";

export const Route = createFileRoute("/alerts")({
	component: AlertsPage,
});

function AlertsPage() {
	return (
		<Container fluid={true}>
			<Alerts />
		</Container>
	);
}


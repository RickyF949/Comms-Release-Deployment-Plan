import reflex as rx
import reflex_enterprise as rxe

from starlette.applications import Starlette

from app.communications_webhook import communications_webhook
from app.models import Base
from app.components.operations import operations_page
from app.states.operations_state import OperationsState

model_metadata = Base.metadata


def index() -> rx.Component:
    return operations_page()


def register_webhook(backend: Starlette) -> Starlette:
    backend.add_route(
        "/api/webhooks/communications",
        communications_webhook,
        methods=["POST"],
    )
    return backend


app = rxe.App(
    api_transformer=register_webhook,
    theme=rx.theme(appearance="light"),
    head_components=[
        rx.el.link(rel="preconnect", href="https://fonts.googleapis.com"),
        rx.el.link(
            rel="preconnect",
            href="https://fonts.gstatic.com",
            cross_origin="",
        ),
        rx.el.link(
            href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&display=swap",
            rel="stylesheet",
        ),
    ],
)
app.add_page(
    index,
    route="/",
    title="Comms Release · Operations",
    on_load=OperationsState.refresh,
)

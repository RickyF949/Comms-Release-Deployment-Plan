import reflex as rx

import os
import reflex_enterprise as rxe

_extra_scopes = (
    os.environ.get("OIDC_EXTRA_SCOPES", "").replace(",", " ").split()
)

config = rxe.Config(
    app_name="app",
    plugins=[
        rx.plugins.SitemapPlugin(),
        rx.plugins.TailwindV4Plugin(),
        rxe.AuthPlugin(
            auth=True,
            login_page="app.pages.auth_login.login_page",
            extra_scopes=_extra_scopes,
        ),
    ],
)

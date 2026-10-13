import reflex as rx

import os
from collections.abc import Sequence

import reflex_enterprise as rxe
from reflex_enterprise.auth import AuthUserState

_PROVIDER_NAME = os.environ.get("OIDC_PROVIDER_NAME", "")
_LOGIN_LABEL = (
    f"Continue with {_PROVIDER_NAME}"
    if _PROVIDER_NAME
    else "Continue with Google"
)


class LoginRedirectState(rx.State):
    @rxe.event(auth=False)
    def continue_to_app(self):
        raw = self.router.page.params.get("redirect_to", "/")
        target = (
            raw
            if isinstance(raw, str)
            and raw.startswith("/")
            and not raw.startswith("//")
            # Browsers treat \ as / and strip tab/CR/LF in URLs, so
            # "/\host" and "/\t/host" both become "//host".
            and not any(c in raw for c in "\t\r\n\\")
            else "/"
        )
        return rx.redirect(target)


def login_buttons(providers: Sequence) -> tuple:
    return tuple(
        provider.get_login_button(
            rx.el.button(
                rx.icon("log-in", class_name="h-4 w-4 text-white"),
                _LOGIN_LABEL,
                class_name="flex w-full items-center justify-center gap-2 rounded-lg bg-teal-800 px-5 py-3 text-sm font-semibold text-white transition-colors hover:bg-teal-900 focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-teal-700",
            )
        )
        for provider in providers
    )


def login_page(*, providers: Sequence, **context) -> rx.Component:
    return rx.fragment(
        rx.el.main(
            rx.el.section(
                rx.el.div(
                    rx.icon(
                        "messages-square", class_name="h-6 w-6 text-teal-800"
                    ),
                    rx.el.span(
                        "Comms Release",
                        class_name="text-lg font-semibold tracking-tight text-stone-900",
                    ),
                    class_name="mb-9 flex items-center justify-center gap-3",
                ),
                rx.el.div(
                    rx.el.p(
                        "OPERATIONS ACCESS",
                        class_name="mb-3 text-xs font-semibold tracking-widest text-teal-800",
                    ),
                    rx.el.h1(
                        "Welcome back",
                        class_name="mb-3 text-2xl font-semibold tracking-tight text-stone-900",
                    ),
                    rx.el.p(
                        "Sign in to your communications workspace.",
                        class_name="mb-7 text-sm leading-6 text-stone-600",
                    ),
                    *login_buttons(providers),
                    rx.el.div(
                        rx.icon(
                            "shield-check",
                            class_name="h-4 w-4 shrink-0 text-teal-800",
                        ),
                        rx.el.p(
                            "Secure access for your team",
                            class_name="text-xs text-stone-500",
                        ),
                        class_name="mt-6 flex items-center justify-center gap-2 border-t border-stone-200 pt-5",
                    ),
                    class_name="rounded-xl border border-stone-200 bg-white p-7 text-center sm:p-9",
                ),
                class_name="w-full max-w-sm",
            ),
            class_name="flex min-h-dvh items-center justify-center bg-[#f7f6f2] px-5 py-12 font-['Inter'] text-stone-900",
        ),
        rx.cond(
            AuthUserState.provider_name != "",
            rx.el.div(on_mount=LoginRedirectState.continue_to_app),
        ),
    )

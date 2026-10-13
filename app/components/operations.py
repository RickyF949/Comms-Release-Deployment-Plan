import reflex as rx

from reflex_enterprise.auth import User

from app.states.operations_state import OperationsState as State


BUTTON = "inline-flex items-center justify-center gap-2 rounded-lg border border-stone-200 bg-white px-3 py-2 text-sm font-medium text-stone-700 transition-colors hover:bg-stone-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-teal-700 disabled:cursor-not-allowed disabled:opacity-50"
PRIMARY = "inline-flex items-center justify-center gap-2 rounded-lg bg-[#0f766e] px-4 py-2 text-sm font-semibold text-white hover:bg-teal-800 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-teal-700 disabled:cursor-not-allowed disabled:opacity-50"


def badge(status: str) -> rx.Component:
    return rx.el.span(
        rx.el.span(class_name="h-1.5 w-1.5 rounded-full bg-current"),
        status,
        class_name=rx.match(
            status,
            (
                "pending",
                "inline-flex w-fit items-center gap-2 rounded-full bg-stone-100 px-2.5 py-1 text-xs font-medium capitalize text-stone-600",
            ),
            (
                "processing",
                "inline-flex w-fit items-center gap-2 rounded-full bg-blue-100 px-2.5 py-1 text-xs font-medium capitalize text-blue-500",
            ),
            (
                "sent",
                "inline-flex w-fit items-center gap-2 rounded-full bg-green-100 px-2.5 py-1 text-xs font-medium capitalize text-green-500",
            ),
            (
                "failed",
                "inline-flex w-fit items-center gap-2 rounded-full bg-red-100 px-2.5 py-1 text-xs font-medium capitalize text-red-500",
            ),
            "inline-flex w-fit items-center gap-2 rounded-full bg-stone-100 px-2.5 py-1 text-xs text-stone-600",
        ),
    )


def header() -> rx.Component:
    return rx.el.header(
        rx.el.div(
            rx.el.div(
                rx.icon("messages-square", class_name="h-5 w-5 text-white"),
                class_name="flex h-9 w-9 items-center justify-center rounded-lg bg-[#0f766e]",
            ),
            rx.el.div(
                rx.el.p(
                    "Comms Release",
                    class_name="text-base font-semibold tracking-tight text-stone-900",
                ),
                rx.el.p(
                    "Operations workspace", class_name="text-xs text-stone-500"
                ),
            ),
            class_name="flex items-center gap-3",
        ),
        rx.el.div(
            rx.el.div(
                rx.el.p(
                    User.name, class_name="text-sm font-medium text-stone-900"
                ),
                rx.el.p(
                    User.email, class_name="break-all text-xs text-stone-500"
                ),
                class_name="text-right",
            ),
            rx.el.button(
                rx.icon("log-out", class_name="h-4 w-4"),
                rx.el.span("Sign out", class_name="hidden sm:inline"),
                on_click=User.logout,
                aria_label="Sign out",
                class_name=BUTTON,
            ),
            class_name="flex items-center gap-4",
        ),
        class_name="flex flex-wrap items-center justify-between gap-4 border-b border-stone-200 bg-white px-5 py-4 sm:px-8",
    )


def status_tile(status: str) -> rx.Component:
    return rx.el.button(
        rx.el.div(
            rx.el.span(
                status,
                class_name="text-xs font-medium capitalize text-stone-500",
            ),
            rx.icon("arrow-up-right", class_name="h-3.5 w-3.5 text-stone-400"),
            class_name="flex items-center justify-between",
        ),
        rx.el.p(
            State.counts[status],
            class_name="mt-2 text-2xl font-semibold tracking-tight text-stone-900",
        ),
        on_click=lambda: State.filter_status(status),
        aria_label=f"Filter {status} jobs",
        class_name=rx.cond(
            State.status_filter == status,
            "w-full rounded-xl border border-teal-700 bg-teal-50/60 p-4 text-left focus-visible:outline-2 focus-visible:outline-teal-700",
            "w-full rounded-xl border border-stone-200 bg-white p-4 text-left hover:border-teal-700 focus-visible:outline-2 focus-visible:outline-teal-700",
        ),
    )


def filter_button(status: str) -> rx.Component:
    return rx.el.button(
        status,
        rx.el.span(
            State.counts[status],
            class_name="rounded-full bg-white/70 px-1.5 py-0.5 text-[10px]",
        ),
        on_click=lambda: State.filter_status(status),
        aria_pressed=State.status_filter == status,
        class_name=rx.cond(
            State.status_filter == status,
            "flex items-center gap-2 rounded-md bg-teal-50 px-3 py-2 text-xs font-semibold capitalize text-[#0f766e] focus-visible:outline-2 focus-visible:outline-teal-700",
            "flex items-center gap-2 rounded-md bg-white px-3 py-2 text-xs font-medium capitalize text-stone-500 hover:bg-stone-50 focus-visible:outline-2 focus-visible:outline-teal-700",
        ),
    )


def column(label: str, icon: str) -> rx.Component:
    return rx.el.th(
        rx.el.div(
            rx.icon(icon, class_name="h-3.5 w-3.5"),
            label,
            class_name="flex items-center gap-2",
        ),
        scope="col",
        class_name="whitespace-nowrap px-4 py-3 text-left text-xs font-medium text-stone-500",
    )


def job_row(job: dict[str, str]) -> rx.Component:
    return rx.el.tr(
        rx.el.td(
            rx.el.button(
                job["job_id"],
                on_click=lambda: State.select_job(job["id"]),
                class_name="max-w-48 truncate rounded text-left text-sm font-semibold text-[#0f766e] hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-teal-700",
                aria_label=f"View details for job {job['job_id']}",
            ),
            class_name="px-4 py-4",
        ),
        rx.el.td(badge(job["status"]), class_name="px-4 py-4"),
        rx.el.td(
            job["merchant"],
            class_name="max-w-40 truncate px-4 py-4 text-sm text-stone-700",
        ),
        rx.el.td(
            rx.el.p(
                job["customer"], class_name="text-sm font-medium text-stone-800"
            ),
            rx.el.p(job["phone"], class_name="mt-1 text-xs text-stone-500"),
            class_name="px-4 py-4",
        ),
        rx.el.td(
            job["delivery"],
            class_name="whitespace-nowrap px-4 py-4 text-sm text-stone-600",
        ),
        rx.el.td(
            job["received"],
            class_name="whitespace-nowrap px-4 py-4 text-xs text-stone-500",
        ),
        key=job["id"],
        class_name=rx.cond(
            State.selected_id == job["id"],
            "border-t border-stone-100 bg-teal-50/50",
            "border-t border-stone-100 bg-white even:bg-stone-50/40 hover:bg-stone-50",
        ),
    )


def queue_table() -> rx.Component:
    return rx.el.section(
        rx.el.div(
            rx.el.div(
                rx.foreach(State.statuses, filter_button),
                class_name="flex flex-wrap gap-1",
            ),
            rx.el.p(
                "Newest received first ↓", class_name="text-xs text-stone-500"
            ),
            class_name="flex flex-wrap items-center justify-between gap-3 border-b border-stone-200 px-3 py-3",
        ),
        rx.cond(
            State.loading,
            rx.el.div(
                rx.el.p("Loading queue…", class_name="text-sm text-stone-500"),
                class_name="animate-pulse bg-stone-50 p-10",
                role="status",
            ),
            rx.cond(
                State.jobs.length() > 0,
                rx.el.div(
                    rx.el.table(
                        rx.el.thead(
                            rx.el.tr(
                                column("Job", "hash"),
                                column("Status", "circle-dot"),
                                column("Merchant", "store"),
                                column("Customer / phone", "user"),
                                column("Delivery date", "calendar"),
                                column("Received ↓", "clock"),
                                class_name="bg-stone-50/70",
                            )
                        ),
                        rx.el.tbody(rx.foreach(State.jobs, job_row)),
                        class_name="table-auto w-full min-w-[850px]",
                    ),
                    class_name="w-full overflow-x-auto",
                ),
                rx.el.div(
                    rx.icon(
                        "inbox",
                        class_name="mx-auto mb-3 h-7 w-7 text-stone-400",
                    ),
                    rx.el.p(
                        "No jobs in this view",
                        class_name="text-sm font-semibold text-stone-700",
                    ),
                    rx.el.p(
                        "Choose another status or import a CSV to add communications.",
                        class_name="mt-1 text-xs text-stone-500",
                    ),
                    class_name="bg-white px-5 py-12 text-center",
                ),
            ),
        ),
        rx.el.div(
            rx.el.p(
                f"Page {State.page + 1} · {State.counts[State.status_filter]} matching jobs",
                class_name="text-xs text-stone-500",
            ),
            rx.el.div(
                rx.el.button(
                    rx.icon("chevron-left", class_name="h-4 w-4"),
                    "Previous",
                    on_click=lambda: State.change_page(-1),
                    disabled=(State.page == 0) | State.loading,
                    class_name=BUTTON,
                ),
                rx.el.button(
                    "Next",
                    rx.icon("chevron-right", class_name="h-4 w-4"),
                    on_click=lambda: State.change_page(1),
                    disabled=(
                        (State.page + 1) * 25
                        >= State.counts[State.status_filter]
                    )
                    | State.loading,
                    class_name=BUTTON,
                ),
                class_name="flex gap-2",
            ),
            class_name="flex flex-wrap items-center justify-between gap-3 border-t border-stone-200 px-4 py-3",
        ),
        class_name="w-full overflow-hidden rounded-xl border border-stone-200 bg-white",
        aria_label="Communications queue",
    )


def info(label: str, value: str) -> rx.Component:
    return rx.el.div(
        rx.el.dt(label, class_name="text-xs text-stone-500"),
        rx.el.dd(
            value,
            class_name="mt-1 break-words text-sm font-medium text-stone-800",
        ),
    )


def attempt(log: dict[str, str]) -> rx.Component:
    return rx.el.details(
        rx.el.summary(
            rx.el.span(
                f"Attempt {log['number']} · HTTP {log['http']}",
                class_name="text-xs font-semibold text-stone-700",
            ),
            rx.el.span(log["time"], class_name="ml-2 text-xs text-stone-500"),
            class_name="cursor-pointer rounded py-3 focus-visible:outline-2 focus-visible:outline-teal-700",
        ),
        rx.el.p(
            rx.cond(log["error"] != "", log["error"], "No error recorded."),
            class_name="mb-2 whitespace-pre-wrap break-all text-xs text-stone-600",
        ),
        rx.el.pre(
            rx.cond(
                log["response"] != "",
                log["response"],
                "No provider response recorded.",
            ),
            class_name="max-h-48 overflow-auto whitespace-pre-wrap break-all rounded-lg bg-stone-50 p-3 text-xs text-stone-600",
        ),
        key=log["id"],
        class_name="border-t border-stone-100",
    )


def retry_confirmation() -> rx.Component:
    return rx.cond(
        State.confirm_open,
        rx.el.form(
            rx.el.p(
                "Confirm manual retry",
                class_name="text-sm font-semibold text-stone-900",
            ),
            rx.el.p(
                "Delivery may already have occurred. Reconcile the provider outcome before requeueing; a retry can send a duplicate SMS. This only returns the job to pending and preserves all attempts.",
                class_name="mt-2 text-xs leading-5 text-stone-600",
            ),
            rx.el.label(
                rx.el.input(
                    type="checkbox",
                    required=True,
                    name="acknowledge",
                    class_name="h-4 w-4 accent-teal-700",
                ),
                rx.el.span(
                    "I have reconciled the outcome and acknowledge the duplicate-delivery risk.",
                    class_name="text-xs text-stone-700",
                ),
                class_name="my-4 flex items-start gap-2",
            ),
            rx.el.div(
                rx.el.button(
                    "Cancel",
                    type="button",
                    on_click=State.cancel_confirmation,
                    class_name=BUTTON,
                ),
                rx.el.button(
                    "Confirm & requeue",
                    type="submit",
                    disabled=State.retry_busy,
                    class_name=PRIMARY,
                ),
                class_name="flex flex-wrap gap-2",
            ),
            on_submit=State.submit_retry,
            class_name="mt-4 rounded-lg border border-yellow-200 bg-yellow-50 p-4",
        ),
    )


def details_panel() -> rx.Component:
    return rx.el.section(
        rx.el.div(
            rx.icon("file-text", class_name="h-4 w-4 text-[#0f766e]"),
            rx.el.h2(
                "Job details",
                class_name="text-base font-semibold text-stone-900",
            ),
            class_name="mb-5 flex items-center gap-2",
        ),
        rx.cond(
            State.selected_id != "",
            rx.el.div(
                rx.el.div(
                    rx.el.p(
                        State.detail["job_id"],
                        class_name="break-all text-sm font-semibold text-stone-900",
                    ),
                    badge(State.detail["status"]),
                    class_name="mb-5 flex flex-wrap items-center justify-between gap-2",
                ),
                rx.el.dl(
                    info("Merchant", State.detail["merchant"]),
                    info("Customer", State.detail["customer"]),
                    info("Phone", State.detail["phone"]),
                    info("Delivery date", State.detail["delivery"]),
                    info("Received", State.detail["received"]),
                    info("Attempts", State.detail["attempts"]),
                    info("Last attempt", State.detail["last_attempt"]),
                    info("Sent", State.detail["sent"]),
                    class_name="grid grid-cols-1 gap-4 sm:grid-cols-2",
                ),
                rx.el.div(
                    rx.el.p(
                        "Latest error",
                        class_name="mb-2 text-xs font-semibold text-stone-500",
                    ),
                    rx.el.p(
                        rx.cond(
                            State.detail["error"] != "",
                            State.detail["error"],
                            "No job error recorded.",
                        ),
                        class_name="whitespace-pre-wrap break-all text-xs leading-5 text-stone-700",
                    ),
                    rx.el.p(
                        "Latest provider response",
                        class_name="mb-2 mt-4 text-xs font-semibold text-stone-500",
                    ),
                    rx.el.pre(
                        rx.cond(
                            State.detail["response"] != "",
                            State.detail["response"],
                            "No response recorded.",
                        ),
                        class_name="max-h-40 overflow-auto whitespace-pre-wrap break-all rounded-lg bg-stone-50 p-3 text-xs text-stone-600",
                    ),
                    class_name="my-5 border-t border-stone-100 pt-4",
                ),
                rx.cond(
                    State.detail["status"] == "failed",
                    rx.el.button(
                        rx.icon("rotate-ccw", class_name="h-4 w-4"),
                        "Review manual retry",
                        on_click=State.open_confirmation,
                        disabled=State.retry_busy | State.loading,
                        class_name=BUTTON,
                    ),
                ),
                retry_confirmation(),
                rx.el.h3(
                    "Attempt history",
                    class_name="mb-2 mt-5 text-sm font-semibold text-stone-900",
                ),
                rx.cond(
                    State.logs.length() > 0,
                    rx.el.div(
                        rx.foreach(State.logs, attempt),
                        class_name="max-h-96 overflow-y-auto",
                    ),
                    rx.el.p(
                        "No delivery attempts yet.",
                        class_name="text-xs text-stone-500",
                    ),
                ),
                rx.el.p(
                    "Showing up to 100 most recent attempts. Timestamps are UTC.",
                    class_name="mt-3 text-xs text-stone-400",
                ),
            ),
            rx.el.div(
                rx.icon(
                    "mouse-pointer-2", class_name="mb-3 h-6 w-6 text-stone-400"
                ),
                rx.el.p(
                    "Select a job to inspect",
                    class_name="text-sm font-medium text-stone-700",
                ),
                rx.el.p(
                    "Click a job ID above to view its response, errors and attempt history.",
                    class_name="mt-2 text-xs leading-5 text-stone-500",
                ),
                class_name="py-6",
            ),
        ),
        class_name="w-full min-w-0 rounded-xl border border-stone-200 bg-white p-5",
        aria_label="Job details",
    )


def import_stat(label: str, value: int) -> rx.Component:
    return rx.el.div(
        rx.el.p(value, class_name="text-lg font-semibold text-stone-900"),
        rx.el.p(label, class_name="text-[11px] text-stone-500"),
        class_name="rounded-lg bg-stone-50 p-2 text-center",
    )


def import_panel() -> rx.Component:
    return rx.el.section(
        rx.el.div(
            rx.icon("file-up", class_name="h-4 w-4 text-[#0f766e]"),
            rx.el.h2(
                "Import communications",
                class_name="text-base font-semibold text-stone-900",
            ),
            class_name="mb-2 flex items-center gap-2",
        ),
        rx.el.p(
            "Queue delivery reminders from a CSV. Existing merchant + job IDs are deduplicated; conflicting details are rejected.",
            class_name="mb-5 text-xs leading-5 text-stone-500",
        ),
        rx.el.label(
            "Merchant",
            html_for="import-merchant",
            class_name="mb-2 block text-xs font-semibold text-stone-700",
        ),
        rx.el.div(
            rx.el.select(
                rx.el.option("Select a merchant", value=""),
                rx.foreach(
                    State.merchants,
                    lambda merchant: rx.el.option(
                        f"{merchant['name']} · {merchant['id']}",
                        value=merchant["id"],
                        key=merchant["id"],
                    ),
                ),
                id="import-merchant",
                value=State.merchant_id,
                on_change=State.select_merchant,
                disabled=State.import_busy,
                class_name="w-full appearance-none rounded-lg border border-stone-200 bg-white py-2.5 pl-3 pr-9 text-sm text-stone-700 focus:border-teal-700 focus:outline-2 focus:outline-teal-700 disabled:opacity-50",
            ),
            rx.icon(
                "chevron-down",
                class_name="pointer-events-none absolute right-3 top-3 h-4 w-4 text-stone-400",
            ),
            class_name="relative",
        ),
        rx.cond(
            State.merchants.length() == 0,
            rx.el.p(
                "No merchants available. Refresh after a merchant has been configured.",
                class_name="mt-2 text-xs text-stone-500",
            ),
        ),
        rx.el.p(
            "Required columns",
            class_name="mb-2 mt-4 text-xs font-semibold text-stone-700",
        ),
        rx.el.code(
            "job_id,customer_name,customer_phone,delivery_day",
            class_name="block overflow-x-auto rounded-lg bg-stone-50 p-3 text-[11px] text-stone-600",
        ),
        rx.el.p(
            "UTF-8 CSV · E.164 phone (+country code) · YYYY-MM-DD date · up to 2 MiB / 5,000 rows",
            class_name="mb-4 mt-2 text-xs leading-5 text-stone-500",
        ),
        rx.upload.root(
            rx.el.div(
                rx.icon(
                    "upload", class_name="mx-auto mb-2 h-5 w-5 text-[#0f766e]"
                ),
                rx.el.p(
                    "Choose CSV or drop it here",
                    class_name="text-sm font-medium text-stone-700",
                ),
                rx.el.p(
                    "One file per import",
                    class_name="mt-1 text-xs text-stone-500",
                ),
                class_name="p-5 text-center",
            ),
            id="comms_csv",
            accept={"text/csv": [".csv"]},
            multiple=False,
            max_files=1,
            max_size=2097152,
            disabled=State.import_busy,
            class_name="mt-2 cursor-pointer rounded-lg border border-dashed border-stone-300 bg-white hover:bg-stone-50 focus-visible:outline-2 focus-visible:outline-teal-700",
        ),
        rx.el.div(
            rx.foreach(
                rx.selected_files("comms_csv"),
                lambda filename: rx.el.p(
                    filename, class_name="truncate text-xs text-stone-600"
                ),
            ),
            class_name="mt-2",
        ),
        rx.el.div(
            rx.el.button(
                rx.icon("upload", class_name="h-4 w-4"),
                rx.cond(State.import_busy, "Importing…", "Upload & import"),
                on_click=State.handle_upload(
                    rx.upload_files(upload_id="comms_csv")
                ),
                disabled=State.import_busy
                | (State.merchant_id == "")
                | (rx.selected_files("comms_csv").length() == 0),
                class_name=PRIMARY,
            ),
            rx.el.button(
                "Clear",
                on_click=rx.clear_selected_files("comms_csv"),
                disabled=State.import_busy,
                class_name=BUTTON,
            ),
            class_name="my-4 flex flex-wrap gap-2",
        ),
        rx.el.div(
            rx.el.p(
                State.import_state,
                class_name="mb-3 text-xs font-semibold text-stone-700",
            ),
            rx.el.div(
                import_stat("Total", State.total),
                import_stat("Processed", State.processed),
                import_stat("Created", State.created),
                import_stat("Duplicates", State.duplicates),
                import_stat("Errors", State.errors),
                class_name="grid grid-cols-5 gap-2",
            ),
            rx.el.p(
                f"{State.processed} / {State.total} rows processed",
                class_name="mt-2 text-xs text-stone-500",
            ),
            class_name="border-t border-stone-100 pt-4",
            role="status",
            aria_live="polite",
        ),
        rx.cond(
            State.row_errors.length() > 0,
            rx.el.details(
                rx.el.summary(
                    "Row errors",
                    class_name="cursor-pointer text-xs font-semibold text-red-500",
                ),
                rx.el.div(
                    rx.foreach(
                        State.row_errors,
                        lambda error: rx.el.p(
                            error, class_name="mt-2 text-xs text-red-500"
                        ),
                    ),
                    class_name="max-h-48 overflow-y-auto",
                ),
                rx.el.p(
                    "Showing the first 100 row errors.",
                    class_name="mt-2 text-xs text-stone-500",
                ),
                open=True,
                class_name="mt-4 rounded-lg bg-red-50 p-3",
            ),
        ),
        rx.el.p(
            "Imports commit in batches. If interrupted, re-upload the same CSV to resume safely. Import progress is session-only; queued jobs remain in the database.",
            class_name="mt-4 text-xs leading-5 text-stone-500",
        ),
        class_name="w-full min-w-0 rounded-xl border border-stone-200 bg-white p-5",
        aria_label="CSV import",
    )


def operations_page() -> rx.Component:
    return rx.el.div(
        header(),
        rx.el.main(
            rx.el.div(
                rx.el.div(
                    rx.el.p(
                        "COMMUNICATIONS",
                        class_name="mb-2 text-[10px] font-semibold tracking-[0.15em] text-[#0f766e]",
                    ),
                    rx.el.h1(
                        "Release queue",
                        class_name="text-2xl font-semibold tracking-tight text-stone-900",
                    ),
                    rx.el.p(
                        "Monitor delivery reminders, inspect attempts and manage the queue.",
                        class_name="mt-2 text-sm text-stone-500",
                    ),
                ),
                rx.el.div(
                    rx.el.button(
                        rx.icon("refresh-cw", class_name="h-4 w-4"),
                        "Refresh",
                        on_click=State.refresh,
                        disabled=State.loading,
                        class_name=BUTTON,
                    ),
                    rx.el.p(
                        rx.cond(
                            State.refreshed_at != "",
                            f"Updated {State.refreshed_at}",
                            "Waiting for queue data",
                        ),
                        class_name="mt-2 text-xs text-stone-500",
                    ),
                    class_name="sm:text-right",
                ),
                class_name="mb-6 flex flex-wrap items-end justify-between gap-4",
            ),
            rx.cond(
                State.error != "",
                rx.el.div(
                    rx.icon("triangle-alert", class_name="h-4 w-4 shrink-0"),
                    State.error,
                    class_name="mb-4 flex items-center gap-2 rounded-lg bg-red-100 p-3 text-sm text-red-500",
                    role="alert",
                ),
            ),
            rx.cond(
                State.message != "",
                rx.el.p(
                    State.message,
                    class_name="mb-4 rounded-lg bg-teal-50 p-3 text-sm text-[#0f766e]",
                    role="status",
                ),
            ),
            rx.el.div(
                rx.foreach(
                    ["pending", "processing", "sent", "failed"], status_tile
                ),
                class_name="mb-6 grid w-full grid-cols-2 gap-3 md:grid-cols-4",
            ),
            queue_table(),
            rx.el.div(
                details_panel(),
                import_panel(),
                class_name="mt-5 grid w-full grid-cols-1 items-start gap-5 lg:grid-cols-2",
            ),
            rx.el.p(
                "All signed-in users have operator access. Pending jobs are released by the scheduled worker, not by this page.",
                class_name="mt-5 text-xs text-stone-500",
            ),
            class_name="w-full flex-1 px-5 py-6 sm:px-8",
        ),
        class_name="min-h-dvh w-full bg-[#f7f6f2] font-['Inter'] text-stone-900",
    )

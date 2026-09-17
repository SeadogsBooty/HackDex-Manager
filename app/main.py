from version import APP_VERSION
from pydantic import BaseModel
import threading
import time

from uuid import uuid4

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI, Request
from fastapi.responses import (
    HTMLResponse,
    PlainTextResponse,
    RedirectResponse,
)
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles

from catalog import get_catalog, get_catalog_stats
from hackdex_provider import sync_catalog
from matcher import run_matching
from obtain_staging import stage_obtain
from obtain_install import install_staged
from patch_readiness import (
    check_hack_readiness,
    readiness_details,
    readiness_summary,
    reconcile_readiness,
)

from base_rom_registry import (
    get_registry_status,
    sync_registry,
    verification_report,
    verify_base_roms,
)

from base_rom_scanner import (
    enrich_base_hashes,
    get_base_platform_status,
    get_base_summary,
    list_base_roms,
    scan_base_roms,
)
from registry_base_scanner import (
    load_registry,
)

from location_store import (
    add_location,
    configure_hack_parent,
    delete_location,
    discover_hack_parent,
    ensure_default_locations,
    list_locations,
    set_enabled,
)
from review import (
    approve_suggestion,
    assign_match,
    get_hack_choices,
    get_review_summary,
    get_title_review_items,
    get_version_review_items,
    reject_suggestion,
    save_version_decision,
    get_ranked_candidates,
    get_resolved_review_items,
    get_unmatched_review_items,
    ignore_rom,
    reset_review_decision,

)
from database import Base, SessionLocal, engine
from models import (
    Hack,
    HackMatch,
    MatchRejection,
    Rom,
    VersionDecision,
)
from scanner import scan_roms
from library_health import audit_library_health
from settings_store import (
    ensure_defaults,
    ensure_setup_state,
    get_settings,
    setup_is_complete,
    update_settings,
)


from logging_config import (
    configure_logging,
    current_log_file,
    current_log_level,
    get_logger,
    reset_request_id,
    set_log_level,
    set_request_id,
    startup_log_level,
)


from log_reader import (
    read_logs,
    read_raw_log,
)


configure_logging()

logger = get_logger("app")
request_logger = get_logger("request")
scan_logger = get_logger("scanner")

catalog_logger = get_logger("catalog")
matcher_logger = get_logger("matcher")
review_logger = get_logger("review")
base_rom_logger = get_logger("base_roms")
settings_logger = get_logger("settings")


app = FastAPI(
    title="HackDex Manager",
    version=APP_VERSION,
)

templates = Jinja2Templates(
    directory="templates"
)

templates.env.globals["app_version"] = APP_VERSION

app.mount(
    "/static",
    StaticFiles(directory="static"),
    name="static",
)



_SENSITIVE_DIAGNOSTIC_KEYS = {
    "authorization",
    "password",
    "secret",
    "token",
    "api_key",
    "apikey",
    "access_token",
    "refresh_token",
}


def _diagnostic_summary(
    value,
    limit: int = 1600,
):

    if not isinstance(
        value,
        dict,
    ):
        return str(
            type(value).__name__
        )

    parts = []

    for key in sorted(
        value.keys(),
        key=str,
    ):

        lowered = str(
            key
        ).lower()

        if any(
            sensitive in lowered
            for sensitive
            in _SENSITIVE_DIAGNOSTIC_KEYS
        ):
            parts.append(
                f"{key}=[REDACTED]"
            )
            continue

        item = value[key]

        if isinstance(
            item,
            (
                str,
                int,
                float,
                bool,
                type(None),
            ),
        ):
            rendered = repr(
                item
            )

        elif isinstance(
            item,
            list,
        ):
            rendered = (
                f"<list:{len(item)}>"
            )

        elif isinstance(
            item,
            dict,
        ):
            rendered = (
                f"<dict:{len(item)}>"
            )

        else:
            rendered = (
                f"<{type(item).__name__}>"
            )

        parts.append(
            f"{key}={rendered}"
        )

    result = " ".join(
        parts
    )

    return result[:limit]


def _run_logged_operation(
    component_logger,
    operation: str,
    function,
    **context,
):

    started = time.perf_counter()

    context_text = " ".join(
        f"{key}={value}"
        for key, value
        in context.items()
    )

    component_logger.info(
        "%s started%s%s",
        operation,
        " " if context_text else "",
        context_text,
    )

    try:
        result = function()

    except ValueError as exc:

        component_logger.warning(
            "%s rejected%s%s reason=%s",
            operation,
            " " if context_text else "",
            context_text,
            exc,
        )

        raise

    except Exception as exc:

        elapsed_ms = (
            time.perf_counter()
            - started
        ) * 1000

        component_logger.exception(
            "%s failed%s%s "
            "elapsed_ms=%.1f error=%s",
            operation,
            " " if context_text else "",
            context_text,
            elapsed_ms,
            exc,
        )

        raise


    elapsed_ms = (
        time.perf_counter()
        - started
    ) * 1000


    failed = (
        isinstance(
            result,
            dict,
        )
        and result.get(
            "success"
        ) is False
    )


    if failed:

        component_logger.warning(
            "%s completed with failure%s%s "
            "elapsed_ms=%.1f",
            operation,
            " " if context_text else "",
            context_text,
            elapsed_ms,
        )

    else:

        component_logger.info(
            "%s completed%s%s "
            "elapsed_ms=%.1f",
            operation,
            " " if context_text else "",
            context_text,
            elapsed_ms,
        )


    component_logger.debug(
        "%s result_summary=%s",
        operation,
        _diagnostic_summary(
            result
        ),
    )

    return result


@app.middleware("http")
async def hackdex_request_logging(
    request: Request,
    call_next,
):

    started = time.perf_counter()

    method = request.method
    path = request.url.path

    request_id = (
        request.headers.get(
            "X-Request-ID"
        )
        or uuid4().hex[:12]
    )

    token = set_request_id(
        request_id
    )

    quiet_path = (
        path == "/health"
        or path == "/favicon.ico"
        or path.startswith(
            "/static/"
        )
        or path.startswith(
            "/api/logs"
        )
    )

    try:

        try:

            response = await call_next(
                request
            )

        except Exception as exc:

            elapsed_ms = (
                time.perf_counter()
                - started
            ) * 1000

            request_logger.exception(
                "Unhandled request exception "
                "method=%s path=%s "
                "elapsed_ms=%.1f error=%s",
                method,
                path,
                elapsed_ms,
                exc,
            )

            raise


        elapsed_ms = (
            time.perf_counter()
            - started
        ) * 1000

        status_code = (
            response.status_code
        )

        response.headers[
            "X-Request-ID"
        ] = request_id


        # Ignore normal diagnostic polling and the
        # browser's missing favicon request.
        if quiet_path:

            if (
                status_code >= 500
                and path != "/favicon.ico"
            ):
                request_logger.error(
                    "HTTP request "
                    "method=%s path=%s "
                    "status=%s elapsed_ms=%.1f",
                    method,
                    path,
                    status_code,
                    elapsed_ms,
                )

            return response


        if status_code >= 500:

            log_method = (
                request_logger.error
            )

        elif status_code >= 400:

            log_method = (
                request_logger.warning
            )

        elif (
            method
            in {
                "POST",
                "PUT",
                "PATCH",
                "DELETE",
            }
        ):

            log_method = (
                request_logger.info
            )

        else:

            log_method = (
                request_logger.debug
            )


        log_method(
            "HTTP request "
            "method=%s path=%s "
            "status=%s elapsed_ms=%.1f",
            method,
            path,
            status_code,
            elapsed_ms,
        )

        return response

    finally:

        reset_request_id(
            token
        )


Base.metadata.create_all(
    bind=engine
)

ensure_default_locations()

# Must run before ensure_defaults() so an existing
# installation can be migrated to setup_completed=true
# instead of receiving the fresh-install default.
ensure_setup_state()

ensure_defaults()


scan_state = {
    "running": False,
    "last_result": None,
    "last_error": None,
}


def run_scan():
    if scan_state["running"]:
        scan_logger.debug(
            "ROM scan request ignored "
            "because a scan is already running."
        )
        return

    scan_logger.info(
        "ROM scan started."
    )

    scan_state["running"] = True
    scan_state["last_error"] = None

    try:
        result = scan_roms()
        scan_state["last_result"] = result

        scan_logger.info(
            "ROM scan completed result=%s",
            result,
        )

    except Exception as exc:
        scan_state["last_error"] = str(exc)

        scan_logger.exception(
            "ROM scan failed: %s",
            exc,
        )

    finally:
        scan_state["running"] = False


def start_background_scan():
    thread = threading.Thread(
        target=run_scan,
        daemon=True,
    )

    thread.start()


def run_catalog_bootstrap():
    """
    Refresh the built-in HackDex catalog independently
    of ROM and Base ROM scanning.

    Provider failure must never prevent HackDex Manager
    from starting.
    """
    catalog_logger.info(
        "HackDex catalog startup synchronization started."
    )

    try:
        result = sync_catalog()

    except Exception as exc:
        catalog_logger.exception(
            "HackDex catalog startup synchronization "
            "failed: %s",
            exc,
        )
        return

    if result.get("success"):
        catalog_logger.info(
            "HackDex catalog startup synchronization "
            "completed imported=%s source=%s",
            result.get("imported"),
            result.get("source"),
        )

        try:
            matching = run_matching()

            catalog_logger.info(
                "Post-catalog matching completed "
                "result=%s",
                matching,
            )

        except Exception as exc:
            catalog_logger.exception(
                "Post-catalog matching failed: %s",
                exc,
            )

        try:
            readiness = (
                reconcile_readiness(
                    initialize=False,
                )
            )

            catalog_logger.info(
                "Post-catalog readiness reconciliation "
                "completed result=%s",
                readiness,
            )

        except Exception as exc:
            catalog_logger.exception(
                "Post-catalog readiness reconciliation "
                "failed: %s",
                exc,
            )

    else:
        catalog_logger.warning(
            "HackDex catalog startup synchronization "
            "did not complete message=%s",
            result.get("message"),
        )



def run_initial_readiness():
    catalog_logger.info(
        "Initial readiness build started."
    )

    try:
        result = reconcile_readiness(
            initialize=True,
        )

        catalog_logger.info(
            "Initial readiness build "
            "completed result=%s",
            result,
        )

    except Exception as exc:
        catalog_logger.exception(
            "Initial readiness build failed: %s",
            exc,
        )


def start_background_initial_readiness():
    thread = threading.Thread(
        target=run_initial_readiness,
        daemon=True,
    )

    thread.start()



def start_background_catalog_bootstrap():
    thread = threading.Thread(
        target=run_catalog_bootstrap,
        daemon=True,
    )

    thread.start()


scheduler = BackgroundScheduler()

scheduler.add_job(
    start_background_scan,
    "interval",
    hours=6,
    id="rom_scan",
    replace_existing=True,
)

scheduler.start()


# 7E-10 setup completion gate
#
# Fresh installations remain in onboarding until the
# user successfully finishes setup. APIs required by
# onboarding, health checks, and static assets remain
# accessible.
#
SETUP_PROTECTED_PAGES = {
    "/",
    "/base-roms",
    "/review",
    "/library-health",
    "/logs",
    "/settings",
}


@app.middleware("http")
async def require_completed_setup(
    request: Request,
    call_next,
):
    path = request.url.path

    protected = (
        path in SETUP_PROTECTED_PAGES
        or path.startswith(
            "/settings/"
        )
    )

    if (
        request.method == "GET"
        and protected
        and not setup_is_complete()
    ):
        return RedirectResponse(
            url="/setup",
            status_code=303,
        )

    return await call_next(request)



@app.on_event("startup")
def startup():

    logger.info(
        "HackDex Manager startup "
        "version=%s log_level=%s "
        "log_file=%s",
        app.version,
        current_log_level(),
        current_log_file(),
    )

    logger.info(
        "Scheduled ROM scan interval "
        "configured for 6 hours."
    )

    start_background_catalog_bootstrap()
    start_background_scan()


@app.on_event("shutdown")
def shutdown():

    logger.info(
        "HackDex Manager shutdown "
        "version=%s",
        app.version,
    )


class LogLevelUpdate(BaseModel):
    level: str


class LocationCreate(BaseModel):
    kind: str
    path: str
    platform: str = "AUTO"
    label: str | None = None


class LocationEnabled(BaseModel):
    enabled: bool


class HackParentSetup(BaseModel):
    path: str
    apply: bool = False



@app.get("/library-health")
def library_health_page(
    request: Request,
):
    return templates.TemplateResponse(
        "library_health.html",
        {
            "request": request,
        },
    )


@app.get("/api/locations")
def api_locations():
    return list_locations()


@app.post("/api/locations")
def api_add_location(
    payload: LocationCreate,
):
    try:
        return {
            "success": True,
            "location": add_location(
                kind=payload.kind,
                path=payload.path,
                platform=payload.platform,
                label=payload.label,
            ),
        }

    except ValueError as exc:
        return {
            "success": False,
            "message": str(exc),
        }


@app.delete(
    "/api/locations/{location_id}"
)
def api_delete_location(
    location_id: int,
):
    try:
        return delete_location(
            location_id
        )

    except ValueError as exc:
        return {
            "success": False,
            "message": str(exc),
        }


@app.put(
    "/api/locations/{location_id}/enabled"
)
def api_location_enabled(
    location_id: int,
    payload: LocationEnabled,
):
    try:
        return {
            "success": True,
            "location": set_enabled(
                location_id,
                payload.enabled,
            ),
        }

    except ValueError as exc:
        return {
            "success": False,
            "message": str(exc),
        }


@app.get(
    "/base-roms",
    response_class=HTMLResponse,
)
def base_roms_page(request: Request):
    return templates.TemplateResponse(
        "base_roms.html",
        {
            "request": request,
        },
    )


@app.get("/api/base-roms")
def api_base_roms():
    return list_base_roms()


@app.get("/api/base-roms/summary")
def api_base_rom_summary():
    return get_base_summary()


@app.get("/api/base-roms/platforms")
def api_base_rom_platforms():
    return get_base_platform_status()


@app.post("/api/base-roms/enrich-hashes")
def api_base_rom_enrich_hashes():
    return enrich_base_hashes()


@app.post("/api/readiness/{hack_slug}")
def api_check_readiness(
    hack_slug: str,
):
    result = check_hack_readiness(
        hack_slug
    )

    if (
        result.get("status")
        == "BASE_MISSING"
    ):
        from patch_readiness import (
            _required_base_info,
        )

        from database import SessionLocal
        from models import Hack

        db = SessionLocal()

        try:
            hack = (
                db.query(Hack)
                .filter(
                    Hack.slug
                    == hack_slug
                )
                .first()
            )

            required_key = (
                result.get("base_key")
                or (
                    hack.base_rom
                    if hack
                    else None
                )
            )

            if required_key:
                result.update(
                    _required_base_info(
                        required_key
                    )
                )

        finally:
            db.close()

    return result


@app.get("/api/readiness")
def api_readiness_summary():
    return readiness_summary()


@app.post(
    "/api/obtain/{hack_slug}/install/{transaction_id}"
)
def api_install_obtain(
    hack_slug: str,
    transaction_id: str,
    replace: bool = False,
):
    result = install_staged(
        hack_slug,
        transaction_id,
        replace=replace,
    )

    if not result.get("success"):
        return result

    warnings = []

    #
    # A successful different-filename update has
    # already retired the exact old physical ROM.
    # Remove its stale database records before
    # rescanning the new library state.
    #
    retired_rom_id = (
        result.get(
            "retired_rom_id"
        )
    )

    if retired_rom_id:
        cleanup_db = SessionLocal()

        try:
            (
                cleanup_db
                .query(HackMatch)
                .filter(
                    HackMatch.rom_id
                    == retired_rom_id
                )
                .delete(
                    synchronize_session=False
                )
            )

            (
                cleanup_db
                .query(MatchRejection)
                .filter(
                    MatchRejection.rom_id
                    == retired_rom_id
                )
                .delete(
                    synchronize_session=False
                )
            )

            (
                cleanup_db
                .query(VersionDecision)
                .filter(
                    VersionDecision.rom_id
                    == retired_rom_id
                )
                .delete(
                    synchronize_session=False
                )
            )

            (
                cleanup_db
                .query(Rom)
                .filter(
                    Rom.id
                    == retired_rom_id
                )
                .delete(
                    synchronize_session=False
                )
            )

            cleanup_db.commit()

            result[
                "old_db_row_retired"
            ] = True

        except Exception as exc:
            cleanup_db.rollback()

            result[
                "old_db_row_retired"
            ] = False

            warnings.append(
                "Old ROM database cleanup "
                "failed: "
                + str(exc)
            )

        finally:
            cleanup_db.close()

    #
    # The actual ROM install is already complete
    # and verified at this point. Any refresh
    # failure must NOT turn a successful install
    # into an HTTP 500.
    #
    try:
        scan_roms()
        result["scan_complete"] = True

    except Exception as exc:
        result["scan_complete"] = False
        warnings.append(
            "ROM scan failed: "
            + str(exc)
        )

    #
    # Explicitly bind the ROM we just created.
    # HackDex Manager knows this identity exactly,
    # so fuzzy matching should not be required.
    #
    db = SessionLocal()

    try:
        hack = (
            db.query(Hack)
            .filter(
                Hack.slug == hack_slug
            )
            .first()
        )

        rom = (
            db.query(Rom)
            .filter(
                Rom.filename
                == result.get("filename")
            )
            .order_by(
                Rom.id.desc()
            )
            .first()
        )

        if hack is None:
            warnings.append(
                "Installed hack could not "
                "be found in catalog."
            )

        elif rom is None:
            warnings.append(
                "Installed ROM could not "
                "be found after scan."
            )

        else:
            rom.hackdex_slug = (
                hack.slug
            )

            rom.latest_version = (
                hack.latest_version
            )

            rom.installed_version = (
                hack.latest_version
            )

            rom.status = "CURRENT"

            db.commit()

            result["rom_bound"] = True
            result["rom_id"] = rom.id

    except Exception as exc:
        db.rollback()

        result["rom_bound"] = False

        warnings.append(
            "Ownership binding failed: "
            + str(exc)
        )

    finally:
        db.close()

    #
    # Run normal matching afterward for the
    # rest of the library. Failure here also
    # must not invalidate a successful install.
    #
    try:
        run_matching()
        result["matching_complete"] = True

    except Exception as exc:
        result["matching_complete"] = False

        warnings.append(
            "Library matching failed: "
            + str(exc)
        )

    result["warnings"] = warnings

    return result


@app.post(
    "/api/obtain/{hack_slug}/stage"
)
def api_stage_obtain(
    hack_slug: str,
    output_format: str | None = None,
):
    return stage_obtain(
        hack_slug,
        output_format=output_format,
    )


@app.get("/api/readiness/details")
def api_readiness_details():
    return readiness_details()


@app.get("/api/base-roms/catalog")
def api_base_rom_catalog():
    data = load_registry()

    if isinstance(data, dict):
        rows = data.get("roms") or []
    elif isinstance(data, list):
        rows = data
    else:
        rows = []

    return {
        "count": len(rows),
        "roms": rows,
    }


@app.get("/api/base-roms/registry")
def api_base_rom_registry():
    return get_registry_status()


@app.post("/api/base-roms/registry/sync")
def api_base_rom_registry_sync():
    return _run_logged_operation(
        base_rom_logger,
        "base_rom_registry_sync",
        sync_registry,
    )


@app.post("/api/base-roms/verify")
def api_base_rom_verify():
    return _run_logged_operation(
        base_rom_logger,
        "base_rom_verify",
        verify_base_roms,
    )


@app.get("/api/base-roms/verification")
def api_base_rom_verification():
    return verification_report()


@app.post("/api/base-roms/scan")
def api_base_rom_scan():
    return _run_logged_operation(
        base_rom_logger,
        "base_rom_scan",
        scan_base_roms,
    )


@app.get("/api/library-health")
def api_library_health():
    return audit_library_health()




@app.get("/logs")
def logs_legacy_redirect():
    return RedirectResponse(
        url="/settings/logs",
        status_code=307,
    )


@app.get(
    "/settings/logs",
    response_class=HTMLResponse,
)
def logs_page(
    request: Request,
):
    return templates.TemplateResponse(
        "logs.html",
        {
            "request": request,
        },
    )


@app.get(
    "/api/logs/raw",
    response_class=PlainTextResponse,
)
def api_logs_raw(
    lines: int = 5000,
    download: bool = False,
):

    body = read_raw_log(
        lines=lines
    )

    headers = {}

    if download:
        headers[
            "Content-Disposition"
        ] = (
            'attachment; '
            'filename="hackdex-manager.log"'
        )

    return PlainTextResponse(
        body,
        headers=headers,
    )


@app.post("/api/logs/level")
def api_set_log_level(
    payload: LogLevelUpdate,
):

    old_level = current_log_level()

    logger.info(
        "Runtime log-level change "
        "requested old=%s new=%s",
        old_level,
        payload.level,
    )

    try:
        new_level = set_log_level(
            payload.level
        )

    except ValueError as exc:
        return {
            "success": False,
            "message": str(exc),
            "level": current_log_level(),
        }

    logger.info(
        "Runtime log level now %s",
        new_level,
    )

    return {
        "success": True,
        "level": new_level,
        "startup_level":
            startup_log_level(),
        "temporary": True,
    }


@app.get("/api/logs")
def api_logs(
    level: str | None = None,
    component: str | None = None,
    q: str | None = None,
    limit: int = 500,
):
    result = read_logs(
        level=level,
        component=component,
        query=q,
        limit=limit,
    )

    result["configured_level"] = (
        current_log_level()
    )

    result["configured_file"] = (
        current_log_file()
    )

    result["startup_level"] = (
        startup_log_level()
    )

    result["runtime_level"] = (
        current_log_level()
    )

    return result



@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "hackdex-manager",
        "version": app.version,
        "scan_running": scan_state["running"],
    }


@app.get("/api/scan/status")
def api_scan_status():
    return scan_state


@app.post("/api/scan")
def api_scan():
    if scan_state["running"]:
        return {
            "started": False,
            "message": "A scan is already running.",
        }

    start_background_scan()

    return {
        "started": True,
        "message": "Background scan started.",
    }


@app.get("/api/roms")
def api_roms():
    db = SessionLocal()

    try:
        roms = (
            db.query(Rom)
            .order_by(
                Rom.platform,
                Rom.parsed_title,
                Rom.filename,
            )
            .all()
        )

        return [
            {
                "id": rom.id,
                "filename": rom.filename,
                "path": rom.path,
                "platform": rom.platform,
                "library": rom.library,
                "extension": rom.extension,
                "size": rom.size,
                "sha1": rom.sha1,
                "sha256": rom.sha256,
                "parsed_title": rom.parsed_title,
                "installed_version": rom.installed_version,
                "latest_version": rom.latest_version,
                "variant": rom.variant,
                "hackdex_id": rom.hackdex_id,
                "hackdex_slug": rom.hackdex_slug,
                "status": rom.status,
            }
            for rom in roms
        ]

    finally:
        db.close()


@app.get("/api/status")
def api_status():
    db = SessionLocal()

    try:
        total = db.query(Rom).count()

        versions_identified = (
            db.query(Rom)
            .filter(
                Rom.installed_version.isnot(None)
            )
            .count()
        )

        return {
            "tracked": total,
            "versions_identified": versions_identified,
            "scan_running": scan_state["running"],
            "catalog": get_catalog_stats(),
        }

    finally:
        db.close()


@app.post("/api/catalog/sync")
def api_catalog_sync():

    result = _run_logged_operation(
        catalog_logger,
        "catalog_sync",
        sync_catalog,
    )

    if result.get("success"):

        result["matching"] = (
            _run_logged_operation(
                matcher_logger,
                "post_catalog_matching",
                run_matching,
            )
        )

        result["readiness"] = (
            _run_logged_operation(
                catalog_logger,
                "post_catalog_readiness",
                lambda: reconcile_readiness(
                    initialize=False,
                ),
            )
        )

    return result


@app.post("/api/match")
def api_match():
    return _run_logged_operation(
        matcher_logger,
        "manual_matching",
        run_matching,
    )


@app.get("/api/review")
def api_review():
    return {
        "summary":
            get_review_summary(),

        # Backward-compatible key used by the
        # current Needs Review page.
        "title_review":
            get_title_review_items(),

        # v0.4.04 workstation name.
        "ambiguous":
            get_title_review_items(),

        "unmatched":
            get_unmatched_review_items(),

        "version_review":
            get_version_review_items(),

        "resolved":
            get_resolved_review_items(),
    }


@app.post(
    "/api/review/{rom_id}/version/{decision}"
)
def api_version_decision(
    rom_id: int,
    decision: str,
):
    try:
        return _run_logged_operation(
            review_logger,
            "version_decision",
            lambda: save_version_decision(
                rom_id,
                decision,
            ),
            rom_id=rom_id,
            decision=decision,
        )

    except ValueError as exc:
        return {
            "success": False,
            "message": str(exc),
        }




@app.get(
    "/api/review/{rom_id}/candidates"
)
def api_review_candidates(
    rom_id: int,
    limit: int = 8,
):
    try:
        return get_ranked_candidates(
            rom_id,
            limit,
        )

    except ValueError as exc:
        return {
            "success": False,
            "message": str(exc),
        }


@app.get("/api/review/unmatched")
def api_review_unmatched():
    return get_unmatched_review_items()


@app.get("/api/review/resolved")
def api_review_resolved():
    return get_resolved_review_items()


@app.post(
    "/api/review/{rom_id}/ignore"
)
def api_review_ignore(
    rom_id: int,
):
    try:
        return _run_logged_operation(
            review_logger,
            "review_ignore",
            lambda: ignore_rom(
                rom_id
            ),
            rom_id=rom_id,
        )

    except ValueError as exc:
        return {
            "success": False,
            "message": str(exc),
        }


@app.post(
    "/api/review/{rom_id}/reset"
)
def api_review_reset(
    rom_id: int,
):
    try:
        return _run_logged_operation(
            review_logger,
            "review_reset",
            lambda: reset_review_decision(
                rom_id
            ),
            rom_id=rom_id,
        )

    except ValueError as exc:
        return {
            "success": False,
            "message": str(exc),
        }


@app.get("/api/review/hacks")
def api_review_hacks():
    return get_hack_choices()


@app.post("/api/review/{rom_id}/approve")
def api_review_approve(
    rom_id: int,
):
    try:
        return _run_logged_operation(
            review_logger,
            "review_approve",
            lambda: approve_suggestion(
                rom_id
            ),
            rom_id=rom_id,
        )

    except ValueError as exc:
        return {
            "success": False,
            "message": str(exc),
        }


@app.post("/api/review/{rom_id}/reject")
def api_review_reject(
    rom_id: int,
):
    try:
        return _run_logged_operation(
            review_logger,
            "review_reject",
            lambda: reject_suggestion(
                rom_id
            ),
            rom_id=rom_id,
        )

    except ValueError as exc:
        return {
            "success": False,
            "message": str(exc),
        }


@app.post(
    "/api/review/{rom_id}/assign/{hack_slug}"
)
def api_review_assign(
    rom_id: int,
    hack_slug: str,
):
    try:
        return _run_logged_operation(
            review_logger,
            "review_assign",
            lambda: assign_match(
                rom_id,
                hack_slug,
            ),
            rom_id=rom_id,
            hack_slug=hack_slug,
        )

    except ValueError as exc:
        return {
            "success": False,
            "message": str(exc),
        }


@app.get("/review", response_class=HTMLResponse)
def review_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="review.html",
        context={},
    )


@app.get("/api/catalog")
def api_catalog():
    return get_catalog()


@app.get("/api/catalog/stats")
def api_catalog_stats():
    return get_catalog_stats()


@app.get("/api/settings")
def api_get_settings():
    return get_settings()


@app.put("/api/settings")
async def api_update_settings(
    request: Request
):
    payload = await request.json()

    settings_logger.info(
        "Settings update requested "
        "keys=%s",
        sorted(
            str(key)
            for key in payload.keys()
        ),
    )

    result = _run_logged_operation(
        settings_logger,
        "settings_update",
        lambda: update_settings(
            payload
        ),
    )

    return result


@app.get(
    "/setup",
    response_class=HTMLResponse,
)
def setup_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="setup.html",
        context={},
    )


@app.get("/api/setup/status")
def api_setup_status():
    settings = get_settings()

    rom_root = settings.get(
        "base_rom_root",
        "/roms",
    )

    def directory_state(path):
        import os
        from pathlib import Path

        target = Path(path)

        return {
            "path":
                str(target),

            "exists":
                target.exists(),

            "directory":
                target.is_dir()
                if target.exists()
                else False,

            "readable":
                (
                    target.is_dir()
                    and os.access(
                        target,
                        os.R_OK | os.X_OK,
                    )
                ),

            "writable":
                (
                    target.is_dir()
                    and os.access(
                        target,
                        os.W_OK | os.X_OK,
                    )
                ),
        }

    return {
        "setup_completed":
            setup_is_complete(),

        "rom":
            directory_state(
                rom_root
            ),

        "data":
            directory_state(
                "/data"
            ),

        "staging":
            directory_state(
                "/staging"
            ),

        "hack_parent":
            settings.get(
                "hack_parent_root",
                "/hacks",
            ),

        "hack_locations":
            list_locations(
                kind="hack"
            ),

        "base_platforms":
            get_base_platform_status(),

        "catalog":
            get_catalog_stats(),
    }


@app.post("/api/setup/hack-parent")
def api_setup_hack_parent(
    payload: HackParentSetup,
):
    try:
        if payload.apply:
            result = (
                configure_hack_parent(
                    payload.path
                )
            )

            update_settings({
                "hack_parent_root":
                    payload.path,
            })

            return {
                "success": True,
                "result": result,
            }

        return {
            "success": True,
            "result":
                discover_hack_parent(
                    payload.path
                ),
        }

    except ValueError as exc:
        return {
            "success": False,
            "message": str(exc),
        }


@app.post("/api/setup/initialize")
def api_setup_initialize():
    result = {
        "success": False,
    }

    catalog_result = (
        _run_logged_operation(
            catalog_logger,
            "setup_catalog_sync",
            sync_catalog,
        )
    )

    result["catalog"] = (
        catalog_result
    )

    if not catalog_result.get(
        "success"
    ):
        result["message"] = (
            "HackDex catalog synchronization "
            "did not complete."
        )
        return result

    locations = list_locations(
        kind="hack"
    )

    ready_locations = [
        row
        for row in locations
        if (
            row.get("enabled")
            and row.get("state")
            == "READY"
        )
    ]

    if not ready_locations:
        result["message"] = (
            "At least one readable hack "
            "library location is required."
        )
        return result

    result["base_roms"] = (
        _run_logged_operation(
            base_rom_logger,
            "setup_base_rom_scan",
            scan_base_roms,
        )
    )

    result["roms"] = (
        _run_logged_operation(
            scan_logger,
            "setup_rom_scan",
            scan_roms,
        )
    )

    result["matching"] = (
        _run_logged_operation(
            matcher_logger,
            "setup_matching",
            run_matching,
        )
    )

    update_settings({
        "setup_completed":
            "true",
    })

    # Do not launch a full first-run readiness sweep here.
    #
    # A fresh catalog can contain hundreds of patches.
    # Downloading/inspecting all of them immediately can
    # overwhelm the provider and trigger rate limiting.
    #
    # Readiness is reconciled incrementally after normal
    # catalog activity and on established installations.
    result["success"] = True
    result["message"] = (
        "HackDex Manager setup completed."
    )

    return result


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):

    if not setup_is_complete():
        return RedirectResponse(
            url="/setup",
            status_code=303,
        )

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={},
    )


@app.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="settings.html",
        context={
            "settings_page": "home",
        },
    )


@app.get(
    "/settings/{settings_page}",
    response_class=HTMLResponse,
)
def settings_subpage(
    request: Request,
    settings_page: str,
):
    # User-facing terminology is "Download".
    # Keep "obtain" internally for backward compatibility.
    if settings_page == "download":
        settings_page = "obtain"

    allowed_pages = {
        "library",
        "obtain",
        "catalog",
        "appearance",
        "about",
    }

    if settings_page not in allowed_pages:
        settings_page = "home"

    return templates.TemplateResponse(
        request=request,
        name="settings.html",
        context={
            "settings_page":
                settings_page,
        },
    )

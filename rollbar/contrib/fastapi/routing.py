__all__ = ['add_to']

import logging
import sys
from typing import Callable, Optional, Type, Union

from fastapi import APIRouter, FastAPI, Request, Response
from fastapi.routing import APIRoute

import rollbar
from .utils import fastapi_min_version, get_installed_middlewares, has_bare_routing
from rollbar.contrib.starlette.requests import store_current_request
from rollbar.lib._async import RollbarAsyncError, try_report

log = logging.getLogger(__name__)


@fastapi_min_version('0.41.0')
def add_to(app_or_router: Union[FastAPI, APIRouter]) -> Optional[Type[APIRoute]]:
    """
    Adds RollbarLoggingRoute handler to the router app.

    This is the recommended way for integration with FastAPI.
    Alternatively to using middleware, the handler may fill
    more data in the payload (e.g. request body).

    app_or_router: FastAPI app or router

    Note: The route handler must be added before adding user routes

    Requirements: FastAPI v0.41.0+

    Example usage:

    from fastapi import FastAPI
    from rollbar.contrib.fastapi import add_to as rollbar_add_to

    app = FastAPI()
    rollbar_add_to(app)

    """
    if not has_bare_routing(app_or_router):
        log.error(
            'RollbarLoggingRoute must to be added to a bare router'
            ' (before adding routes). See docs for more details.'
        )
        return None

    installed_middlewares = get_installed_middlewares(app_or_router)
    if installed_middlewares:
        log.warning(
            f'Detected middleware installed {installed_middlewares}'
            ' while loading Rollbar route handler.'
            ' This can cause in duplicate occurrences.'
        )

    if isinstance(app_or_router, FastAPI):
        _add_to_app(app_or_router)
    elif isinstance(app_or_router, APIRouter):
        _add_to_router(app_or_router)
    else:
        log.error('Error adding RollbarLoggingRoute to application.')
        return None

    return RollbarLoggingRoute


class RollbarLoggingRoute(APIRoute):
    def get_route_handler(self) -> Callable:
        router_handler = super().get_route_handler()

        async def rollbar_route_handler(request: Request) -> Response:
            try:
                store_current_request(request)
                return await router_handler(request)
            except Exception:
                await request.body()
                exc_info = sys.exc_info()

                try:
                    await try_report(exc_info, request)
                except RollbarAsyncError:
                    rollbar.report_exc_info(exc_info, request)
                raise

        return rollbar_route_handler


def _add_to_app(app):
    app.router.route_class = RollbarLoggingRoute


def _add_to_router(router):
    router.route_class = RollbarLoggingRoute

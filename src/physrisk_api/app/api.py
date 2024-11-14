import json
import os
from datetime import datetime, timedelta, timezone

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from fastapi_jwt_auth import AuthJWT
from jwt import ExpiredSignatureError
from physrisk.container import Container
from physrisk.requests import Requester

api_router = APIRouter(prefix="/api")

@api_router.post("/token")
def create_token(request: Request, Authorize: AuthJWT = Depends()):
    body = request.json()
    email = body.get("email", None)
    password = body.get("password", None)
    if email != "test" or password != os.environ["OSC_TEST_USER_KEY"]:
        raise HTTPException(status_code=401, detail="Wrong email or password")

    access_token = Authorize.create_access_token(subject=email, user_claims={"data_access": "osc"})
    response = {"access_token": access_token}
    return response

@api_router.post("/get_hazard_data")
@api_router.post("/get_hazard_data_availability")
@api_router.post("/get_asset_exposure")
@api_router.post("/get_asset_impact")
@inject
def hazard_data(request: Request, requester: Requester = Provide[Container.requester], Authorize: AuthJWT = Depends()):
    """Retrieve data from physrisk library based on request URL and JSON data."""

    log = logging.getLogger("uvicorn")
    request_id = os.path.basename(request.url.path)
    request_dict = request.json()

    log.debug(f"Received '{request_id}' request")

    try:
        try:
            Authorize.jwt_optional()
            # if no JWT, default to 'public' access level
            data_access: str = Authorize.get_jwt_subject() or "osc"
        except ExpiredSignatureError:
            log.info("Signature has expired")
            data_access = "osc"
        except Exception as exc_info:
            log.warning(f"No JWT for '{request_id}' request", exc_info=exc_info)
            # 'public' or 'osc'
            data_access: str = "osc"  # type:ignore
        request_dict["group_ids"] = [data_access]  # type:ignore
        resp_data = requester.get(request_id=request_id, request_dict=request_dict)
        resp_data = json.loads(resp_data)
    except Exception as exc_info:
        log.error(f"Invalid '{request_id}' request", exc_info=exc_info)
        raise HTTPException(status_code=400, detail="Invalid request")

    # Response object should hold a list of items, models or measures.
    # If not, none were found matching the request's criteria.
    if not (
        resp_data.get("items")
        or resp_data.get("models")
        or resp_data.get("asset_impacts")
        or resp_data.get("risk_measures")
    ):
        log.error(f"No results returned for '{request_id}' request")
        raise HTTPException(status_code=404, detail="No results found")

    return resp_data

@api_router.get("/images/{resource}.{format}")
@api_router.get("/tiles/{resource}/{z}/{x}/{y}.{format}")
@inject
def get_image(resource: str, x: int = None, y: int = None, z: int = None, format: str = "png", requester: Requester = Provide[Container.requester], Authorize: AuthJWT = Depends()):
    """Request that physrisk converts an array to image.
    In the tiled form of the request will return the requested tile if an array pyramid exists; otherwise an
    exception is thrown.
    If tiles are not specified then a whole-aray image is created. This is  intended for small arrays,
    say <~ 1500x1500 pixels. Otherwise we use tiled form of request or Mapbox to host tilesets.
    """
    log = logging.getLogger("uvicorn")
    log.info(f"Creating raster image for {resource}.")
    request_id = os.path.basename(resource)
    min_value_arg = request.query_params.get("minValue")
    min_value = float(min_value_arg) if min_value_arg is not None else None
    max_value_arg = request.query_params.get("maxValue")
    max_value = float(max_value_arg) if max_value_arg is not None else None
    colormap = request.query_params.get("colormap")
    scenario_id = request.query_params.get("scenarioId")
    year = int(request.query_params.get("year"))  # type:ignore
    try:
        Authorize.jwt_optional()
        # if no JWT, default to 'osc' access level
        data_access: str = Authorize.get_jwt_subject() or "osc"
    except Exception as exc_info:
        log.warning(f"No JWT for '{request_id}' request", exc_info=exc_info)
        # 'public' or 'osc'
        data_access: str = "osc"  # type:ignore

    image_binary = requester.get_image(
        request_dict={
            "resource": resource,
            "tile": None if not x or not y or not z else (int(x), int(y), int(z)),
            "colormap": colormap,
            "scenario_id": scenario_id,
            "year": year,
            "group_ids": [data_access],
            "max_value": max_value,
            "min_value": min_value,
        }
    )
    return Response(content=image_binary, media_type="image/png")

@api_router.get("/reset")
@inject
def reset(container: Container = Provide[Container]):
    # container.requester.reset()
    container.reset_singletons()
    return "Reset successful"

@api_router.middleware("http")
async def refresh_expiring_jwts(request: Request, call_next):
    response = await call_next(request)
    if request.method == "OPTIONS":
        return response
    try:
        Authorize = AuthJWT(request)
        Authorize.jwt_optional()
        jwt = Authorize.get_raw_jwt()
        if "exp" not in jwt:
            return response
        exp_timestamp = jwt["exp"]
        now = datetime.now(timezone.utc)
        target_timestamp = datetime.timestamp(now + timedelta(minutes=30))
        if target_timestamp > exp_timestamp:
            access_token = Authorize.create_access_token(subject=Authorize.get_jwt_subject())
            data = response.body
            if isinstance(data, dict):
                data["access_token"] = access_token
                response = JSONResponse(content=data)
        return response
    except ExpiredSignatureError:
        log = logging.getLogger("uvicorn")
        log.info("Signature has expired")
        return response
    except Exception as exc_info:
        log = logging.getLogger("uvicorn")
        log.warning("Cannot refresh JWT", exc_info=exc_info)
        # Case where there is not a valid JWT. Just return the original response
        return response

@api_router.post("/logout")
def logout(Authorize: AuthJWT = Depends()):
    response = JSONResponse(content={"msg": "logout successful"})
    Authorize.unset_jwt_cookies(response)
    return response

@api_router.post("/profile")
def profile(Authorize: AuthJWT = Depends()):
    Authorize.jwt_required()
    identity = Authorize.get_jwt_subject()
    response_body = {"id": identity}
    return response_body

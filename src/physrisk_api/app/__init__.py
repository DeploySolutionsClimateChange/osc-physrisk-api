import logging
import os
import pathlib
from datetime import timedelta

from dependency_injector import providers
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from physrisk.container import Container

from physrisk_api.app.override_providers import provide_s3_zarr_store

from .service import main


def create_app():
    dotenv_dir = os.environ.get("CREDENTIAL_DOTENV_DIR", os.getcwd())
    dotenv_path = pathlib.Path(dotenv_dir) / "credentials.env"
    if os.path.exists(dotenv_path):
        load_dotenv(dotenv_path=dotenv_path, override=True)

    app = FastAPI()
    logging.basicConfig(level=logging.INFO)
    logging.info("Starting physrisk_api...")

    container = Container()
    container.wire(modules=[".api"])
    # this is not needed but demonstrates how to override providers in physrisk Container.
    container.override_providers(zarr_store=providers.Singleton(provide_s3_zarr_store))
    # container.override_providers(config =
    # providers.Configuration(default={"zarr_sources": ["embedded", "hazard_test"]}))

    app.container = container
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # The 'main' router should be the only one registered here.
    # All other routes or routers should register with 'main'.
    app.include_router(main)

    return app

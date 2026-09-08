from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor

from shapely.geometry import shape
from tilebox.datasets import Client as DatasetClient
from tilebox.datasets.assets import Asset, AssetCollection, AssetLocation
from tilebox.workflows import ExecutionContext, Task
from tilebox.workflows.automations import StorageEventTask

from catalog_ingestion.config import (
    BUCKET_LOCATION,
    COLLECTION_NAME,
    DEFAULT_PREFIX,
    catalog_slug,
)

TASK_NAMESPACE = "tilebox.com/catalog-ingestion"
BACKFILL_BATCH_SIZE = 500
DOWNLOAD_WORKERS = 16


class BackfillCatalog(Task):
    catalog_code_name: str
    prefix: str = DEFAULT_PREFIX

    @staticmethod
    def identifier() -> tuple[str, str]:
        return f"{TASK_NAMESPACE}/BackfillCatalog", "v2.1"

    def execute(self, context: ExecutionContext) -> None:
        context.current_task.display = "BackfillCatalog"
        (
            DatasetClient()
            .dataset(catalog_slug(self.catalog_code_name))
            .get_or_create_collection(COLLECTION_NAME)
        )
        bucket = context.runner_context.gcs_client(BUCKET_LOCATION)
        batch_starts = []
        product_count = 0
        for blob in bucket.list_blobs(
            prefix=f"{self.prefix}/",
            match_glob=f"{self.prefix}/**/item.json",
        ):
            if product_count % BACKFILL_BATCH_SIZE == 0:
                batch_starts.append(blob.name)
            product_count += 1

        if not batch_starts:
            raise ValueError(f"No metadata files found under {self.prefix!r}")

        context.logger.info(
            "Discovered product metadata",
            catalog_code_name=self.catalog_code_name,
            batch_count=len(batch_starts),
            product_count=product_count,
            prefix=self.prefix,
        )
        context.progress("products cataloged").add(product_count)
        context.submit_subtasks(
            [
                IngestProducts(
                    catalog_code_name=self.catalog_code_name,
                    prefix=self.prefix,
                    start_offset=start_offset,
                    batch_size=BACKFILL_BATCH_SIZE,
                )
                for start_offset in batch_starts
            ],
            max_retries=2,
        )


class CatalogStorageEvent(StorageEventTask):
    catalog_code_name: str

    @staticmethod
    def identifier() -> tuple[str, str]:
        return f"{TASK_NAMESPACE}/CatalogStorageEvent", "v2.1"

    def execute(self, context: ExecutionContext) -> None:
        metadata_path = self.trigger.location.lstrip("/")
        context.current_task.display = "CatalogStorageEvent"
        context.logger.info("Received product metadata", path=metadata_path)
        context.submit_subtask(
            IngestProducts(
                catalog_code_name=self.catalog_code_name,
                prefix=DEFAULT_PREFIX,
                start_offset=metadata_path,
                batch_size=1,
            ),
            max_retries=2,
        )


class IngestProducts(Task):
    catalog_code_name: str
    start_offset: str
    batch_size: int
    prefix: str = DEFAULT_PREFIX

    @staticmethod
    def identifier() -> tuple[str, str]:
        return f"{TASK_NAMESPACE}/IngestProducts", "v1.0"

    def execute(self, context: ExecutionContext) -> None:
        if not 1 <= self.batch_size <= BACKFILL_BATCH_SIZE:
            raise ValueError(
                f"batch_size must be between 1 and {BACKFILL_BATCH_SIZE}"
            )

        bucket = context.runner_context.gcs_client(BUCKET_LOCATION)
        paths = [
            blob.name
            for blob in bucket.list_blobs(
                prefix=f"{self.prefix}/",
                start_offset=self.start_offset,
                match_glob=f"{self.prefix}/**/item.json",
                max_results=self.batch_size,
            )
        ]
        if not paths or paths[0] != self.start_offset:
            raise ValueError(f"Metadata file not found: {self.start_offset}")

        context.current_task.display = f"IngestProducts({len(paths)} products)"

        def load_record(path: str) -> dict:
            metadata = json.loads(bucket.blob(path).download_as_bytes())
            return metadata_record(metadata)

        with ThreadPoolExecutor(max_workers=min(DOWNLOAD_WORKERS, len(paths))) as executor:
            records = list(executor.map(load_record, paths))

        with context.tracer.span("catalog.ingest") as span:
            span.set_attribute("product_count", len(records))
            collection = (
                DatasetClient()
                .dataset(catalog_slug(self.catalog_code_name))
                .get_or_create_collection(COLLECTION_NAME)
            )
            datapoint_ids = collection.ingest(records, allow_existing=True)

        context.logger.info(
            "Cataloged products",
            count=len(datapoint_ids),
            first_path=paths[0],
            last_path=paths[-1],
        )
        context.progress("products cataloged").done(len(records))


def metadata_record(metadata: dict) -> dict:
    assets = AssetCollection.from_assets(
        [
            Asset(
                key=key,
                primary=AssetLocation(value["href"]),
                media_type=value["type"],
                title=value.get("title"),
                roles=frozenset(value.get("roles", [])),
            )
            for key, value in metadata["assets"].items()
        ]
    )
    return {
        "time": metadata["properties"]["datetime"],
        "geometry": shape(metadata["geometry"]),
        "product_id": metadata["id"],
        "orbit_direction": metadata["properties"]["orbit_direction"],
        "polarizations": metadata["properties"]["polarizations"],
        "processing_version": metadata["properties"]["processing_version"],
        **assets.to_fields(),
    }

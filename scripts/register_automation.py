import argparse

from tilebox.workflows import Client

from catalog_ingestion.config import (
    BUCKET_LOCATION,
    DEFAULT_PREFIX,
)
from catalog_ingestion.tasks import CatalogStorageEvent


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("catalog_code_name")
    args = parser.parse_args()

    automations = Client().automations()
    name = f"Catalog new products: {args.catalog_code_name}"
    existing = next(
        (
            automation
            for automation in automations.all()
            if automation.name == name
        ),
        None,
    )
    if existing:
        print(f"Automation already exists: {existing.id}")
        return

    location = next(
        location
        for location in automations.storage_locations()
        if location.location == BUCKET_LOCATION
    )
    automation = automations.create_storage_event_automation(
        name,
        CatalogStorageEvent(catalog_code_name=args.catalog_code_name),
        triggers=[(location, f"{DEFAULT_PREFIX}/**/item.json")],
        max_retries=2,
    )
    print(f"Created automation: {automation.id}")


if __name__ == "__main__":
    main()

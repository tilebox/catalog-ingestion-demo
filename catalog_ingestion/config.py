BUCKET_LOCATION = "your-gcp-project:your-bucket"
DEFAULT_PREFIX = "catalog-ingestion/products"
COLLECTION_NAME = "RTC"
ORGANIZATION_SLUG = "your-organization-slug"


def catalog_slug(code_name: str) -> str:
    return f"{ORGANIZATION_SLUG}.{code_name}"

BUCKET_LOCATION = "your-gcp-project:your-bucket"
DEFAULT_PREFIX = "catalog-ingestion/products"
COLLECTION_NAME = "RTC"
DATASET_NAMESPACE = "your-namespace"


def catalog_slug(code_name: str) -> str:
    return f"{DATASET_NAMESPACE}.{code_name}"

from tilebox.workflows import Runner

from catalog_ingestion.tasks import BackfillCatalog, CatalogStorageEvent, IngestProducts

runner = Runner(tasks=[BackfillCatalog, CatalogStorageEvent, IngestProducts])

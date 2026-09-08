# Catalog ingestion demo

Build a searchable geospatial catalog from metadata files in Google Cloud Storage.
Backfill existing products, then use storage events to catalog new products as
they arrive. The imagery stays in the bucket.

The backfill and storage automation use the same ingestion task:

```text
BackfillCatalog ──────▶ IngestProducts (batches of up to 500)
CatalogStorageEvent ─▶ IngestProducts (one product)
```

The video uses 5,000 synthetic radar products with real Sentinel-1 acquisition
footprints. This repository contains the ingestion code; it does not include the
demo data, product generator, or one-off metadata repair tools.

## Requirements

- Python 3.12 or later, [uv](https://docs.astral.sh/uv/), and the
  [Tilebox CLI](https://docs.tilebox.com/).
- A Tilebox API key with access to datasets and workflows.
- Your demo cluster configured as the organization's default cluster. The commands
  below use that cluster without an explicit cluster argument.
- A GCS bucket registered as a storage location in Tilebox. Its storage events must
  be connected to Tilebox for the automation to run.
- A runner with permission to list and read the bucket's objects.

## Configure the project

```sh
git clone https://github.com/tilebox/catalog-ingestion-demo.git
cd catalog-ingestion-demo
uv sync --locked
export TILEBOX_API_KEY='your-api-key'
tilebox whoami
tilebox automation storage-locations --json
```

Edit `catalog_ingestion/config.py`:

- Set `BUCKET_LOCATION` to the registered GCS location, in `project:bucket` form.
- Set `DATASET_NAMESPACE` to your Tilebox dataset namespace.
- Set `DEFAULT_PREFIX` to the directory containing your products. The default is
  `catalog-ingestion/products`.

Create a workflow for this checkout:

```sh
tilebox workflow create "Catalog ingestion demo" --json
```

Copy the returned `slug` into `tilebox.workflow.toml`. This repository already
contains the workflow files, so there is no need to run `tilebox workflow init`.

Publish and deploy:

```sh
tilebox workflow publish-release --json
tilebox workflow deploy-release --latest --json
```

Configuration is included in the release. Publish and deploy again after changing
the bucket, namespace, or prefix.

## Product metadata

Each product has its own directory:

```text
catalog-ingestion/products/<product-id>/
├── vv.tif
├── vh.tif
├── preview.png
└── item.json
```

The ingestion task reads `item.json`. It expects a GeoJSON Feature with these
fields. Asset URLs must be absolute; replace the illustrative values below with
your product's metadata.

```json
{
  "type": "Feature",
  "stac_version": "1.1.0",
  "id": "example-product-001",
  "geometry": {
    "type": "Polygon",
    "coordinates": [[[14, 47], [15, 47], [15, 48], [14, 48], [14, 47]]]
  },
  "properties": {
    "datetime": "2026-08-01T10:00:00Z",
    "orbit_direction": "descending",
    "polarizations": ["VV", "VH"],
    "processing_version": "1.0.0"
  },
  "assets": {
    "vv": {
      "href": "gs://your-bucket/catalog-ingestion/products/example-product-001/vv.tif",
      "type": "image/tiff; application=geotiff; profile=cloud-optimized",
      "roles": ["data"]
    },
    "vh": {
      "href": "gs://your-bucket/catalog-ingestion/products/example-product-001/vh.tif",
      "type": "image/tiff; application=geotiff; profile=cloud-optimized",
      "roles": ["data"]
    }
  },
  "links": []
}
```

Asset keys are not fixed. A product can also include preview and metadata assets.
The workflow stores their locations and metadata without downloading the imagery.

## Create and backfill the catalog

These commands work in Bash and Zsh. Use a new catalog code name for each rehearsal.

```sh
export CATALOG_CODE_NAME=radar_products_demo

tilebox dataset create \
  --name "Radar products" \
  --code-name "$CATALOG_CODE_NAME" \
  --summary "Radar product metadata and asset locations" \
  --schema-file schema.json \
  --json

tilebox job submit \
  --name backfill-catalog \
  --task tilebox.com/catalog-ingestion/BackfillCatalog \
  --version v2.1 \
  --input "{\"catalog_code_name\":\"$CATALOG_CODE_NAME\"}" \
  --wait --json
```

The backfill lists `**/item.json` under the configured prefix and submits one task
per batch of 500 products. Within each batch, it downloads up to 16 metadata files
concurrently. For 5,000 products, the job has one root task and ten ingestion tasks.

Keep the prefix unchanged during backfill: pause product uploads and metadata
edits until the job completes. The batches use positions in the bucket listing,
not a snapshot of its contents.

## Query the catalog

Set the namespace to the same value as `DATASET_NAMESPACE` in the configuration.
Choose a date range that contains your products.

```sh
export DATASET_NAMESPACE=your-namespace

tilebox dataset query "$DATASET_NAMESPACE.$CATALOG_CODE_NAME" \
  --collections RTC \
  --after 2026-08-01 --before 2026-08-28 \
  --limit 100 --json

tilebox dataset query "$DATASET_NAMESPACE.$CATALOG_CODE_NAME" \
  --collections RTC \
  --after 2026-08-01 --before 2026-08-28 \
  --spatial-extent 'POLYGON((9.5 46.3,17.2 46.3,17.2 49.1,9.5 49.1,9.5 46.3))' \
  --filter "orbit_direction = 'ascending'" \
  --limit 100 --json
```

You can also open the catalog in the [Tilebox Console](https://console.tilebox.com/)
to query it on a map and inspect individual products.

## Catalog new products automatically

After the backfill completes, register the storage automation:

```sh
uv run python scripts/register_automation.py "$CATALOG_CODE_NAME"
tilebox automation list --json
```

The automation watches `<DEFAULT_PREFIX>/**/item.json` in the configured bucket.
When a metadata file arrives, `CatalogStorageEvent` submits an `IngestProducts`
task for that file. Re-running the registration script leaves an existing
automation with the same name unchanged.

Upload a new product's imagery first and its metadata last. For example, using
the [Google Cloud CLI](https://cloud.google.com/sdk/docs/install):

```sh
export PRODUCT_DIR=./new-product
export PRODUCT_DEST=gs://your-bucket/catalog-ingestion/products/new-product

gcloud storage cp "$PRODUCT_DIR/vv.tif" "$PRODUCT_DIR/vh.tif" \
  "$PRODUCT_DIR/preview.png" "$PRODUCT_DEST/"
gcloud storage cp "$PRODUCT_DIR/item.json" "$PRODUCT_DEST/item.json"
```

The metadata must reference the uploaded files. Check the triggered job and
refresh the catalog to see the new product:

```sh
tilebox job list --last 1h --json
tilebox job get JOB_ID --json
tilebox job logs JOB_ID --sort desc --limit 50 --json
```

## Scope

This example handles initial backfill and newly uploaded products. It does not
synchronize edits or deletions. `allow_existing=True` allows existing records;
do not use it to update their metadata. Use a fresh catalog when replacing demo metadata.
Disable the storage automation before bulk metadata rewrites to avoid triggering
an ingestion job for every changed file.

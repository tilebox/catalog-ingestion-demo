# Catalog ingestion demo

Build a searchable geospatial catalog from metadata files in cloud storage.
Backfill existing products, then use storage events to catalog new products as
they arrive.

[Watch the demo on YouTube](https://youtu.be/HTT4Cl6ks98).

Use this project as a starting point for your own catalog. Point your coding agent
at this repository and your data or metadata, then ask it to adapt the dataset
schema, metadata parsing, and ingestion tasks to your products and requirements.
The demo data is not public.

## Requirements

You need Python 3.12+, [uv](https://docs.astral.sh/uv/), the
[Tilebox CLI](https://docs.tilebox.com/), and a Tilebox API key with access to
datasets and workflows. Your runner needs permission to list and read your GCS
bucket. Register the bucket as a Tilebox storage location and
connect its storage events to Tilebox.

Storage automations are in closed beta. To request access, email
[tilebox-devs@tilebox.com](mailto:tilebox-devs@tilebox.com).

## Setup

Replace `<...>` placeholders with your values. Use the same catalog code name
throughout.

```sh
git clone https://github.com/tilebox/catalog-ingestion-demo.git
cd catalog-ingestion-demo
uv sync
export TILEBOX_API_KEY='<your-api-key>'
tilebox automation storage-locations
```

Edit [catalog_ingestion/config.py](catalog_ingestion/config.py):

- `BUCKET_LOCATION`: Your registered GCS location, in `project:bucket` form.
- `ORGANIZATION_SLUG`: Your organization's slug.
- `DEFAULT_PREFIX`: The bucket directory containing your products.

The example reads an `item.json` file per product. See
[`metadata_record`](catalog_ingestion/tasks.py) for the expected metadata fields
and [schema.json](schema.json) for the catalog schema. Asset URLs must be absolute.
You can also adapt the ingestion task to open product files and extract metadata
directly.

Create a workflow:

```sh
tilebox workflow create "Catalog ingestion demo"
```

Copy the returned `slug` into `tilebox.workflow.toml`, then publish and deploy:

```sh
tilebox workflow publish-release
tilebox workflow deploy-release --latest
```

Publish and deploy again after changing the code or configuration.

## Backfill the catalog

Edit [documentation.md](documentation.md) to describe your dataset. The
`--description-file` flag attaches this Markdown documentation to the catalog.
Create the catalog and ingest the existing products:

```sh
tilebox dataset create \
  --name '<catalog-name>' \
  --code-name '<catalog-code-name>' \
  --summary 'Product metadata and asset locations' \
  --schema-file schema.json \
  --description-file documentation.md

tilebox job submit \
  --name backfill-catalog \
  --task '<organization-slug>/catalog-ingestion/BackfillCatalog' \
  --version v0.1 \
  --input '{"catalog_code_name":"<catalog-code-name>"}' \
  --wait
```

The backfill reads `**/item.json` under the configured prefix in batches of up to
500 products. Pause uploads and metadata changes under that prefix until it finishes.

## Query the catalog

Use the dataset slug returned when creating the catalog and a date range that
contains your products:

```sh
tilebox dataset query '<dataset-slug>' \
  --collections RTC \
  --after '<YYYY-MM-DD>' --before '<YYYY-MM-DD>' \
  --filter "orbit_direction = 'ascending'" \
  --limit 100
```

Open the catalog in the [Tilebox Console](https://console.tilebox.com/) to query it
on a map and inspect products.

## Catalog new products automatically

After backfill, register the storage automation:

```sh
uv run python scripts/register_automation.py '<catalog-code-name>'
tilebox automation list
```

The automation watches `<DEFAULT_PREFIX>/**/item.json`. Upload each product's
assets first and its metadata last. For example, with the
[Google Cloud CLI](https://cloud.google.com/sdk/docs/install):

```sh
gcloud storage cp '<local-product-dir>/*.tif' 'gs://<bucket>/<prefix>/<product-id>/'
gcloud storage cp '<local-product-dir>/item.json' 'gs://<bucket>/<prefix>/<product-id>/item.json'
```

Check the triggered job, then refresh the catalog:

```sh
tilebox job list --last 1h
tilebox job logs '<job-id>' --sort desc --limit 50
```

This example ingests existing and new products; it does not synchronize edits or
deletions. Use a fresh catalog when replacing metadata, and disable the automation
before bulk metadata rewrites.

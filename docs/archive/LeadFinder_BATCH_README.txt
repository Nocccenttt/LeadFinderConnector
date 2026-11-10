LEADFINDER BATCH-NAMING VERSION

Run:
python seo_lead_finder_prospecting_batch.py --niche "plumber" --area "Philadelphia, PA"

The default output will automatically be:
plumber - Philadelphia, PA.csv

Another example:
python seo_lead_finder_prospecting_batch.py --niche "roofing" --area "Houston, TX"

Output:
roofing - Houston, TX.csv

Each search/area gets its own CSV, so running multiple batches will not
overwrite earlier batches.

You can still choose a custom filename:
python seo_lead_finder_prospecting_batch.py --niche "plumber" --area "Philadelphia, PA" --output "philly-plumbers.csv"

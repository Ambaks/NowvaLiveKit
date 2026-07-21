# config/

Configuration files for the Nowva platform.

## Files

- `biomechanics.yaml` — Pipeline configuration: fault detection thresholds, filter parameters, model paths, rep counting settings. Loaded once at startup by `biomechanics.config.load_pipeline_config()`.

- `gunicorn_config.py` — Production Gunicorn settings for local/Mac deployment. 4 workers, preload enabled, 120s timeout, port 8001.

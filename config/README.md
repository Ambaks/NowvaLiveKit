# config/

Configuration files for the Nowva platform.

## Files

- `biomechanics.yaml` — Pipeline configuration: fault detection thresholds, filter parameters, model paths, rep counting settings. Loaded once at startup by `biomechanics.config.load_pipeline_config()`.

- `gunicorn_config.py` — Production Gunicorn settings for local/Mac deployment. 4 workers, preload enabled, 120s timeout, port 8001.

- `gunicorn_config_gcp.py` — GCP Free Tier variant. 2 workers, optimized for 1GB RAM, warning-level logging.

- `nginx_production.conf` — Nginx reverse proxy config for nowvasports.com. Routes `/api`, `/ws`, `/docs` to Gunicorn backend.

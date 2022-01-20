#!/bin/bash

gunicorn -c gunicorn.conf.py \
    -b 0.0.0.0:$PORT -k uvicorn.workers.UvicornWorker -w $NUM_WORKERS \
    --access-logfile - --error-logfile - --log-level debug $RELOAD \
    --max-requests $MAX_REQUESTS --max-requests-jitter $MAX_REQUESTS_JITTER \
    app:app

#!/bin/bash -x

pmgrc=$HOME/.pmgrc.yaml
[[ ! -e $pmgrc ]] && echo "PMG_DUMMY_VAR: dummy" > $pmgrc

exec ddtrace-run gunicorn --statsd-host $DD_AGENT_HOST:8125 \
    -b 0.0.0.0:$PORT -k uvicorn.workers.UvicornWorker -w $NUM_WORKERS \
    --access-logfile - --error-logfile - $RELOAD \
    --max-requests $MAX_REQUESTS --max-requests-jitter $MAX_REQUESTS_JITTER \
    --timeout 45 \
    app:app

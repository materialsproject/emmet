#!/bin/bash

pmgrc=$HOME/.pmgrc.yaml
[[ ! -e $pmgrc ]] && echo "PMG_DUMMY_VAR: dummy" > $pmgrc

exec ddtrace-run gunicorn --statsd-host $DD_AGENT_HOST:8125 \
    -b 0.0.0.0:$PORT -k uvicorn.workers.UvicornWorker -w $NUM_WORKERS \
    --access-logfile - --error-logfile - $RELOAD \
    --access-logformat '%(h)s %(t)s %(m)s %(U)s?%(q)s %(H)s %(s)s %(b)s "%(f)s" "%(a)s" %(D)s %(p)s %({x-consumer-id}i)s' \
    --max-requests $MAX_REQUESTS --max-requests-jitter $MAX_REQUESTS_JITTER \
    app:app

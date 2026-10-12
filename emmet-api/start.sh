#!/bin/bash

set -e
PMGRC=$HOME/.pmgrc.yaml
[[ ! -e "$PMGRC" ]] && echo "PMG_DUMMY_VAR: dummy" >"$PMGRC"

STATS_ARG=""
SERVER_APP="app:app"
BIND_ARG="-b 0.0.0.0:$PORT"
WORKER_ARGS="-k uvicorn.workers.UvicornWorker -w $NUM_WORKERS"
# Logging (structured JSON) is configured in gunicorn.conf.py and app.py;
# the access log is written by the app's LoggingMiddleware (see mp_logging)
CONFIG_ARGS="-c gunicorn.conf.py $RELOAD"
REQS_ARGS="--max-requests $MAX_REQUESTS --max-requests-jitter $MAX_REQUESTS_JITTER"
OTHER_ARGS="--timeout 120"
MAIN_ARGS="$BIND_ARG $WORKER_ARGS $CONFIG_ARGS $REQS_ARGS $OTHER_ARGS"

set -x

if [[ -n "$DD_TRACE_HOST" ]]; then
  wait-for-it.sh "$DD_TRACE_HOST" -q -s -t 10 && STATS_ARG="--statsd-host $DD_AGENT_HOST:8125" || echo "WARNING: datadog agent unreachable"
fi

[[ -n "$STATS_ARG" ]] && CMD="ddtrace-run gunicorn $STATS_ARG" || CMD="gunicorn"
exec $CMD $MAIN_ARGS $SERVER_APP

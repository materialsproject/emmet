#!/bin/bash

set -e
PMGRC=$HOME/.pmgrc.yaml
[[ ! -e "$PMGRC" ]] && echo "PMG_DUMMY_VAR: dummy" >"$PMGRC"

STATS_ARG=""
SERVER_APP="app:app"
BIND_ARG="-b 0.0.0.0:$PORT"
WORKER_ARGS="-k uvicorn.workers.UvicornWorker -w $NUM_WORKERS"
LOG_ARGS="--access-logfile - --error-logfile - $RELOAD"
REQS_ARGS="--max-requests $MAX_REQUESTS --max-requests-jitter $MAX_REQUESTS_JITTER"
OTHER_ARGS="--timeout 120"
MAIN_ARGS="$BIND_ARG $WORKER_ARGS $LOG_ARGS $REQS_ARGS $OTHER_ARGS"
ACCESS_LOG_FORMAT=(--access-logformat '%(h)s %(t)s %(m)s %(U)s?%(q)s %(H)s %(s)s %(b)s "%(f)s" "%(a)s" %(D)s %(p)s %({x-consumer-id}i)s %({x-callback-name}o)s %({x-consumer-groups}o)s')

set -x

if [[ -n "$DD_TRACE_HOST" ]]; then
  wait-for-it.sh "$DD_TRACE_HOST" -q -s -t 10 && STATS_ARG="--statsd-host $DD_AGENT_HOST:8125" || echo "WARNING: datadog agent unreachable"
fi

[[ -n "$STATS_ARG" ]] && CMD="ddtrace-run gunicorn $STATS_ARG" || CMD="gunicorn"
exec $CMD $MAIN_ARGS "${ACCESS_LOG_FORMAT[@]}" $SERVER_APP

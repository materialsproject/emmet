#!/bin/sh

curl -f "http://localhost:$PORT/heartbeat" || exit 1

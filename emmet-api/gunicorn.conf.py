def post_worker_init(worker):
    import ddtrace.bootstrap.sitecustomize
    import ddtrace
    from ddtrace.runtime import RuntimeMetrics
    RuntimeMetrics.enable(tracer=ddtrace.tracer, dogstatsd_url=ddtrace.tracer._dogstatsd_url, flush_interval=10)

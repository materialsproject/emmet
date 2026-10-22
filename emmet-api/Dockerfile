FROM materialsproject/devops:python-3.1213.2 AS base
RUN apt-get update && apt-get install -y --no-install-recommends libopenblas-dev libjpeg62 curl && apt-get clean

FROM base AS builder
RUN apt-get update && apt-get install -y --no-install-recommends gcc git g++ cmake make libsnappy-dev wget && apt-get clean
ENV PATH /root/.local/bin:$PATH
WORKDIR /emmet-api
ENV PIP_FLAGS "--user --no-cache-dir --compile"
COPY requirements/deployment.txt ./requirements.txt
# emSign bootstrap (2026-10): install hash-pinned pip first, then everything else
RUN pip install $PIP_FLAGS "pip @ https://files.pythonhosted.org/packages/3f/06/3e4420302363fbb71be3c7f35ce042f54bfca330e3e66b3a2e3c4cca579f/pip-26.2.2-py3-none-any.whl#sha256=fd7f4dfa8190e014013b9f08f3e973f4e4c26ffd179a204895533a7254813a70" && \
  pip install $PIP_FLAGS --upgrade pip-tools && \
  pip-sync requirements.txt --pip-args "$PIP_FLAGS"

COPY emmet emmet
COPY pyproject.toml .
# No .git in the build context, so uv-dynamic-versioning can't derive the version
# from tags; supply it explicitly. Defaults to 0.0.0 if API_VERSION isn't passed.
ARG API_VERSION=0.0.0
RUN UV_DYNAMIC_VERSIONING_BYPASS=${API_VERSION} pip install $PIP_FLAGS --no-deps .
RUN wget -q https://raw.githubusercontent.com/vishnubob/wait-for-it/master/wait-for-it.sh && \
  chmod +x wait-for-it.sh && mv wait-for-it.sh /root/.local/bin/

FROM base
ARG BUILDARCH
ENV BUILDARCH=x86_64
COPY --from=builder /root/.local/lib/python3.12/site-packages /root/.local/lib/python3.12/site-packages
COPY --from=builder /root/.local/bin /root/.local/bin
COPY --from=builder /usr/lib/$BUILDARCH-linux-gnu/libsnappy* /usr/lib/$BUILDARCH-linux-gnu/
COPY --from=builder /emmet-api /emmet-api
WORKDIR /emmet-api
ARG VERSION
ENV PATH=/root/.local/bin:$PATH \
  PYTHONUNBUFFERED=1 \
  FLASK_APP=emmet-api \
  FLASK_ENV=production \
  PORT=10001 \
  NUM_WORKERS=4 \
  RELOAD="" \
  MAX_REQUESTS=0 \
  MAX_REQUESTS_JITTER=0 \
  DD_TRACE_HOST=localhost:8126 \
  DD_SERVICE=next-gen-api \
  DD_ENV=prod \
  DD_VERSION=$VERSION \
  DD_PROFILING_ENABLED=true \
  DD_LOGS_INJECTION=true \
  DD_TRACE_SAMPLE_RATE=1

COPY app.py .
COPY material_resources.py .
COPY molecule_resources.py .
COPY start.sh .
COPY healthcheck.sh .
COPY gunicorn.conf.py .
COPY mp_logging mp_logging
RUN chmod +x start.sh healthcheck.sh

LABEL com.datadoghq.ad.logs='[{"source": "mp-backend", "service": "next-gen-api"}]'

EXPOSE 10001 20001
CMD ./start.sh

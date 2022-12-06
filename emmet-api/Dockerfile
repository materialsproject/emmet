FROM materialsproject/devops:python-3.915.1 as base

FROM base as builder
RUN apt-get update && apt-get install -y --no-install-recommends gcc git g++ cmake make libsnappy-dev wget && apt-get clean
ENV PATH /root/.local/bin:$PATH
WORKDIR /emmet-api
ENV PIP_FLAGS "--user --no-cache-dir --compile"
COPY requirements/deployment.txt ./requirements.txt
RUN pip install $PIP_FLAGS --upgrade pip pip-tools setuptools-scm && \
    pip-sync requirements.txt --pip-args "$PIP_FLAGS"

COPY emmet emmet
COPY setup.py .
ARG API_VERSION
RUN SETUPTOOLS_SCM_PRETEND_VERSION=${API_VERSION} pip install $PIP_FLAGS --no-deps .
RUN wget -q https://raw.githubusercontent.com/vishnubob/wait-for-it/master/wait-for-it.sh && \
    chmod +x wait-for-it.sh && mv wait-for-it.sh /root/.local/bin/

FROM base
COPY --from=builder /root/.local/lib/python3.9/site-packages /root/.local/lib/python3.9/site-packages
COPY --from=builder /root/.local/bin /root/.local/bin
COPY --from=builder /usr/lib/x86_64-linux-gnu/libsnappy* /usr/lib/x86_64-linux-gnu/
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
    MAX_REQUESTS=100000 \
    MAX_REQUESTS_JITTER=10000 \
    DD_TRACE_HOST=localhost:8126 \
    DD_SERVICE=next-gen-api \
    DD_ENV=prod \
    DD_VERSION=$VERSION

COPY app.py .
COPY start.sh .
RUN chmod +x start.sh

LABEL com.datadoghq.ad.logs='[{"source": "gunicorn", "service": "next-gen-api"}]'

EXPOSE 10001 20001
CMD wait-for-it.sh $DD_TRACE_HOST -q -s -t 60 -- ./start.sh

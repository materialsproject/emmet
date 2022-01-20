FROM materialsproject/devops:python-3.97.11 as base

FROM base as builder
RUN apt-get update && apt-get install -y --no-install-recommends gcc git g++ cmake make libsnappy-dev wget && apt-get clean
ENV PATH /root/.local/bin:$PATH
WORKDIR /emmet-api
ENV PIP_FLAGS "--user --no-cache-dir --compile"
COPY requirements.txt ./
RUN pip install $PIP_FLAGS -r requirements.txt && pip install $PIP_FLAGS setuptools-scm

COPY emmet emmet
COPY _version.py .
COPY setup.py .
RUN pip install $PIP_FLAGS -e .[server]
RUN wget -q https://raw.githubusercontent.com/vishnubob/wait-for-it/master/wait-for-it.sh && \
    chmod +x wait-for-it.sh && mv wait-for-it.sh /root/.local/bin/

FROM base
COPY --from=builder /root/.local/lib/python3.9/site-packages /root/.local/lib/python3.9/site-packages
COPY --from=builder /root/.local/bin /root/.local/bin
COPY --from=builder /usr/lib/x86_64-linux-gnu/libsnappy* /usr/lib/x86_64-linux-gnu/
COPY --from=builder /emmet-api /emmet-api
WORKDIR /emmet-api
ENV PATH=/root/.local/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    FLASK_APP=emmet-api \
    FLASK_ENV=production \
    PORT=5001 \
    NUM_WORKERS=4 \
    RELOAD="" \
    MAX_REQUESTS=100000 \
    MAX_REQUESTS_JITTER=10000 \
    DD_TRACE_HOST=localhost:8126

COPY app.py .
COPY gunicorn.conf.py .
COPY start.sh .

EXPOSE 5001
CMD wait-for-it.sh $DD_TRACE_HOST -s -t 60 -- ./start.sh

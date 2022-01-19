FROM materialsproject/devops:python-3.97.11 as base

FROM base as builder
RUN apt-get update && apt-get install -y --no-install-recommends gcc git g++ cmake make libsnappy-dev && apt-get clean
ENV PATH /root/.local/bin:$PATH
WORKDIR /emmet-api
ENV PIP_FLAGS "--user --no-cache-dir --compile"
COPY emmet-api/requirements.txt ./
RUN pip install $PIP_FLAGS -r requirements.txt && pip install $PIP_FLAGS setuptools-scm

COPY emmet-api/emmet emmet
COPY emmet-api/_version.py .
COPY emmet-api/app.py .
COPY emmet-api/setup.py .
RUN pip install $PIP_FLAGS -e .[server]

FROM base
COPY --from=builder /root/.local/lib/python3.9/site-packages /root/.local/lib/python3.9/site-packages
COPY --from=builder /root/.local/bin /root/.local/bin
COPY --from=builder /usr/lib/x86_64-linux-gnu/libsnappy* /usr/lib/x86_64-linux-gnu/
COPY --from=builder /emmet-api /emmet-api
WORKDIR /emmet-api
ENV PATH=/root/.local/bin:$PATH
ENV PYTHONUNBUFFERED 1
ENV FLASK_APP emmet-api
ENV FLASK_ENV production
ENV PORT 5001
ENV NUM_WORKERS 4
ENV RELOAD ""

EXPOSE 5001
CMD gunicorn -b 0.0.0.0:$PORT -k uvicorn.workers.UvicornWorker -w $NUM_WORKERS --log-level debug --access-logfile - $RELOAD app:app

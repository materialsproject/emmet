ARG PYVER
FROM python:${PYVER}

ARG PYVER
ENV PYVER ${PYVER}
RUN apt-get update -y && apt-get install -y openbabel libopenbabel-dev swig && \
    ln -s /usr/include/openbabel3 /usr/local/include/openbabel3

ARG PACKAGE
ENV PACKAGE ${PACKAGE}
RUN echo ${PYVER}
COPY ${PACKAGE}/requirements/ubuntu-latest_py${PYVER}_extras.txt ./requirements.txt

RUN python3 -m pip install --upgrade pip pip-tools && \
    python3 -m piptools sync --user requirements.txt

COPY ${PACKAGE} ${PACKAGE}

ARG API_VERSION
RUN SETUPTOOLS_SCM_PRETEND_VERSION=${API_VERSION} python3 -m pip install --user --no-deps -e ${PACKAGE}

RUN mkdir tests
COPY tests/conftest.py tests/
COPY tests/test_files tests/test_files
COPY tests/${PACKAGE} tests/${PACKAGE}
CMD python3 -m pytest tests/${PACKAGE}

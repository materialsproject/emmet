"""Retrieve CIF and metadata from the ICSD API.

This module is based on
    https://github.com/lrcfmd/ICSDClient/
"""

from __future__ import annotations

import logging
import multiprocessing
import os
import re
from time import time
from typing import TYPE_CHECKING, Self

import numpy as np
import requests
from pydantic import BaseModel, Field, PrivateAttr
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from emmet.core.connectors.icsd.enums import (
    IcsdAdvancedSearchKeys,
    IcsdDataFields,
    IcsdSubset,
)
from emmet.core.connectors.icsd.schemas import IcsdPropertyDoc
from emmet.core.connectors.icsd.settings import IcsdClientSettings

if TYPE_CHECKING:
    from typing import Any

SETTINGS = IcsdClientSettings()

# ICSD tokens expire in one hour
_ICSD_TOKEN_TIMEOUT = 3600

logger = logging.getLogger(__name__)


class IcsdClient(BaseModel):
    """Query data via the ICSD API."""

    username: str = Field(SETTINGS.USERNAME)
    password: str = Field(SETTINGS.PASSWORD)

    max_retries: int = Field(SETTINGS.MAX_RETRIES)
    timeout: float = Field(SETTINGS.TIMEOUT)
    max_batch_size: int = Field(SETTINGS.MAX_BATCH_SIZE)

    use_document_model: bool = Field(True)
    num_parallel_requests: int | None = Field(None)

    _auth_token: str | None = PrivateAttr(None)
    _session_start_time: float | None = PrivateAttr(None)
    _session: requests.Session | None = PrivateAttr(None)

    @property
    def _is_windows(self) -> bool:
        return os.name == "nt"

    def refresh_session(self, force: bool = False) -> None:
        if self._session_start_time is None:
            self._session_start_time = time()

        if (
            self._auth_token is None
            or ((time() - self._session_start_time) > 0.98 * _ICSD_TOKEN_TIMEOUT)
            or force
        ):
            if self._session:
                self.logout()
            self._session_start_time = time()
            self.login()

    def login(self) -> None:

        response = requests.post(
            "https://icsd.fiz-karlsruhe.de/ws/auth/login",
            headers={
                "accept": "text/plain",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={
                "loginid": self.username,
                "password": self.password,
            },
        )
        if response.status_code == 200:
            self._auth_token = response.headers["ICSD-Auth-Token"]
            if self._auth_token is None:
                raise ValueError(
                    f"{self.__module__}.{self.__class__.__name__} "
                    f"failed to fetch auth token: {response.content}"
                )
        else:
            raise ValueError(
                f"{self.__module__}.{self.__class__.__name__} "
                "failed to fetch auth token with status code "
                f"{response.status_code}: {response.content!r}"
            )

        self._session = requests.Session()
        self._session.headers = {"ICSD-Auth-Token": self._auth_token}
        retry = Retry(
            total=self.max_retries,
            read=self.max_retries,
            connect=self.max_retries,
            respect_retry_after_header=True,
            status_forcelist=[429, 504, 502],  # rate limiting
            backoff_factor=0.1,
        )
        adapter = HTTPAdapter(max_retries=retry)
        self._session.mount("http://", adapter)
        self._session.mount("https://", adapter)

    def logout(self) -> None:

        if not self._session:
            return

        _ = self._session.get(
            "https://icsd.fiz-karlsruhe.de/ws/auth/logout",
            headers={
                "accept": "text/plain",
            },
            params=[("windowsclient", self._is_windows)],
        )
        self._auth_token = None
        self._session_start_time = None
        self._session.close()
        self._session = None

    def __enter__(self) -> Self:
        self.login()
        return self

    def __exit__(self, *args) -> None:
        self.logout()

    def __del__(self) -> None:
        self.logout()

    def _get(self, *args, **kwargs) -> requests.Response:
        self.refresh_session()
        assert self._session is not None

        params = tuple(
            list(kwargs.pop("params", [])) + [("windowsclient", self._is_windows)]
        )
        resp = self._session.get(*args, **kwargs, params=params)
        if resp.status_code != 200:
            logger.warning(
                f"{self.__module__}.{self.__class__.__name__} "
                "failed to fetch content with status code "
                f"{resp.status_code}: {resp.content!r}"
            )
        return resp

    def _get_cifs(self, collection_codes: str | list[str]) -> dict[int, str]:
        if isinstance(collection_codes, str):
            collection_codes = [collection_codes]

        if len(collection_codes) == 1:
            url = f"https://icsd.fiz-karlsruhe.de/ws/cif/{collection_codes[0]}"
            params = []
        else:
            url = "https://icsd.fiz-karlsruhe.de/ws/cif/multiple"
            params = [("idnum", collection_codes)]

        cif_str = self._get(
            url,
            headers={"accept": "application/cif"},
            params=params,
        ).content.decode()

        return {
            int(match.group(1)): "#(C)" + cif_body
            for cif_body in cif_str.split("\n#(C)")[1:]
            if (match := re.search(r"_database_code_ICSD ([0-9]+)", cif_body))
        }

    def _search(
        self,
        indices: list[str],
        properties: list[str | IcsdDataFields] | None = None,
        include_cif: bool = False,
        include_metadata: bool = False,
        _data: list | None = None,
    ) -> list[dict[str, Any]]:

        self.refresh_session(force=True)
        search_props = [
            (
                prop.value
                if isinstance(prop, IcsdDataFields)
                else IcsdDataFields(prop).value
            )
            for prop in (properties or list(IcsdDataFields))
        ]

        if len(indices) > self.max_batch_size:
            batched_ids: list[list[str]] = [
                v.tolist()
                for v in np.array_split(
                    indices, np.ceil(len(indices) / self.max_batch_size)
                )
            ]

            data = []
            for i, batch in enumerate(batched_ids):
                data.extend(
                    self._search(
                        batch,
                        properties=search_props,
                        include_cif=include_cif,
                        include_metadata=include_metadata,
                        _data=_data,
                    )
                )
            return data

        if not include_cif and not include_metadata:
            return [{"icsd_internal_id": int(idx) for idx in indices}]

        if include_metadata:
            if "CollectionCode" not in search_props:
                search_props.append("CollectionCode")

            response = self._get(
                "https://icsd.fiz-karlsruhe.de/ws/csv",
                headers={
                    "accept": "application/csv",
                },
                params=(
                    ("idnum", tuple(indices)),
                    ("listSelection", search_props),
                ),
            )

            data = []
            if response.status_code == 200:
                csv_data = [
                    row.split("\t") for row in response.content.decode().splitlines()
                ]
                columns = csv_data[0][:-1]

                data += [
                    {IcsdDataFields[k].value: row[i] for i, k in enumerate(columns)}
                    for row in csv_data[1:]
                ]
            else:
                if "Authentication not successful" in response.content:
                    raise ValueError(
                        "Failed to authenticate ICSD client. Please check your credentials"
                    )
                logger.warning(
                    f"{self.__module__}.{self.__class__.__name__} "
                    "csv search failed with status code "
                    f"{response.status_code}: {response.content!r}"
                )

        if include_cif:
            cifs = self._get_cifs(indices)
            if include_metadata:
                for i, doc in enumerate(data):
                    data[i]["cif"] = cifs.get(int(doc["collection_code"]))
            else:
                data = [{"collection_code": cc, "cif": cif} for cc, cif in cifs.items()]

        if _data:
            _data.extend(data)
        return data

    def search(
        self,
        subset: IcsdSubset | str | None = None,
        properties: list[str | IcsdDataFields] | None = None,
        include_cif: bool = False,
        include_metadata: bool = False,
        **kwargs,
    ) -> list:

        query_vars = []
        for k in IcsdAdvancedSearchKeys:
            if (v := kwargs.get(k.value)) is not None or (
                v := kwargs.get(k.name) is not None
            ):
                if isinstance(v, tuple):
                    v = f"{v[0]}-{v[1]}"
                elif isinstance(v, list):
                    v = ",".join(v)
                query_vars.append(f"{k.name.lower()} : {v}")
        query_str = " and ".join(query_vars)

        params = [("query", query_str)]
        if subset:
            params.append(("content type", IcsdSubset(subset).name))

        response = self._get(
            "https://icsd.fiz-karlsruhe.de/ws/search/expert",
            headers={
                "accept": "application/xml",
            },
            params=params,
        )

        idxs: list[str] = []
        if matches := re.match(".*<idnums>(.*)</idnums>.*", response.content.decode()):
            idxs.extend(list(matches.groups())[0].split())

        if self.num_parallel_requests and len(idxs) > self.num_parallel_requests:
            batched_idxs = np.array_split(idxs, self.num_parallel_requests)

            manager = multiprocessing.Manager()
            procs = []
            res = manager.list()
            for iproc in range(self.num_parallel_requests):
                proc = multiprocessing.Process(
                    target=self._search,
                    args=(batched_idxs[iproc].tolist(),),
                    kwargs={
                        "properties": properties,
                        "include_cif": include_cif,
                        "include_metadata": include_metadata,
                        "_data": res,
                    },
                )
                proc.start()
                procs.append(proc)

            for proc in procs:
                proc.join()
            return list(res)

        data = self._search(
            idxs,
            properties=properties,
            include_cif=include_cif,
            include_metadata=include_metadata,
        )
        if subset:
            for i in range(len(data)):
                data[i]["subset"] = subset

        if self.use_document_model:
            data = [IcsdPropertyDoc(**props) for props in data]
        return data

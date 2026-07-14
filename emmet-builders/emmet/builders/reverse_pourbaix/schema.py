"""Constants defining the reverse-Pourbaix data schema.

Single source of truth for everything that has to stay in sync between
the downloader and the web app:

- The (pH, V) grid (must match ``ReversePourbaixDiagramComponent._snap_to_grid``)
- Any(filter_solids, ion_concentration) combinations
- The parquet column dtypes and the partitioning scheme
- ``SCHEMA_VERSION`` for compatibility checking at load time

If you ever change the grid, the conc options, or the column set, bump
``SCHEMA_VERSION``.
"""

from __future__ import annotations

import numpy as np
import pyarrow as pa

SCHEMA_VERSION = "2.0.0"

# (pH, V) grid. Must match ReversePourbaixDiagramComponent._snap_to_grid:
#   pH snaps to integers 0..14, V snaps to half-integers in [-2, 2].
PH_VALUES: np.ndarray = np.arange(15, dtype=np.int8)
V_VALUES: np.ndarray = np.linspace(-2.0, 2.0, 9, dtype=np.float32)

# Define these options, optional, now only kept defaults
FILTER_SOLIDS_OPTIONS: tuple[bool, ...] = (True,)
ION_CONCENTRATION_OPTIONS: tuple[float, ...] = (1e-6,)

# Convenience handles for the single-combo build.
DEFAULT_FILTER_SOLIDS: bool = FILTER_SOLIDS_OPTIONS[0]
DEFAULT_ION_CONCENTRATION: float = ION_CONCENTRATION_OPTIONS[0]

# Parquet schema. Decomposition energy is the only payload; mp_id +
# (filter_solids, ion_concentration, pH, V) is the natural composite key.
PARQUET_SCHEMA = pa.schema(
    [
        pa.field("mp_id", pa.string(), nullable=False),
        pa.field("filter_solids", pa.bool_(), nullable=False),
        pa.field("ion_concentration", pa.float64(), nullable=False),
        pa.field("pH", pa.int8(), nullable=False),
        pa.field("V", pa.float32(), nullable=False),
        pa.field("decomposition_energy", pa.float32(), nullable=False),
    ],
    metadata={
        "schema_version": SCHEMA_VERSION,
        "ph_grid": ",".join(str(p) for p in PH_VALUES.tolist()),
        "v_grid": ",".join(str(v) for v in V_VALUES.tolist()),
    },
)

PARTITION_COLS: tuple[str, ...] = ("filter_solids", "ion_concentration")

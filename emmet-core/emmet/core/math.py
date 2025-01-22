"""Define types used for array-like data."""

Vector3D = tuple[float, float, float]
"""Real space vector."""

Matrix3D = tuple[Vector3D, Vector3D, Vector3D]
"""Real space Matrix."""

Vector6D = tuple[float, float, float, float, float, float]
"""6D Voigt matrix component."""

MatrixVoigt = tuple[Vector6D, Vector6D, Vector6D, Vector6D, Vector6D, Vector6D]
""""Voigt representation of a 3x3x3x3 tensor."""

Tensor3R = list[list[list[float]]]
"""Generic tensor of rank 3."""

Tensor4R = list[list[list[list[float]]]]
"""Generic tensor of rank 4."""

ListVector3D = list[float]
"""Real space vector as list."""

ListMatrix3D = list[ListVector3D]
"""Real space Matrix as list."""

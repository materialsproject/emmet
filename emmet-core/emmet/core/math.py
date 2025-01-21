"""Define types used for array-like data."""
from typing import TypeVar

Vector3D = TypeVar("Vector3D", bound=tuple[float, float, float])
Vector3D.__doc__ = "Real space vector"  # type: ignore

Matrix3D = TypeVar("Matrix3D", bound=tuple[Vector3D, Vector3D, Vector3D])
Matrix3D.__doc__ = "Real space Matrix"  # type: ignore

Vector6D = TypeVar("Vector6D", bound=tuple[float, float, float, float, float, float])
Vector6D.__doc__ = "6D Voigt matrix component"  # type: ignore

MatrixVoigt = TypeVar(
    "MatrixVoigt",
    bound=tuple[Vector6D, Vector6D, Vector6D, Vector6D, Vector6D, Vector6D],
)
MatrixVoigt.__doc__ = "Voigt representation of a 3x3x3x3 tensor"  # type: ignore

Tensor3R = TypeVar("Tensor3R", bound=list[list[list[float]]])
Tensor3R.__doc__ = "Generic tensor of rank 3"  # type: ignore

Tensor4R = TypeVar("Tensor4R", bound=list[list[list[list[float]]]])
Tensor4R.__doc__ = "Generic tensor of rank 4"  # type: ignore

ListVector3D = TypeVar("ListVector3D", bound=list[float])
ListVector3D.__doc__ = "Real space vector as list"  # type: ignore

ListMatrix3D = TypeVar("ListMatrix3D", bound=list[ListVector3D])
ListMatrix3D.__doc__ = "Real space Matrix as list"  # type: ignore

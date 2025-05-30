from typing import Tuple, List

Vector3D = Tuple[float, float, float]
Vector3D.__doc__ = "Real space vector"  # type: ignore

Matrix3D = Tuple[Vector3D, Vector3D, Vector3D]
Matrix3D.__doc__ = "Real space Matrix"  # type: ignore

Vector6D = Tuple[float, float, float, float, float, float]
Vector6D.__doc__ = "6D Voigt matrix component"  # type: ignore

MatrixVoigt = Tuple[Vector6D, Vector6D, Vector6D, Vector6D, Vector6D, Vector6D]
Vector6D.__doc__ = "Voigt representation of a 3x3x3x3 tensor"  # type: ignore

Tensor3R = List[List[List[float]]]
Tensor3R.__doc__ = "Generic tensor of rank 3"  # type: ignore

Tensor4R = List[List[List[List[float]]]]
Tensor4R.__doc__ = "Generic tensor of rank 4"  # type: ignore

ListVector3D = List[float]
ListVector3D.__doc__ = "Real space vector as list"  # type: ignore

ListMatrix3D = List[ListVector3D]
ListMatrix3D.__doc__ = "Real space Matrix as list"  # type: ignore

VOIGT_INDICES = [(0, 0), (1, 1), (2, 2), (1, 2), (0, 2), (0, 1)]


def matrix_3x3_to_voigt(matrix: Matrix3D) -> list[float]:
    """Convert a 3x3 symmetric matrix to its Voigt vector representation.

    Parameters
    -----------
    matrix : Matrix3D

    Returns
    -----------
    list of float
    """
    return [matrix[idx[0]][idx[1]] for idx in VOIGT_INDICES]

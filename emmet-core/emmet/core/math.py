Vector3D = tuple[float, float, float]

Matrix3D = tuple[Vector3D, Vector3D, Vector3D]

Vector6D = tuple[float, float, float, float, float, float]

MatrixVoigt = tuple[Vector6D, Vector6D, Vector6D, Vector6D, Vector6D, Vector6D]

Tensor3R = list[list[list[float]]]

Tensor4R = list[list[list[list[float]]]]

ListVector3D = list[float]

ListMatrix3D = list[ListVector3D]

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

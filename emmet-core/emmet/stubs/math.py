from typing import Tuple, List

Vector3D = Tuple[float, float, float]
Vector3D.__doc__ = "Real space vector"  # type: ignore

Matrix3D = Tuple[Vector3D, Vector3D, Vector3D]
Matrix3D.__doc__ = "Real space Matrix"  # type: ignore

Tensor3R = List[List[List[float]]]
Tensor3R.__doc__ = "Generic tensor of rank 3"  # type: ignore

Tensor4R = List[List[List[List[float]]]]
Tensor4R.__doc__ = "Generic tensor of rank 4"  # type: ignore

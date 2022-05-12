import numpy as np

from emmet.core.elasticity import ElasticityDoc, is_upper_triangular


def test_is_upper_triangular():

    t = np.eye(3)
    t[0, 1] = 1e-5
    assert is_upper_triangular(t)

    t = np.eye(3)
    t[1, 0] = 1e-5
    assert not is_upper_triangular(t)

    t = np.eye(3)
    t[1, 0] = 1e-5
    assert is_upper_triangular(t, tol=1e-4)

"""
This file defines any arbitrary global variables used in Materials Project
database building and in the website code, to ensure consistency between
different modules and packages.
"""

# Fractional length tolerance for structure matching
LTOL = 0.2

# Site tolerance for structure matching. Defined as the fraction
# of the average free length per atom = ( V / Nsites ) ** (1/3)
STOL = 0.3

# Angle tolerance for structure matching in degrees.
ANGLE_TOL = 5

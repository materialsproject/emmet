def get_free_energy(energy, enthalpy, entropy, temperature=298.15):
    """
    Helper function to calculate Gibbs free energy from electronic energy, enthalpy, and entropy

    :param energy: Electronic energy in Ha
    :param enthalpy: Enthalpy in kcal/mol
    :param entropy: Entropy in cal/mol-K
    :param temperature: Temperature in K. Default is 298.15, 25C

    returns: Free energy in eV

    """
    return energy * 27.2114 + enthalpy * 0.043363 - temperature * entropy * 0.000043363
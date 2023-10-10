import numpy as np
from emmet.core.vasp.calc_types.enums import TaskType


def _check_incar(
    reasons,
    warnings,
    valid_input_set,
    structure,
    task_doc,
    calcs_reversed,
    ionic_steps, 
    nionic_steps,
    parameters,
    incar, 
    potcar,
    vasp_major_version,
    vasp_minor_version,
    vasp_patch_version,
    task_type,
    fft_grid_tolerance,
):
    # note that all changes to `reasons` and `warnings` can be done in-place (and hence there is no need to return those variables after every functionc all). 
    # # Any cases where that is not done is just to make the code more readable. I didn't think that would be necessary here.
    _check_chemical_shift_params(reasons, parameters, valid_input_set)
    _check_dipol_correction_params(reasons, parameters, valid_input_set)
    _check_electronic_params(reasons, parameters, valid_input_set, structure, potcar)
    _check_electronic_projector_params(reasons, parameters, incar, valid_input_set)
    _check_fft_params(reasons, parameters, incar, valid_input_set, structure, fft_grid_tolerance)
    _check_hybrid_functional_params(reasons, parameters, valid_input_set)
    _check_ionic_params(reasons, warnings, parameters, valid_input_set, task_doc, calcs_reversed, nionic_steps, ionic_steps, structure)
    _check_ismear_and_sigma(reasons, warnings, parameters, task_doc, ionic_steps, nionic_steps, structure)
    _check_lmaxmix_and_lmaxtau(reasons, warnings, parameters, incar, valid_input_set, structure, task_type)
    _check_magnetism_params(reasons, parameters, valid_input_set)
    _check_misc_params(reasons, warnings, parameters, incar, valid_input_set, calcs_reversed, vasp_major_version, vasp_minor_version, structure)
    _check_precision_params(reasons, parameters, valid_input_set)
    _check_startup_params(reasons, parameters, incar, valid_input_set)
    _check_symmetry_params(reasons, parameters, valid_input_set)
    _check_u_params(reasons, incar, parameters, valid_input_set)
    _check_write_params(reasons, parameters, valid_input_set)
   
    return reasons

def _get_default_nbands(structure, parameters, nelect):
    """
    This method is copied from the `estimate_nbands` function in pymatgen.io.vasp.sets.py.
    The only noteworthy changes (should) be that there is no reliance on the user setting
    up the psp_resources for pymatgen.
    """
    nions = len(structure.sites)
    
    if parameters.get("ISPIN", "1") == 1:
        nmag = 0
    else:
        nmag = sum(parameters.get("MAGMOM",[0]))
        nmag = np.floor((nmag+1)/2)
        
    possible_val_1 = np.floor((nelect+2)/2) + max(np.floor(nions/2),3)
    possible_val_2 = np.floor(nelect*0.6)
    
    default_nbands = max(possible_val_1, possible_val_2) + nmag
    
    if "LNONCOLLINEAR" in parameters.keys():
        if parameters["LNONCOLLINEAR"] == True:
            default_nbands = default_nbands * 2
    
    if "NPAR" in parameters.keys():
        npar = parameters["NPAR"]
        default_nbands = (np.floor((default_nbands+npar-1)/npar))*npar
    
    return int(default_nbands)


def _get_default_nelect(structure, valid_input_set, potcar = None):
    # for parsing raw calculation files or for users without the VASP pseudopotentials set up in the pymatgen `psp_resources` directory
    if potcar != None:
        zval_dict = {p.symbol.split("_")[0]: p.zval for p in potcar} # num of electrons each species should have according to the POTCAR  
                    # change something like "Fe_pv" to just "Fe" for easier matching of species
        default_nelect = 0
        for site in structure.sites:
            default_nelect += zval_dict[site.species_string]
    # else try using functions that require the `psp_resources` directory to be set up for pymatgen.
    else:
        default_nelect = valid_input_set.nelect
    
    return int(default_nelect)
    

def _get_valid_ismears_and_sigma(parameters, bandgap, nionic_steps):
    
    extra_comments_for_ismear_and_sigma = f"This is flagged as incorrect because this calculation had a bandgap of {round(bandgap,3)}"

    if bandgap > 1e-4: # value taken from https://github.com/materialsproject/pymatgen/blob/1f98fa21258837ac174105e00e7ac8563e119ef0/pymatgen/io/vasp/sets.py#L969
        valid_ismears = [-5,0]
        valid_sigma = 0.05
    else:
        valid_ismears = [0,1,2]
        cur_nsw = parameters.get("NSW", 0)
        if cur_nsw == 0:
            valid_ismears.append(-5) # ISMEAR = -5 is valid for metals *only* when doing static calc
            extra_comments_for_ismear_and_sigma += " and is a static calculation"
        else:
            extra_comments_for_ismear_and_sigma += " and is a non-static calculation"
        valid_sigma = 0.2
    extra_comments_for_ismear_and_sigma += "."
    
    return valid_ismears, valid_sigma, extra_comments_for_ismear_and_sigma


def _check_chemical_shift_params(reasons, parameters, valid_input_set):
    # LCHIMAG.
    default_lchimag = False
    valid_lchimag = valid_input_set.incar.get("LCHIMAG", default_lchimag)
    _check_required_params(reasons, parameters, "LCHIMAG", default_lchimag, valid_lchimag)
    
    # LNMR_SYM_RED.
    default_lnmr_sym_red = False
    valid_lnmr_sym_red = valid_input_set.incar.get("LNMR_SYM_RED", default_lnmr_sym_red)
    _check_required_params(reasons, parameters, "LNMR_SYM_RED", default_lnmr_sym_red, valid_lnmr_sym_red)
    

def _check_dipol_correction_params(reasons, parameters, valid_input_set):
    # LDIPOL.
    default_ldipol = False
    valid_ldipol = valid_input_set.incar.get("LDIPOL", default_ldipol)
    _check_required_params(reasons, parameters, "LDIPOL", default_ldipol, valid_ldipol)
    
    # LMONO.
    default_lmono = False
    valid_lmono = valid_input_set.incar.get("LMONO", default_lmono)
    _check_required_params(reasons, parameters, "LMONO", default_lmono, valid_lmono)
    
    # IDIPOL.
    default_idipol = 0
    valid_idipol = valid_input_set.incar.get("IDIPOL", default_idipol)
    _check_required_params(reasons, parameters, "IDIPOL", default_idipol, valid_idipol)
    
    # EPSILON.
    default_epsilon = 1.0
    valid_epsilon = valid_input_set.incar.get("EPSILON", default_epsilon)
    _check_required_params(reasons, parameters, "EPSILON", default_epsilon, valid_epsilon)

    # EFIELD.
    default_efield = 0.0
    valid_efield = valid_input_set.incar.get("EFIELD", default_efield)
    _check_required_params(reasons, parameters, "EFIELD", default_efield, valid_efield)


def _check_electronic_params(reasons, parameters, valid_input_set, structure, potcar = None):

    # EDIFF. Should be the same or smaller than in valid_input_set
    valid_ediff = valid_input_set.incar.get("EDIFF", 1e-4)
    _check_relative_params(reasons, parameters, "EDIFF", 1e-4, valid_ediff, "less than or equal to")
    
    # ENCUT. Should be the same or greater than in valid_input_set, as this can affect energies & other results.
    # *** Note: "ENCUT" is not actually detected by the `Vasprun.parameters` object from pymatgen.io.vasp.outputs.
    #           Rather, the ENMAX tag in the `Vasprun.parameters` object contains the relevant value for ENCUT.
    cur_encut = parameters.get("ENMAX", 0)
    valid_encut = valid_input_set.incar.get("ENCUT", np.inf)
    _check_relative_params(reasons, parameters, "ENMAX", 0, valid_encut, "greater than or equal to")
    
    # ENINI. Only check for IALGO = 48 / ALGO = VeryFast, as this is the only algo that uses this tag.
    if parameters.get("IALGO", 38) == 48:
        _check_relative_params(reasons, parameters, "ENINI", 0, valid_encut, "greater than or equal to")
        
    # ENAUG. Should only be checked for calculations where the relevant MP input set specifies ENAUG. 
    # In that case, ENAUG should be the same or greater than in valid_input_set.
    if "ENAUG" in valid_input_set.incar.keys():
        cur_enaug = parameters.get("ENAUG", 0)
        valid_enaug = valid_input_set.incar.get("ENAUG", np.inf)
        _check_relative_params(reasons, parameters, "ENAUG", 0, valid_enaug, "greater than or equal to")
    
    # IALGO.
    valid_ialgos = [38, 58, 68, 90] # TODO: figure out if 'normal' algos every really affect results other than convergence 
    _check_allowed_params(reasons, parameters, "IALGO", 38, valid_ialgos)
    
    # NELECT.
    default_nelect = _get_default_nelect(structure, valid_input_set, potcar = potcar)
    _check_required_params(reasons, parameters, "NELECT", default_nelect, default_nelect)
    
    # NBANDS.
    min_nbands = int(np.ceil(default_nelect/2) + 1)
    default_nbands = _get_default_nbands(structure, parameters, default_nelect)
    # check for too many bands (can lead to unphysical electronic structures, see https://github.com/materialsproject/custodian/issues/224 for more context
    too_many_bands_msg = "Too many bands can lead to unphysical electronic structure (see https://github.com/materialsproject/custodian/issues/224 for more context.)"
    _check_relative_params(reasons, parameters, "NBANDS", default_nbands, 4*default_nbands, "less than or equal to", extra_comments_upon_failure=too_many_bands_msg)
    # check for too few bands (leads to degenerate energies)
    _check_relative_params(reasons, parameters, "NBANDS", default_nbands, min_nbands, "greater than or equal to")
    

def _check_electronic_projector_params(reasons, parameters, incar, valid_input_set):
    # LREAL. Should be Auto or False (consistent with MP input sets).
    # Do NOT use the value for LREAL from the `Vasprun.parameters` object, as VASP changes these values automatically.
    # Rather, check the LREAL value in the `Vasprun.incar` object.
    if str(valid_input_set.incar.get("LREAL")).upper() in ["AUTO", "A"]:
        valid_lreals = ["FALSE", "AUTO", "A"]
    elif str(valid_input_set.incar.get("LREAL")).upper() in ["FALSE"]:
        valid_lreals = ["FALSE"]
        
    cur_lreal = str(incar.get("LREAL", "False")).upper()
    if cur_lreal not in valid_lreals:
        reasons.append(f"INPUT SETTINGS --> LREAL: is set to {cur_lreal}, but should be one of {valid_lreals}.")

    # # # LREAL. As per VASP warnings, LREAL should only be `False` for smaller structures.
    # # # Do NOT use the value for LREAL from the `Vasprun.parameters` object, as VASP changes these values automatically.
    # # # Rather, check the LREAL value in the `Vasprun.incar` object.
    # # # For larger structures, LREAL can be `False` or `Auto`
    # # if len(structure) < 16:
    # #     valid_lreals = ["FALSE"]
    # # if len(structure) >= 16:
    # #     valid_lreals = ["FALSE", "AUTO", "A"]
    # # # VASP actually changes the value of LREAL the second time it is printed to vasprun.xml. Hence, we check the INCAR instead.
    # # cur_lreal = str(incar.get("LREAL", "False")).upper()
    # # if cur_lreal not in valid_lreals:
    # #     reasons.append(f"INPUT SETTINGS --> LREAL: is set to {cur_lreal}, but should be one of {valid_lreals}.")
        
        
    # LMAXPAW.
    default_lmaxpaw = -100
    valid_lmaxpaw = valid_input_set.incar.get("LMAXPAW", default_lmaxpaw)
    _check_required_params(reasons, parameters, "LMAXPAW", default_lmaxpaw, valid_lmaxpaw)
        
    # NLSPLINE. Should be False unless specified by the valid_input_set.
    default_nlspline = False
    valid_nlspline = valid_input_set.incar.get("NLSPLINE", default_nlspline)
    _check_required_params(reasons, parameters, "NLSPLINE", default_nlspline, valid_nlspline)
    

def _check_fft_params(reasons, parameters, incar, valid_input_set, structure, fft_grid_tolerance,):

    # NGX/Y/Z and NGXF/YF/ZF. Not checked if not in INCAR file (as this means the VASP default was used).
    if any(i for i in ["NGX", "NGY", "NGZ", "NGXF", "NGYF", "NGZF"] if i in incar.keys()):

        cur_prec = parameters.get("PREC", "NORMAL").upper()
        cur_encut = parameters.get("ENMAX", np.inf)
        cur_enaug = parameters.get("ENAUG", np.inf)
        
        valid_encut_for_fft_grid_params = max(cur_encut, valid_input_set.incar.get("ENCUT"))
        ([valid_ngx, valid_ngy, valid_ngz], [valid_ngxf, valid_ngyf, valid_ngzf]) = valid_input_set.calculate_ng(custom_encut = valid_encut_for_fft_grid_params)
        valid_ngx = int(valid_ngx * fft_grid_tolerance)
        valid_ngy = int(valid_ngy * fft_grid_tolerance)
        valid_ngz = int(valid_ngz * fft_grid_tolerance)
        valid_ngxf = int(valid_ngxf * fft_grid_tolerance)
        valid_ngyf = int(valid_ngyf * fft_grid_tolerance)
        valid_ngzf = int(valid_ngzf * fft_grid_tolerance)

        extra_comments_for_FFT_grid = "This likely means the number FFT grid points was modified by the user. If not, please create a GitHub issue."
        
        _check_relative_params(reasons, parameters, "NGX", np.inf, valid_ngx, "greater than or equal to", extra_comments_upon_failure = extra_comments_for_FFT_grid)
        _check_relative_params(reasons, parameters, "NGY", np.inf, valid_ngy, "greater than or equal to", extra_comments_upon_failure = extra_comments_for_FFT_grid)
        _check_relative_params(reasons, parameters, "NGZ", np.inf, valid_ngz, "greater than or equal to", extra_comments_upon_failure = extra_comments_for_FFT_grid)
        _check_relative_params(reasons, parameters, "NGXF", np.inf, valid_ngxf, "greater than or equal to", extra_comments_upon_failure = extra_comments_for_FFT_grid)
        _check_relative_params(reasons, parameters, "NGYF", np.inf, valid_ngyf, "greater than or equal to", extra_comments_upon_failure = extra_comments_for_FFT_grid)
        _check_relative_params(reasons, parameters, "NGZF", np.inf, valid_ngzf, "greater than or equal to", extra_comments_upon_failure = extra_comments_for_FFT_grid)

    # ADDGRID.
    default_addgrid = False
    valid_addgrid = valid_input_set.incar.get("ADDGRID", default_addgrid)
    _check_required_params(reasons, parameters, "ADDGRID", default_addgrid, valid_addgrid)


def _check_hybrid_functional_params(reasons, parameters, valid_input_set):
    valid_lhfcalc = valid_input_set.incar.get("LHFCALC", False)
    if valid_lhfcalc:
        default_aexx = 0.25
        default_aggac = 0
        default_aggax = 1.0 - parameters.get("AEXX", default_aexx)
        default_aldax = 1.0 - parameters.get("AEXX", default_aexx)
        default_amggax = 1.0 - parameters.get("AEXX", default_aexx)
    else:
        default_aexx = 0
        default_aggac = 1.0
        default_aggax = 1.0
        default_aldax = 1.0
        default_amggax = 1.0
    
    if valid_lhfcalc and parameters.get("AEXX", default_aexx) == 1:
        default_aldac = 0
        default_amggac = 0
    else:
        default_aldac = 1.0
        default_amggac = 1.0
        
    valid_aexx = valid_input_set.incar.get("AEXX", default_aexx)
    valid_aggac = valid_input_set.incar.get("AGGAC", default_aggac)
    valid_aggax = valid_input_set.incar.get("AGGAX", default_aggax)
    valid_aldac = valid_input_set.incar.get("ALDAC", default_aldac)
    valid_aldax = valid_input_set.incar.get("ALDAX", default_aldax)
    valid_amggac = valid_input_set.incar.get("AMGGAC", default_amggac)
    valid_amggax = valid_input_set.incar.get("AMGGAX", default_amggax)
    
    _check_required_params(reasons, parameters, "AEXX", default_aexx, valid_aexx, allow_close=True)
    _check_required_params(reasons, parameters, "AGGAC", default_aggac, valid_aggac, allow_close=True)
    _check_required_params(reasons, parameters, "AGGAX", default_aggax, valid_aggax, allow_close=True)
    _check_required_params(reasons, parameters, "ALDAC", default_aldac, valid_aldac, allow_close=True)
    _check_required_params(reasons, parameters, "ALDAX", default_aldax, valid_aldax, allow_close=True)
    _check_required_params(reasons, parameters, "AMGGAC", default_amggac, valid_amggac, allow_close=True)
    _check_required_params(reasons, parameters, "AMGGAX", default_amggax, valid_amggax, allow_close=True)
    _check_required_params(reasons, parameters, "LHFCALC", False, valid_lhfcalc)
    

def _check_ionic_params(reasons, warnings, parameters, valid_input_set, task_doc, calcs_reversed, nionic_steps, ionic_steps, structure):
    # IBRION.
    default_ibrion = 0
    if valid_input_set.incar.get("IBRION", default_ibrion) not in [-1, 1, 2]:
        valid_ibrion = valid_input_set.incar.get("IBRION", default_ibrion)
        _check_required_params(reasons, parameters, "IBRION", default_ibrion, valid_ibrion)
    else:
        valid_ibrions = [-1, 1, 2]
        _check_allowed_params(reasons, parameters, "IBRION", default_ibrion, valid_ibrions)
    
    # ISIF. 
    default_isif = 2
    valid_min_isif = 2 ######################################################################################################################################
    _check_relative_params(reasons, parameters, "ISIF", default_isif, valid_min_isif, "greater than or equal to", extra_comments_upon_failure = "ISIF values < 2 do not output the complete stress tensor.")

    # PSTRESS.
    default_pstress = 0.0
    valid_pstress = valid_input_set.incar.get("PSTRESS", default_pstress)
    _check_required_params(reasons, parameters, "PSTRESS", default_pstress, valid_pstress, allow_close=True)

    # POTIM.
    if parameters.get("IBRION", 0) in [1,2,3,5,6]: # POTIM is only used for some IBRION values
        valid_max_potim = 5
        _check_relative_params(reasons, parameters, "POTIM", 0.5, valid_max_potim, "less than or equal to", extra_comments_upon_failure="POTIM being so high will likely lead to erroneous results.")
        # Check for large changes in energy between ionic steps (usually indicates too high POTIM)
        if nionic_steps > 1:
            # Do not use `e_0_energy`, as there is a bug in the vasprun.xml when printing that variable
            # (see https://www.vasp.at/forum/viewtopic.php?t=16942 for more details).
            cur_ionic_step_energies = [ionic_step['e_fr_energy'] for ionic_step in ionic_steps]
            cur_ionic_step_energy_gradient = np.diff(cur_ionic_step_energies)
            cur_max_ionic_step_energy_change_per_atom = max(np.abs(cur_ionic_step_energy_gradient)) / structure.num_sites
            valid_max_energy_change_per_atom = 1  
            if cur_max_ionic_step_energy_change_per_atom > valid_max_energy_change_per_atom:
                reasons.append(f"INPUT SETTINGS --> POTIM: The energy changed by a maximum of {cur_max_ionic_step_energy_change_per_atom} eV/atom "\
                               f"between ionic steps, which is greater than the maximum allowed of {valid_max_energy_change_per_atom} eV/atom. "\
                               f"This indicates that the POTIM is too high.")
    
    # SCALEE.
    default_scalee = 1.0
    valid_scalee = valid_input_set.incar.get("SCALEE", default_scalee)
    _check_required_params(reasons, parameters, "SCALEE", default_scalee, valid_scalee, allow_close=True)

    # EDIFFG.
    # Should be the same or smaller than in valid_input_set. Force-based cutoffs (not in every
    # every MP-compliant input set, but often have comparable or even better results) will also be accepted
    ######## I am **NOT** confident that this should be the final check. Perhaps I need convincing (or perhaps it does indeed need to be changed...)
    ######## TODO:    -somehow identify if a material is a vdW structure, in which case force-convergence should maybe be more strict?
    valid_ediff = valid_input_set.incar.get("EDIFF", 1e-4)
    ediffg_in_input_set = valid_input_set.incar.get("EDIFFG", 10*valid_ediff)  

    if ediffg_in_input_set > 0:
        valid_ediffg_energy = ediffg_in_input_set
        valid_ediffg_force = -0.05
    elif ediffg_in_input_set < 0:
        valid_ediffg_energy = 10*valid_ediff
        valid_ediffg_force = ediffg_in_input_set

    if task_doc.output.forces == None:
        is_force_converged = False
        warnings.append("TaskDoc does not contain output forces!")
    else:
        is_force_converged = all([(np.linalg.norm(force_on_atom) <= abs(valid_ediffg_force)) for force_on_atom in task_doc.output.forces])

    if parameters.get("NSW",0) == 0 or nionic_steps <= 1:
        is_converged = is_force_converged ##############################################################################################
    else:
        energy_of_last_step = calcs_reversed[0]['output']['ionic_steps'][-1]['e_0_energy']
        energy_of_second_to_last_step = calcs_reversed[0]['output']['ionic_steps'][-2]['e_0_energy']
        is_energy_converged = abs(energy_of_last_step - energy_of_second_to_last_step) <= valid_ediffg_energy
        is_converged = any([is_energy_converged, is_force_converged])

    if not is_converged:
        reasons.append("CONVERGENCE --> Structure is not converged according to the EDIFFG.")
    

def _check_ismear_and_sigma(reasons, warnings, parameters, task_doc, ionic_steps, nionic_steps, structure):
    bandgap = task_doc.output.bandgap
    
    valid_ismears, valid_sigma, extra_comments_for_ismear_and_sigma = _get_valid_ismears_and_sigma(parameters, bandgap, nionic_steps)

    # ISMEAR.
    _check_allowed_params(reasons, parameters, "ISMEAR", 1, valid_ismears, extra_comments_upon_failure=extra_comments_for_ismear_and_sigma)
    
    # SIGMA.
    ### TODO: improve logic SIGMA reasons given in the case where you have a material that should have been relaxed with ISMEAR in [-5, 0], but used ISMEAR in [1,2].
    ###       Because in such cases, the user wouldn't need to update the SIGMA if they use tetrahedron smearing.
    cur_ismear = parameters.get("ISMEAR", 1)
    if cur_ismear not in [-5, -4, -2]: # SIGMA is not used by the tetrahedron method.
        _check_relative_params(reasons, parameters, "SIGMA", 0.2, valid_sigma, "less than or equal to", extra_comments_upon_failure=extra_comments_for_ismear_and_sigma)
    else:
        warnings.append(f"SIGMA is not being directly checked, as an ISMEAR of {cur_ismear} is being used. However, given the bandgap of {round(bandgap,3)}, the maximum SIGMA used should be {valid_sigma} if using an ISMEAR *not* in [-5, -4, -2].")
    
    # Also check if SIGMA is too large according to the VASP wiki,
    # which occurs when the entropy term in the energy is greater than 1 meV/atom.
    all_eentropies_per_atom = []
    for ionic_step in ionic_steps:
        electronic_steps = ionic_step['electronic_steps']
        # print(electronic_steps)
        for elec_step in electronic_steps:
            if 'eentropy' in elec_step.keys():
                if elec_step['eentropy'] != None:
                    all_eentropies_per_atom.append(elec_step['eentropy'] / structure.num_sites)
    
    cur_max_eentropy_per_atom = max(abs(np.array(all_eentropies_per_atom)))
    valid_max_eentropy_per_atom = 0.001
        
    if cur_max_eentropy_per_atom > valid_max_eentropy_per_atom:
        reasons.append(f"INPUT SETTINGS --> SIGMA: The entropy term (T*S) in the energy was {round(1000 * cur_max_eentropy_per_atom, 3)} meV/atom, which is "\
                       f"greater than the {round(1000 * valid_max_eentropy_per_atom, 1)} meV/atom maximum suggested in the VASP wiki. "\
                       f"Thus, SIGMA should be decreased.")


def _check_lmaxmix_and_lmaxtau(reasons, warnings, parameters, incar, valid_input_set, structure, task_type):
    """
    Check that LMAXMIX and LMAXTAU are above the required value. Also ensure that they are not greater than 6, 
    as that is inadvisable according to the VASP development team (as of writing this in August 2023).
    """
    
    valid_lmaxmix = valid_input_set.incar.get("LMAXMIX", 2)
    valid_lmaxtau = min(valid_lmaxmix + 2, 6)
    lmaxmix_or_lmaxtau_too_high_msg = "From empirical testing, using LMAXMIX and / or LMAXTAU > 6 appears to introduce computational instabilities, " \
        "and is currently inadvisable according to the VASP development team."
    
    # Write out checks manually to better control error message.
    # LMAXMIX.
    cur_lmaxmix = parameters.get("LMAXMIX", 2)
    if (cur_lmaxmix < valid_lmaxmix) or (cur_lmaxmix > 6):
        if valid_lmaxmix < 6:
            lmaxmix_msg = f"INPUT SETTINGS --> LMAXMIX: value is set to {cur_lmaxmix}, but should be between {valid_lmaxmix} and 6."
        else:
            lmaxmix_msg = f"INPUT SETTINGS --> LMAXMIX: value is set to {cur_lmaxmix}, but should be {valid_lmaxmix}."
        # add additional context for invalidation if user set LMAXMIX > 6
        if cur_lmaxmix > 6:
            lmaxmix_msg += lmaxmix_or_lmaxtau_too_high_msg
            
        # Either add to reasons or warnings depending on task type (as this affects NSCF calcs the most)
        # @ Andrew Rosen, is this an adequate check? Or should we somehow also be checking for cases where
        # a previous SCF calc used the wrong LMAXMIX too?
        if task_type == TaskType.NSCF_Uniform or task_type == TaskType.NSCF_Line or parameters.get("ICHARG", 2) >= 10:
            reasons.append(lmaxmix_msg)
        else:
            warnings.append(lmaxmix_msg)
    
    
    # LMAXTAU. Only check for METAGGA calculations
    if incar.get("METAGGA", None) not in ["--", None, "None"]:

        # cannot check LMAXTAU in the `Vasprun.parameters` object, as LMAXTAU is not printed to the parameters. Rather, we must check the INCAR.
        cur_lmaxtau = incar.get("LMAXTAU", 6)
        if (cur_lmaxtau < valid_lmaxtau) or (cur_lmaxtau > 6):
            if valid_lmaxtau < 6:
                lmaxtau_msg = f"INPUT SETTINGS --> LMAXTAU: value is set to {cur_lmaxtau}, but should be between {valid_lmaxtau} and 6."
            else:
                lmaxtau_msg = f"INPUT SETTINGS --> LMAXTAU: value is set to {cur_lmaxtau}, but should be {valid_lmaxtau}."
            # add additional context for invalidation if user set LMAXTAU > 6
            if cur_lmaxtau > 6:
                lmaxtau_msg += lmaxmix_or_lmaxtau_too_high_msg
                
            reasons.append(lmaxtau_msg)
            

def _check_magnetism_params(reasons, parameters, valid_input_set):
    # LNONCOLLINEAR.
    default_lnoncollinear = False
    valid_lnoncollinear = valid_input_set.incar.get("LNONCOLLINEAR", default_lnoncollinear)
    _check_required_params(reasons, parameters, "LNONCOLLINEAR", default_lnoncollinear, valid_lnoncollinear)
    
    # LSORBIT.
    default_lsorbit = False
    valid_lsorbit = valid_input_set.incar.get("LSORBIT", default_lsorbit)
    _check_required_params(reasons, parameters, "LSORBIT", default_lsorbit, valid_lsorbit)
    

def _check_misc_params(reasons, warnings, parameters, incar, valid_input_set, calcs_reversed, vasp_major_version, vasp_minor_version, structure):
    
    # DEPER.
    valid_deper = valid_input_set.incar.get("DEPER", 0.3)
    _check_required_params(reasons, parameters, "DEPER", 0.3, valid_deper, allow_close=True)
    
    # EBREAK.
    valid_ebreak = valid_input_set.incar.get("EBREAK", 0.0)
    _check_required_params(reasons, parameters, "EBREAK", 0.0, valid_ebreak, allow_close=True)
    
    # GGA_COMPAT.
    valid_gga_compat = valid_input_set.incar.get("GGA_COMPAT", True)
    _check_required_params(reasons, parameters, "GGA_COMPAT", True, valid_gga_compat)
    
    # ICORELEVEL.
    valid_icorelevel = valid_input_set.incar.get("ICORELEVEL", 0)
    _check_required_params(reasons, parameters, "ICORELEVEL", 0, valid_icorelevel)
    
    # IMAGES.
    valid_images = valid_input_set.incar.get("IMAGES", 0)
    _check_required_params(reasons, parameters, "IMAGES", 0, valid_images)
    
    # IVDW.
    valid_ivdw = valid_input_set.incar.get("IVDW", 0)
    _check_required_params(reasons, parameters, "IVDW", 0, valid_ivdw)
    
    # LBERRY.
    valid_lberry = valid_input_set.incar.get("LBERRY", False)
    _check_required_params(reasons, parameters, "LBERRY", False, valid_lberry)
    
    # LCALCEPS.
    valid_lcalceps = valid_input_set.incar.get("LCALCEPS", False)
    _check_required_params(reasons, parameters, "LCALCEPS", False, valid_lcalceps)
    
    # LCALCPOL.
    valid_lcalcpol = valid_input_set.incar.get("LCALCPOL", False)
    _check_required_params(reasons, parameters, "LCALCPOL", False, valid_lcalcpol)
    
    # LEPSILON.
    valid_lepsilon = valid_input_set.incar.get("LEPSILON", False)
    _check_required_params(reasons, parameters, "LEPSILON", False, valid_lepsilon)
    
    # LHYPERFINE.
    valid_lhyperfine = valid_input_set.incar.get("LHYPERFINE", False)
    _check_required_params(reasons, parameters, "LHYPERFINE", False, valid_lhyperfine)
    
    # LKPOINTS_OPT.
    valid_lkpoints_opt = valid_input_set.incar.get("LKPOINTS_OPT", False)
    _check_required_params(reasons, parameters, "LKPOINTS_OPT", False, valid_lkpoints_opt)
    
    # LKPROJ.
    valid_lkproj = valid_input_set.incar.get("LKPROJ", False)
    _check_required_params(reasons, parameters, "LKPROJ", False, valid_lkproj)
    
    # LMP2LT.
    valid_lmp2lt = valid_input_set.incar.get("LMP2LT", False)
    _check_required_params(reasons, parameters, "LMP2LT", False, valid_lmp2lt)
    
    # LOCPROJ.
    valid_locproj = valid_input_set.incar.get("LOCPROJ", None)
    _check_required_params(reasons, parameters, "LOCPROJ", None, valid_locproj)
    
    # LRPA.
    valid_lrpa = valid_input_set.incar.get("LRPA", False)
    _check_required_params(reasons, parameters, "LRPA", False, valid_lrpa)
    
    # LSMP2LT.
    valid_lsmp2lt = valid_input_set.incar.get("LSMP2LT", False)
    _check_required_params(reasons, parameters, "LSMP2LT", False, valid_lsmp2lt)
    
    # LSPECTRAL.
    valid_lspectral = valid_input_set.incar.get("LSPECTRAL", False)
    _check_required_params(reasons, parameters, "LSPECTRAL", False, valid_lspectral)
    
    # LSUBROT.
    valid_lsubrot = valid_input_set.incar.get("LSUBROT", False)
    _check_required_params(reasons, parameters, "LSUBROT", False, valid_lsubrot)
    
    # ML_LMLFF.
    valid_ml_lmlff = valid_input_set.incar.get("ML_LMLFF", False)
    _check_required_params(reasons, parameters, "ML_LMLFF", False, valid_ml_lmlff)
    
    # WEIMIN.
    valid_weimin = valid_input_set.incar.get("WEIMIN", 0.001)
    _check_relative_params(reasons, parameters, "WEIMIN", 0.001, valid_weimin, "less than or equal to")

    
    # EFERMI. Only available for VASP >= 6.4. Should not be set to a numerical value, as this may change the number of electrons.
    if (vasp_major_version >= 6) and (vasp_minor_version >= 4):
        # must check EFERMI in the *incar*, as it is saved as a numerical value after VASP guesses it in the vasprun.xml `parameters`
        # (which would always cause this check to fail, even if the user set EFERMI properly in the INCAR).
        cur_efermi = incar.get("EFERMI", "LEGACY")
        allowed_efermis = ["LEGACY", "MIDGAP"]
        if cur_efermi not in allowed_efermis:
            reasons.append(f"INPUT SETTINGS --> EFERMI: should be one of {allowed_efermis}.")
    
    # IWAVPR.
    if "IWAVPR" in incar.keys():
        reasons.append("INPUT SETTINGS --> VASP discourages users from setting the IWAVPR tag (as of July 2023).")
    
    # LASPH.
    valid_lasph = valid_input_set.incar.get("LASPH", True)
    _check_required_params(reasons, parameters, "LASPH", False, valid_lasph)
    
    # LCORR.
    cur_ialgo = parameters.get("IALGO", 38)
    if cur_ialgo != 58:
        _check_required_params(reasons, parameters, "LCORR", True, True)    
    
    # LORBIT.
    cur_ispin = parameters.get("ISPIN", 1)
    # cur_lorbit = incar.get("LORBIT") if "LORBIT" in incar.keys() else parameters.get("LORBIT", None)
    if (cur_ispin == 2) and (len(calcs_reversed[0]["output"]["outcar"]["magnetization"]) != structure.num_sites):
        reasons.append(f"INPUT SETTINGS --> LORBIT: magnetization values were not written to the OUTCAR. This is usually due to LORBIT being set to None or False for calculations with ISPIN=2.")

    if parameters.get("LORBIT", -np.inf) >= 11 and parameters.get("ISYM", 2) and (vasp_major_version < 6):
        warnings.append("For LORBIT >= 11 and ISYM = 2 the partial charge densities are not correctly symmetrized and can result "\
                        "in different charges for symmetrically equivalent partial charge densities. This issue is fixed as of version "\
                        ">=6. See the vasp wiki page for LORBIT for more details.")    
        
    
    # RWIGS.
    if True in (x != -1.0 for x in parameters.get("RWIGS", [-1])): # do not allow RWIGS to be changed, as this affects outputs like the magmom on each atom
        reasons.append(f"INPUT SETTINGS --> RWIGS: should not be set. This is because it will change some outputs like the magmom on each site.")
        
    # VCA.
    if True in (x != 1.0 for x in parameters.get("VCA", [1])): # do not allow VCA calculations
        reasons.append(f"INPUT SETTINGS --> VCA: should not be set")
    

def _check_precision_params(reasons, parameters, valid_input_set):
    # PREC.
    default_prec = "NORMAL"
    if valid_input_set.incar.get("PREC", default_prec).upper() in ["ACCURATE", "HIGH"]:
        valid_precs = ["ACCURATE", "ACCURA", "HIGH"]
    else:
        raise ValueError("Validation code check for PREC tag needs to be updated to account for a new input set!")
    _check_allowed_params(reasons, parameters, "PREC", default_prec, valid_precs)
    
    # ROPT. Should be better than or equal to default for the PREC level. This only matters if projectors are done in real-space.
    # Note that if the user sets LREAL = Auto in their Incar, it will show up as "True" in the `parameters` object (hence we use the `parameters` object)
    if str(parameters.get("LREAL", "FALSE")).upper() == "TRUE": # this only matters if projectors are done in real-space.
        cur_prec = parameters.get("PREC", "Normal").upper()
        if cur_prec == "NORMAL":
            default_ropt = -5e-4
        elif cur_prec in ["ACCURATE", "ACCURA"]:
            default_ropt = -2.5e-4
        elif cur_prec == "LOW":
            default_ropt = -0.01
        elif cur_prec == "MED":
            default_ropt = -0.002
        elif cur_prec == "HIGH":
            default_ropt = -4e-4
            
        cur_ropt = parameters.get("ROPT", [default_ropt])
        if True in (x < default_ropt for x in cur_ropt):
            reasons.append(f"INPUT SETTINGS --> ROPT: value is set to {cur_ropt}, but should be {default_ropt} or stricter.")
    

def _check_startup_params(reasons, parameters, incar, valid_input_set):
    # ICHARG.
    if valid_input_set.incar.get("ICHARG", 2) < 10:
        valid_icharg = 9 # should be <10 (SCF calcs)
        _check_relative_params(reasons, parameters, "ICHARG", 2, valid_icharg, "less than or equal to")
    else:
        valid_icharg = valid_input_set.incar.get("ICHARG")
        _check_required_params(reasons, parameters, "ICHARG", 2, valid_icharg)
    
    # INIWAV.
    default_iniwav = 1
    valid_iniwav = valid_input_set.incar.get("INIWAV", default_iniwav)
    _check_required_params(reasons, parameters, "INIWAV", default_iniwav, valid_iniwav)
    
    # ISTART.
    valid_istarts = [0, 1, 2]
    _check_allowed_params(reasons, parameters, "ISTART", 0, valid_istarts)
    

def _check_symmetry_params(reasons, parameters, valid_input_set):
    # ISYM.
    default_isym = 3 if parameters.get("LHFCALC", False) else 2
    # allow ISYM as good or better than what is specified in the valid_input_set.
    if "ISYM" in valid_input_set.incar.keys():
        if valid_input_set.incar.get("ISYM") == 3:
            valid_isyms = [-1,0,2,3]
        elif valid_input_set.incar.get("ISYM") == 2:
            valid_isyms = [-1,0,2]
        elif valid_input_set.incar.get("ISYM") == 0:
            valid_isyms = [-1,0]
        elif valid_input_set.incar.get("ISYM") == -1:
            valid_isyms = [-1]
    else: # otherwise let ISYM = -1, 0, or 2
        valid_isyms = [-1,0,2]
    _check_allowed_params(reasons, parameters, "ISYM", default_isym, valid_isyms)
    
    # SYMPREC. 
    default_symprec = 1e-5
    valid_symprec = 1e-3 # custodian will set SYMPREC to a maximum of 1e-3 (as of August 2023)
    extra_comments_for_symprec = "If you believe that this SYMPREC value is necessary (perhaps this calculation has a very large cell), please create a GitHub issue and we will consider to admit your calculations."
    _check_relative_params(reasons, parameters, "SYMPREC", default_symprec, valid_symprec, "less than or equal to", extra_comments_upon_failure=extra_comments_for_symprec)


def _check_u_params(reasons, incar, parameters, valid_input_set):
    if parameters.get("LDAU", False) == True:
        valid_ldauu = valid_input_set.incar.get("LDAUU", [])
        cur_ldauu = incar.get("LDAUU", [])
        if cur_ldauu != valid_ldauu:
            reasons.append(f"INPUT SETTINGS --> LDAUU: set to {cur_ldauu}, but should be set to {valid_ldauu}.")

        valid_ldauj = valid_input_set.incar.get("LDAUJ", [])
        cur_ldauj = incar.get("LDAUJ", [])
        if cur_ldauj != valid_ldauj:
            reasons.append(f"INPUT SETTINGS --> LDAUJ: set to {cur_ldauj}, but should be set to {valid_ldauj}.")

        valid_ldaul = valid_input_set.incar.get("LDAUL", [])
        cur_ldaul = incar.get("LDAUL", [])
        if cur_ldaul != valid_ldaul:
            reasons.append(f"INPUT SETTINGS --> LDAUL: set to {cur_ldaul}, but should be set to {valid_ldaul}")

        valid_ldautype = valid_input_set.incar.get("LDAUTYPE", [2])
        if isinstance(valid_ldautype, list):
            valid_ldautype = valid_ldautype[0]
        cur_ldautype = parameters.get("LDAUTYPE", [2])[0]
        if cur_ldautype != valid_ldautype:
            reasons.append(f"INPUT SETTINGS --> LDAUTYPE: set to {cur_ldautype}, but should be set to {valid_ldautype}")


def _check_write_params(reasons, parameters, valid_input_set):
    # NWRITE.
    valid_nwrite = valid_input_set.incar.get("NWRITE", 2) # expect this to almost always default to 2
    extra_comments_for_nwrite = f"NWRITE < {valid_nwrite} does not output all of the results we need."
    _check_relative_params(reasons, parameters, "NWRITE", 2, valid_nwrite, "greater than or equal to", extra_comments_upon_failure=extra_comments_for_nwrite)
    
    # LEFG.
    valid_lefg = valid_input_set.incar.get("LEFG", False)
    _check_required_params(reasons, parameters, "LEFG", False, valid_lefg)    
    
    # LOPTICS.
    valid_loptics = valid_input_set.incar.get("LOPTICS", False)
    _check_required_params(reasons, parameters, "LOPTICS", False, valid_loptics)
    
    
    

def _check_required_params(reasons, parameters, input_tag, default_val, required_val, allow_close=False, extra_comments_upon_failure=""):
    cur_val = parameters.get(input_tag, default_val)

    if allow_close:
        if not np.isclose(cur_val, required_val, rtol=1e-05, atol=1e-05): # need to be careful of this
            msg = f"INPUT SETTINGS --> {input_tag}: set to {cur_val}, but should be {required_val}."
            if extra_comments_upon_failure != "":
                msg += " " + extra_comments_upon_failure
            reasons.append(msg)
    else:
        if cur_val != required_val:
            msg = f"INPUT SETTINGS --> {input_tag}: set to {cur_val}, but should be {required_val}."
            if extra_comments_upon_failure != "":
                msg += " " + extra_comments_upon_failure
            reasons.append(msg)


def _check_allowed_params(reasons, parameters, input_tag, default_val, allowed_vals, extra_comments_upon_failure=""):
    # convert to (uppercase) string if allowed vals are also strings
    if any(isinstance(item,str) for item in allowed_vals):
        cur_val = str(parameters.get(input_tag, default_val)).upper()
    else:
        cur_val = parameters.get(input_tag, default_val)

    if cur_val not in allowed_vals:
        msg = f"INPUT SETTINGS --> {input_tag}: set to {cur_val}, but should be one of {allowed_vals}."
        if extra_comments_upon_failure != "":
            msg += " " + extra_comments_upon_failure
        reasons.append(msg)


def _check_relative_params(reasons, parameters, input_tag, default_val, valid_val, should_be, extra_comments_upon_failure=""):
    cur_val = parameters.get(input_tag, default_val)

    if input_tag == "ENMAX": # change output message for ENMAX / ENCUT to be more clear to users (as they set ENCUT, but this is stored as ENMAX)
        input_tag = "ENCUT"

    if should_be == "less than or equal to":
        if cur_val > valid_val: # check for greater than (opposite of <=)
            msg = f"INPUT SETTINGS --> {input_tag}: set to {cur_val}, but should be less than or equal to {valid_val}."
            if extra_comments_upon_failure != "":
                msg += " " + extra_comments_upon_failure
            reasons.append(msg)
    if should_be == "greater than or equal to":
        if cur_val < valid_val: # check for less than (opposite of >=)
            msg = f"INPUT SETTINGS --> {input_tag}: set to {cur_val}, but should be greater than or equal to {valid_val}."
            if extra_comments_upon_failure != "":
                msg += " " + extra_comments_upon_failure
            reasons.append(msg)
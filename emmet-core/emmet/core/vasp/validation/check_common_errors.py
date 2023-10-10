import numpy as np

def _check_common_errors(
    reasons, 
    warnings, 
    task_doc, 
    calcs_reversed, 
    parameters, 
    incar, 
    structure, 
    valid_max_allowed_scf_gradient, 
    ionic_steps, 
    num_ionic_steps_to_avg_drift_over
):
    # Check for cases where both GGA and METAGGA are set. This should *not* be allowed, as it can erroneously change
    # the outputted energy significantly. See https://github.com/materialsproject/atomate2/issues/453#issuecomment-1699605867
    # for more details.
    if incar.get("GGA", "--") != "--" and str(incar.get("METAGGA", None)).lower() not in ["--", "none"]:
        reasons.append(
            "KNOWN BUG --> GGA and METAGGA should never be specified together, as this can cause major errors in the "
            "outputted energy. See https://github.com/materialsproject/atomate2/issues/453#issuecomment-1699605867 "
            "for more information."
        )


    # check if structure electronically converged
    final_esteps = ionic_steps[-1]["electronic_steps"] if incar.get("ALGO", "Normal").lower() != "chi" else 0
    # In a response function run there is no ionic steps, there is no scf step
    if parameters.get("LEPSILON", False):
        i = 1
        to_check = {"e_wo_entrp", "e_fr_energy", "e_0_energy"}
        while set(final_esteps[i]) == to_check:
            i += 1
        is_converged = (i + 1 != parameters.get("NELM", 60))
    elif len(final_esteps) < parameters.get("NELM", 60):
        is_converged = True
    else:
        is_converged = False
        
    if not is_converged:
        reasons.append(f"CONVERGENCE --> Did not achieve electronic convergence in the final ionic step. NELM should be increased.")
    
    
    # Check if drift force is too large
    try:
        all_drift_forces = calcs_reversed[0]["output"]["outcar"]["drift"]
        if len(all_drift_forces) < num_ionic_steps_to_avg_drift_over:
            drift_forces_to_avg_over = all_drift_forces
        else:
            drift_forces_to_avg_over = all_drift_forces[::-1][: num_ionic_steps_to_avg_drift_over]

        drift_mags_to_avg_over = [np.linalg.norm(drift_forces) for drift_forces in drift_forces_to_avg_over]
        cur_avg_drift_mag = np.average(drift_mags_to_avg_over)
        
        valid_max_drift = 0.05
        if cur_avg_drift_mag > valid_max_drift:
            reasons.append(f"CONVERGENCE --> Excessive drift of {round(cur_avg_drift_mag,4)} eV/A is greater than allowed "\
                           f"value of {valid_max_drift} eV/A.")
    except Exception as e:
        warnings.append("Drift forces not contained in calcs_reversed! Can not check for excessive drift.")
        
        
    # Check for excessively positive final energies (which usually indicates a bad structure)
    valid_max_energy_per_atom = 50
    cur_final_energy_per_atom = task_doc.output.energy_per_atom
    if cur_final_energy_per_atom > valid_max_energy_per_atom:
        reasons.append(f"LARGE POSITIVE FINAL ENERGY --> Final energy is {round(cur_final_energy_per_atom,4)} eV/atom, which is "\
                       f"greater than the maximum allowed value of {valid_max_energy_per_atom} eV/atom.")


    # Check for excessively large final magnetic moments
    ### TODO: make this also work for elements Gd and Eu, which have magmoms >5 in at least one of their pure structures
    valid_max_magmoms = {"Gd": 10, "Eu": 10}
    cur_magmoms = [abs(mag["tot"]) for mag in calcs_reversed[0]["output"]["outcar"]["magnetization"]]
    bad_site_magmom_msgs = []
    if len(cur_magmoms) > 0:
        for site_num in range(0, len(structure)):
            cur_site_ele = structure.sites[site_num].species_string
            cur_site_magmom = cur_magmoms[site_num]
            if cur_site_ele in valid_max_magmoms.keys():
                cur_site_max_allowed_magmom = valid_max_magmoms[cur_site_ele]
            else:
                cur_site_max_allowed_magmom = 5

            if cur_site_magmom > cur_site_max_allowed_magmom:
                bad_site_magmom_msgs.append(
                    f"at least one {cur_site_ele} site with magmom greater than {cur_site_max_allowed_magmom}"
                )
    if len(bad_site_magmom_msgs) > 0:
        msg = f"MAGNETISM --> Final structure contains sites with magnetic moments that are very likely erroneous. This includes: "
        msg = msg + "; ".join(set(bad_site_magmom_msgs)) + "." 
        reasons.append(msg)

        
    # Check for a SCF gradient that is too large (usually indicates unstable calculations)
    # NOTE: do NOT use `e_0_energy`, as there is a bug in the vasprun.xml when printing that variable
    # (see https://www.vasp.at/forum/viewtopic.php?t=16942 for more details).
    skip = abs(parameters.get("NELMDL", -5)) - 1
    energies = [
        d["e_fr_energy"]
        for d in ionic_steps[-1]["electronic_steps"]
    ]
    if len(energies) > skip:
        cur_max_gradient = np.max(np.gradient(energies)[skip:])
        cur_max_gradient_per_atom = cur_max_gradient / structure.num_sites
        if cur_max_gradient_per_atom > valid_max_allowed_scf_gradient:
            warnings.append(f"STABILITY --> The max SCF gradient is {round(cur_max_gradient_per_atom,4)} eV/atom, which is larger than the typical max expected value of {valid_max_allowed_scf_gradient} eV/atom. "\
                           f"This sometimes indicates an unstable calculation.")
    else:
        warnings.append(
            "Not enough electronic steps to compute valid gradient"
            " and compare with max SCF gradient tolerance."
        )
        

    # Check for Am and Po elements. These currently do not have proper elemental entries
    # and will not get treated properly by the thermo builder.
    chemsys = task_doc.chemsys
    if ("Am" in chemsys) or ("Po" in chemsys):
        reasons.append("COMPOSITION --> Your structure contains the elements Am and/or Po, which are not currently being accepted.")

    return reasons
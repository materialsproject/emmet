import numpy as np

def _check_kpoints_kspacing(
    reasons, 
    task_type,
    parameters,
    kpts_tolerance, 
    valid_input_set, 
    calcs_reversed, 
    allow_explicit_kpoint_mesh, 
    allow_kpoint_shifts,
    structure
):
    
    # Check number of kpoints used
    valid_num_kpts = _get_valid_num_kpts(valid_input_set, structure)    
    valid_num_kpts = int(np.floor(valid_num_kpts * kpts_tolerance))    
    cur_kpoints_obj = calcs_reversed[0]['input']['kpoints']
    cur_num_kpts = max(
        cur_kpoints_obj.get("nkpoints", 0),
        np.prod(cur_kpoints_obj.get("kpoints")),
        len(cur_kpoints_obj.get("kpoints"))
    )
    if cur_num_kpts < valid_num_kpts:
        reasons.append(f"INPUT SETTINGS --> KPOINTS or KSPACING: {cur_num_kpts} kpoints were used, but it should have been at least {valid_num_kpts}.")
    
    # check for valid kpoint mesh (which depends on symmetry of the structure)
    cur_kpoint_style = cur_kpoints_obj.get("generation_style").lower()
    is_hexagonal = structure.lattice.is_hexagonal()
    is_face_centered = (structure.get_space_group_info()[0][0] == "F")
    monkhorst_mesh_is_invalid = (is_hexagonal or is_face_centered)
    if cur_kpoint_style == "monkhorst" and monkhorst_mesh_is_invalid:
        if all([x%2 == 1 for x in cur_kpoints_obj.get("kpoints")[0]]): # allow monkhorst with all odd number of subdivs.
            pass
        else:
            reasons.append(f"INPUT SETTINGS --> KPOINTS or KGAMMA: monkhorst-pack kpoint mesh was used with only even subdivisions, but the structure has symmetry that is incompatible with monkhorst-pack meshes.")
    

    # Check for explicit kpoint meshes
    if not allow_explicit_kpoint_mesh:
        if len(cur_kpoints_obj['kpoints']) > 1:
            reasons.append(f"INPUT SETTINGS --> KPOINTS: explicitly defining the kpoint mesh is not currently allowed. Automatic kpoint generation is required.")

    # Check for user shifts
    if not allow_kpoint_shifts:
        if any(shift_val != 0 for shift_val in cur_kpoints_obj['usershift']):
            reasons.append(f"INPUT SETTINGS --> KPOINTS: shifting the kpoint mesh is not currently allowed.") 
    
    return reasons


def _get_valid_num_kpts(valid_input_set, structure):
    # If MP input set specifies KSPACING in the INCAR
    if ("KSPACING" in valid_input_set.incar.keys()) and (valid_input_set.kpoints == None):
        valid_kspacing = valid_input_set.incar.get("KSPACING", 0.5)
        latt_cur_anorm = structure.lattice.abc
        # number of kpoints along each of the three lattice vectors
        n_1 = max(1, np.ceil( (1/latt_cur_anorm[0]) * 2 * np.pi / valid_kspacing) )
        n_2 = max(1, np.ceil( (1/latt_cur_anorm[1]) * 2 * np.pi / valid_kspacing) )
        n_3 = max(1, np.ceil( (1/latt_cur_anorm[2]) * 2 * np.pi / valid_kspacing) )
        valid_num_kpts = n_1 * n_2 * n_3
    # If MP input set specifies a KPOINTS file
    else:
        valid_num_kpts = valid_input_set.kpoints.num_kpts or np.prod(valid_input_set.kpoints.kpts[0])
            
    return int(valid_num_kpts)
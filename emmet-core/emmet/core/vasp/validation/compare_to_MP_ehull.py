from mp_api.client import MPRester
from pymatgen.analysis.phase_diagram import PhaseDiagram, PDEntry
from pymatgen.entries.mixing_scheme import MaterialsProjectDFTMixingScheme
from pymatgen.entries.computed_entries import ComputedStructureEntry


def compare_to_MP_ehull(mp_api_key = None, task_doc = None):

    if mp_api_key == None:
        raise ValueError("Please input your mp API key")

    # get ComputedStructureEntry from taskdoc.
    # The `taskdoc.structure_entry()` does not work directly, as the `entry` field in the taskdoc is None
    entry = task_doc.get_entry(task_doc.calcs_reversed, task_id = "-1")
    entry_dict = entry.as_dict()
    entry_dict['structure'] = task_doc.output.structure
    cur_structure_entry = ComputedStructureEntry.from_dict(entry_dict)
    elements = task_doc.output.structure.composition.to_reduced_dict.keys()

    with MPRester(mp_api_key) as mpr:

        # Obtain GGA, GGA+U, and r2SCAN ComputedStructureEntry objects
        entries = mpr.get_entries_in_chemsys(elements=elements,
                                            compatible_only = True,
                                            additional_criteria={"thermo_types": ["GGA_GGA+U", "R2SCAN"], "is_stable": True}) 
        
        entries.append(cur_structure_entry)
        
        # Apply corrections locally with the mixing scheme
        scheme = MaterialsProjectDFTMixingScheme()
        corrected_entries = scheme.process_entries(entries)
                
        # Construct phase diagram
        pd = PhaseDiagram(corrected_entries)
        cur_corrected_structure_entry = [entry for entry in corrected_entries if entry.entry_id == "-1"][0]
        e_above_hull = pd.get_e_above_hull(cur_corrected_structure_entry)

        return e_above_hull
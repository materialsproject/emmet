import os

from pymatgen.core.structure import Structure
from maggma.builders import MapBuilder

from robocrys import StructureCondenser, StructureDescriber
from robocrys import __version__ as robocrys_version

__author__ = "Alex Ganose"


class RobocrysBuilder(MapBuilder):

    def __init__(self, materials, robocrys, **kwargs):
        """Runs robocrystallographer to get the condensed structure and
        structure description.

        Args:
            materials (Store): Store of materials documents.
            robocrys (Store): Store of condensed structure and
                text structure description.
            **kwargs: Keyword arguments that will get passed to the builder
                super method.
        """
        self.materials = materials
        self.robocrys = robocrys

        self.condenser = StructureCondenser()
        self.describer = StructureDescriber(describe_symmetry_labels=False)

        super().__init__(source=materials, target=robocrys, ufn=self.calc,
                         projection=["structure"], **kwargs)

    def calc(self, item):
        """Calculates robocrystallographer on an item.

        Args:
            item (dict): A dict with a task_id and a structure.

        Returns:
            dict: The robocrystallographer information dict with they keys:

            - ``"condensed_structure"``: The condensed structure dictionary.
            - ``"description"``: The text description.
        """
        self.logger.debug("Running robocrys on {}".format(
            item[self.materials.key]))

        structure = Structure.from_dict(item["structure"])
        doc = {"_robocrys_version": robocrys_version}

        try:
            self.logger.debug("Adding oxidation states for {}".format(
                item[self.materials.key]))
            structure.add_oxidation_state_by_guess(max_sites=-80)
        except ValueError:
            self.logger.warning("Could not add oxidation states for {}".format(
                item[self.materials.key]))

        condensed_structure = self.condenser.condense_structure(structure)
        description = self.describer.describe(condensed_structure)
        doc.update({"condensed_structure": condensed_structure,
                    "description": description})
        
        return doc


class TextToSpeech(MapBuilder):
    def __init__(self, robocrys, robocrys_audio, service_keyfile_path=None, **kwargs):
        """Calls Google Cloud Text-to-Speech API to build MP3 audio for robocrystallographer text descriptions.

        NOTE: This has been tested only informally and is not currently used to build audio on the MP website.
        Rather, the `SpeechSynthesisUtterance` functionality native to modern web browsers is currently used.

        Args:
            robocrys (Store): Store of condensed structure and text structure description.
            robocrys_audio (Store): Store of structure description audio.
            service_keyfile_path (str): file path of the JSON file that contains Google Cloud service account key.
            **kwargs: Keyword arguments that will get passed to the builder super method.
        """
        self.robocrys = robocrys
        self.robocrys_audio = robocrys_audio
        self.service_keyfile_path = service_keyfile_path
        self.kwargs = kwargs

        super().__init__(source=self.robocrys, target=self.robocrys_audio, ufn=self.get_audio,
                         projection=["description"], **kwargs)

    def get_audio(self, item):
        """Fetches audio for robocrystallographer text description.

        Audio content is binary, writable as e.g.
        ```
        with open('output.mp3', 'wb') as out:
           out.write(response.audio_content)
        ```

        Args:
            item (dict): A dict with material_id and description.

        Returns:
            dict: {material_id, last_updated, audio}
        """
        os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = self.service_keyfile_path
        from google.cloud import texttospeech
        client = texttospeech.TextToSpeechClient()
        voice = texttospeech.types.VoiceSelectionParams(language_code='en-US', name='en-US-Standard-E')
        audio_config = texttospeech.types.AudioConfig(audio_encoding=texttospeech.enums.AudioEncoding.MP3)
        synthesis_input = texttospeech.types.SynthesisInput
        inp = synthesis_input(text=item["description"][:1000])
        response = client.synthesize_speech(inp, voice, audio_config)
        item.pop("description")
        item["audio"] = response.audio_content  # binary
        return item

import json
import tiktoken
import ollama
import re
import os

DORIAN = "dorian2b/vera"
AYA_EXP = "aya-expanse"
LLAMA_3_1 = "llama3.1"


# PROMPT TEMPLATES:

LN_TRANSLATION_INSTRUCTIONS = """
Make sure the translation is honest to original content in meaning and implication
Do not paraphrase!,
Output has to be in a single exact json format, like:,
```json
{
    "original": "Japanese text to be translated",
    "translation": "Your English text translation here (No other nested json, just direct string as value to the key!)"
}
```
It should adhere to correct json format!
Now translate all of this into english with above rules in mind:
"""

VN_NSS_JSON_TRANSLATION_INSTRUCTION = """
You will be given a list of jsons in the following format:
```json
{
    "text": [
        "「んなバカな！」",
        "「そんな単純に、セカイが滅びるかッ！」"
    ]
}
You have to return the same json, but the values in "Name" and "text" field 
translated to english, for the above example, this will be the output:
```json
{
    "text": [
        "No way!",
        "The world won't end that easily!"
    ]
}
```
Sometimes, in the "text" field, you will find <RUBY></RUBY> tag(s), like this:
`伝説の初代<RUBY text="エトワール">魔女</RUBY>`
Make sure to keep the tags and translate the text, for example for above, the translated
form will be:
`The legendary first-generation <RUBY text="Etoile">witch</RUBY>`
Now with above rules in mind, translate the following json:
"""

CHECK_GLOSSARY = """
I am going to give you a glossary,
The keys are japanese names, and the nested json structure's 'actualname' key
is the word to be used, and 'gender' gives the gender incase it is necessary
The exact format of the json is like: 
[
    "japanesename1" : {
        "actualname": "English translation of japanesename1 to be used",
        "gender": "Gender of the japanesename1",
    },
    "japanesename2" : {
        "actualname": "English translation of japanesename2 to be used",
        "gender": "Gender of the japanesename2",
    },
...]
Now you will be asked to translate some text with above glossary
While translating the text, wherever one of the japanese name above appears in japanese text
Use the actualname in the translated text as equivalent
If japanese name does not exist in the glossary use your best guess.
Here is the Glossary:
"""

SYSTEM_PROMPT = """
You are a sophisticated and precise japanese to english translator, 
that translates with all the implied nuance when required 
, is specialized in analyzing given japanese text, 
and giving accurate json format output in the precise manner 
the user asks you to.
"""

NOUN_GLOSSARY_CREATION_INSTRUCTIONS = """
Extract all the people's names, nick names and city/town/country/village names, 
then give it's pronounciation in english and the translated 
english name as output in exact json format like:
```json
[
    {
        "japanesename": "the original language name",
        "englishphonetic": "English phonetics for the name",
        "actualname": "English name for the corresponding japanesename"
    },
    {
        "japanesename": "the original language name 1",
        "englishphonetic": "English phonetics for the name 1",
        "actualname": "English name for the corresponding japanesename"
    },
...]
```
Do not add any other comments to the json!
"""

FIX_JSON_PROMPT_TEMPLATE = """
The following json string:

"{}"

Failed to load with the following error:

"{}"

Please check and fix the json string.
"""

class VnTranslator:
    """
    This class is created to take care of Japanese translation for Novels 
    (though with some simple modifications this can be used for any language)

    The class usage flow goes along these lines:
    * Read story summary. (can be further expanded for some context if required)
    * Create glossary using LLM, and save LLM response.
    * Create glossary JSON from saved response and save. [You might want to go through this and fix it a bit]
    * Load the glossary JSON.
    * Read content from input location.
    * Feed to LLM as small pieces, while using Glossary for name consistency. (and perhaps minimal context)
    * Save LLM response(s) to files(s)
    * Go through the response and clean the data, if required.
    """
    def __init__(self, raw_loc, raw_glossary_loc, glossary_loc, raw_translate_loc, refined_translation_loc, summary_file):
        self.raw_loc = raw_loc # Can be any raw readable form path, nss-json folder, ln-txt file, etc
        self.raw_glossary_loc = raw_glossary_loc
        self.glossary_loc = glossary_loc
        self.raw_translate_loc = raw_translate_loc # Can be any raw translation path, nss-json folder, ln-tex file
        self.refined_translation_loc = refined_translation_loc
        self.loaded_glossary = dict()
        self.summary_file = summary_file

    def create_raw_glossary(self):
        """
        Uses the LLM to create a name glossary for consistency during translation.
        """
        with open(self.raw_glossary_loc, 'w', encoding='utf-8') as out_file:
            for chunk in VnTranslator.get_chunks(self.summary_file, tokens_per_chunk=400):
                response = VnTranslator.do_with_text(VnTranslator.get_instruction_prompt(NOUN_GLOSSARY_CREATION_INSTRUCTIONS, chunk), model=LLAMA_3_1)
                out_file.write(response + "\n\n")

        print(f"Glossary creation complete, check {self.raw_glossary_loc}")


    def create_glossary_json(self):
        """
        Converts the raw glossary created to JSON files.
        """
        VnTranslator.extract_json_from_text(self.raw_glossary_loc, self.glossary_loc, "glossary_json_creation_error_logs.txt")
        processed_json_eles = []

        with open(self.glossary_loc, 'r', encoding='utf-8') as file:
            data = json.load(file)

            # To cache already added names.
            names_read = set()

            for ele_list in data:
                for ele in ele_list:
                    # Check if the name was already added from a previous chunk before adding it to final json
                    if ele["japanesename"] not in names_read:
                        if "gender" not in ele:
                            ele["gender"] = None
                        if "ischar" not in ele:
                            ele["ischar"] = False
                        names_read.add(ele["japanesename"])
                        processed_json_eles.append(ele)
        # Dump the JSON to the provided location.
        VnTranslator.dump_json_dic_to_json_file(self.glossary_loc, processed_json_eles)
        

    def load_glossary(self):
        """
        Loads glossary from the specified location to use later.
        """
        with open(self.glossary_loc, 'r', encoding='utf-8') as file: 
            data= json.load(file)
            for ele in data:
                self.loaded_glossary[ele["japanesename"]] = {
                    "actualname" : ele["actualname"],
                    "gender" : ele["gender"],
                    # "is_char" : ele["is_char"]
                }

    def create_raw_translation_vn_nss_json(self):
        """
        This method, reads through nss JSON files in a given folder, translates some part into english
        And paste it at an output location, mirroring the file names.
        """
        failure_log = []

        for root, _, files in os.walk(self.raw_loc):
            for file_name in files:
                file_path = os.path.join(root, file_name)

                print(f"Processing file: {file_path}")
                collected_json = []
                for index, element in enumerate(VnTranslator.read_nss_json_content(file_path)):

                    if element:

                        # Extract relevant portion for translation
                        translation_json = {
                            "text": element["text"]
                        }
                        # Convert into string.
                        str_json_ele = json.dumps(translation_json, ensure_ascii=False, indent=4)
                        # Translate
                        response = VnTranslator.do_with_text(
                            self.get_translate_with_glossary_prompt(str_json_ele, 
                                                                    translation_instruction=VN_NSS_JSON_TRANSLATION_INSTRUCTION)
                        )
                        # Detect Json markdown using regex and extract content.
                        json_block = re.findall(r'```json(.*?)```', response, re.DOTALL)
                        if json_block:
                            # Try to parse the JSON string
                            json_data, failure = VnTranslator.loadJsonWithReTry(file_name, index, json_block[0])

                            if failure:
                                # Log if parsing failed.
                                failure_log.append(failure)
                            else:
                                # Extract the data.
                                json_data["text label"] = element["text label"]
                                json_data["voice tag"] = element["voice tag"]
                                json_data["Name"] = element["Name"]
                                collected_json.append(json_data)
                
                file_json = {
                    "content": collected_json
                }
                # Dumb translated json to given location.
                translated_json_file_path = os.path.join(self.raw_translate_loc, file_name)
                VnTranslator.dump_json_dic_to_json_file(translated_json_file_path, file_json)


    def create_raw_translation_ln(self):
        """
        Raw translation Lightnovel content, which is just raw text.
        """
        with open(self.raw_translate_loc, 'w', encoding='utf-8') as out_file:
            # Convert file into chunks
            for chunk in VnTranslator.get_chunks(self.raw_loc):
                response = VnTranslator.do_with_text(self.get_translate_with_glossary_prompt(chunk))
                # Write translated chunks to a file.
                out_file.write(response + "\n\n")  # Write translated chunk

        print(f"Raw translation complete, check {self.raw_translate_loc}")


    def clean_translation_ln(self):
        """
        INCOMPLETE METHOD.
        Will be later used to process the LLM generated translation content and create 
        mode cohesive data that can be read like a normal chapter.
        """
        cleaned_translation = []
        with open(self.raw_translate_loc, 'r', encoding='utf-8') as file:
            content = file.read()
            translated_block = re.findall(r'"translation":(.*?)}', content, re.DOTALL)

            for block in translated_block:
                print(block)
                # TODO: Further cleaning steps comes here


    def get_translate_with_glossary_prompt(self, chunk, translation_instruction=LN_TRANSLATION_INSTRUCTIONS):
        """
        A simple function, that goes through the input chunk, filters out glossary based on the chunk
        and constructs a prompt along with the filtered glossary, for LLM to translate.
        """
        glossary_to_include = dict()
        for key in self.loaded_glossary.keys():
            if key in chunk:
                glossary_to_include[key] = self.loaded_glossary[key]
        
        glossary_to_include = json.dumps(glossary_to_include, ensure_ascii=False)
        prompt = f"{VnTranslator.get_instruction_prompt(CHECK_GLOSSARY, glossary_to_include)}\n{VnTranslator.get_instruction_prompt(translation_instruction, chunk)}"
        return prompt
    

    @staticmethod
    def dump_json_dic_to_json_file(out_path, json_dic):
        """
        Dumb a dictionary into a JSON file.
        """
        try:
            with open(out_path, 'w', encoding='utf-8') as json_file:
                json.dump(json_dic, json_file, ensure_ascii=False, indent=4)
            print(f"Content saved to {out_path}")
        except Exception as e:
            print(f"Error saving content to {json_dic}: {e}")
    

    @staticmethod
    def extract_json_from_text(input_file, out_json_file, error_log_file):
        """
        This will just extract the ```json``` info and dump it as json into another file
        any further processing in the json file needs to be done
        """
        combined_list = []
        failure_log = []

        with open(input_file, 'r', encoding='utf-8') as file:
            content = file.read()

            # Extract JSON markdown content
            json_blocks = re.findall(r'```json(.*?)```', content, re.DOTALL)

            for index, block in enumerate(json_blocks):

                # Try to load it as json data
                json_data, failure = VnTranslator.loadJsonWithReTry(file.name, index, block)

                if failure:
                    # Log if it failed.
                    failure_log.append(failure)
                    continue
                else:
                    # Add to JSON to write.
                    combined_list.append(json_data)

        # Write the JSON content to given path
        with open(out_json_file, 'w', encoding='utf-8') as output_file: 
            json.dump(combined_list, output_file, indent=4, ensure_ascii=False)

        # Log failures to a file.
        if failure_log:
            with open(error_log_file, 'w', encoding='utf-8') as output_file: 
                output_file.writelines(failure_log)

    
    @staticmethod
    def loadJsonWithReTry(file_name, json_index, json_str):
        """
        This method, tries to load a json string as a dictionary object,
        if it fails, it tries to use LLM to fix it, and if it fails again,
        returns a failure message.
        """
        json_data = None
        failure = None
        try:
            # Try to load the JSON
            json_data = json.loads(json_str.strip())
        except Exception as e:
            print(f"JSON extraction for {file_name}, for element {json_index} failed! Attempting fix...")

            # Try to use the LLM to fix the failure. 
            # The prompt will be a combination of the failed json, and the error.
            prompt = VnTranslator.getFixJsonPrompt(json_str.strip(), e)
            response = VnTranslator.do_with_text(prompt)
            try:
                # Extract content from JSON markdown and try loading again.
                json_str = re.findall(r'```json(.*?)```', response, re.DOTALL)[0]
                json_data = json.loads(json_str.strip())
                print("Success, issue resolved.")
            except Exception as e:
                # Add failure message if required.
                failure = f"Unable to load json string at inex: {json_index} from file: {file_name}." +\
                f"The json string is \n\n {json_str} \n\n and error received is \n\n{e}\n\n"
                print(f"Retrying failed: {failure}")
        return (json_data, failure)
    

    @staticmethod
    def getFixJsonPrompt(incorrectJson, error):
        """
        A simple method to create prompt for JSON fixing.
        """
        return FIX_JSON_PROMPT_TEMPLATE.format(incorrectJson, error)
    

    @staticmethod
    def read_nss_json_content(file_path):
        """
        Reads a JSON file and yields each element from the 'content' list as a JSON string.
        """
        with open(file_path, 'r', encoding='utf-8') as file:
            data = json.load(file)
            for element in data.get('content', []):
                yield element


    @staticmethod
    def get_chunks(file_path, tokens_per_chunk=500, encoding_name="cl100k_base"):
        """
        Gives the content of a particular file as chunks.
        """
        # Use a compatible tokenizer for tokenization
        tokenizer = tiktoken.get_encoding(encoding_name)
        with open(file_path, 'r', encoding='utf-8') as file:
            text = file.read()

        # Tokenize file content
        tokens = tokenizer.encode(text)

        # Yields one chunk at a time.
        for i in range(0, len(tokens), tokens_per_chunk):
            yield tokenizer.decode(tokens[i:i + tokens_per_chunk])

    @staticmethod
    def get_instruction_prompt(instructions, input_text):
        """
        Returns a prompt, given instruction and text to process.
        """
        return instructions + input_text

    @staticmethod
    def do_with_text(prompt, model=AYA_EXP, system_prompt=SYSTEM_PROMPT):
        """
        Crux of the project, basically runs a prompt on a Model that is running
        on a local OLLAMA server.
        """
        response = ollama.chat( 
            model=model, 
            messages=[ 
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': prompt} 
            ] 
        )
        return response["message"]["content"].strip()


# Example usage flow.
NSS_INPUT_FOLDER = "nss/folder/input/path"
NSS_OUTPUT_FOLDER = "nss/folder/output/path"
RAW_GLOSSARY = "raw_glossary.txt"
GLOSSARY_JSON = "glossary.json"
FINAL_CONTENT = "final.txt"
STORY_SUMMARY = "summary.txt"

vn = VnTranslator(NSS_INPUT_FOLDER, RAW_GLOSSARY, GLOSSARY_JSON, NSS_OUTPUT_FOLDER, FINAL_CONTENT, STORY_SUMMARY)
vn.create_raw_glossary()
vn.create_glossary_json()
vn.load_glossary()
vn.create_raw_translation()
vn.clean_translation()
vn.create_raw_translation_vn_nss_json()






    
    
    
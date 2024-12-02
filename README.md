# VnTranslator: A Japanese-to-English Novel Translation Toolkit

## Overview

**VnTranslator** is a Python-based project designed to translate Japanese novels into English while ensuring consistency, especially with names and terms. The toolkit utilizes a locally running AI model (via Ollama) for processing and provides functionalities to create, refine, and utilize glossaries for accurate translations.
***Note:*** This is not a complete project, and is likely to go through a lot more iterations of changes, for more refined translations.

## Features

- **Glossary Creation**: Automatically extract names and key terms from input text, translating them with phonetics and gender information.
- **Name Consistency**: Ensures consistent translations of names and terms across the text using a glossary.
- **JSON-based Translation**: Handles translation of JSON-structured content with about 99% integrity on testing.

## Requirements

### Python Libraries
- `json`
- `tiktoken`
- `ollama`
- `re`
- `os`

### Ollama AI Dependencies
- A running **Ollama AI server** with models like `dorian2b/vera`, `aya-expanse`, or `llama3.1` is required.

## Installation
1. Install required Python packages:
   ```bash
   pip install tiktoken ollama
   ```

2. Ensure the **Ollama server** is running on your system with the required models.

## Usage

### Workflow Overview

1. **Glossary Creation**: Extract names and key terms from input text and generate a glossary for consistent translations.
2. **Translation**: Translate raw text or JSON content using the glossary previously created.
3. **Refinement**: Clean and refine the translated text for better readability (Work in progress).

### Example Usage

```python
# Define input and output paths
NSS_INPUT_FOLDER = "nss/folder/input/path"
NSS_OUTPUT_FOLDER = "nss/folder/output/path"
RAW_GLOSSARY = "raw_glossary.txt"
GLOSSARY_JSON = "glossary.json"
FINAL_CONTENT = "final.txt"
STORY_SUMMARY = "summary.txt"

# Initialize the translator
vn = VnTranslator(
    raw_loc=NSS_INPUT_FOLDER,
    raw_glossary_loc=RAW_GLOSSARY,
    glossary_loc=GLOSSARY_JSON,
    raw_translate_loc=NSS_OUTPUT_FOLDER,
    refined_translation_loc=FINAL_CONTENT,
    summary_file=STORY_SUMMARY
)

# Run the workflow
vn.create_raw_glossary()  # Step 1: Create glossary
vn.create_glossary_json()  # Step 2: Convert glossary to JSON
vn.load_glossary()  # Step 3: Load glossary
vn.create_raw_translation_vn_nss_json()  # Step 4: Translate content
```

## Input Formats

- **Text Files**: For light novel translations.
- **JSON Files**: For structured visual novel content.

## Glossary Format

Example of a glossary in JSON:
```json
[
    {
        "japanesename": "魔女",
        "englishphonetic": "Majo",
        "actualname": "Witch"
    }
]
```
This can be changed later to include more context for better translation.

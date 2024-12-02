import os
import re
import chardet
import json

INPUT_FOLDER = "folder/with/nss/files"
OUTPUT_FOLDER = "folder/for/nss/json/output"


def detect_encoding(file_path):
    """Detect the file encoding."""
    with open(file_path, 'rb') as f:
        result = chardet.detect(f.read())
        return result['encoding']
    

def extract_pre_content(file_path):
    try:
        with open(file_path, 'r', encoding=detect_encoding(file_path)) as file:
            content = file.read()

        # Use a regular expression to find all content within <PRE></PRE> tags
        pre_contents = re.findall(r'<PRE.*?>(.*?)</PRE>', content, re.DOTALL)

        return pre_contents
    except:
        return "<Encoding Error>"
    

def save_content_to_json(content, json_path):
    """Save extracted content to a JSON file."""
    try:
        with open(json_path, 'w', encoding='utf-8') as json_file:
            json.dump({"content": process_content(content)}, json_file, ensure_ascii=False, indent=4)
        print(f"Content saved to {json_path}")
    except Exception as e:
        print(f"Error saving content to {json_path}: {e}")

def process_content(content: list[str]):
    processed = []

    for entry in content:
        # Find all <text label> sections
        lines = entry.splitlines()

        ele = {
            "text label": None,
            "Name": [],
            "voice tag": [],
            "text": [],
        }

        # JSON parsing logic, specific to NSS files of certain format
        # Will require changes
        for line in lines:
            if line != "":
                if "[text" in line:
                    ele["text label"] = line
                elif "「" in line:
                    if len(ele["Name"]) != len(ele["text"]) + 1:
                        ele["Name"].append(None)
                    if len(ele["voice tag"]) != len(ele["text"]) + 1:
                        ele["voice tag"].append(None)
                    ele["text"].append(line)
                elif "【" in line:
                    ele["Name"].append(line)
                elif "<voice" in line:
                    if len(ele["Name"]) != len(ele["voice tag"]) + 1:
                        ele["Name"].append(None)
                    ele["voice tag"].append(line)
                else:
                    if len(ele["text"]) == 0:
                        ele["text"].append(line)
                    elif ele["text"] and "」" in ele["text"][-1]:
                        if len(ele["Name"]) != len(ele["text"]) + 1:
                            ele["Name"].append(None)
                        if len(ele["voice tag"]) != len(ele["text"]) + 1:
                            ele["voice tag"].append(None)
                        ele["text"].append(line)
                    else:
                        ele["text"][-1] = ele["text"][-1] + "\n" + line

        processed.append(ele)
        
    return processed

def process_folder(folder_path, out_path):
    """Iterates through all files in the folder and extracts <PRE></PRE> content."""
    for root, _, files in os.walk(folder_path):
        for file_name in files:
            file_path = os.path.join(root, file_name)
            print(f"Processing file: {file_path}")
            pre_contents = extract_pre_content(file_path)
                
            if pre_contents:
                # Construct the path for the output JSON file (same name, .json extension)
                json_path = os.path.splitext(os.path.join(out_path, file_name))[0] + '.json'
                
                # Save extracted content to the JSON file
                save_content_to_json(pre_contents, json_path)

# Example usage
process_folder(INPUT_FOLDER, OUTPUT_FOLDER)
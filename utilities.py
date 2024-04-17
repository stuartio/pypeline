import json
import os
import urllib.parse
from jsonpath_ng.ext import parse
from akamai.edgegrid import EdgeRc
import click


def sanitizeFileName(unsafe_filename):
    safe_filename = unsafe_filename
    bad_characters = ["\\", "/", ":", "*", "?", '"', "<", ">", "|"]

    for bad_char in bad_characters:
        encoded_char = urllib.parse.quote(bad_char, safe="")
        safe_filename = safe_filename.replace(bad_char, encoded_char)

    # Trim trailing spaces
    safe_filename = safe_filename.strip()
    return safe_filename


def split_child_rule(rule, directory, use_full_paths, parent_path):
    if not os.path.exists(directory):
        # report("split_child_rule", "Making directory: " + directory, level="debug")
        os.mkdir(directory)

    sanitized_rule_name = sanitizeFileName(rule["name"])
    children_directory = directory + "/" + sanitized_rule_name

    for index, child in enumerate(rule["children"]):
        child_filename = sanitizeFileName(child["name"])

        # Handle use_full_paths option
        child_path = ""
        if use_full_paths and parent_path:
            child_path = parent_path + "/" + sanitized_rule_name
        else:
            child_path = sanitized_rule_name

        split_child_rule(child, children_directory, use_full_paths, child_path)

        rule["children"][index] = f"#include:{child_path}/{child_filename}.json"

    rule_filename = directory + "/" + sanitized_rule_name + ".json"
    with open(rule_filename, "w") as rule_file:
        json.dump(rule, rule_file, indent=2)


def split_rules(rules, output_directory, use_full_paths):
    ## Check Output Directory and create if required
    if not os.path.exists(output_directory):
        # report("split_rules", "Making directory: " + output_directory, level="debug")
        os.mkdir(output_directory)

    ## Iterate through child rules
    for index, child in enumerate(rules["rules"]["children"]):
        child_filename = sanitizeFileName(child["name"]) + ".json"
        split_child_rule(child, output_directory, use_full_paths, parent_path="")
        rules["rules"]["children"][index] = "#include:" + child_filename

    ## Create variables file
    variables_filename = output_directory + "/pmVariables.json"
    with open(variables_filename, "w") as variables_file:
        json.dump(rules["rules"]["variables"], variables_file, indent=2)
    rules["rules"]["variables"] = "#include:pmVariables.json"

    main_filename = output_directory + "/main.json"
    with open(main_filename, "w") as main_file:
        json.dump(rules["rules"], main_file, indent=2)


def merge_child_rule(file_path, main_dir):
    # report("merge_child_rule", "Loading file: " + file_path, level="debug")
    with open(file_path, "r") as file:
        rules = json.load(file)

    # Infer parent dir
    parent_dir = os.path.dirname(file_path)

    for index, child in enumerate(rules["children"]):
        if isinstance(child, str) and "#include:" in child:
            include_filename = child.replace("#include:", "")

            # Check if child file is relative to parent folder, or to main json
            relative_include_path = parent_dir + "/" + include_filename
            main_include_path = main_dir + "/" + include_filename

            if os.path.isfile(relative_include_path):
                child_path = relative_include_path
            elif os.path.isfile(main_include_path):
                child_path = main_include_path
            else:
                raise Exception(
                    f"File {include_filename} not found as either relative or full path from main. Please confirm file exists and try again."
                )

            child_rules = merge_child_rule(child_path, main_dir)
            rules["children"][index] = child_rules

    return rules


def merge_rules(main_file_path):
    rules = {}
    # report("merge_rules", "Loading main file: " + main_file_path, level="debug")
    with open(main_file_path, "r") as file:
        rules["rules"] = json.load(file)
    main_dir = os.path.dirname(main_file_path)
    child_file_prefix = main_dir + "/"

    for index, child in enumerate(rules["rules"]["children"]):
        if isinstance(child, str) and "#include:" in child:
            child_filename = child.replace("#include:", child_file_prefix)
            child_rules = merge_child_rule(child_filename, main_dir)
            rules["rules"]["children"][index] = child_rules

    if isinstance(rules["rules"]["variables"], str) and "#include:" in rules["rules"]["variables"]:
        variables_filename = rules["rules"]["variables"].replace("#include:", child_file_prefix)
        # report("merge_rules", "Loading variables file: " + variables_filename, level="debug")
        with open(variables_filename, "r") as variables_file:
            rules["rules"]["variables"] = json.load(variables_file)

    return rules


def get_credentials(edgerc_path, section, account_key):
    credential_elements = ["host", "client_token", "access_token", "client_secret", "account_key"]
    credentials = {}
    edgerc = None
    if edgerc_path is None:
        env_elements_present = True
        ## if no edgerc path supplied, check for env variables first
        for element in credential_elements:
            if section == "default":
                env_variable = "AKAMAI_" + element.upper()
            else:
                env_variable = "AKAMAI_" + section.upper() + "_" + element.upper()
            if os.getenv(env_variable) is not None:
                credentials[element] = os.getenv(env_variable)
            else:
                env_elements_present = False

        ## If any edgerc elements missing, look for default EdgeRCFile location
        if not env_elements_present:
            edgerc = EdgeRc("~/.edgerc")
    elif os.path.exists(edgerc_path):
        edgerc = EdgeRc(edgerc_path)
    else:
        raise (Exception("Specified EdgeRC File does not exist"))

    if edgerc is not None:
        for element in credential_elements:
            credentials[element] = edgerc.get(section, element)

    if account_key is not None:
        credentials["account_key"] = account_key
    return credentials


def apply_variable_by_jsonpath(rules, path, value):
    jsonpath_expression = parse(path)
    rule_found = jsonpath_expression.find(rules)

    if len(rule_found) > 0:
        jsonpath_expression.update(rules, value)
    else:
        click.secho(f"WARNING: Path '{path}' not found in supplied rules. No update performed", fg="yellow")
    return rules

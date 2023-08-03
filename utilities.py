import json
import os
import urllib.parse
from jsonpath_ng.ext import parse
from akamai.edgegrid import EdgeRc
import click

def sanitizeFileName(unsafe_filename):
    safe_filename = unsafe_filename
    bad_characters = [
        '\\',
        '/',
        ':',
        '*',
        '?',
        '"',
        '<',
        '>',
        '|'
    ]

    for bad_char in bad_characters:
        encoded_char = urllib.parse.quote(bad_char, safe='')
        safe_filename = safe_filename.replace(bad_char, encoded_char)
    return safe_filename

def split_child_rule(rule, directory):
    # print('Parsing rule: ' + rule['name'])
    if not os.path.exists(directory):
        # print('Making directory: ' + directory)
        os.mkdir(directory)

    sanitized_rule_name = sanitizeFileName(rule['name'])
    children_directory = directory + '/' + sanitized_rule_name
    
    for index, child in enumerate(rule['children']):
        child_filename = sanitizeFileName(child['name'])
        split_child_rule(child, children_directory)
        rule['children'][index] = '#include:{d}/{f}.json'.format(d = sanitized_rule_name, f = child_filename)

    rule_filename = directory + '/' + sanitized_rule_name + '.json'
    with open(rule_filename, 'w') as rule_file:
        json.dump(rule, rule_file, indent = 2)
    

def split_rules(rules, output_directory):
    ## Check Output Directory and create if required
    if not os.path.exists(output_directory):
        # print('Making directory: ' + output_directory)
        os.mkdir(output_directory)

    ## Iterate through child rules
    for index, child in enumerate(rules['rules']['children']):
        child_filename = sanitizeFileName(child['name']) + '.json'
        split_child_rule(child, output_directory)
        rules['rules']['children'][index] = '#include:' + child_filename
    
    ## Create variables file
    variables_filename = output_directory + '/pmVariables.json'
    with open(variables_filename, 'w') as variables_file:
        json.dump(rules['rules']['variables'], variables_file, indent = 2)
    rules['rules']['variables'] = '#include:pmVariables.json'

    main_filename = output_directory + '/main.json'
    with open(main_filename, 'w') as main_file:
        json.dump(rules['rules'], main_file, indent=2)

def merge_child_rule(file_path):
    # print('Loading file: ' + file_path)
    with open(file_path, 'r') as file:
        rules = json.load(file)
    parent_file_dir = os.path.dirname(file_path)
    child_file_prefix = parent_file_dir + '/'

    for index, child in enumerate(rules['children']):
        if isinstance(child, str) and '#include:' in child:
            child_filename = child.replace('#include:',child_file_prefix)
            child_rules = merge_child_rule(child_filename)
            rules['children'][index] = child_rules

    return rules

def merge_rules(main_file_path):
    rules = {}
    # print('Loading main file: ' + main_file_path)
    with open(main_file_path, 'r') as file:
        rules['rules'] = json.load(file)
    parent_file_dir = os.path.dirname(main_file_path)
    child_file_prefix = parent_file_dir + '/'

    for index, child in enumerate(rules['rules']['children']):
        if isinstance(child, str) and '#include:' in child:
            child_filename = child.replace('#include:',child_file_prefix)
            child_rules = merge_child_rule(child_filename)
            rules['rules']['children'][index] = child_rules

    if isinstance(rules['rules']['variables'], str) and '#include:' in rules['rules']['variables']:
        variables_filename = rules['rules']['variables'].replace('#include:',child_file_prefix)
        # print('Loading variables file: ' + variables_filename)
        with open(variables_filename, 'r') as variables_file:
            rules['rules']['variables'] = json.load(variables_file)

    return rules

def get_credentials(edgerc_path, section, account_key):
    credential_elements = ['host', 'client_token', 'access_token', 'client_secret', 'account_key']
    credentials = {}
    edgerc = None
    if edgerc_path is None:
        env_elements_present = True
        ## if no edgerc path supplied, check for env variables first
        for element in credential_elements:
            if section == 'default':
                env_variable = 'AKAMAI_' + element.upper()
            else:
                env_variable = 'AKAMAI_' + section.upper() + '_' + element.upper()
            if os.getenv(env_variable) is not None:
                credentials[element] = os.getenv(env_variable)
            else:
                env_elements_present = False
        
        ## If any edgerc elements missing, look for default EdgeRCFile location
        if not env_elements_present:
            edgerc = EdgeRc('~/.edgerc')
    elif os.path.exists(edgerc_path):
        edgerc = EdgeRc(edgerc_path)
    else:
        raise(Exception('Specified EdgeRC File does not exist'))
    
    if edgerc is not None:
        for element in credential_elements:
            credentials[element] = edgerc.get(section, element)

    if account_key is not None:
        credentials['account_key'] = account_key
    return credentials

def apply_variable_by_jsonpath(rules, path, value):
    jsonpath_expression = parse(path)
    rule_found = jsonpath_expression.find(rules)

    if len(rule_found) > 0:
        jsonpath_expression.update(rules, value)
    else:
        click.secho('WARNING: Path "{p}" not found in supplied rules. No update performed'.format(p = path), fg = 'yellow')
    return rules
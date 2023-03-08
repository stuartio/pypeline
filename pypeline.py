import json
import click
import os
import sys
import re
from datetime import datetime
from akamai.property import Property
from utilities import *

def get_environment(environment_name):
    environment = [e for e in CONFIG['environments'] if e['name'] == environment_name]
    if len(environment) == 0:
        click.secho('Environment "{e}" not found in pipeline config. Please check and try again'.format(e = environment_name), fg='red')
        sys.exit(1)
    else:
        environment = environment[0]
    
    return environment

def get_property(property_name):
    property_instances = PROPERTY_CLIENT.findProperty(property_name)
    if len(property_instances) == 0:
        click.secho("Failed to find property: {p} . Can't proceed, sorry".format(p = property_name), fg='red')
        sys.exit(1)
    property_instances = sorted(property_instances, key=lambda p: int(p['propertyVersion']), reverse=True)
    return property_instances[0]

def merge_pipeline(pipeline_folder, environment_name):
    ## Load variable definitions
    variable_definitions_file = pipeline_folder + '/variableDefinitions.json'
    if os.path.exists(variable_definitions_file):
        with open(variable_definitions_file, 'r') as f:
            VARIABLE_DEFINITIONS = json.load(f)
    else:
        click.secho('Variable definitions not found at: {v} . Cannot proceed'.format(v = variable_definitions_file), fg='red')
        sys.exit(1)

    ## Env-specific variables
    env_variables_file = pipeline_folder + '/environments/' + environment_name + '/variables.json'
    if os.path.exists(env_variables_file):
        with open(env_variables_file, 'r') as f:
            ENV_VARIABLES = json.load(f)
    else:
        click.secho('Environment variables file not found at: {e} . Cannot proceed'.format(e = env_variables_file), fg='red')
        sys.exit(1)

    ## Load templates to dict
    main_file = pipeline_folder + '/templates/main.json'
    rules = merge_rules(main_file)

    ## Interpolate variables
    for variable in VARIABLE_DEFINITIONS:
        if variable['name'] in ENV_VARIABLES.keys():
            env_variable_value = ENV_VARIABLES[variable['name']]
        else:
            env_variable_value = variable['default']

        apply_variable_by_jsonpath(rules, variable['jsonPath'], env_variable_value)
    
    return rules

@click.group()
@click.option('--edgerc', '-e', 'edgerc_path', default=None, help="Edgerc settings file")
@click.option('--section', '-s', 'section', default='default', help="Section in Edgerc file")
@click.option('--account-key', '-a', 'account_key', default=None, help="Account Switch Key")
@click.option('--pipeline', 'pipeline_folder', type=click.Path(exists=True, dir_okay=True), default='.', help="Pipeline folder")
def cli(edgerc_path, section, account_key, pipeline_folder):
    # Load Config
    global CONFIG
    config_file = pipeline_folder + '/pipeline.json'
    with open(config_file, 'r') as f:
        CONFIG = json.load(f)

    ## Set up clients
    global PROPERTY_CLIENT
    PROPERTY_CLIENT = Property(edgerc_path, section, account_key)

@cli.command('import')
@click.option('--property', '-p', 'import_property', required=True, help="Property Name to import")
@click.option('--version', '-v', 'import_property_version', required=False, help="Property version to import. Defaults to latest")
@click.option('--ruleFormat', 'rule_format', required=False, default='latest', help="Rule format with which to pull down property rules. Defaults to 'latest'")
@click.pass_context
def import_property(ctx, import_property, import_property_version, rule_format):
    """
    Retrieve rules from PAPI and break them down into templates
    """

    property = get_property(import_property)

    ## Check property exists
    if property is None:
        raise(Exception('Property {p} not found'.format(p = import_property)))

    ## Set latest version if version omitted
    if import_property_version is None:
        import_property_version = property['propertyVersion']

    ## Get rules from PAPI
    rules = PROPERTY_CLIENT.getPropertyRules(property['propertyId'], import_property_version, rule_format)

    ## Set destination folder
    dest_folder = ctx.parent.params['pipeline_folder'] + '/templates'

    ## Create template folder if missing
    if not os.path.exists(dest_folder):
        os.mkdir(dest_folder)

    ## Split rules into templates folder
    split_rules(rules, dest_folder)

    click.echo("Property Imported to {d}".format(d = dest_folder))

@cli.command('update')
@click.option('--environment', 'environment_name', required=True, help="Environment to update")
@click.pass_context
def update(ctx, environment_name):
    """
    Merge templates and variables & push to PAPI
    """

    ## Get environment from config
    environment = get_environment(environment_name)

    ## Interpolate rules
    rules = merge_pipeline(ctx.parent.params['pipeline_folder'], environment_name)

    ## Get Property Status
    property = get_property(environment['propertyName'])
    VERSIONLINK_MATCH = '.*/versions/([\d]+)'

    ## Don't need to create new version so just go for it
    if property['productionStatus'] == 'INACTIVE' and property['stagingStatus'] == 'INACTIVE':
        update_version = property['propertyVersion']
    else:
        click.secho('Creating new version of property {p}'.format(p = property['propertyName']), fg='yellow')
        new_version_result = PROPERTY_CLIENT.newPropertyVersion(property['propertyId'], property['propertyVersion'])
        version_matches = re.match(VERSIONLINK_MATCH, new_version_result)
        update_version = version_matches.group(1)

    ## Set Version Notes
    now = datetime.now()
    rules['comments'] = 'Pypeline update: {time}'.format(time = now.strftime("%m/%d/%Y, %H:%M:%S"))

    ## Send updated config to PAPI
    click.secho('Pushing updates to version {v} of property {p}'.format(v = update_version, p = property['propertyName']), fg='yellow')
    try:
        update_result = PROPERTY_CLIENT.updateVersion(property['propertyId'], update_version, rules, CONFIG['ruleFormat'])
    except:
        click.echo('Failed to update property {p}. Bailing out...'.format(p = property['propertyName']))
        sys.exit(1)

    click.secho("Environment {e} updated".format(e = environment_name), fg='green')

@cli.command('merge')
@click.option('--environment', 'environment_name', required=True, help="Environment to update")
@click.pass_context
def merge(ctx, environment_name):
    ## Interpolate rules
    rules = merge_pipeline(ctx.parent.params['pipeline_folder'], environment_name)

    # Write rules to dist for now
    dist_folder = ctx.parent.params['pipeline_folder'] + '/dist'
    if not os.path.exists(dist_folder):
        os.mkdir(dist_folder)
    dist_file = dist_folder + '/' + environment_name + '.json'
    with open(dist_file, 'w') as f:
        json.dump(rules, f, indent=2)
    click.echo('Wrote updated rules to: {f}'.format(f = dist_file))
    click.secho('Merge complete', fg='green')


@cli.command('activate')
@click.option('--environment', 'environment_name', required=True, help="Environment to activate")
@click.option('--network', 'network', required=False, default='Staging', help="Network on which to activate. Staging or Production, defaults to Staging")
@click.option('--email', 'email', required=True, help="Comma-separated email list for activation")
@click.pass_context
def activate(ctx, environment_name, network, email):
    ## Get environment from config
    environment = get_environment(environment_name)

    ## Get Property Status
    property = get_property(environment['propertyName'])

    if network.lower() == 'staging' and property['stagingStatus'] != 'INACTIVE':
        click.secho('Version {v} of property {p} is already active on Staging. Nothing to do'.format(p = property['propertyName'], v = property['propertyVersion']), fg='red')
        sys.exit(1)
    elif network.lower() == 'production' and property['productionStatus'] != 'INACTIVE':
        click.secho('Version {v} of property {p} is already active on Production. Nothing to do'.format(p = property['propertyName'], v = property['propertyVersion']), fg='red')
        sys.exit(1)
    
    ## Activate to chosen network
    try:
        activate_result = PROPERTY_CLIENT.activate(property['propertyId'], property['propertyVersion'], network, email)
    except:
        click.echo('Failed to activate version {v} of property {p} to {n}. Bailing out...'.format(v = property['propertyVersion'], p = property['propertyName'], n = network))
        sys.exit(1)



if __name__ == '__main__':
    cli()
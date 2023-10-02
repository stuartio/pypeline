import json
import click
import os
import shutil
import sys
import re
from datetime import datetime
from ak.property import Property
from utilities import *


def get_config(folder):
    # Load Config
    CONFIG_FILE = folder + "/pipeline.json"
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    else:
        click.secho(
            'pipeline.json does not exist at "{f}". Please confirm location or use --name parameter to specify another folder'.format(
                f=folder
            ),
            fg="red",
        )
        sys.exit(1)


def get_variable_definitions(folder):
    variable_definitions_file = folder + "/variableDefinitions.json"
    if os.path.exists(variable_definitions_file):
        with open(variable_definitions_file, "r") as f:
            VARIABLE_DEFINITIONS = json.load(f)
    else:
        click.secho(
            "Variable definitions not found at: {v} . Cannot proceed".format(v=variable_definitions_file), fg="red"
        )
        sys.exit(1)

    return VARIABLE_DEFINITIONS


def get_environment(environment_name, CONFIG):
    environment = [e for e in CONFIG["environments"] if e["name"] == environment_name]
    if len(environment) == 0:
        click.secho(
            'Environment "{e}" not found in pipeline config. Please check and try again'.format(e=environment_name),
            fg="red",
        )
        sys.exit(1)
    else:
        environment = environment[0]

    return environment


def get_property(property_name):
    property_instances = PROPERTY_CLIENT.findProperty(property_name)
    if len(property_instances) == 0:
        click.secho("Failed to find property: {p} . Can't proceed, sorry".format(p=property_name), fg="red")
        sys.exit(1)
    property_instances = sorted(property_instances, key=lambda p: int(p["propertyVersion"]), reverse=True)
    return property_instances[0]


def get_hostnames(folder, environment_name):
    ## Env-specific variables
    hostnames_file = folder + "/environments/" + environment_name + "/hostnames.json"
    if os.path.exists(hostnames_file):
        with open(hostnames_file, "r") as f:
            HOSTNAMES = json.load(f)
    else:
        click.secho("Hostnames variables file not found at: {e} . Cannot proceed".format(e=hostnames_file), fg="red")
        sys.exit(1)

    return HOSTNAMES


def merge_pipeline(folder, environment_name):
    ## Get variable defs
    VARIABLE_DEFINITIONS = get_variable_definitions(folder)

    ## Env-specific variables
    env_variables_file = folder + "/environments/" + environment_name + "/variables.json"
    if os.path.exists(env_variables_file):
        with open(env_variables_file, "r") as f:
            ENV_VARIABLES = json.load(f)
    else:
        click.secho(
            "Environment variables file not found at: {e} . Cannot proceed".format(e=env_variables_file), fg="red"
        )
        sys.exit(1)

    ## Load templates to dict
    main_file = folder + "/templates/main.json"
    rules = merge_rules(main_file)

    ## Interpolate variables
    for variable in VARIABLE_DEFINITIONS:
        if variable["name"] in ENV_VARIABLES.keys():
            env_variable_value = ENV_VARIABLES[variable["name"]]
        else:
            env_variable_value = variable["default"]

        if "jsonPaths" in variable.keys():
            for path in variable["jsonPaths"]:
                apply_variable_by_jsonpath(rules, path, env_variable_value)
        else:
            ## Cast rules to string, replace globally and cast back to dict
            rules_str = json.dumps(rules)
            if isinstance(env_variable_value, bool):
                rules_str = rules_str.replace('"${env.%s}"' % variable["name"], json.dumps(env_variable_value))
            elif isinstance(env_variable_value, int):
                rules_str = rules_str.replace('"${env.%s}"' % variable["name"], str(env_variable_value))
            else:
                rules_str = rules_str.replace("${env.%s}" % variable["name"], env_variable_value)
            rules = json.loads(rules_str)

    ## Remove out of scope rules
    rules["rules"] = remove_out_of_scope_rules(rules["rules"], environment_name)

    return rules


def remove_out_of_scope_rules(rules, environment_name):
    # Search rule comments for pypeline_env, and remove any rule referencing an env other than the current one
    if "children" in rules.keys():
        parsed_children = []
        for child in rules["children"]:
            if "comments" in child.keys():
                scoped_environments_found = re.search("pypeline_env:([^;]+)", child["comments"])
                # Parse comments. If environment name in pypeline_env include child in output
                if scoped_environments_found is not None:
                    scoped_environments = scoped_environments_found.group(1).replace(" ", "")
                    scoped_environments = scoped_environments.split(",")
                    if environment_name in scoped_environments:
                        parsed_children.append(child)
                # If no pypeline_env comment, include child by default
                else:
                    parsed_children.append(child)
            # If no comments at all, include child by default
            else:
                parsed_children.append(child)

        # Recurse through child rules
        for parsed_child in parsed_children:
            parsed_child = remove_out_of_scope_rules(parsed_child, environment_name)
        # Replace children with parsed
        rules["children"] = parsed_children
    return rules


@click.group()
@click.option("--edgerc", "-e", "edgerc_path", default=None, help="Edgerc settings file")
@click.option("--section", "-s", "section", default="default", help="Section in Edgerc file")
@click.option("--account-key", "-a", "account_key", default=None, help="Account Switch Key")
@click.option("--folder", "folder", type=click.Path(exists=True, dir_okay=True), default=".", help="Pipeline folder")
def cli(edgerc_path, section, account_key, folder):
    ## Set up clients
    global PROPERTY_CLIENT
    PROPERTY_CLIENT = Property(edgerc_path, section, account_key)


@cli.command("import")
@click.option("--property", "-p", "import_property", required=True, help="Property Name to import")
@click.option(
    "--version", "-v", "import_property_version", required=False, help="Property version to import. Defaults to latest"
)
@click.option(
    "--ruleFormat",
    "rule_format",
    required=False,
    default="latest",
    help="Rule format with which to pull down property rules. Defaults to 'latest'",
)
@click.pass_context
def import_property(ctx, import_property, import_property_version, rule_format):
    """
    Retrieve rules from PAPI and break them down into templates
    """

    property = get_property(import_property)

    ## Check property exists
    if property is None:
        raise (Exception("Property {p} not found".format(p=import_property)))

    ## Set latest version if version omitted
    if import_property_version is None:
        import_property_version = property["propertyVersion"]

    ## Get rules from PAPI
    rules = PROPERTY_CLIENT.getPropertyRules(property["propertyId"], import_property_version, rule_format)

    ## Set destination folder
    dest_folder = ctx.parent.params["folder"] + "/templates"

    ## Clear templates folder and recreate
    if os.path.exists(dest_folder):
        shutil.rmtree(dest_folder)
    os.mkdir(dest_folder)

    ## Split rules into templates folder
    split_rules(rules, dest_folder)

    click.echo("Property '{p}' imported to {d}".format(p=import_property, d=dest_folder))


@cli.command("update")
@click.option("--environment", "environment_name", required=True, help="Environment to update")
@click.option("--notes", "notes", required=False, help="Version notes to be added")
@click.pass_context
def update(ctx, environment_name, notes):
    """
    Merge templates and variables & push to PAPI
    """
    ## Get config
    CONFIG = get_config(ctx.parent.params["folder"])

    ## Get environment from config
    environment = get_environment(environment_name, CONFIG)

    ## Interpolate rules
    rules = merge_pipeline(ctx.parent.params["folder"], environment_name)

    ## Get hostnames
    hostnames = get_hostnames(ctx.parent.params["folder"], environment_name)

    ## Get Property Status
    property = get_property(environment["propertyName"])
    VERSIONLINK_MATCH = ".*/versions/([\d]+)"

    ## Don't need to create new version so just go for it
    if property["productionStatus"] == "INACTIVE" and property["stagingStatus"] == "INACTIVE":
        update_version = property["propertyVersion"]
    else:
        click.secho("Creating new version of property {p}".format(p=property["propertyName"]), fg="yellow")
        new_version_result = PROPERTY_CLIENT.newPropertyVersion(property["propertyId"], property["propertyVersion"])
        version_matches = re.match(VERSIONLINK_MATCH, new_version_result)
        update_version = version_matches.group(1)

    ## Set Version Notes
    now = datetime.now()
    if notes is None:
        rules["comments"] = "Pypeline update: {time}".format(time=now.strftime("%m/%d/%Y, %H:%M:%S"))
    else:
        rules["comments"] = notes

    ## Send updated config to PAPI
    click.secho(
        "Pushing updates to version {v} of property {p}".format(v=update_version, p=property["propertyName"]),
        fg="yellow",
    )
    try:
        rules_update_result = PROPERTY_CLIENT.updateVersion(
            property["propertyId"], update_version, rules, CONFIG["ruleFormat"]
        )
    except:
        click.echo("Failed to update rules for property {p}. Bailing out...".format(p=property["propertyName"]))
        click.echo(str(hostnames_update_result))
        sys.exit(1)

    click.secho(
        "Setting hostnames for version {v} of property {p}".format(v=update_version, p=property["propertyName"]),
        fg="yellow",
    )
    try:
        hostnames_update_result = PROPERTY_CLIENT.setHostnames(property["propertyId"], update_version, hostnames)
    except:
        click.echo("Failed to update hostnames for property {p}. Bailing out...".format(p=property["propertyName"]))
        click.echo(str(hostnames_update_result))
        sys.exit(1)

    click.secho("Environment {e} updated".format(e=environment_name), fg="green")


@cli.command("merge")
@click.option("--environment", "environment_name", required=True, help="Environment to update")
@click.pass_context
def merge(ctx, environment_name):
    """
    Collate templates and apply variables, then output json file to dist folder
    """

    ## Interpolate rules
    rules = merge_pipeline(ctx.parent.params["folder"], environment_name)

    # Write rules to dist for now
    dist_folder = ctx.parent.params["folder"] + "/dist"
    if not os.path.exists(dist_folder):
        os.mkdir(dist_folder)
    dist_file = dist_folder + "/" + environment_name + ".json"
    with open(dist_file, "w") as f:
        json.dump(rules, f, indent=2)
    click.echo("Wrote updated rules to: {f}".format(f=dist_file))
    click.secho("Merge complete", fg="green")


@cli.command("activate")
@click.option("--environment", "environment_name", required=True, help="Environment to activate")
@click.option(
    "--network",
    "network",
    required=False,
    default="Staging",
    help="Network on which to activate. Staging or Production, defaults to Staging",
)
@click.option("--email", "email", required=True, help="Comma-separated email list for activation")
@click.pass_context
def activate(ctx, environment_name, network, email):
    """
    Activate an environment on Staging or Production
    """
    ## Get config
    CONFIG = get_config(ctx.parent.params["folder"])

    ## Get environment from config
    environment = get_environment(environment_name, CONFIG)

    ## Get Property Status
    property = get_property(environment["propertyName"])

    if network.lower() == "staging" and property["stagingStatus"] != "INACTIVE":
        click.secho(
            "Version {v} of property {p} is already active on Staging. Nothing to do".format(
                p=property["propertyName"], v=property["propertyVersion"]
            ),
            fg="red",
        )
        sys.exit(1)
    elif network.lower() == "production" and property["productionStatus"] != "INACTIVE":
        click.secho(
            "Version {v} of property {p} is already active on Production. Nothing to do".format(
                p=property["propertyName"], v=property["propertyVersion"]
            ),
            fg="red",
        )
        sys.exit(1)

    activations = PROPERTY_CLIENT.listActivations(property["propertyId"])
    pending_activations = [a for a in activations if a["status"] == "PENDING"]
    if len(pending_activations) > 0:
        click.echo(
            "There is a pending activation of version {v} of property {p}. Please wait until this is complete then update and try again".format(
                v=pending_activations[0]["propertyVersion"], p=pending_activations[0]["propertyName"], n=network
            )
        )
        sys.exit(1)

    ## Activate to chosen network
    try:
        activate_result = PROPERTY_CLIENT.activate(property["propertyId"], property["propertyVersion"], network, email)
    except:
        click.echo(
            "Failed to activate version {v} of property {p} to {n}. Bailing out...".format(
                v=property["propertyVersion"], p=property["propertyName"], n=network
            )
        )
        sys.exit(1)


@cli.command("create")
@click.option("--name", "name", required=True, help="Name for your new pipeline")
@click.option("--ruleFormat", "rule_format", required=False, default="latest", help="Rule format for property updates")
@click.pass_context
def create(ctx, name, rule_format):
    """
    Create a new pipeline
    """

    ## Set pipeline folder
    pipeline_folder = ctx.parent.params["folder"] + "/" + name

    ## Check and create pipeline folder
    if os.path.exists(pipeline_folder):
        click.secho(
            'Folder "{f}" already exists. Please delete this folder or choose another'.format(f=pipeline_folder),
            fg="red",
        )
        sys.exit(1)
    else:
        os.mkdir(pipeline_folder)

    ## Create pipeline.json
    pipeline = {"name": name, "ruleFormat": rule_format, "environments": []}

    pipeline_file = pipeline_folder + "/pipeline.json"
    with open(pipeline_file, "w") as f:
        json.dump(pipeline, f, indent=2)

    ## Create variableDefinitions.json
    variable_definitions_file = pipeline_folder + "/variableDefinitions.json"
    with open(variable_definitions_file, "w") as f:
        json.dump([], f, indent=2)

    ## Create folders
    templates_dir = pipeline_folder + "/templates"
    environments_dir = pipeline_folder + "/environments"
    os.mkdir(templates_dir)
    os.mkdir(environments_dir)


@cli.command("add-environment")
@click.option("--name", "name", required=True, help="Name of environment to add")
@click.option("--property", "property_name", required=True, help="Name of property for this environment")
@click.pass_context
def add_environment(ctx, name, property_name):
    """
    Add an environment to your pipeline
    """
    ## Get config
    CONFIG = get_config(ctx.parent.params["folder"])

    ## Set folders
    pipeline_folder = ctx.parent.params["folder"]
    environment_folder = pipeline_folder + "/environments/" + name

    ## Check environment doesn't already exist
    existing_environment = [e for e in CONFIG["environments"] if e["name"] == name]
    if len(existing_environment) > 0:
        click.secho("ERROR: Environment {e} already exists".format(e=name), fg="red")
        sys.exit(1)

    ## Find property and get hostnames before doing anything else, in case it breaks
    property = get_property(property_name)
    hostnames = PROPERTY_CLIENT.listHostnames(property["propertyId"], property["propertyVersion"])

    ## Update CONFIG
    environment = {"name": name, "propertyName": property_name}
    CONFIG["environments"].append(environment)

    config_file = pipeline_folder + "/pipeline.json"
    with open(config_file, "w") as f:
        json.dump(CONFIG, f, indent=2)

    ## Check and create pipeline folder
    if not os.path.exists(environment_folder):
        os.mkdir(environment_folder)

    ## variables.json
    environment_variables = {}
    VARIABLE_DEFINITIONS = get_variable_definitions(ctx.parent.params["folder"])
    for variable in VARIABLE_DEFINITIONS:
        environment_variables[variable["name"]] = variable.get("default", None)

    environment_variables_file = environment_folder + "/variables.json"
    with open(environment_variables_file, "w") as f:
        json.dump(environment_variables, f, indent=2)

    ## hostnames.json
    hostnames_file = environment_folder + "/hostnames.json"
    with open(hostnames_file, "w") as f:
        json.dump(hostnames, f, indent=2)

    click.secho('Added environment "{e}" to pipeline'.format(e=name))


@cli.command("add-variable")
@click.option("--name", "variable_name", required=True, help="Name of variable to add to variableDefinitions")
@click.option(
    "--JSONPaths",
    "variable_paths",
    required=False,
    help="Comma-separated list of JSONPaths to locate value in rule tree. Only required if using positional variables",
)
@click.option("--default", "variable_default", required=False, default=None, help="Default value for your variable")
@click.pass_context
def add_variable(ctx, variable_name, variable_paths, variable_default):
    """
    Add a variable to your pipeline's variableDefinitions
    """
    pipeline_folder = ctx.parent.params["folder"]
    CONFIG = get_config(pipeline_folder)

    ## Add to variableDefinitions
    variable_definitions = get_variable_definitions(pipeline_folder)
    existing_variable = [v for v in variable_definitions if v["name"] == variable_name]
    if len(existing_variable) > 0:
        click.secho('Variable "{v}" already exists in variableDefinitions.json'.format(v=variable_name), fg="red")
        sys.exit(1)

    ## Cast likely integer variables to int
    if variable_default is not None and re.match("^[0-9]+$", variable_default):
        variable_default = int(variable_default)

    new_variable = {"name": variable_name, "default": variable_default}

    if variable_paths is not None:
        new_variable["jsonPaths"] = variable_paths.replace(", ", ",").split(",")
    variable_definitions.append(new_variable)

    variable_definitions_file = pipeline_folder + "/variableDefinitions.json"
    with open(variable_definitions_file, "w") as f:
        json.dump(variable_definitions, f, indent=2)

    ## Add to existing variables files for each environment
    for environment in CONFIG["environments"]:
        environment_variables_file = pipeline_folder + "/environments/" + environment["name"] + "/variables.json"
        with open(environment_variables_file, "r") as f:
            variables = json.load(f)
            if variable_name not in variables.keys():
                variables[variable_name] = variable_default
        with open(environment_variables_file, "w") as f:
            json.dump(variables, f, indent=2)


@cli.command("status")
@click.option(
    "--environment",
    "environment_name",
    required=False,
    help="Specific environment to check. If omitted all environments will be displayed",
)
@click.pass_context
def status(ctx, environment_name):
    """
    Show status of properties in each environment
    """
    ## Get config
    CONFIG = get_config(ctx.parent.params["folder"])

    for environment in CONFIG["environments"]:
        ## Skip other envs if environment specified
        if environment_name is not None and environment["name"] != environment_name:
            continue

        property = get_property(environment["propertyName"])
        click.echo("-----------------------------------------")
        click.secho("Environment: ", nl=False, fg="blue")
        click.echo(environment["name"])
        click.secho("Property Name: ", nl=False, fg="blue")
        click.echo(property["propertyName"])
        click.secho("Property ID: ", nl=False, fg="blue")
        click.echo(property["propertyId"])
        click.secho("Property Version: ", nl=False, fg="blue")
        click.echo(property["propertyVersion"])
        if "note" in property.keys():
            click.secho("Note: ", nl=False, fg="blue")
            click.echo(property["note"])
        click.secho("Staging Status: ", nl=False, fg="blue")
        click.echo(property["stagingStatus"])
        click.secho("Production Status: ", nl=False, fg="blue")
        click.echo(property["productionStatus"])


@cli.command("set-ruleformat")
@click.option("--ruleFormat", "rule_format", required=True, help="Property Rule Format to use with this pipeline")
@click.pass_context
def set_rule_format(ctx, rule_format):
    """
    Set rule format for this pipeline
    """
    ## Get config
    CONFIG = get_config(ctx.parent.params["folder"])
    CONFIG["ruleFormat"] = rule_format
    CONFIG_FILE = ctx.parent.params["folder"] + "/pipeline.json"
    with open(CONFIG_FILE, "w") as f:
        json.dump(CONFIG, f, indent=2)

    click.secho("Rule format updated to {r}".format(r=rule_format), fg="green")


if __name__ == "__main__":
    cli()

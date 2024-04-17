## Pypeline

Python-based implementation of pipeline logic to manage properties. The following operations are supported:

```shell
Usage: pypeline.py [OPTIONS] COMMAND [ARGS]...

Options:
  -e, --edgerc TEXT       Edgerc settings file
  -s, --section TEXT      Section in Edgerc file
  -a, --account-key TEXT  Account Switch Key
  --folder PATH           Pipeline folder
  --help                  Show this message and exit.

Commands:
  activate         Activate an environment on Staging or Production
  add-environment  Add an environment to your pipeline
  add-variable     Add a variable to your pipeline's variableDefinitions
  create           Create a new pipeline
  import           Retrieve rules from PAPI and break them down into...
  merge            Collate templates and apply variables, then output...
  set-ruleformat   Set rule format for this pipeline
  status           Show status of properties in each environment
  update           Merge templates and variables & push to PAPI
```

### Dependencies

This script has been tested with Python 3.8 and 3.11. It may work with lower versions but this is entirely untested. Also, your Python environment must contain the pips listed in `requirements.txt`. To install all of them in a single command run

```
python -m pip install -r requirements.txt
```

### Getting help

You can get the information above by simply running the `pypeline` script with no parameters, or by adding `--help` to your command. Take note of the `--folder` parameter, as this is used in all commands except `create`. Should it be omitted then the local folder will be used (a value of `.`).

Each individual command has its own help output, which will show you which options are supported and whether each one is required or optional. For example, you can find the available options on the `update` command by running

```shell
python pypeline.py update --help
```

```
Usage: pypeline.py update [OPTIONS]

  Merge templates and variables & push to PAPI

Options:
  --environment TEXT  Environment to update  [required]
  --notes TEXT        Version notes to be added
  --help              Show this message and exit.
```

> Note: global options, such as `--folder` must be provided _before_ the command, e.g. `python pypeline.py --folder mypipeline update --environment dev`

### Variable Setup

Variables can be configured in one of two ways. If you create a variable without the --JSONPaths parameter then it is considered a 'value variable'. In these cases pypeline will locate all instances of `${env.<variable name>}` throughout your rule tree and replace them with the value you have specified per environment. Value variables can be either string, integer or boolean, though you cannot create a boolean variable from the command line and must edit the variableDefinitions.json file manually to achieve this. Boolean variables can be used to enable or disable behaviours that you do not wish to be removed from one environment or another.

Alternatively, you can specify the location(s) in JSON Path format of where you would like to replace your variable. For example, if you wanted to replace the default origin hostname you could specify a JSON Path of `$.rules.behaviors[0].options.hostname`. The benefit of this approach is that you do not need to touch your templates, and as such re-importing them would not require you to update your local copy.

### Environment-specific rules

Pypeline has the capability of only including a rule or rules in a given set of environments. This feature is often achieved by simply setting a PMUSER variable with the environment name, and scoping rules to match. However, there are various rules which cannot exist under match conditions (such as Siteshield), for which this feature should achieve the desired result. 

Environment scoping can be achieved by editing your property templates (either in JSON or in the Property Manager UI) and adding a comment in the desired rule of the form

`pypeline_env:dev,prod;`

Each rule will be checked for this tag, and will be removed if the tag exists but the current environment is not included in the comment, e.g. if a rule contains the comment above but the environment being evaluted is `staging` then the rule in question would be removed from the merged rule tree.

The pypeline_env can contain any number of environments, and can exist in any position within the comment field. The trailing semi-colon is only required if further comments will follow, as it acts as a delimiter.

> Note: Scoping is performed at the rule level, not the behavior level. If you wish to scope a single behavior move it into its own child rule

Have a look at the Siteshield.json file in the example/demopipeline/templates directory for an example of this in action.

### Cross-Compatibility

By default, when you import rules to json snippets, the path for a given #include is relative to the file in which it appears, i.e. if `rule1/rule2.json` is referencing a file called `rule3.json` the statement will be `#include:rule3.json`. However, JSON snippets are often used in the Akamai Terraform provider, which expects #include paths to be relative to the main.json, rather than the file where they are created. In our example this would be `#include:rule1/rule3.json`. Pypeline can read files in both modes, but if you wish to use this format during the `import` command you need to include teh --useFullPaths option.

### Examples

1. Create a new pipeline in the local directory called `mypipeline`

```shell
python pypeline.py create --name mypipeline
```

2. Import the latest version of an existing property to your pipeline as its templates

```shell
python pypeline.py --folder mypipeline import --property www.example.com
```

2a. Import the latest version of an existing property to your pipeline as its templates, but use include paths relative to the main json file.

```shell
python pypeline.py --folder mypipeline import --property www.example.com --useFUllPaths
```

3. Import a specific version of an existing property to your pipeline as its templates

```shell
python pypeline.py --folder mypipeline import --property www.example.com --version 10
```

4. Add an environment to your pipeline

```shell
python pypeline.py --folder mypipeline add-environment --name dev --property dev.example.com
```

5. Add a value variable to your pipeline

```shell
python pypeline.py --folder mypipeline add-variable --name default_origin
```

6. Add a value variable with a default value to your pipeline

```shell
python pypeline.py --folder mypipeline add-variable --name default_origin --default origin.example.com
```

6. Add a positional variable to your pipeline

```shell
python pypeline.py --folder mypipeline add-variable --name default_origin --JSONPaths $.rules.behaviors[0].options.hostname
```

6. Add a positional variable with multiple locations to your pipeline

```shell
python pypeline.py --folder mypipeline add-variable --name default_origin --JSONPaths $.rules.behaviors[0].options.hostname,$.rules.children[3].behaviors[0].options.hostname
```

7. Push updates to a given environment in your pipeline, creating a new version if required

```shell
python pypeline.py --folder mypipeline update --environment dev --notes 'commit:12345'
```

8. Activate an environment in your pipeline to staging

```shell
python pypeline.py --folder mypipeline activate --environment dev --network Staging --email noreply@example.com
```

9. Update the rule format in use in your property, and re-import template rules in that format

```shell
python pypeline.py --folder mypipeline set-ruleformat --ruleFormat v2023-01-05
python pypeline.py --folder mypipeline import --property www.example.com --ruleFormat v2023-01-05
```

10. Display the status of all environments in your pipeline

```shell
python pypeline.py --folder mypipeline status
```

11. Display the status of a single environment in your pipeline

```shell
python pypeline.py --folder mypipeline status --environment dev 
```

### Manual updates

While commands such as `add-environment` and `add-variable` are included in the tool there is nothing preventing users from manually editing `pipeline.json`, `variableDefinitions.json` or any other file contained in the pipeline folder. Manual changes should cause no issues, so long as they retain the schema of the automatically created files.
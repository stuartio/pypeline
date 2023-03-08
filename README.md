## Pypeline

Python-based implementation of pipeline logic to manage properties. The following operations are supported:

- Import - Will download a property, break it down into multiple JSON files (one per rule) and save to the /template directory under your pipeline folder
- Update - Will merge variables from the shared variableDefinitions.json and values from an environment's variables.json files and superimpose them over the contents of the templates directory. This is then pushed to PAPI to update the property of that environment
- Merge - Will perform similarly to Update, but will not push to PAPI. Instead a file is written to the dist folder under your pipeline folder
- Activate - Will activate a given environment on either Staging or Production

### Variable Setup

In order to make it easier for you to sync UI changes down, you no longer need to replace values within the templates folder. Instead each variable is defined with a JSONPath to where it would be located in the combined rule tree. If you move behaviours you will need to update these paths, and there is currently no automated way to infer paths.
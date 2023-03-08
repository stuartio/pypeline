from .base import Akamai

class Property(Akamai):
    
    def listGroups(self):
        path = '/papi/v1/groups'
        result = self.get(path, None, None)
        return result['groups']['items']

    def listHostnames(self, propertyId, version):
        path = '/papi/v1/properties/{propertyId}/versions/{version}/hostnames'.format(propertyId = propertyId, version = version)
        result = self.get(path, None, None)
        return result['hostnames']['items']

    def getProperty(self, propertyId):
        path = '/papi/v1/properties/{propertyId}'.format(propertyId = propertyId)
        result = self.get(path, None, None)
        return result['properties']['items'][0]
    
    def getPropertyRules(self, propertyId, propertyVersion, ruleFormat = None):
        path = '/papi/v1/properties/{propertyId}/versions/{propertyVersion}/rules'.format(propertyId = propertyId, propertyVersion = propertyVersion)
        if ruleFormat is not None:
            headers = {
                'Accept':'application/vnd.akamai.papirules.{ruleFormat}+json'.format(ruleFormat = ruleFormat)
            }
        result = self.get(path, None, None)
        return result

    def bulkSearch(self, body):
        path = '/papi/v1/bulk/rules-search-requests-synch'
        result = self.post(path, None, None, body)
        return result['results']

    def findProperty(self, propertyName):
        path = '/papi/v1/search/find-by-value'
        body = { "propertyName": propertyName }
        result = self.post(path, None, None, body)
        return result['versions']['items']

    def newPropertyVersion(self, propertyId, createFromVersion):
        path = '/papi/v1/properties/{propertyId}/versions'.format(propertyId = propertyId)
        body = { "createFromVersion": createFromVersion }
        result = self.post(path, None, None, body)
        return result['versionLink']

    def updateVersion(self, propertyId, propertyVersion, rules, ruleFormat):
        path = '/papi/v1/properties/{propertyId}/versions/{propertyVersion}/rules'.format(propertyId = propertyId, propertyVersion = propertyVersion)
        headers = []
        if ruleFormat is not None:
            headers = {
                'Content-Type':'application/vnd.akamai.papirules.{ruleFormat}+json'.format(ruleFormat = ruleFormat)
            }
        result = self.put(path, None, headers, rules)
        return result

    def activate(self, propertyId, propertyVersion, network, emailaddresses, notes = None):
        path = '/papi/v1/properties/{propertyId}/activations'.format(propertyId = propertyId)
        body = {
            "acknowledgeAllWarnings": True,
            "activationType": "ACTIVATE",
            "network": network,
            "notifyEmails": emailaddresses.split(),
            "note": notes,
            "propertyVersion": propertyVersion
        }

        result = self.post(path, None, None, body)
        return result
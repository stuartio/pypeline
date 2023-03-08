from akamai.edgegrid import EdgeGridAuth, EdgeRc
import os.path
import os
import requests
import json

def get_credentials_from_edgerc(edgerc_path, section):
    expanded_path = os.path.expanduser(edgerc_path)
    if os.path.exists(expanded_path):
        edgerc = EdgeRc(edgerc_path)
        credentials = {
            'host':             edgerc.get(section, 'host'),
            'client_token':     edgerc.get(section, 'client_token'),
            'access_token':     edgerc.get(section, 'access_token'),
            'client_secret':    edgerc.get(section, 'client_secret')
        }
        return credentials
    else:
        return None

def get_credentials_from_environment(section):
    credentials = {}
    prefix = ''
    if section.lower() != 'default':
        prefix = section.upper() + '_'
    
    credential_elements = ['host','client_token','access_token','client_secret']
    for element in credential_elements:
        env_var = 'AKAMAI_' + prefix + element
        if os.getenv(env_var) is not None:
            credentials[element] = os.getenv(env_var)
        else:
            return None

    return credentials

class Akamai:
    def __init__(self, edgerc, section, accountSwitchKey):
        self.DEFAULT_EDGERC = '~/.edgerc'
        self.DEFAULT_SECTION = 'default'

        self.edgerc = edgerc
        if section is not None:
            self.section = section
        else:
            self.section = self.DEFAULT_SECTION
        self.accountSwitchKey = accountSwitchKey
        self.credentials = None

        self.session = requests.Session()

        ## Check for creds in EdgeRC, if supplied
        if edgerc is not None:
            self.credentials = get_credentials_from_edgerc(self.edgerc, self.section)

        ## Next, check env vars
        if self.credentials is None:
            self.credentials = get_credentials_from_environment(self.section)

        ## Finally, check edgerc path
        if self.credentials is None:
            self.credentials = get_credentials_from_edgerc(self.DEFAULT_EDGERC, self.section)

        ## If no luck from all options, panic.
        if self.credentials is None:
            raise(Exception('Failed to find Akamai credentials from EdgeRC or Environment Variables'))
        
        self.baseurl = 'https://' + self.credentials['host']
        self.session.auth = EdgeGridAuth(
            client_token = self.credentials['client_token'],
            client_secret = self.credentials['client_secret'],
            access_token = self.credentials['access_token']
        )
        
        self.headers = {
            'content-type': 'application/json',
            'PAPI-Use-Prefixes': 'false'
        }

    def getEdgeRCLocation(self):
        return self.edgerc

    def getSection(self):
        return self.section
    
    def getHost(self):
        return self.credentials['host']

    def getClientToken(self):
        return self.credentials['client_token']

    def getAccessToken(self):
        return self.credentials['access_token']

    def getClientSecret(self):
        return self.credentials['client_secret']
    
    def getAccountSwitchKey(self):
         return self.accountSwitchKey

    def do(self, method, path, query, headers, body = None):
        # Append accountSwitchKey query param
        if self.accountSwitchKey is not None:
            if query is not None:
                if not query.startswith("?"):
                    query = "?" + query
                query += "&accountSwitchKey=%s" % self.accountSwitchKey
            else:
                query = "?accountSwitchKey=%s" % self.accountSwitchKey

        # Append query
        if query is not None:
            request_url = self.baseurl + path + query
        else:
            request_url = self.baseurl + path

        # Override headers
        if headers is not None:
            for header in headers.keys():
                self.headers[header] = headers[header]

        # Body could be a dict. If so convert to json string
        if not isinstance(body, str):
            body = json.dumps(body)

        try:
            if method == 'GET':
                result = self.session.get(request_url, headers = self.headers, data = body)
            elif method == 'POST':
                result = self.session.post(request_url, headers = self.headers, data = body)
            elif method == 'PUT':
                result = self.session.put(request_url, headers = self.headers, data = body)
        except requests.exceptions.RequestException as err:
            print (err)
        
        # 4xx/5xx errors do not always throw, so manually do so
        if result.status_code >= 400:
            raise ValueError(str(result.status_code) + ' response: ' + result.text)
        else:
            return json.loads(result.content)

    def get(self, path, query, headers):
        return self.do('GET', path, query, headers)

    def post(self, path, query, headers, body):
        return self.do('POST', path, query, headers, body)

    def put(self, path, query, headers, body):
        return self.do('PUT', path, query, headers, body)
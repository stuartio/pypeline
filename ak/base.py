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
            "host": edgerc.get(section, "host"),
            "client_token": edgerc.get(section, "client_token"),
            "access_token": edgerc.get(section, "access_token"),
            "client_secret": edgerc.get(section, "client_secret"),
            "account_key": edgerc.get(section, "account_key", fallback=None),
        }
        return credentials
    else:
        return None


def get_credentials_from_environment(section):
    credentials = {}
    prefix = ""
    if section.lower() != "default":
        prefix = section.upper() + "_"

    credential_elements = ["host", "client_token", "access_token", "client_secret"]
    for element in credential_elements:
        env_var = "AKAMAI_" + prefix + element.upper()
        if os.getenv(env_var) is not None:
            credentials[element] = os.getenv(env_var)
        else:
            # If any element is missing return None
            return None

    # Find account_key, if it exists
    env_account_key = "AKAMAI_" + prefix + "ACCOUNT_KEY"
    credentials["account_key"] = os.getenv(env_account_key)

    return credentials


class Akamai:
    def __init__(self, edgerc=None, section=None, accountSwitchKey=None):
        self.DEFAULT_EDGERC = "~/.edgerc"
        self.DEFAULT_SECTION = "default"

        if edgerc is not None:
            self.edgerc = edgerc
        if section is not None:
            self.section = section
        else:
            self.section = self.DEFAULT_SECTION
        self.credentials = None

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
            raise (Exception("Failed to find Akamai credentials from EdgeRC or Environment Variables"))

        # Override ASK with supplied variable, if present
        if accountSwitchKey:
            self.credentials["account_key"] = accountSwitchKey

    def get_edgerc(self):
        return self.edgerc

    def get_section(self):
        return self.section

    def get_host(self):
        return self.credentials["host"]

    def get_client_token(self):
        return self.credentials["client_token"]

    def get_access_token(self):
        return self.credentials["access_token"]

    def get_client_secret(self):
        return self.credentials["client_secret"]

    def get_account_key(self):
        return self.credentials["account_key"]

    def get_credentials(self):
        return self.credentials

    def do(self, method, path, query, headers, body=None):
        self.baseurl = "https://" + self.credentials["host"]

        self.headers = {"PAPI-Use-Prefixes": "false", "accept": "application/json", "connection": "close"}

        if body is not None:
            self.headers["content-type"] = "application/json"

        # Append accountSwitchKey query param
        if self.credentials["account_key"] is not None:
            if query is not None:
                query += "&accountSwitchKey=%s" % self.credentials["account_key"]
            else:
                query = "?accountSwitchKey=%s" % self.credentials["account_key"]

        # Remove errant ? at the start of query to avoid duplicates
        if query is not None and query.startswith("?"):
            query = query[1:]

        # Append query
        if query is not None:
            request_url = self.baseurl + path + "?" + query
        else:
            request_url = self.baseurl + path

        # Override headers
        if headers is not None:
            for header in headers.keys():
                self.headers[header] = headers[header]

        # Body could be a dict. If so convert to json string
        if not isinstance(body, str):
            body = json.dumps(body)

        ## Property handle keep-alives and other open sessions
        with requests.Session() as session:
            session.auth = EdgeGridAuth(
                client_token=self.credentials["client_token"],
                client_secret=self.credentials["client_secret"],
                access_token=self.credentials["access_token"],
            )

            try:
                if method == "GET":
                    result = session.get(request_url, headers=self.headers)
                elif method == "POST":
                    result = session.post(request_url, headers=self.headers, data=body)
                elif method == "PUT":
                    result = session.put(request_url, headers=self.headers, data=body)
            except requests.exceptions.RequestException as err:
                print(err)
                return

            # 4xx/5xx errors do not always throw, so manually do so
            if result is not None and result.status_code >= 400:
                raise ValueError(str(result.status_code) + " response: " + result.text)
            else:
                return json.loads(result.content)

    def get(self, path, query=None, headers=None):
        return self.do("GET", path, query, headers)

    def post(self, path, query=None, headers=None, body=None):
        return self.do("POST", path, query, headers, body)

    def put(self, path, query=None, headers=None, body=None):
        return self.do("PUT", path, query, headers, body)

#!/usr/bin/env python3
"""
Module to interface with a Matrix Homeserver instance and regularly post others'
participating Homeserver versions to a room.
"""

import configparser
import json
import logging
import os
import time

import requests

FEDTEST_URL = 'https://federationtester.matrix.org/api/report?server_name='


def member_server(user_id):
    """
    Function to return the server name from the user_id

    user_id: (str) User ID to parse

    Returns: (str) server
    """

    if user_id[0] != '@':
        return None

    return user_id.split(':')[1]


def query_homeserver_version(server):
    """
    Function to query the Federation Tester to retrieve the running version
    for a server

    server: (str) Server to get version for

    Returns: (str) Version string of the server
    """
    try:
        req = requests.get(f'{FEDTEST_URL}{server}', timeout=10000)
    except requests.exceptions.Timeout:
        logging.warning('Timeout contacting the Federation Tester')
        return '[TIMEOUT]'

    data = json.loads(req.text)

    if not data['FederationOK']:
        return '[OFFLINE]'

    try:
        return data['Version']['version']
    except KeyError:
        return '[ERROR]'


class Matrix:
    """
    Class for the Matrix Homeserver
    """

    def __init__(self, endpoint):
        """
        Initialisation method.

        endpoint: (str) Endpoint URL of the Matrix Homeserver to connect to
        """
        self.clienturl = f'{endpoint}/_matrix/client/r0'
        self.token = None
        self.room_id = None
        self.room_url = None


    def api_call(self, method, url, data=None):
        """
        Call the API with the parameter defined.

        Returns: (str) Output from the REST API call
        """
        req = method(
            url,
            headers={'Authorization': f'Bearer {self.token}'},
            data=data,
        )

        if req.status_code != 200:
            logging.error(req.text)
            return ''

        return req.text


    def login(self, username, password):
        """
        Login to the Homeserver

        username: (str) Username to login with
        password: (str) Password for username
        """
        login_url = f'{self.clienturl}/login'
        req = requests.get(login_url)
        flow = json.loads(req.text)['flows'][0]['type']

        req = self.api_call(
            requests.post,
            login_url,
            data=f'{{ "type": "{flow}",'
                 f'"user": "{username}",'
                 f'"password": "{password}" }}',
        )

        self.token = json.loads(req)['access_token']


    def join_room(self, room_id):
        """
        Join the specified room

        room_id: (str) Homeserver room ID
        """

        self.room_id = room_id
        self.room_url = f'{self.clienturl}/rooms/{room_id}'

        self.api_call(
            requests.post,
            f'{self.room_url}/join',
            data='{}',
        )


    def room_members(self):
        """
        Return a list of the room members

        Returns: (list) [(str) member]
        """

        req = self.api_call(
            requests.get,
            f'{self.room_url}/joined_members',
        )
        return json.loads(req)['joined'].keys()


    def message(self, text):
        """
        Send a message to the currently set room

        text: (str) Message to send
        """

        self.api_call(
            requests.put,
            f'{self.room_url}/send/m.room.message/{time.time()}',
            data=f'{{'
                 f'"msgtype": "m.text",'
                 f'"body": "{text}",'
                 f'"format": "org.matrix.custom.html",'
                 f'"formatted_body": "<pre><code>{text}</code></pre>"'
                 f'}}',
        )


class ServerList(list):
    """
    Class to handle the list of servers
    """
    def __str__(self):
        maxlen_server = max(
            len('Homeserver'),
            len(max(self, key=lambda i: len(i['host']))['host'])
        )
        maxlen_version = max(
            len('Version'),
            len(max(self, key=lambda i: len(i['version']))['version'])
        )

        version_table = ''
        version_table += f'| {"Homeserver".ljust(maxlen_server)} | '
        version_table += f'{"Version".ljust(maxlen_version)} |\\n'
        version_table += f'| {"".ljust(maxlen_server, "-")} | '
        version_table += f'{"".ljust(maxlen_version, "-")} |\\n'
        for server in self:
            version_table += f'| {server["host"].ljust(maxlen_server)} | '
            version_table += f'<a href=\\"{FEDTEST_URL}{server["host"]}\\">{server["version"]}</a>'
            version_table += f'{"".ljust(maxlen_version - len(server["version"]))} |\\n'

        return str(version_table)


if __name__ == '__main__':
    def main():
        """
        Main program logic
        """
        configfile = os.path.splitext(__file__)[0] + '.conf'
        config = configparser.ConfigParser(allow_no_value=True)
        config.read_file(open(configfile))

        matrix = Matrix(endpoint=config.get('homeserver', 'url'))
        matrix.login(
            config.get('homeserver', 'username'),
            config.get('homeserver', 'password'),
        )
        matrix.join_room(config.get('homeserver', 'room_id'))

        dead_servers = list(config['dead_servers'].keys())

        # Return a unique list of Homeservers with any dead ones removed
        member_servers = sorted(
            list(
                set(map(member_server, matrix.room_members())) - set(dead_servers)
            )
        )

        srvlst = ServerList()
        for server in member_servers:
            srvlst.append(
                {
                    'host': server,
                    'version': query_homeserver_version(server),
                }
            )

        matrix.message(str(srvlst))

    main()

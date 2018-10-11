from __future__ import unicode_literals
import argparse
from datetime import datetime
import appdirs
import json
import os
import stat

LISTS_PATH = os.path.join(appdirs.user_config_dir("slack-cli"), "id-cache.json")

from . import errors
from . import names
from . import slack
from . import token



def get_parser(description):
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("-t", "--token",
                        help="Explicitely specify Slack API token which will be saved to {}.".format(token.TOKEN_PATH))
    parser.add_argument("-T", "--team", help="""
        Team domain to interact with. This is the name that appears in the
        Slack url: https://xxx.slack.com. Use this option to interact with
        different teams. If unspecified, default to the team that was last used.
    """)
    return parser

def parse_args(parser):
    """
    Parse cli arguments and initialize slack client.
    """
    args = parser.parse_args()
    slack.init(user_token=args.token, team=args.team)
    return args

def get_source_id(source_name):
    sources = get_sources([source_name])
    if not sources:
        raise errors.SourceDoesNotExistError(source_name)
    return sources[0]["id"]

def get_source_ids(source_names):
    return {
        s['id']: s['name'] for s in get_sources(source_names)
    }

def get_sources(source_names):
    def filter_objects(objects):
        return [
            obj for obj in objects if len(source_names) == 0 or obj['name'] in source_names
        ]

    def load_lists():
        lists = []
        if os.path.exists(LISTS_PATH):
            with open(LISTS_PATH) as lists_file:
                lists = json.load(lists_file)
        return lists

    sources = []
    lists = load_lists()
    sources += filter_objects(lists['channels'])
    sources += filter_objects(lists['groups'])
    sources += filter_objects(lists['members'])
    if len(sources) > 0:
        return sources

    sources = []
    sources += filter_objects(slack.client().channels.list().body['channels'])
    sources += filter_objects(slack.client().groups.list().body['groups'])
    sources += filter_objects(slack.client().users.list().body['members'])
    return sources

def upload_file(path, destination_id):
    return slack.client().files.upload(path, channels=destination_id)


def search_messages(source_name, count=20):
    messages = []
    page = 1
    while len(messages) < count:
        response_body = slack.client().search.messages("in:{}".format(source_name), page=page, count=1000).body
        # Note that in the response, messages are sorted by *descending* date
        # (most recent first)
        messages = response_body["messages"]["matches"][::-1] + messages
        paging = response_body["messages"]["paging"]
        if paging["page"] == paging["pages"]:
            break
        page += 1

    # Print the last count messages
    for message in messages[-count:]:
        print(format_message(source_name, message))

def format_message(source_name, message):
    time = datetime.fromtimestamp(float(message['ts']))
    # Some bots do not have a 'user' entry, but only a 'username'
    username = names.username(message['user']) if message.get('user') else message['username']
    return "[@{} {}] {}: {}".format(
        source_name, time.strftime("%Y-%m-%d %H:%M:%S"),
        username, message['text']
    )

def cache_source_ids():
    lists = {}
    client = slack.client()
    lists['channels'] = []
    for obj in client.channels.list().body['channels']:
        lists['channels'].append({'id': obj['id'], 'name': obj['name']})
    lists['groups'] = []
    for obj in client.groups.list().body['groups']:
        lists['groups'].append({'id': obj['id'], 'name': obj['name']})
    lists['members'] = []
    for obj in client.users.list().body['members']:
        lists['members'].append({'id': obj['id'], 'name': obj['name'], 'display_name': obj['profile']['display_name']})

    with open(LISTS_PATH, 'w') as lists_file:
        json.dump(lists, lists_file, sort_keys=True, indent=4)
    os.chmod(LISTS_PATH, stat.S_IREAD | stat.S_IWRITE)

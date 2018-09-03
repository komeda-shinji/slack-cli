import subprocess
import sys
import select

from . import errors
from . import slack
from . import stream
from . import utils


def main():
    try:
        sys.exit(run())
    except errors.SourceDoesNotExistError as e:
        sys.stderr.write("Channel, group or user '{}' does not exist".format(e.args[0]))
        sys.exit(1)
    except errors.InvalidSlackToken as e:
        sys.stderr.write("Invalid Slack token: '{}'".format(e.args[0]))
        sys.exit(1)

def run():
    parser = utils.get_parser("""Send, pipe, upload and receive Slack messages from the CLI""")
    group_send = parser.add_argument_group("Send messages")
    group_send.add_argument("-d", "--dst", help="Send message to a Slack channel, group or username")
    group_send.add_argument("-f", "--file", help="Upload file")
    group_send.add_argument("--pre", action="store_true", help="Send as verbatim `message`")
    group_send.add_argument(
        "--run", action="store_true",
        help="Run the message as a shell command and send both the message and the command output"
    )
    group_send.add_argument("messages", nargs="*",
                            help="Messages to send (messages can also be sent from standard input)")

    group_receive = parser.add_argument_group("Receive messages")
    group_receive.add_argument("-s", "--src", action='append',
                               help="Receive messages from a Slack channel, group or username")
    group_receive.add_argument("-l", "--last", type=int,
                               help="Print the last N messages")
    group_send.add_argument("--save-cache", action="store_true", help="Create source id cache")

    args = utils.parse_args(parser)

    # Debug command line arguments
    error_message = args_error_message(args)
    if error_message:
        sys.stderr.write(error_message)
        parser.print_help()
        return 1

    # Save cache file
    if args.save_cache:
        save_cache()
        return 0

    # Stream content
    if args.src and args.last is None:
        stream.receive(args.src)
        return 0

    # Print last messages
    if args.src and args.last is not None:
        last_messages(args.src, args.last)
        return 0

    # Send file
    if args.file:
        upload_file(args.dst, args.file)
        return 0

    # Pipe content
    if not args.messages:
        pipe(args.dst, pre=args.pre)
        return 0

    # Send messages
    for message in args.messages:
        if args.run:
            run_command(args.dst, message)
        else:
            send_message(args.dst, message, pre=args.pre)
    return 0

# pylint: disable=too-many-return-statements
def args_error_message(args):
    if args.save_cache and (not args.dst and not args.src):
        return None
    if args.dst and args.src:
        return "Incompatible arguments: --src and --dst\n"
    if not args.dst and not args.src:
        return "Invalid arguments: one of --src or --dst must be specified\n"
    if args.dst and args.last:
        return "Incompatible arguments: --dst and --last\n"
    if args.src and args.file:
        return "Incompatible arguments: --src and --file\n"
    if args.file and args.messages:
        return "Incompatible arguments: `messages` and --file\n"

    return None

######### Receive

def last_messages(sources, count):
    for source in sources:
        utils.search_messages(source, count=count)

######### Send

def pipe(destination, pre=False):
    destination_id = utils.get_source_id(destination)
    if sys.stdin.isatty():
        for line in sys.stdin:
            line = line.strip()
            if line:
                slack.post_message(destination_id, line, pre=pre)
    else:
        lines = []
        while sys.stdin in select.select([sys.stdin], [], [], 0)[0]:
            line = sys.stdin.readline()
            if not line: break
            lines.append(line)
        if len(lines) > 0:
            slack.post_message(destination_id, ''.join(lines), pre=pre)

def run_command(destination, command):
    destination_id = utils.get_source_id(destination)
    command_result = subprocess.check_output(command, shell=True)
    message = "$ " + command + "\n" + command_result.decode("utf-8")
    slack.post_message(destination_id, message, pre=True)

def send_message(destination, message, pre=False):
    destination_id = utils.get_source_id(destination)
    slack.post_message(destination_id, message, pre=pre)

def upload_file(destination, path):
    destination_id = utils.get_source_id(destination)
    utils.upload_file(path, destination_id)

def save_cache():
    utils.cache_source_ids()

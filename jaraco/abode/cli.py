"""Command-line interface."""

import argparse
import code
import contextlib
import getpass
import importlib
import json
import logging
import os
import time

import keyring
from more_itertools import always_iterable

import jaraco.abode
from jaraco.context import suppress
from jaraco.functools import pass_none

from . import Client
from .helpers import timeline as TIMELINE
from .helpers import urls

log = logging.getLogger(__name__)


@suppress(ImportError)
def enable_color():
    import colorlog

    fmt = "%(asctime)s %(levelname)s (%(threadName)s) [%(name)s] %(message)s"
    colorfmt = f"%(log_color)s{fmt}%(reset)s"
    datefmt = '%Y-%m-%d %H:%M:%S'

    handler = logging.getLogger().handlers[0]
    handler.setFormatter(
        colorlog.ColoredFormatter(
            colorfmt,
            datefmt=datefmt,
            reset=True,
            log_colors=dict(
                DEBUG='cyan',
                INFO='green',
                WARNING='yellow',
                ERROR='red',
                CRITICAL='red',
            ),
        )
    )


def setup_logging(log_level=logging.INFO):
    """Set up the logging."""
    logging.basicConfig(level=log_level)

    # Suppress overly verbose logs from libraries that aren't helpful
    logging.getLogger('requests').setLevel(logging.WARNING)
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('aiohttp.access').setLevel(logging.WARNING)

    enable_color()
    logging.getLogger().setLevel(log_level)


def build_parser():
    """
    Get parsed arguments.

    >>> parser = build_parser()
    """
    parser = argparse.ArgumentParser("abode")

    parser.add_argument(
        '-u', '--username', help='Username', default=os.environ.get('ABODE_USERNAME')
    )

    parser.add_argument('-p', '--password', help='Password')

    parser.add_argument('--mfa', help='Multifactor authentication code')

    parser.add_argument(
        '--mode',
        help='Output current alarm mode',
        default=False,
        action="store_true",
    )

    parser.add_argument(
        '--arm',
        metavar='mode',
        help='Arm alarm to mode',
    )

    parser.add_argument(
        '--set',
        metavar='setting=value',
        help='Set setting to a value',
        action='append',
    )

    parser.add_argument(
        '--devices',
        help='Output all devices',
        default=False,
        action="store_true",
    )

    parser.add_argument(
        '--device',
        metavar='device_id',
        help='Output one device for device_id',
        action='append',
    )

    parser.add_argument(
        '--interact',
        default=False,
        action="store_true",
        help="interact with the client after running other operations",
    )

    parser.add_argument(
        '--json',
        metavar='device_id',
        help='Output the json for device_id',
        action='append',
    )

    parser.add_argument(
        '--on',
        metavar='device_id',
        help='Switch on a given device_id',
        action='append',
    )

    parser.add_argument(
        '--off',
        metavar='device_id',
        help='Switch off a given device_id',
        action='append',
    )

    parser.add_argument(
        '--lock',
        metavar='device_id',
        help='Lock a given device_id',
        action='append',
    )

    parser.add_argument(
        '--unlock',
        metavar='device_id',
        help='Unlock a given device_id',
        action='append',
    )

    parser.add_argument(
        '--automations',
        help='Output all automations',
        default=False,
        action="store_true",
    )

    parser.add_argument(
        '--activate',
        metavar='automation_id',
        help='Activate (enable) an automation by automation_id',
        action='append',
    )

    parser.add_argument(
        '--deactivate',
        metavar='automation_id',
        help='Deactivate (disable) an automation by automation_id',
        action='append',
    )

    parser.add_argument(
        '--trigger',
        metavar='automation_id',
        help='Trigger (apply) a manual (quick) automation by automation_id',
        action='append',
    )

    parser.add_argument(
        '--capture',
        metavar='device_id',
        help='Trigger a new image capture for the given device_id',
        action='append',
    )

    parser.add_argument(
        '--stream',
        metavar='device_id=location/details.json',
        help='Start a new KVS stream for the given device_id and save the details to a file',
        action='append',
    )

    parser.add_argument(
        '--image',
        metavar='device_id=location/image.jpg',
        help='Save an image from a camera (if available) to the given path',
        action='append',
    )

    parser.add_argument(
        '--listen',
        help='Block and listen for device_id',
        default=False,
        action="store_true",
    )

    parser.add_argument(
        '--debug',
        help='Enable debug logging',
        default=False,
        action="store_true",
    )

    parser.add_argument(
        '--quiet',
        help='Output only warnings and errors',
        default=False,
        action="store_true",
    )

    return parser


def _create_client_instance(args):
    return Client(
        username=args.username,
        password=args.password,
        get_devices=args.mfa is None,
    )


@contextlib.contextmanager
def _log_errors_and_logout(client):
    try:
        yield client
    except jaraco.abode.Exception as exc:
        log.error(exc)
    finally:
        client.logout()


def _device_print(dev, append=''):
    log.info("%s%s", dev.desc, append)


def _device_callback(dev):
    _device_print(dev, ", At: " + time.strftime("%Y-%m-%d %H:%M:%S"))


def _timeline_callback(resp):
    event_code = int(resp['event_code'])
    if 5100 <= event_code <= 5199:
        # Ignore device changes
        return

    tmpl = '{event_name} - {event_type} at {date} {time}'
    log.info(tmpl.format_map(resp))


class Dispatcher:  # pragma: no cover
    def __init__(self, client, args):
        self.client = client
        self.args = args

    def dispatch(self):
        self.login()
        self.output_current_mode()
        self.change_system_mode()
        self.set_setting()
        self.switch_on()
        self.switch_off()
        self.lock()
        self.unlock()
        self.output_json()
        self.print_all_automations()
        self.enable_automation()
        self.disable_automation()
        self.trigger_automation()
        self.trigger_image_capture()
        self.start_kvs_stream()
        self.save_camera_image()
        self.print_all_devices()
        self.print_specific_devices()
        self.start_device_change_listener()
        self.interact()

    def login(self):
        if not self.args.mfa:
            return
        self.client.login(mfa_code=self.args.mfa)
        # fetch devices from Abode
        self.client.get_devices()

    def interact(self):
        if not self.args.interact:
            return

        with contextlib.suppress(ImportError):
            # Allow Up/Down/History in the console
            importlib.import_module('readline')

        banner = 'Interact with the Abode `client`.'
        code.InteractiveConsole(dict(client=self.client)).interact(banner=banner)

    def output_current_mode(self):
        if not self.args.mode:
            return
        log.info("Current alarm mode: %s", self.client.get_alarm().mode)

    def change_system_mode(self):
        if not self.args.arm:
            return
        if self.client.get_alarm().set_mode(self.args.arm):
            log.info("Alarm mode changed to: %s", self.args.arm)
        else:
            log.warning("Failed to change alarm mode to: %s", self.args.arm)

    def set_setting(self):
        for setting in always_iterable(self.args.set):
            key, _, val = setting.partition("=")
            if self.client.set_setting(key, val):
                log.info("Setting %s changed to %s", key, val)

    def _get_device(self, id):
        device = self.client.get_device(id)
        if not device:
            log.warning("Could not find device with id: %s", id)
        return device

    def switch_on(self):
        for device_id in always_iterable(self.args.on):
            self._switch_on(self._get_device(device_id))

    @staticmethod
    @pass_none
    def _switch_on(device):
        if device.switch_on():
            log.info("Switched on device with id: %s", device.id)

    def switch_off(self):
        for device_id in always_iterable(self.args.off):
            self._switch_off(self._get_device(device_id))

    @staticmethod
    @pass_none
    def _switch_off(device):
        if device.switch_off():
            log.info("Switched off device with id: %s", device.id)

    def lock(self):
        for device_id in always_iterable(self.args.lock):
            self._lock(self._get_device(device_id))

    @staticmethod
    @pass_none
    def _lock(device):
        if device.lock():
            log.info("Locked device with id: %s", device.id)

    def unlock(self):
        for device_id in always_iterable(self.args.unlock):
            self._unlock(self._get_device(device_id))

    @staticmethod
    @pass_none
    def _unlock(device):
        if device.unlock():
            log.info("Unlocked device with id: %s", device.id)

    def output_json(self):
        for device_id in always_iterable(self.args.json):
            self._output_json(self._get_device(device_id))

    @staticmethod
    @pass_none
    def _output_json(device):
        print(
            json.dumps(
                device._state,
                sort_keys=True,
                indent=4,
                separators=(',', ': '),
            )
        )

    def print_all_automations(self):
        if not self.args.automations:
            return
        for automation in self.client.get_automations():
            _device_print(automation)

    def _get_automation(self, id):
        automation = self.client.get_automation(id)
        if not automation:
            log.warning("Could not find automation with id: %s", id)
        return automation

    def enable_automation(self):
        for automation_id in always_iterable(self.args.activate):
            self._enable_automation(self._get_automation(automation_id))

    @staticmethod
    @pass_none
    def _enable_automation(automation):
        if automation.enable(True):
            log.info("Activated automation with id: %s", automation.id)

    def disable_automation(self):
        for automation_id in always_iterable(self.args.deactivate):
            self._disable_automation(self._get_automation(automation_id))

    @staticmethod
    @pass_none
    def _disable_automation(automation):
        if automation.enable(False):
            log.info("Deactivated automation with id: %s", automation.id)

    def trigger_automation(self):
        for automation_id in always_iterable(self.args.trigger):
            self._trigger_automation(self._get_automation(automation_id))

    @staticmethod
    @pass_none
    def _trigger_automation(automation):
        if automation.trigger():
            log.info("Triggered automation with id: %s", automation.id)

    def trigger_image_capture(self):
        for device_id in always_iterable(self.args.capture):
            self._trigger_image_capture(self._get_device(device_id))

    @staticmethod
    @pass_none
    def _trigger_image_capture(device):
        if device.capture():
            log.info("Image requested from device with id: %s", device.id)
        else:
            log.warning("Failed to request image from device with id: %s", device.id)

    def start_kvs_stream(self):
        for keyval in always_iterable(self.args.stream):
            dev, _, loc = keyval.partition("=")
            self._start_kvs_stream(self._get_device(dev), loc)

    @staticmethod
    @pass_none
    def _start_kvs_stream(device, path):
        if not device.start_kvs_stream(path):
            log.warning("Failed to start KVS stream for device with id: %s", device.id)

    def save_camera_image(self):
        for keyval in always_iterable(self.args.image):
            dev, _, loc = keyval.partition("=")
            self._save_camera_image(self._get_device(dev), loc)

    @staticmethod
    @pass_none
    def _save_camera_image(device, path):
        try:
            if device.refresh_image() and device.image_to_file(path):
                log.info("Saved image to %s for device id: %s", path, device.id)
        except jaraco.abode.Exception as exc:
            log.warning("Unable to save image: %s", exc)

    def print_all_devices(self):
        if not self.args.devices:
            return
        for device in self.client.get_devices():
            _device_print(device)

    def print_specific_devices(self):
        for device_id in always_iterable(self.args.device):
            device = self._get_device(device_id)
            device and self._print_specific_device(device)

    def _print_specific_device(self, device):
        _device_print(device)

        # Register the specific devices if we decide to listen.
        self.client.events.add_device_callback(device.id, _device_callback)

    def start_device_change_listener(self):
        if not self.args.listen:
            return
        # If no devices were specified then listen to all devices.
        if self.args.device is None:
            log.info("Adding all devices to listener...")

            for device in self.client.get_devices():
                self.client.events.add_device_callback(device.id, _device_callback)

        self.client.events.add_timeline_callback(TIMELINE.ALL, _timeline_callback)

        log.info("Listening for device and timeline updates...")
        self.client.events.start()
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            self.client.events.stop()
            log.info("Device update listening stopped.")


def _get_password(args):
    if not args.username:
        raise SystemExit("Username unknown. Pass a username or set ABODE_USERNAME.")
    args.password = args.password or _get_or_set_password(args.username)


def _get_or_set_password(username):
    password = keyring.get_password(urls.BASE, username)
    if not password:
        password = getpass.getpass(f"Password for {username}: ")
        keyring.set_password(urls.BASE, username, password)
    return password


def main():
    """Execute command line helper."""
    args = build_parser().parse_args()
    _get_password(args)

    setup_logging(log_level=logging.INFO + 10 * (args.quiet - args.debug))

    with _log_errors_and_logout(_create_client_instance(args)) as client:
        Dispatcher(client, args).dispatch()


if __name__ == "__main__":
    main()

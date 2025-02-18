"""Abode binary sensor device."""

from . import base
from . import status as STATUS


class BinarySensor(base.Device):
    """Class to represent an on / off, online/offline sensor."""

    @property
    def is_on(self):
        """
        Get sensor state.

        Assume offline or open (worst case).
        """
        return self.status not in (
            STATUS.OFF,
            STATUS.OFFLINE,
            STATUS.CLOSED,
        )


class Connectivity(BinarySensor):
    tags = (
        'glass',
        'keypad',
        'remote_controller',
        'siren',
        # status display
        'bx',
        # moisture
        'water_sensor',
        'fix_panic',
        'smoke_detector',
    )


class Motion(BinarySensor):
    tags = (
        'pir',
        'povs',
    )

    @property
    def is_on(self):
        if self.type == 'Occupancy':
            return self.status not in STATUS.ONLINE
        return super().is_on


class Door(BinarySensor):
    tags = ('door_contact',)

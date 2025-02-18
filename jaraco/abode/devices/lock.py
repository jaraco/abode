"""Abode lock device."""

from . import base
from . import status as STATUS


class Lock(base.Device):
    """Class to represent a door lock."""

    tags = (
        'door_lock',
        'retrofit_lock',
    )

    def lock(self) -> None:
        """Lock the device."""
        self.set_status(int(STATUS.Lock.CLOSED))
        self._state['status'] = STATUS.Lock.CLOSED

    def unlock(self) -> None:
        """Unlock the device."""
        self.set_status(int(STATUS.Lock.OPEN))
        self._state['status'] = STATUS.Lock.OPEN

    @property
    def is_locked(self):
        """
        Get locked state.

        Err on side of caution, assume if lock isn't closed then it's open.
        """
        return self.status == STATUS.Lock.CLOSED

"""Representation of an automation configured in Abode."""
import logging
import warnings

import jaraco.abode

from ._itertools import single
from .helpers import urls
from .helpers import errors as ERROR
from .state import Stateful

log = logging.getLogger(__name__)


class Automation(Stateful):
    """Class for viewing and controlling automations."""

    def __init__(self, abode, state):
        self._client = abode
        self._state = state

    def enable(self, enable: bool):
        """Enable or disable the automation."""
        path = urls.AUTOMATION_ID.format(id=self.id)

        response = self._client.send_request(
            method="patch", path=path, data={'enabled': enable}
        )

        state = single(response.json())

        if state['id'] != self._state['id'] or state['enabled'] != enable:
            raise jaraco.abode.Exception(ERROR.INVALID_AUTOMATION_EDIT_RESPONSE)

        self.update(state)

        log.info("Set automation %s enable to: %s", self.name, self.enabled)
        log.debug("Automation response: %s", response.text)

    def trigger(self):
        """Trigger the automation."""
        path = urls.AUTOMATION_APPLY.format(id=self.id)

        self._client.send_request(method="post", path=path)

        log.info("Automation triggered: %s", self.name)

    def refresh(self):
        """Refresh the automation."""
        path = urls.AUTOMATION_ID.format(id=self.id)

        response = self._client.send_request(method="get", path=path)
        state = single(response.json())

        if state['id'] != self.id:
            raise jaraco.abode.Exception(ERROR.INVALID_AUTOMATION_REFRESH_RESPONSE)

        self.update(state)

    @property
    def automation_id(self):
        """Get the id of the automation."""
        warnings.warn(
            "Automation.automation_id is deprecated. Use .id.", DeprecationWarning
        )
        return self.id

    @property
    def is_enabled(self):
        """Return True if the automation is enabled."""
        warnings.warn(
            "Automation.is_enabled is deprecated. Use .enabled.", DeprecationWarning
        )
        return self.enabled

    @property
    def desc(self):
        """Get a short description of the automation."""
        return '{} (ID: {}, Enabled: {})'.format(self.name, self.id, self.enabled)

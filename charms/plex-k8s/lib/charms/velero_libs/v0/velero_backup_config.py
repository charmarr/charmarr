"""# VeleroBackupConfig library.

This library implements the Requirer and Provider roles for the `velero_backup_config` relation
interface. It is used by client charms to declare backup specifications, and by the Velero Operator
charm to consume them and execute backup and restore operations.

The `velero_backup_config` interface allows a charm (the provider) to provide a declarative
description of what Kubernetes resources should be included in a backup. These specifications are
sent to the Velero Operator charm (the requirer), which executes the backup using the Velero CLI
and Kubernetes CRDs.

This interface follows a least-privilege model: client charms do not manipulate cluster resources
themselves. Instead, they define what should be backed up
and leave execution to the Velero Operator.

See Also:
- Interface spec: https://github.com/canonical/charm-relation-interfaces/tree/main/interfaces/velero_backup_config/v0
- Velero Operator charm: https://charmhub.io/velero-operator

## Getting Started

To get started using the library, fetch the library with `charmcraft`.

```shell
cd some-charm
charmcraft fetch-lib charms.velero_libs.v0.velero_backup_config
```

Then in your charm, do:

```python
from charms.velero_libs.v0.velero_backup_config import (
    VeleroBackupProvider,
    VeleroBackupSpec,
)

class SomeCharm(CharmBase):
  def __init__(self, *args):
    # ...
    self.user_workload_backup = VeleroBackupProvider(
        self,
        relation_name="user-workloads-backup",
        spec=VeleroBackupSpec(
            include_namespaces=["user-namespace"],
            include_resources=["persistentvolumeclaims", "services", "deployments"],
            ttl=str(self.config["ttl"]),
        )
        # Optional, if you want to refresh the data on custom events
        # In this case, the TTL will be refreshed in the databag on config_changed event
        refresh_event=[self.on.config_changed]
    )
    # ...
```
"""

import logging
import re
from typing import Dict, List, Optional, Union

from ops import BoundEvent, EventBase
from ops.charm import CharmBase
from ops.framework import Object
from pydantic import BaseModel

# The unique Charmhub library identifier, never change it
LIBID = "3fcd828c77024b0f9a7ea3544805456b"

# Increment this major API version when introducing breaking changes
LIBAPI = 0

# Increment this PATCH version before using `charmcraft publish-lib` or reset
# to 0 if you are raising the major API version
LIBPATCH = 1

# Regex to check if the provided TTL is a correct duration
DURATION_REGEX = r"^(?=.*\d)(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?$"

SPEC_FIELD = "spec"
APP_FIELD = "app"
RELATION_FIELD = "relation_name"
MODEL_FIELD = "model"

logger = logging.getLogger(__name__)


class VeleroBackupSpec(BaseModel):
    """Dataclass representing the Velero backup configuration.

    Args:
        include_namespaces (Optional[List[str]]): Namespaces to include in the backup.
        include_resources (Optional[List[str]]): Resources to include in the backup.
        exclude_namespaces (Optional[List[str]]): Namespaces to exclude from the backup.
        exclude_resources (Optional[List[str]]): Resources to exclude from the backup.
        label_selector (Optional[Dict[str, str]]): Label selector for filtering resources.
        include_cluster_resources (Optional[bool]):
            Whether to include cluster-wide resources in the backup.
            Defaults to None (auto detect based on resources).
        ttl (Optional[str]): TTL for the backup, if applicable. Example: "24h", "10m10s", etc.
    """

    include_namespaces: Optional[List[str]] = None
    include_resources: Optional[List[str]] = None
    exclude_namespaces: Optional[List[str]] = None
    exclude_resources: Optional[List[str]] = None
    label_selector: Optional[Dict[str, str]] = None
    ttl: Optional[str] = None
    include_cluster_resources: Optional[bool] = None

    def __post_init__(self):
        """Validate the specification."""
        if self.ttl and not re.match(DURATION_REGEX, self.ttl):
            raise ValueError(
                f"Invalid TTL format: {self.ttl}. Expected format: '24h', '10h10m10s', etc."
            )


class VeleroBackupRequier(Object):
    """Requirer class for the Velero backup configuration relation."""

    def __init__(self, charm: CharmBase, relation_name: str):
        """Initialize the requirer.

        Args:
            charm (CharmBase): The charm instance that requires backup configuration.
            relation_name (str): The name of the relation. (from metadata.yaml)
        """
        super().__init__(charm, relation_name)
        self._charm = charm
        self._relation_name = relation_name

    def get_backup_spec(
        self, app_name: str, endpoint: str, model: str
    ) -> Optional[VeleroBackupSpec]:
        """Get a VeleroBackupSpec for a given (app, endpoint, model).

        Args:
            app_name (str): The name of the application for which the backup is configured
            endpoint (str): The name of the relation. (from metadata.yaml)
            model (str): The model name of the application.

        Returns:
            Optional[VeleroBackupSpec]: The backup specification if available, otherwise None.
        """
        relations = self.model.relations[self._relation_name]

        for relation in relations:
            data = relation.data.get(relation.app, {})
            if (
                data.get(APP_FIELD) == app_name
                and data.get(MODEL_FIELD) == model
                and data.get(RELATION_FIELD) == endpoint
            ):
                json_data = data.get(SPEC_FIELD, "{}")
                return VeleroBackupSpec.model_validate_json(json_data)

        logger.warning("No backup spec found for app '%s' and endpoint '%s'", app_name, endpoint)
        return None

    def get_all_backup_specs(self) -> List[VeleroBackupSpec]:
        """Get a list of all active VeleroBackupSpec objects across all relations.

        Returns:
            List[VeleroBackupSpec]: A list of all active backup specifications.
        """
        specs = []
        relations = self.model.relations[self._relation_name]

        for relation in relations:
            json_data = relation.data[relation.app].get(SPEC_FIELD, "{}")
            specs.append(VeleroBackupSpec.model_validate_json(json_data))

        return specs


class VeleroBackupProvider(Object):
    """Provider class for the Velero backup configuration relation."""

    def __init__(
        self,
        charm: CharmBase,
        relation_name: str,
        spec: VeleroBackupSpec,
        refresh_event: Optional[Union[BoundEvent, List[BoundEvent]]] = None,
    ):
        """Intialize the provider with the specified backup configuration.

        Args:
            charm (CharmBase): The charm instance that provides backup.
            relation_name (str): The name of the relation. (from metadata.yaml)
            spec (VeleroBackupSpec): The backup specification to be used
            refresh_event (Optional[Union[BoundEvent, List[BoundEvent]]]):
                Optional event(s) to trigger data sending.
        """
        super().__init__(charm, relation_name)
        self._charm = charm
        self._app_name = self._charm.app.name
        self._model = self._charm.model.name
        self._relation_name = relation_name
        self._spec = spec

        self.framework.observe(self._charm.on.leader_elected, self._send_data)
        self.framework.observe(
            self._charm.on[self._relation_name].relation_created, self._send_data
        )
        self.framework.observe(self._charm.on.upgrade_charm, self._send_data)

        if refresh_event:
            if not isinstance(refresh_event, (tuple, list)):
                refresh_event = [refresh_event]
            for event in refresh_event:
                self.framework.observe(event, self._send_data)

    def _send_data(self, event: EventBase):
        """Handle any event where we should send data to the relation."""
        if not self._charm.model.unit.is_leader():
            logger.warning(
                "VeleroBackupProvider handled send_data event when it is not a leader. "
                "Skiping event - no data sent"
            )
            return

        relations = self._charm.model.relations.get(self._relation_name)

        if not relations:
            logger.warning(
                "VeleroBackupProvider handled send_data event but no relation '%s' found "
                "Skiping event - no data sent",
                self._relation_name,
            )
            return
        for relation in relations:
            relation.data[self._charm.app].update(
                {
                    MODEL_FIELD: self._model,
                    APP_FIELD: self._app_name,
                    RELATION_FIELD: self._relation_name,
                    SPEC_FIELD: self._spec.model_dump_json(),
                }
            )

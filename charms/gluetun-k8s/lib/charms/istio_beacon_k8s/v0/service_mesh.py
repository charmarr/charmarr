# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

"""# Service Mesh Library.

This library facilitates adding your charmed application to a service mesh, leveraging the
`service_mesh` and `cross_model_mesh` interfaces to provide secure, policy-driven traffic
management between applications.

## Overview

Service meshes provide capabilities for routing, controlling, and monitoring traffic between
applications. A key feature is the ability to restrict traffic between Pods. For example, you can define that Pod MetricsScraper can `GET` from Pod MetricsProducer
at `/metrics` on port `9090`, while preventing SomeOtherPod from accessing it.

## Consumer

The ServiceMeshConsumer object subscribes a charm and its workloads to a related service mesh.
Since application relations often indicate traffic flow patterns (e.g., DbConsumer requiring
DbProducer), ServiceMeshConsumer provides automated creation of traffic rules based on
application relations. \

The ServiceMeshConsumer implements the `requirer` side of the juju relation.

### Setup

First, add the required relations to your `charmcraft.yaml`:

```yaml
requires:
  service-mesh:
    limit: 1
    interface: service_mesh
    description: |
      Subscribe this charm into a service mesh to enforce authorization policies.
  require-cmr-mesh:
    interface: cross_model_mesh
    description: |
      Allow a cross-model application access to catalogue via the service mesh.
      This relation provides additional data required by the service mesh to enforce cross-model authorization policies.

provides:
  provide-cmr-mesh:
    interface: cross_model_mesh
    description: |
      Access a cross-model application from catalogue via the service mesh.
      This relation provides additional data required by the service mesh to enforce cross-model authorization policies.
```

Instantiate a ServiceMeshConsumer object in your charm's `__init__` method:

```python
from charms.istio_beacon_k8s.v0.service_mesh import Method, Endpoint, AppPolicy, UnitPolicy, ServiceMeshConsumer

class MyCharm(CharmBase):
    def __init__(self, *args):
        super().__init__(*args)
        self._mesh = ServiceMeshConsumer(
            self,
            policies=[
                AppPolicy(
                    relation="data",
                    endpoints=[
                        Endpoint(
                            ports=[HTTP_LISTEN_PORT],
                            methods=[Method.get],
                            paths=["/data"],
                        ),
                    ],
                ),
                UnitPolicy(
                    relation="metrics",
                    ports=[HTTP_LISTEN_PORT],
                ),
            ],
        )
```

This example creates two policies:
- An app policy - When related over the `data` relation, allow the related application to `GET` this application's `/data` endpoint on the specified port through the app's Kubernetes service.
- A unit policy - When related over the `metrics` relation, allow the related application to access this application's unit pods directly on the specified port without any other restriction. UnitPolicy does not support fine-grained access control on the methods and paths via `Endpoints`.

An AppPolicy can be used to control how the source application can communicate with the target application via the app address.
A UnitPolicy allows access to the specified port but only to the unit pods of the charm via individual unit addresses.

### Cross-Model Relations
To request service mesh policies for cross-model relations, additional information is required.

For any charm that wants to grant access to a related application (say, the above example
charm providing a `data` relation), these charms must also implement and relate over the
`cross_model_mesh` relation.  For `cross_model_mesh`, the charm granting access should be the
provider, and the charm trying to communicate should be the requirer.

### Joining the Mesh

For most charms, instantiating ServiceMeshConsumer automatically configures the charm
to join the mesh. For legacy "podspec" style charms or charms deploying custom
Kubernetes resources, you must manually apply the labels returned by
`ServiceMeshConsumer.labels()` to your pods.

## Provider

The ServiceMeshProvider implements the provider side of the juju relation. To provide a service mesh, instantiate ServiceMeshProvider in your charm's `__init__` method:

```python
from charms.istio_beacon_k8s.v0.service_mesh import ServiceMeshProvider

class MyServiceMeshCharm(CharmBase):
    def __init__(self, *args):
        super().__init__(*args)
        self._mesh = ServiceMeshProvider(
            charm=self,
            labels={"istio.io/dataplane-mode": "ambient"},
            mesh_relation_name="service-mesh",
        )
```

### Configuration

The `labels` argument specifies the labels that indicate to the service mesh that a Pod
should be subscribed to the mesh. These labels are service-mesh specific, for eg.:
- For Istio ambient mesh: `{"istio.io/dataplane-mode": "ambient"}`
- For Istio sidecar mesh: `{"istio-injection": "enabled"}`

### Accessing Mesh Policies

The provider exposes the `mesh_info()` method that returns a list of MeshPolicy objects
for configuring the service mesh:

```python
for policy in self._mesh.mesh_info():
    configure_service_mesh_policy(policy)
```

## Data Models

- **Method**: Defines enum for HTTP methods (GET, POST, PUT, etc.)
- **Endpoint**: Defines traffic endpoints with hosts, ports, methods, and paths
- **AppPolicy**: Defines application level authorization policy for the consumer
- **UnitPolicy**: Defines unit level authorization policy for the consumer
- **MeshPolicy**: Contains complete policy information for mesh configuration
- **CMRData**: Contains cross-model relation metadata
"""

import enum
import hashlib
import json
import logging
import warnings
from typing import Dict, List, Literal, Optional, Set, Type, Union

import httpx
import pydantic
from charmed_service_mesh_helpers.models import (
    AuthorizationPolicySpec,
    From,
    Operation,
    PolicyTargetReference,
    Rule,
    Source,
    To,
    WorkloadSelector,
)
from lightkube import Client
from lightkube.models.meta_v1 import ObjectMeta
from lightkube.resources.apps_v1 import StatefulSet
from lightkube.resources.core_v1 import ConfigMap, Service
from lightkube_extensions.batch import KubernetesResourceManager
from lightkube_extensions.types import (
    AuthorizationPolicy,
    LightkubeResourcesList,
    LightkubeResourceTypesSet,
)
from ops import CharmBase, Object, RelationMapping
from pydantic import Field

POLICY_RESOURCE_TYPES = {
    "istio": {AuthorizationPolicy},
}

LIBID = "3f40cb7e3569454a92ac2541c5ca0a0c"  # Never change this
LIBAPI = 0
LIBPATCH = 19

PYDEPS = [
    "lightkube",
    "pydantic",
    "charmed-service-mesh-helpers",
    "lightkube-extensions",
]

logger = logging.getLogger(__name__)

# Juju application names are limited to 63 characters, so we can use the app_name directly here and still keep under
# Kubernetes's 253 character limit.
label_configmap_name_template = "juju-service-mesh-{app_name}-labels"


class MeshType(str, enum.Enum):
    """Supported mesh types."""

    istio = "istio"


class Method(str, enum.Enum):
    """HTTP method."""

    connect = "CONNECT"
    delete = "DELETE"
    get = "GET"
    head = "HEAD"
    options = "OPTIONS"
    patch = "PATCH"
    post = "POST"
    put = "PUT"
    trace = "TRACE"


class Endpoint(pydantic.BaseModel):
    """Data type for a policy endpoint."""

    hosts: Optional[List[str]] = None
    ports: Optional[List[int]] = None
    methods: Optional[List[Method]] = None
    paths: Optional[List[str]] = None


class PolicyTargetType(str, enum.Enum):
    """Target type for Policy classes."""

    app = "app"
    unit = "unit"


class Policy(pydantic.BaseModel):
    """Data type for defining a policy for your charm."""

    relation: str
    endpoints: List[Endpoint]
    service: Optional[str] = None

    def __init__(self, **data):
        warnings.warn(
            "Policy is deprecated. Use AppPolicy for fine-grained application-level policies "
            "or UnitPolicy to allow access to charm units. For migration, Policy can be "
            "directly replaced with AppPolicy.",
            DeprecationWarning,
            stacklevel=2
        )
        super().__init__(**data)


class AppPolicy(pydantic.BaseModel):
    """Data type for defining a policy for your charm application."""

    relation: str
    endpoints: List[Endpoint]
    service: Optional[str] = None


class UnitPolicy(pydantic.BaseModel):
    """Data type for defining a policy for your charm unit."""

    relation: str
    # UnitPolicy at the moment only supports access control over ports.
    # This limitation stems from the currently supported upstream service meshes (Istio).
    # Since other attributes of Endpoints class are not supported, the easiest implementation was to use just the ports attribute in this class.
    ports: Optional[List[int]] = None


class MeshPolicy(pydantic.BaseModel):
    """A Generic MeshPolicy data type that describes mesh policies in a way that is agnostic to the mesh type.

    This is also used as the data type for storing service mesh policy information and thereby
    defining a standard interface for charmed mesh managed policies.
    """

    source_namespace: str
    source_app_name: str
    target_namespace: str
    target_app_name: Optional[str] = None
    target_selector_labels: Optional[Dict[str, str]] = None
    target_service: Optional[str] = None
    target_type: Literal[PolicyTargetType.app, PolicyTargetType.unit] = PolicyTargetType.app
    endpoints: List[Endpoint] = Field(default_factory=list)

    @pydantic.model_validator(mode="after")
    def _validate(self):
        """Validate cross field constraints for the mesh policy."""
        if self.target_type == PolicyTargetType.app:
            self._validate_app_policy()
        elif self.target_type == PolicyTargetType.unit:
            self._validate_unit_policy()
        return self

    def _validate_app_policy(self) -> None:
        """Validate app-targeted policy constraints."""
        if not any([self.target_app_name, self.target_service]):
            raise ValueError(
                f"Bad policy configuration. Neither target_app_name nor target_service "
                f"specified for MeshPolicy with target_type {self.target_type}"
            )
        if self.target_selector_labels:
            raise ValueError(
                f"Bad policy configuration. MeshPolicy with target_type {self.target_type} "
                f"does not support target_selector_labels."
            )

    def _validate_unit_policy(self) -> None:
        """Validate unit-targeted policy constraints."""
        if self.target_app_name and self.target_selector_labels:
            raise ValueError(
                f"Bad policy configuration. MeshPolicy with target_type {self.target_type} "
                f"cannot specify both target_app_name and target_selector_labels."
            )
        if self.target_service:
            raise ValueError(
                f"Bad policy configuration. MeshPolicy with target_type {self.target_type} "
                f"does not support target_service."
            )


class ServiceMeshProviderAppData(pydantic.BaseModel):
    """Data type for the application data provided by the provider side of the service-mesh interface."""

    labels: Dict[str, str]
    mesh_type: MeshType


class CMRData(pydantic.BaseModel):
    """Data type containing the info required for cross-model relations."""

    app_name: str
    juju_model_name: str


class ServiceMeshConsumer(Object):
    """Class used for joining a service mesh."""

    def __init__(
        self,
        charm: CharmBase,
        mesh_relation_name: str = "service-mesh",
        cross_model_mesh_requires_name: str = "require-cmr-mesh",
        cross_model_mesh_provides_name: str = "provide-cmr-mesh",
        policies: Optional[List[Union[Policy, AppPolicy, UnitPolicy]]] = None,
        auto_join: bool = True,
    ):
        """Class used for joining a service mesh.

        Args:
            charm: The charm instantiating this object.
            mesh_relation_name: The relation name as defined in metadata.yaml or charmcraft.yaml
                for the relation which uses the service_mesh interface.
            cross_model_mesh_requires_name: The relation name as defined in metadata.yaml or
                charmcraft.yaml for the relation which requires the cross_model_mesh interface.
            cross_model_mesh_provides_name: The relation name as defined in metadata.yaml or
                charmcraft.yaml for the relation which provides the cross_model_mesh interface.
            policies: List of access policies this charm supports.
            auto_join: Automatically join the mesh by applying labels to charm pods.
        """
        super().__init__(charm, mesh_relation_name)
        self._charm = charm
        self._relation = self._charm.model.get_relation(mesh_relation_name)
        self._cmr_relations = self._charm.model.relations[cross_model_mesh_provides_name]
        self._policies = policies or []
        self._label_configmap_name = label_configmap_name_template.format(app_name=self._charm.app.name)
        self._lightkube_client = None
        if auto_join:
            self.framework.observe(
                self._charm.on[mesh_relation_name].relation_changed, self._update_labels
            )
            self.framework.observe(
                self._charm.on[mesh_relation_name].relation_broken, self._on_mesh_broken
            )
        self.framework.observe(
            self._charm.on[mesh_relation_name].relation_created, self._relations_changed
        )
        self.framework.observe(
            self._charm.on[cross_model_mesh_requires_name].relation_created, self._send_cmr_data
        )
        self.framework.observe(
            self._charm.on[cross_model_mesh_provides_name].relation_changed,
            self._relations_changed,
        )
        self.framework.observe(self._charm.on.upgrade_charm, self._relations_changed)
        relations = {policy.relation for policy in self._policies}
        for relation in relations:
            self.framework.observe(
                self._charm.on[relation].relation_created, self._relations_changed
            )
            self.framework.observe(
                self._charm.on[relation].relation_broken, self._relations_changed
            )

    def _send_cmr_data(self, event):
        """Send app and model information for CMR."""
        if not self._charm.unit.is_leader():
            return
        data = CMRData(
            app_name=self._charm.app.name, juju_model_name=self._charm.model.name
        ).model_dump()
        event.relation.data[self._charm.app]["cmr_data"] = json.dumps(data)

    def _relations_changed(self, _event):
        if not self._charm.unit.is_leader():
            return
        self.update_service_mesh()

    def update_service_mesh(self):
        """Update the service mesh.

        Gathers information from all relations of the charm and updates the mesh appropriately to
        allow communication.
        """
        if self._relation is None:
            return
        logger.debug("Updating service mesh policies.")

        # Collect the remote data from any fully established cross_model_relation integrations
        # {remote application name: cmr relation data}
        cmr_application_data = get_data_from_cmr_relation(self._cmr_relations)

        mesh_policies = build_mesh_policies(
            relation_mapping=self._charm.model.relations,
            target_app_name=self._charm.app.name,
            target_namespace=self._my_namespace(),
            policies=self._policies,
            cmr_application_data=cmr_application_data,
        )
        self._relation.data[self._charm.app]["policies"] = json.dumps([p.model_dump() for p in mesh_policies])

    def _my_namespace(self):
        """Return the namespace of the running charm."""
        # This method currently assumes the namespace is the same as the model name. We
        # should consider if there is a better way to do this.
        return self._charm.model.name

    def _get_app_data(self) -> Optional[ServiceMeshProviderAppData]:
        """Return the relation data for the remote application."""
        if self._relation is None or not self._relation.app:
            return None

        raw_data = self._relation.data[self._relation.app]
        if len(raw_data) == 0:
            return None

        raw_data = {k: json.loads(v) for k, v in raw_data.items()}
        return ServiceMeshProviderAppData.model_validate(raw_data)


    def labels(self) -> dict:
        """Labels required for a pod to join the mesh."""
        app_data = self._get_app_data()
        if app_data is None:
            return {}
        return app_data.labels

    def mesh_type(self) -> Optional[MeshType]:
        """Return the type of the service mesh."""
        app_data = self._get_app_data()
        if app_data is None:
            return None
        return app_data.mesh_type

    def _on_mesh_broken(self, _event):
        if not self._charm.unit.is_leader():
            return
        self._set_labels({})
        self._delete_label_configmap()

    def _update_labels(self, _event):
        self._set_labels(self.labels())

    def _set_labels(self, labels: dict) -> None:
        """Add labels to the charm's Pods (via StatefulSet) and Service to put the charm on the mesh."""
        reconcile_charm_labels(
            client=self.lightkube_client,
            app_name=self._charm.app.name,
            namespace=self._charm.model.name,
            label_configmap_name=self._label_configmap_name,
            labels=labels
        )

    def _delete_label_configmap(self) -> None:
        client = self.lightkube_client
        client.delete(res=ConfigMap, name=self._label_configmap_name)

    @property
    def lightkube_client(self):
        """Returns a lightkube client configured for this library.

        This indirection is implemented to avoid complex mocking in integration tests, allowing the integration tests to
        do something equivalent to:
            ```python
           mesh_consumer = ServiceMeshConsumer(...)
           mesh_consumer._lightkube_client = mocked_lightkube_client
           ```
        """
        if self._lightkube_client is None:
            self._lightkube_client = Client(
                namespace=self._charm.model.name, field_manager=self._charm.app.name
            )
        return self._lightkube_client


class ServiceMeshProvider(Object):
    """Provide a service mesh to applications."""

    def __init__(
        self,
        charm: CharmBase,
        labels: Dict[str, str],
        mesh_type: MeshType,
        mesh_relation_name: str = "service-mesh",
    ):
        """Class used to provide information needed to join the service mesh.

        Args:
            charm: The charm instantiating this object.
            labels: The labels which related applications need to apply to use the mesh.
            mesh_type: The type of this service mesh.
            mesh_relation_name: The relation name as defined in metadata.yaml or charmcraft.yaml
                for the relation which uses the service_mesh interface.
        """
        super().__init__(charm, mesh_relation_name)
        self._charm = charm
        self._relation_name = mesh_relation_name
        self._labels = labels
        self._mesh_type = mesh_type
        self.framework.observe(
            self._charm.on[mesh_relation_name].relation_created, self._relation_created
        )
        self.framework.observe(
            self._charm.on.config_changed, self._on_config_changed
        )

    def _relation_created(self, _event):
        self.update_relations()

    def _on_config_changed(self, _event):
        self.update_relations()

    def update_relations(self):
        """Update all relations with the labels needed to use the mesh."""
        # Only the leader unit can update the application data bag
        if self._charm.unit.is_leader():
            data = ServiceMeshProviderAppData(
                labels=self._labels,
                mesh_type=self._mesh_type
            ).model_dump(mode="json", by_alias=True, exclude_defaults=True, round_trip=True)
            # Flatten any nested objects, since relation databags are str:str mappings
            data = {k: json.dumps(v) for k, v in data.items()}
            for relation in self._charm.model.relations[self._relation_name]:
                relation.data[self._charm.app].update(data)

    def mesh_info(self) -> List[MeshPolicy]:
        """Return the relation data that defines Policies requested by the related applications."""
        mesh_info = []
        for relation in self._charm.model.relations[self._relation_name]:
            policies_data = json.loads(relation.data[relation.app].get("policies", "[]"))
            policies = [MeshPolicy.model_validate(policy) for policy in policies_data]
            mesh_info.extend(policies)
        return mesh_info


def build_mesh_policies(
        relation_mapping: RelationMapping,
        target_app_name: str,
        target_namespace: str,
        policies: List[Union[Policy, AppPolicy, UnitPolicy]],
        cmr_application_data: Optional[Dict[str, CMRData]] = None,
) -> List[MeshPolicy]:
    """Generate MeshPolicy that implement the given policies for the currently related applications.

    Args:
        relation_mapping: Charm's RelationMapping object, for example self.model.relations.
        target_app_name: The name of the target application, for example self.app.name.
        target_namespace: The namespace of the target application, for example self.model.name.
        policies: List of AppPolicy, or UnitPolicy objects defining the access rules.
        cmr_application_data: Data for cross-model relations, mapping app names to CMRData.
    """
    if not cmr_application_data:
        cmr_application_data = {}

    mesh_policies = []
    for policy in policies:
        logger.debug(f"Processing policy for relation endpoint '{policy.relation}'.")
        for relation in relation_mapping[policy.relation]:
            logger.debug(f"Processing policy for related application '{relation.app.name}'.")
            if relation.app.name in cmr_application_data:
                logger.debug(f"Found cross model relation: {relation.name}. Creating policy.")
                source_app_name = cmr_application_data[relation.app.name].app_name
                source_namespace = cmr_application_data[relation.app.name].juju_model_name
            else:
                logger.debug(f"Found in-model relation: {relation.name}. Creating policy.")
                source_app_name = relation.app.name
                source_namespace = target_namespace

            if isinstance(policy, UnitPolicy):
                mesh_policies.append(
                    MeshPolicy(
                        source_namespace=source_namespace,
                        source_app_name=source_app_name,
                        target_namespace=target_namespace,
                        target_app_name=target_app_name,
                        target_service=None,
                        target_type=PolicyTargetType.unit,
                        endpoints=[
                            Endpoint(
                                ports=policy.ports,
                            )
                        ]
                        if policy.ports
                        else [],
                    )
                )
            else:
               mesh_policies.append(
                    MeshPolicy(
                        source_namespace=source_namespace,
                        source_app_name=source_app_name,
                        target_namespace=target_namespace,
                        target_app_name=target_app_name,
                        target_service=policy.service,
                        target_type=PolicyTargetType.app,
                        endpoints=policy.endpoints,
                    )
                )

    return mesh_policies


def reconcile_charm_labels(client: Client, app_name: str, namespace: str,  label_configmap_name: str, labels: Dict[str, str]) -> None:
    """Reconciles zero or more user-defined additional Kubernetes labels that are put on a Charm's Kubernetes objects.

    This function manages a group of user-defined labels that are added to a Charm's Kubernetes objects (the charm Pods
    (via editing the StatefulSet) and Service).  Its primary uses are:
    * adding labels to a Charm's objects
    * updating or removing labels on a Charm's Kubernetes objects that were previously set by this method

    To enable removal of labels, we also create a ConfigMap that stores the labels we last set.  This way the function
    itself can be stateless.

    This function takes a little care to avoid removing labels added by other means, but it does not provide exhaustive
    guarantees for safety.  It is up to the caller to ensure that the labels they pass in are not already in use.

    Args:
        client: The lightkube Client to use for Kubernetes API calls.
        app_name: The name of the application (Charm) to reconcile labels for.
        namespace: The namespace in which the application is running.
        label_configmap_name: The name of the ConfigMap that stores the labels.
        labels: A dictionary of labels to set on the Charm's Kubernetes objects. Any labels that were previously created
                by this method but omitted in `labels` now will be removed from the Kubernetes objects.
    """
    patch_labels: Dict[str, Optional[str]] = dict(labels)
    try:
        config_map = client.get(ConfigMap, label_configmap_name)
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            config_map = _init_label_configmap(client, label_configmap_name, namespace)
        else:
            raise
    if config_map.data:
        config_map_labels = json.loads(config_map.data["labels"])
        for label in config_map_labels:
            if label not in patch_labels:
                # The label was previously set. Setting it to None will delete it.
                patch_labels[label] = None

    # Patch just the labels instead of the entire resource defintion.
    # This minimal approach reduces the chance of 409 conflicts when other actors are modifying the resources.
    # Retrying here is a bad idea as we WANT to get a 409 when someone else patches OUR labels. We shouldn't mask that.
    client.patch(res=StatefulSet, name=app_name, obj={
        "spec": {"template": {"metadata": {"labels": patch_labels}}}
    })
    client.patch(res=Service, name=app_name, obj={
        "metadata": {"labels": patch_labels}
    })

    # Store our actively managed labels in a ConfigMap so next call we know which we might need to delete.
    # This should not include any labels that are nulled out as they're now out of scope.
    config_map_labels = {k: v for k, v in patch_labels.items() if v is not None}
    config_map.data = {"labels": json.dumps(config_map_labels)}
    client.patch(res=ConfigMap, name=label_configmap_name, obj=config_map)


def _init_label_configmap(client, name, namespace) -> ConfigMap:
    """Create a ConfigMap with data of {labels: {}}, returning the lightkube ConfigMap object."""
    obj = ConfigMap(
        data={"labels": "{}"},
        metadata=ObjectMeta(
            name=name,
            namespace=namespace,
        ),
    )
    client.create(obj=obj)
    return obj


########################################
#  MESH NETWORK POLICY MANAGER HELPERS #
########################################
def _get_peer_identity_for_juju_application(app_name, namespace):
    """Return a Juju application's peer identity.

    Format returned is defined by `principals` in
    [this reference](https://istio.io/latest/docs/reference/config/security/authorization-policy/#Source):

    This function relies on the Juju convention that each application gets a ServiceAccount of the same name in the same
    namespace.
    """
    service_account = app_name
    return _get_peer_identity_for_service_account(service_account, namespace)


def _get_peer_identity_for_service_account(service_account, namespace):
    """Return a ServiceAccount's peer identity.

    Format returned is defined by `principals` in
    [this reference](https://istio.io/latest/docs/reference/config/security/authorization-policy/#Source):
        "cluster.local/ns/{namespace}/sa/{service_account}"
    """
    return f"cluster.local/ns/{namespace}/sa/{service_account}"


def _hash_pydantic_model(model: pydantic.BaseModel) -> str:
    """Hash a pydantic BaseModel object.

    This is a simple hashing of the json model dump of the pydantic model.  Items that are excluded from this dump
    will not affect the output.
    """

    def _stable_hash(data):
        return hashlib.sha256(str(data).encode()).hexdigest()

    # Note: This hash will be affected by changes in how pydantic stringifies data, so if they change things our hash
    # will change too.  If that proves an issue, we could implement something more controlled here.
    return _stable_hash(model)


def _generate_network_policy_name(app_name: str, model_name: str, mesh_policy: MeshPolicy) -> str:
        """Generate a unique name for the network policy resource, suffixing a hash of the MeshPolicy to avoid collisions.

        The name has the following general format:
            {app_name}-{model_name}-policy-{source_app_name}-{source_namespace}-{target_app_name/target_service/custom-selector}-{hash}
        but source_app_name and the name of the target will be truncated if the total name exceeds Kubernetes's limit of 253
        characters.
        """
        # omit target_app_namespace from the name here because that will be the namespace the policy is generated in, so
        # adding it here is redundant
        target = mesh_policy.target_app_name or mesh_policy.target_service or "custom-selector"

        name = "-".join(
            [
                app_name,
                model_name,
                "policy",
                mesh_policy.source_app_name,
                mesh_policy.source_namespace,
                target,
                _hash_pydantic_model(mesh_policy)[:8],
            ]
        )
        if len(name) > 253:
            # Truncate the name to fit within Kubernetes's 253-character limit
            # juju app names and models must be <= 63 characters each and we have ~20 characters of static text, so
            # if name is too long just take the first 30 characters of source_app_name, source_namespace, and
            # target_app_name to be safe.
            name = "-".join(
                [
                    app_name,
                    model_name,
                    "policy",
                    mesh_policy.source_app_name[:30],
                    mesh_policy.source_namespace[:30],
                    target[:30],
                    _hash_pydantic_model(mesh_policy)[:8],
                ]
            )
        return name


def _build_policy_resources_istio(app_name: str, model_name: str, policies: List[MeshPolicy]) -> Union[LightkubeResourcesList, List[None]]:
        """Build the required authorization policy resources for istio service mesh."""
        authorization_policies = [None] * len(policies)
        for i, policy in enumerate(policies):
            # L4 policy created for target Juju units (workloads)
            if policy.target_type == PolicyTargetType.unit:
                # if the mesh policy of type unit contain any of the L7 attributes, warn and don't create the policy
                valid_unit_policy = not any(
                    endpoint.methods or endpoint.paths or endpoint.hosts
                    for endpoint in policy.endpoints
                )
                if not valid_unit_policy:
                    logger.error(
                        f"UnitPolicy requested between {policy.source_app_name} and {policy.target_app_name} is not created as it contains some disallowed policy attributes."
                        "UnitPolicy for Istio service mesh cannot contain paths, methods or hosts"
                    )
                    continue

                # Build match labels based on policy definition
                workload_selector = None
                if policy.target_app_name:
                    workload_selector = WorkloadSelector(
                        matchLabels={
                            "app.kubernetes.io/name": policy.target_app_name,
                        }
                    )
                if policy.target_selector_labels:
                    workload_selector = WorkloadSelector(
                        matchLabels=policy.target_selector_labels
                    )

                authorization_policies[i] = AuthorizationPolicy(  # type: ignore[assignment]
                    metadata=ObjectMeta(
                        name=_generate_network_policy_name(app_name, model_name, policy),
                        namespace=policy.target_namespace,
                    ),
                    spec=AuthorizationPolicySpec(
                        selector=workload_selector,
                        rules=[
                            Rule(
                                from_=[  # type: ignore # this is accessible via an alias
                                    From(
                                        source=Source(
                                            principals=[
                                                _get_peer_identity_for_juju_application(
                                                    policy.source_app_name, policy.source_namespace
                                                )
                                            ]
                                        )
                                    )
                                ],
                                to=[
                                    To(
                                        operation=Operation(
                                            # TODO: Make these ports strings instead of ints in endpoint?
                                            ports=[str(p) for p in endpoint.ports]
                                            if endpoint.ports
                                            else [],
                                        )
                                    )
                                    for endpoint in policy.endpoints
                                ],
                            ),
                        ],
                    ).model_dump(by_alias=True, exclude_unset=True, exclude_none=True),
                )

            # L7 policy created for target Juju applications (services)
            elif policy.target_type == PolicyTargetType.app:
                target_service = policy.target_service or policy.target_app_name
                if policy.target_service is None:
                    logger.info(
                        f"Got policy for application '{policy.target_app_name}' that has no target_service. "
                        f"Defaulting to application name."
                    )
                if all([policy.target_service, policy.target_app_name]):
                    logger.info(
                        f"Got policy for application '{policy.target_app_name}' that has both target_service and target_app_name. "
                        f"Using {target_service} for policy target definition."
                    )

                authorization_policies[i] = AuthorizationPolicy(  # type: ignore[assignment]
                    metadata=ObjectMeta(
                        name=_generate_network_policy_name(app_name, model_name, policy),
                        namespace=policy.target_namespace,
                    ),
                    spec=AuthorizationPolicySpec(
                        targetRefs=[
                            PolicyTargetReference(
                                kind="Service",
                                group="",
                                name=target_service,  # type: ignore
                            )
                        ],
                        rules=[
                            Rule(
                                from_=[  # type: ignore # this is accessible via an alias
                                    From(
                                        source=Source(
                                            principals=[
                                                _get_peer_identity_for_juju_application(
                                                    policy.source_app_name, policy.source_namespace
                                                )
                                            ]
                                        )
                                    )
                                ],
                                to=[
                                    To(
                                        operation=Operation(
                                            # TODO: Make these ports strings instead of ints in endpoint?
                                            ports=[str(p) for p in endpoint.ports]
                                            if endpoint.ports
                                            else [],
                                            hosts=endpoint.hosts,
                                            methods=endpoint.methods,  # type: ignore
                                            paths=endpoint.paths,
                                        )
                                    )
                                    for endpoint in policy.endpoints
                                ],
                            )
                        ],
                        # by_alias=True because the model includes an alias for the `from` field
                        # exclude_unset=True because unset fields will be treated as their default values in Kubernetes
                        # exclude_none=True because null values in this data always mean the Kubernetes default
                    ).model_dump(by_alias=True, exclude_unset=True, exclude_none=True),
                )

            else:
                raise ValueError("Failed to build requested istio authorization policy. Unknown target_type for policy.")

        return authorization_policies


class PolicyResourceManager():
    """A Mesh agnostic policy resource manager that manages manifests of different policy manifests in Kubernetes.

    This can be used by the charms to create and manage their own policy resources under circumstances like but not limited to
        i.   Using Canonical Service Mesh in a non-managed model_name
        ii.  Managing highly custom policies that cannot be defined in the ServiceMeshConsumer
        iii. Managing authorization policies between charms that are not related to the charmed service mesh's beacon.

    The PolicyResourceManager provides a reconcile method that can be used in the charm's own reconciler methods for reconciling
    the policies managed by the charm to the desired state.

    Example:
    ```python
    from charms.istio_beacon_k8s.v0.service_mesh import (
        MeshPolicy,
        PolicyTargetType,
        Endpoint,
        PolicyResourceManager,
        MeshType,
    )

    class MyCharm(CharmBase):

        def __init__(self, *args):
            super().__init__(*args)
            self._mesh = ServiceMeshConsumer(self)

            self.observe_everything()

        def _get_policy_manager(self):
            prm = PolicyResourceManager(
                charm=self,
                lightkube_client=self.lightkube_client,
                labels={
                    "label-key": "label-value-that-helps-identify-this-resource",
                },
            )
            return prm

        def _get_policies_i_manage(self):
            policies=[
                # policy to allow juju_app_a in juju_app_a_model to talk to juju_app_b in juju_app_b_model with a service
                # name juju_app_b_service through its service address in ports 8080 and 443 to GET /foo and /bar paths.
                MeshPolicy[
                    source_namespace="juju_app_a_model",
                    source_app_name="juju_app_a",
                    target_namespace="juju_app_b_model",
                    target_app_name="juju_app_b",
                    target_service="juju_app_b_service",
                    target_type=PolicyTargetType.app,
                    endpoints=[
                        Endpoint(
                            ports=[8080, 443],
                            methods=[Method.get],
                            paths=["/foo", "/bar"]
                        )
                    ]
                ],
                # policy to allow juju_app_a in juju_app_a_model to talk to juju_app_c in juju_app_c_model with a service
                # name same as the app name through its service address in ports 8080 and 443 to GET /foo.
                MeshPolicy[
                    source_namespace="juju_app_a_model",
                    source_app_name="juju_app_a",
                    target_namespace="juju_app_c_model",
                    target_app_name="juju_app_c",
                    target_type=PolicyTargetType.app,
                    endpoints=[
                        Endpoint(
                            ports=[8080, 443],
                            methods=[Method.get],
                            paths=["/foo"]
                        )
                    ]
                ],
                # policy to allow juju_app_a in juju_app_a_model to talk to juju_app_d in juju_app_d_model with a service
                # through its pod address in ports 8080. For unit type policies paths and methods restrictions don't apply.
                MeshPolicy[
                    source_namespace="juju_app_a_model",
                    source_app_name="juju_app_a",
                    target_namespace="juju_app_d_model",
                    target_app_name="juju_app_d",
                    target_type=PolicyTargetType.unit,
                    endpoints=[
                        Endpoint(
                            ports=[8080]
                        )
                    ]
                ]
            ]
            return policies

        def _on_remove(self):
            prm = self._get_policy_manager()
            prm.delete()

        def _reconcile(self):
            prm = self._get_policy_manager()
            policies = self._get_policies_i_manage()
            prm.reconcile(policies, MeshType.istio)
    ````
    Args:
        charm (ops.CharmBase): The charm instantiating this object.
        lightkube_client (lightkube.Client): Lightkube Client to use for all k8s operations.
                                             This Client must be instantiated with a
                                             field_manager, otherwise it cannot be used to
                                             .apply() resources because the kubernetes server
                                             side apply patch method requires it. A good option
                                             for this is to use the application name (eg:
                                             `self.model.app.name` or
                                             `self.model.app.name +'_' self.model.name`).
        mesh_type (charms.istio_beacon_k8s.v0.service_mesh.MeshType): The type of service mesh for which
                                                                      the policy resources are to be generated.
                                                                      (eg: MeshType.istio)
        labels (dict): A dict of labels to use as a label selector for all resources
                           managed by this KRM.  These will be added to any applied resources at
                           .apply() time and will be used to find existing resources in
                           .get_deployed_resources().
                           Recommended input for this is:
                             labels = {
                              'app.kubernetes.io/name': f"{self.model.app.name}-{self.model.name}",
                              'kubernetes-resource-handler-scope': 'some-user-chosen-scope'
                             }
                           See `get_default_labels` for a helper to generate this label dict.
        logger (logging.Logger): (Optional) A logger to use for logging (so that log messages
                                 emitted here will appear under the caller's log namespace).
                                 If not provided, a default logger will be created.
    """
    def __init__(
        self,
        charm: CharmBase,
        lightkube_client: Client,
        labels: Optional[Dict] = None,
        logger: Optional[logging.Logger] = None,
    ):
        self._app_name = charm.app.name
        self._model_name = charm.model.name
        resource_types = self._get_all_supported_policy_resource_types()

        if logger is None:
            self.log = logging.getLogger(__name__)
        else:
            self.log = logger
        self._krm = KubernetesResourceManager(
            labels=labels,
            resource_types=resource_types,  # type: ignore
            lightkube_client=lightkube_client,
            logger=self.log,
        )

    @staticmethod
    def _get_all_supported_policy_resource_types() -> LightkubeResourceTypesSet:
        """Return all the resource types supported by the PRM class."""
        all_types: Set[Type] = set()
        for resource_types in POLICY_RESOURCE_TYPES.values():
            all_types.update(resource_types)
        return all_types

    @staticmethod
    def _get_policy_resource_builder(mesh_type: MeshType):
        if mesh_type == MeshType.istio:
            return _build_policy_resources_istio
        raise ValueError(f"PolicyResourceManager instantiated with an unknown mesh type: {mesh_type}. Check Canonical Service Mesh documentation for currently supported mesh types.")

    def _build_policy_resources(self, policies: List[MeshPolicy], mesh_type: MeshType) -> LightkubeResourcesList:
        """Build the Lightkube resources for the managed policies."""
        policy_resource_builder = self._get_policy_resource_builder(mesh_type)
        return policy_resource_builder(self._app_name, self._model_name, policies)  # type: ignore

    def _validate_raw_policies(self, raw_policies: List[AuthorizationPolicy]) -> None:  # type: ignore[type-arg]
        """Validate that raw_policies contain only supported resource types.

        Raises:
            TypeError: If a raw_policy is not of a supported type.
        """
        supported_types = self._get_all_supported_policy_resource_types()
        if not supported_types:
            raise RuntimeError("No supported policy resource types found in PolicyResourceManager.")
        for policy in raw_policies:
            if type(policy) not in supported_types:
                self.log.error(
                    f"raw_policy of type '{type(policy).__name__}' is not a supported policy resource type."
                )
                raise TypeError(
                    f"raw_policy of type '{type(policy).__name__}' is not a supported policy resource type. "
                    f"Supported types: {[t.__name__ for t in supported_types]}"
                )

    def reconcile(
        self,
        policies: List[MeshPolicy],
        mesh_type: MeshType,
        raw_policies: Optional[List[AuthorizationPolicy]] = None,  # type: ignore[type-arg]
        force: bool = True,
        ignore_missing: bool = True,
    ) -> None:
        """Reconcile the given policies, removing, updating, or creating objects as required.

        The MeshPolicy objects are first converted into manifests for Kubernetes policy resources that the
        service mesh can understand. eg: AuthorizationPolicy resources for Istio service mesh.

        This method will:
        * create a list of policy resources containing a policy resource for every provided MeshPolicy object
        * optionally merge with raw_policies (pre-built policy resources provided by the caller)
        * get all resources currently deployed that match the label selector in self.labels
        * compare the existing resources to the desired resources provided, deleting any resources
          that exist but are not in the desired resource list
        * call krm.apply() to create any new resources and update any remaining existing ones to the
          desired state

        Args:
            policies: A list of MeshPolicy objects that define the required behaviour of the policy resources.
            mesh_type: The type of service mesh the charm is connected to. This information can be obtained from ServiceMeshConsumer.
            raw_policies: *(optional)* Pre-built policy resources to merge with the built policies.
                          These must be of supported types (e.g., AuthorizationPolicy for Istio).
            force: *(optional)* Passed to self.apply().  This will force apply over any resources
                   marked as managed by another field manager.
            ignore_missing: *(optional)* Avoid raising 404 errors on deletion (defaults to True)

        Raises:
            TypeError: If raw_policies contains resources of unsupported types.
        """
        if raw_policies:
            self._validate_raw_policies(raw_policies)

        all_resources: List = list(self._build_policy_resources(policies, mesh_type)) if policies else []
        if raw_policies:
            all_resources.extend(raw_policies)

        if not all_resources:
            self.delete(ignore_missing=ignore_missing)
            return

        self._krm.reconcile(all_resources, force=force, ignore_missing=ignore_missing)

    def delete(self, ignore_missing=True):
        """Delete all the policy resources handled by this manager.

        Requires that self.labels and self.resource_types be set.

        Args:
            ignore_missing: *(optional)* Avoid raising 404 errors on deletion (defaults to True)
        """
        try:
            self._krm.delete(ignore_missing=ignore_missing)
        # FIXME: this is a workaround and should be handled by the upstream krm. Issue exists: https://github.com/canonical/lightkube-extensions/issues/4
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404 and ignore_missing:
                # CRD doesn't exist, nothing to delete (only when ignore_missing=True)
                self.log.info("CRD not found, skipping deletion")
                return
            raise


def get_data_from_cmr_relation(cmr_relations) -> Dict[str, CMRData]:
    """Return a dictionary of CMRData from the established cross-model relations."""
    cmr_data = {}
    for cmr in cmr_relations:
        if "cmr_data" in cmr.data[cmr.app]:
            try:
                cmr_data[cmr.app.name] = CMRData.model_validate(json.loads(cmr.data[cmr.app]["cmr_data"]))
            except pydantic.ValidationError as e:
                logger.error(f"Invalid CMR data for {cmr.app.name}: {e}")
                continue
    return cmr_data

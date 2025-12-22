# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""Mock NFS server for integration testing.

Deploys a lightweight NFS server container in the test namespace
to enable testing of the native-nfs backend without external infrastructure.
"""

import time

from lightkube.models.apps_v1 import DeploymentSpec
from lightkube.models.core_v1 import (
    Capabilities,
    Container,
    ContainerPort,
    EmptyDirVolumeSource,
    EnvVar,
    PodSpec,
    PodTemplateSpec,
    SecurityContext,
    ServicePort,
    ServiceSpec,
    Volume,
    VolumeMount,
)
from lightkube.models.meta_v1 import LabelSelector, ObjectMeta
from lightkube.resources.apps_v1 import Deployment
from lightkube.resources.core_v1 import Service

from charmarr_lib.core import K8sResourceManager

NFS_SERVER_NAME = "mock-nfs-server"
NFS_EXPORT_PATH = "/export"
NFS_IMAGE = "itsthenetwork/nfs-server-alpine:12"


def deploy_nfs_server(k8s: K8sResourceManager, namespace: str, timeout: int = 120) -> str:
    """Deploy a mock NFS server and return its ClusterIP.

    Args:
        k8s: K8sResourceManager instance.
        namespace: Kubernetes namespace to deploy into.
        timeout: Seconds to wait for the server to be ready.

    Returns:
        The ClusterIP of the NFS server service.
    """
    labels = {"app": NFS_SERVER_NAME}

    deployment = Deployment(
        metadata=ObjectMeta(name=NFS_SERVER_NAME, namespace=namespace),
        spec=DeploymentSpec(
            replicas=1,
            selector=LabelSelector(matchLabels=labels),
            template=PodTemplateSpec(
                metadata=ObjectMeta(labels=labels),
                spec=PodSpec(
                    containers=[
                        Container(
                            name="nfs",
                            image=NFS_IMAGE,
                            ports=[
                                ContainerPort(containerPort=2049, name="nfs"),
                            ],
                            env=[
                                EnvVar(name="SHARED_DIRECTORY", value=NFS_EXPORT_PATH),
                            ],
                            securityContext=SecurityContext(
                                privileged=True,
                                capabilities=Capabilities(add=["SYS_ADMIN"]),
                            ),
                            volumeMounts=[
                                VolumeMount(name="export", mountPath=NFS_EXPORT_PATH),
                            ],
                        )
                    ],
                    volumes=[
                        Volume(name="export", emptyDir=EmptyDirVolumeSource()),
                    ],
                ),
            ),
        ),
    )

    service = Service(
        metadata=ObjectMeta(name=NFS_SERVER_NAME, namespace=namespace),
        spec=ServiceSpec(
            selector=labels,
            ports=[
                ServicePort(port=2049, targetPort=2049, name="nfs"),
            ],
        ),
    )

    k8s.apply(deployment)
    k8s.apply(service)

    return _wait_for_nfs_server(k8s, namespace, timeout)


def _wait_for_nfs_server(k8s: K8sResourceManager, namespace: str, timeout: int) -> str:
    """Wait for NFS server to be ready and return its ClusterIP."""
    start = time.time()

    while time.time() - start < timeout:
        try:
            deployment = k8s.get(Deployment, NFS_SERVER_NAME, namespace)
            if (
                deployment.status
                and deployment.status.readyReplicas
                and deployment.status.readyReplicas >= 1
            ):
                service = k8s.get(Service, NFS_SERVER_NAME, namespace)
                if service.spec and service.spec.clusterIP:
                    return service.spec.clusterIP
        except Exception:
            pass

        time.sleep(2)

    raise TimeoutError(f"NFS server not ready after {timeout}s")


def cleanup_nfs_server(k8s: K8sResourceManager, namespace: str) -> None:
    """Remove the mock NFS server from the namespace."""
    k8s.delete(Service, NFS_SERVER_NAME, namespace)
    k8s.delete(Deployment, NFS_SERVER_NAME, namespace)

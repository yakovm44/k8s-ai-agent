from fastapi import FastAPI, HTTPException
from kubernetes import client, config
from kubernetes.config.config_exception import ConfigException

app = FastAPI(
    title="Kubernetes AI Agent",
    description="API for checking Kubernetes Pods health",
    version="1.0.0",
)


def get_kubernetes_client():
    """
    Try to connect to Kubernetes.

    Inside Kubernetes:
        use in-cluster configuration.

    Local development:
        use ~/.kube/config
    """

    try:
        # Running inside Kubernetes
        config.load_incluster_config()
    except ConfigException:
        try:
            # Running locally
            config.load_kube_config()
        except ConfigException as e:
            raise RuntimeError(
                "Could not load Kubernetes configuration"
            ) from e

    return client.CoreV1Api()


@app.get("/")
def root():
    return {
        "service": "kubernetes-ai-agent",
        "status": "running"
    }


@app.get("/health")
def health():
    return {
        "status": "healthy"
    }


@app.get("/pods")
def get_pods(namespace: str = "default"):
    """
    Return all Pods in the requested namespace.
    """

    try:
        v1 = get_kubernetes_client()

        pods = v1.list_namespaced_pod(namespace)

        result = []

        for pod in pods.items:

            container_statuses = pod.status.container_statuses or []

            containers = []

            for container in container_statuses:
                containers.append({
                    "name": container.name,
                    "ready": container.ready,
                    "restart_count": container.restart_count,
                    "state": get_container_state(container)
                })

            result.append({
                "name": pod.metadata.name,
                "namespace": pod.metadata.namespace,
                "phase": pod.status.phase,
                "node": pod.spec.node_name,
                "containers": containers
            })

        return {
            "namespace": namespace,
            "pod_count": len(result),
            "pods": result
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )


@app.get("/pods/unhealthy")
def get_unhealthy_pods(namespace: str = "default"):
    """
    Return only Pods that appear to be unhealthy.
    """

    try:
        v1 = get_kubernetes_client()

        pods = v1.list_namespaced_pod(namespace)

        unhealthy = []

        for pod in pods.items:

            reasons = []

            # Pod phase
            if pod.status.phase not in ["Running", "Succeeded"]:
                reasons.append(
                    f"Pod phase is {pod.status.phase}"
                )

            # Container status
            container_statuses = pod.status.container_statuses or []

            for container in container_statuses:

                if not container.ready:
                    reasons.append(
                        f"Container {container.name} is not ready"
                    )

                if container.restart_count > 5:
                    reasons.append(
                        f"Container {container.name} restarted "
                        f"{container.restart_count} times"
                    )

                state = container.state

                if state.waiting:
                    if state.waiting.reason:
                        reasons.append(
                            f"Container {container.name}: "
                            f"{state.waiting.reason}"
                        )

                if state.terminated:
                    if state.terminated.reason:
                        reasons.append(
                            f"Container {container.name}: "
                            f"{state.terminated.reason}"
                        )

            if reasons:
                unhealthy.append({
                    "name": pod.metadata.name,
                    "namespace": pod.metadata.namespace,
                    "phase": pod.status.phase,
                    "node": pod.spec.node_name,
                    "reasons": reasons
                })

        return {
            "namespace": namespace,
            "unhealthy_pod_count": len(unhealthy),
            "pods": unhealthy
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )


def get_container_state(container):
    """
    Convert Kubernetes container state into a simple string.
    """

    if container.state.running:
        return "Running"

    if container.state.waiting:
        return container.state.waiting.reason or "Waiting"

    if container.state.terminated:
        return container.state.terminated.reason or "Terminated"

    return "Unknown"

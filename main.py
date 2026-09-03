from fastapi import FastAPI
from kubernetes import client, config
from kubernetes.config.config_exception import ConfigException

app = FastAPI()


def get_k8s_client():
    try:
        config.load_incluster_config()
    except ConfigException:
        config.load_kube_config()

    return client.CoreV1Api()


@app.get("/")
def root():
    return {
        "service": "kubernetes-pod-agent",
        "status": "running"
    }


@app.get("/pods")
def get_pods():
    v1 = get_k8s_client()

    pods = v1.list_pod_for_all_namespaces()

    result = []

    for pod in pods.items:
        containers = []

        for container in pod.status.container_statuses or []:
            containers.append({
                "name": container.name,
                "ready": container.ready,
                "restarts": container.restart_count
            })

        result.append({
            "namespace": pod.metadata.namespace,
            "name": pod.metadata.name,
            "phase": pod.status.phase,
            "node": pod.spec.node_name,
            "containers": containers
        })

    return {
        "pod_count": len(result),
        "pods": result
    }


@app.get("/health/pods")
def check_pods_health():
    v1 = get_k8s_client()

    pods = v1.list_pod_for_all_namespaces()

    problems = []
    healthy = 0

    for pod in pods.items:
        pod_problems = []

        # Check Pod phase
        if pod.status.phase != "Running":
            pod_problems.append(
                f"Pod phase is {pod.status.phase}"
            )

        # Check containers
        for container in pod.status.container_statuses or []:

            if not container.ready:
                reason = "container is not ready"

                if container.state.waiting:
                    reason = (
                        container.state.waiting.reason
                        or "container is waiting"
                    )

                pod_problems.append(
                    f"{container.name}: {reason}"
                )

            # More than 5 restarts
            if container.restart_count > 5:
                pod_problems.append(
                    f"{container.name}: "
                    f"{container.restart_count} restarts"
                )

        if pod_problems:
            problems.append({
                "namespace": pod.metadata.namespace,
                "pod": pod.metadata.name,
                "node": pod.spec.node_name,
                "problems": pod_problems
            })
        else:
            healthy += 1

    total = len(pods.items)
    unhealthy = len(problems)

    status = "OK"

    if unhealthy > 0:
        status = "WARNING"

    return {
        "status": status,
        "total_pods": total,
        "healthy": healthy,
        "unhealthy": unhealthy,
        "problems": problems
    }
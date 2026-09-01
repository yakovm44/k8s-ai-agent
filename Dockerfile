FROM python:3.12-slim

RUN pip install --no-cache-dir \
    fastapi \
    uvicorn \
    kubernetes

WORKDIR /app

RUN cat <<'PY' > /app/main.py
from fastapi import FastAPI
from kubernetes import client, config
from kubernetes.config.config_exception import ConfigException

app = FastAPI()


def get_k8s_client():
    try:
        # When running inside Kubernetes
        config.load_incluster_config()
    except ConfigException:
        # For local testing
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


@app.get("/unhealthy")
def get_unhealthy_pods():

    v1 = get_k8s_client()

    pods = v1.list_pod_for_all_namespaces()

    unhealthy = []

    for pod in pods.items:

        reasons = []

        if pod.status.phase not in ["Running", "Succeeded"]:
            reasons.append(
                f"Pod phase: {pod.status.phase}"
            )

        for container in pod.status.container_statuses or []:

            if not container.ready:
                reasons.append(
                    f"Container {container.name} is not ready"
                )

            if container.restart_count > 5:
                reasons.append(
                    f"Container {container.name} restarted "
                    f"{container.restart_count} times"
                )

            if container.state.waiting:
                reasons.append(
                    f"Container {container.name} waiting: "
                    f"{container.state.waiting.reason}"
                )

        if reasons:
            unhealthy.append({
                "namespace": pod.metadata.namespace,
                "name": pod.metadata.name,
                "node": pod.spec.node_name,
                "reasons": reasons
            })

    return {
        "unhealthy_count": len(unhealthy),
        "pods": unhealthy
    }
PY

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
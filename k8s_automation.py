import subprocess
import yaml
import json
from kubernetes import client, config
from kubernetes.client.rest import ApiException
import sys
import os
from typing import Dict, Any

class KubernetesAutomation:
    """A class to automate Kubernetes operations including KEDA installation and deployment management."""

    def __init__(self, kubeconfig_path: str = None):
        """Initialize Kubernetes client with optional kubeconfig path."""
        try:
            if kubeconfig_path and os.path.exists(kubeconfig_path):
                config.load_kube_config(config_file=kubeconfig_path)
            else:
                config.load_incluster_config()  # Fallback for in-cluster execution
            self.core_v1 = client.CoreV1Api()
            self.apps_v1 = client.AppsV1Api()
            self.custom_objects_api = client.CustomObjectsApi()
            print("Successfully connected to Kubernetes cluster")
        except Exception as e:
            print(f"Error connecting to Kubernetes cluster: {str(e)}")
            sys.exit(1)

    def install_helm(self) -> bool:
        """Install Helm if not present and verify installation."""
        try:
            result = subprocess.run(
                ["helm", "version", "--short"],
                capture_output=True, text=True, check=True
            )
            print(f"Helm already installed: {result.stdout.strip()}")
            return True
        except subprocess.CalledProcessError:
            print("Helm not found. Please install Helm manually or ensure it's in PATH.")
            return False
        except Exception as e:
            print(f"Error checking Helm installation: {str(e)}")
            return False

    def install_keda(self, namespace: str = "keda") -> bool:
        """Install KEDA using Helm and verify the operator is running."""
        try:
            # Add KEDA Helm repository
            subprocess.run(["helm", "repo", "add", "kedacore", "https://kedacore.github.io/charts"], check=True)
            subprocess.run(["helm", "repo", "update"], check=True)

            # Create namespace if it doesn't exist
            try:
                self.core_v1.read_namespace(name=namespace)
            except ApiException as e:
                if e.status == 404:
                    namespace_body = client.V1Namespace(metadata=client.V1ObjectMeta(name=namespace))
                    self.core_v1.create_namespace(namespace_body)
                    print(f"Created namespace: {namespace}")
                else:
                    raise e

            # Install KEDA Helm chart
            subprocess.run(
                ["helm", "install", "keda", "kedacore/keda", "--namespace", namespace, "--create-namespace"],
                check=True
            )
            print("KEDA Helm chart installed successfully")

            # Verify KEDA operator is running
            pods = self.core_v1.list_namespaced_pod(namespace=namespace, label_selector="app=keda-operator")
            if not pods.items:
                print("Error: KEDA operator pod not found")
                return False
            for pod in pods.items:
                if pod.status.phase != "Running":
                    print(f"Error: KEDA operator pod {pod.metadata.name} is not running")
                    return False
            print("KEDA operator is running")
            return True
        except subprocess.CalledProcessError as e:
            print(f"Error installing KEDA: {e.stderr}")
            return False
        except ApiException as e:
            print(f"Kubernetes API error: {str(e)}")
            return False
        except Exception as e:
            print(f"Unexpected error installing KEDA: {str(e)}")
            return False

    def create_deployment(self, config_file: str) -> Dict[str, Any]:
        """Create a Kubernetes deployment with KEDA ScaledObject based on a config file."""
        try:
            # Load and validate configuration
            with open(config_file, 'r') as f:
                config_data = yaml.safe_load(f)

            required_fields = ['deployment_name', 'namespace', 'image', 'tag', 'cpu_request', 'cpu_limit',
                              'memory_request', 'memory_limit', 'port', 'min_replicas', 'max_replicas',
                              'scaler_type', 'scaler_config']
            for field in required_fields:
                if field not in config_data:
                    raise ValueError(f"Missing required configuration field: {field}")

            deployment_name = config_data['deployment_name']
            namespace = config_data['namespace']

            # Create namespace if it doesn't exist
            try:
                self.core_v1.read_namespace(name=namespace)
            except ApiException as e:
                if e.status == 404:
                    namespace_body = client.V1Namespace(metadata=client.V1ObjectMeta(name=namespace))
                    self.core_v1.create_namespace(namespace_body)
                    print(f"Created namespace: {namespace}")
                else:
                    raise e

            # Create deployment
            deployment = client.V1Deployment(
                metadata=client.V1ObjectMeta(name=deployment_name, namespace=namespace),
                spec=client.V1DeploymentSpec(
                    replicas=config_data['min_replicas'],
                    selector=client.V1LabelSelector(match_labels={"app": deployment_name}),
                    template=client.V1PodTemplateSpec(
                        metadata=client.V1ObjectMeta(labels={"app": deployment_name}),
                        spec=client.V1PodSpec(
                            containers=[
                                client.V1Container(
                                    name=deployment_name,
                                    image=f"{config_data['image']}:{config_data['tag']}",
                                    ports=[client.V1ContainerPort(container_port=config_data['port'])],
                                    resources=client.V1ResourceRequirements(
                                        requests={"cpu": config_data['cpu_request'], "memory": config_data['memory_request']},
                                        limits={"cpu": config_data['cpu_limit'], "memory": config_data['memory_limit']}
                                    ),
                                    env=[
                                        client.V1EnvVar(name=k, value=v) for k, v in config_data.get('env_vars', {}).items()
                                    ]
                                )
                            ]
                        )
                    )
                )
            )
            self.apps_v1.create_namespaced_deployment(namespace=namespace, body=deployment)
            print(f"Deployment {deployment_name} created in namespace {namespace}")

            # Create service
            service = client.V1Service(
                metadata=client.V1ObjectMeta(name=f"{deployment_name}-service", namespace=namespace),
                spec=client.V1ServiceSpec(
                    selector={"app": deployment_name},
                    ports=[client.V1ServicePort(port=config_data['port'], target_port=config_data['port'])],
                    type="ClusterIP"
                )
            )
            self.core_v1.create_namespaced_service(namespace=namespace, body=service)
            print(f"Service {deployment_name}-service created")

            # Create KEDA ScaledObject
            scaled_object = {
                "apiVersion": "keda.sh/v1alpha1",
                "kind": "ScaledObject",
                "metadata": {"name": f"{deployment_name}-scaler", "namespace": namespace},
                "spec": {
                    "scaleTargetRef": {"name": deployment_name},
                    "minReplicaCount": config_data['min_replicas'],
                    "maxReplicaCount": config_data['max_replicas'],
                    "triggers": [
                        {
                            "type": config_data['scaler_type'],
                            "metadata": config_data['scaler_config']
                        }
                    ]
                }
            }
            self.custom_objects_api.create_namespaced_custom_object(
                group="keda.sh", version="v1alpha1", namespace=namespace,
                plural="scaledobjects", body=scaled_object
            )
            print(f"KEDA ScaledObject {deployment_name}-scaler created")

            # Return deployment details
            return {
                "deployment_name": deployment_name,
                "namespace": namespace,
                "endpoint": f"{deployment_name}-service.{namespace}.svc.cluster.local:{config_data['port']}",
                "scaling_config": {
                    "min_replicas": config_data['min_replicas'],
                    "max_replicas": config_data['max_replicas'],
                    "scaler_type": config_data['scaler_type'],
                    "scaler_config": config_data['scaler_config']
                }
            }
        except FileNotFoundError:
            print(f"Error: Configuration file {config_file} not found")
            return {}
        except yaml.YAMLError:
            print(f"Error: Invalid YAML in configuration file {config_file}")
            return {}
        except ApiException as e:
            print(f"Kubernetes API error: {str(e)}")
            return {}
        except ValueError as e:
            print(f"Validation error: {str(e)}")
            return {}
        except Exception as e:
            print(f"Unexpected error creating deployment: {str(e)}")
            return {}

    def get_deployment_health(self, deployment_name: str, namespace: str) -> Dict[str, Any]:
        """Check the health status of a deployment."""
        try:
            deployment = self.apps_v1.read_namespaced_deployment(name=deployment_name, namespace=namespace)
            status = deployment.status
            pods = self.core_v1.list_namespaced_pod(namespace=namespace, label_selector=f"app={deployment_name}")

            health = {
                "deployment_name": deployment_name,
                "namespace": namespace,
                "replicas": status.replicas,
                "available_replicas": status.available_replicas or 0,
                "ready_replicas": status.ready_replicas or 0,
                "pod_statuses": [
                    {
                        "pod_name": pod.metadata.name,
                        "phase": pod.status.phase,
                        "conditions": [
                            {"type": c.type, "status": c.status} for c in pod.status.conditions or []
                        ]
                    } for pod in pods.items
                ]
            }
            print(f"Health status for deployment {deployment_name}: {json.dumps(health, indent=2)}")
            return health
        except ApiException as e:
            print(f"Error checking deployment health: {str(e)}")
            return {}
        except Exception as e:
            print(f"Unexpected error checking health: {str(e)}")
            return {}

def main():
    """CLI entry point for Kubernetes automation script."""
    import argparse
    parser = argparse.ArgumentParser(description="Kubernetes Automation CLI for KEDA and Deployments")
    parser.add_argument("--kubeconfig", help="Path to kubeconfig file", default=None)
    parser.add_argument("--action", choices=["install", "deploy", "health"], required=True,
                        help="Action to perform: install tools, deploy, or check health")
    parser.add_argument("--config", help="Path to deployment configuration file (for deploy action)")
    parser.add_argument("--deployment", help="Deployment name (for health action)")
    parser.add_argument("--namespace", help="Namespace (for health action)", default="default")

    args = parser.parse_args()
    k8s = KubernetesAutomation(args.kubeconfig)

    if args.action == "install":
        if k8s.install_helm():
            k8s.install_keda()
    elif args.action == "deploy":
        if not args.config:
            print("Error: --config is required for deploy action")
            sys.exit(1)
        k8s.create_deployment(args.config)
    elif args.action == "health":
        if not args.deployment:
            print("Error: --deployment is required for health action")
            sys.exit(1)
        k8s.get_deployment_health(args.deployment, args.namespace)

if __name__ == "__main__":
    main()

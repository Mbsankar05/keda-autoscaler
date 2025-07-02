# keda-autoscaler
# Kubernetes Automation CLI

This project provides a Python CLI script to automate operations on a bare Kubernetes cluster, including connecting to the cluster, installing Helm and KEDA, creating deployments with event-driven autoscaling, and checking deployment health. The script is modular, secure, and follows best practices for Kubernetes resource management.

## Objective
The script automates:
1. Connecting to a Kubernetes cluster via `kubectl`.
2. Installing Helm and KEDA for package management and event-driven autoscaling.
3. Creating deployments with KEDA ScaledObjects for event-driven scaling (e.g., RabbitMQ).
4. Checking health status of deployments.

## Prerequisites
- **Kubernetes Cluster**: A running cluster with `kubectl` configured (kubeconfig file or in-cluster access).
- **Python 3.8+**: Required to run the script.
- **Python Libraries**:
  ```bash
  pip install kubernetes pyyaml
  ```
- **Helm**: Installed locally or accessible in PATH (https://helm.sh/docs/intro/install/).
- **kubectl**: Configured to access the cluster (https://kubernetes.io/docs/tasks/tools/).
- **DockerHub**: Public image access (e.g., `nginxdemos/hello:latest`).
- **RabbitMQ**: For KEDA scaling, a RabbitMQ instance must be running in the cluster (e.g., via `helm install rabbitmq bitnami/rabbitmq`).

## Installation
1. Clone the repository:
   ```bash
   git clone <repository-url>
   cd <repository-directory>
   ```
2. Install Python dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Ensure `kubectl` and Helm are installed and configured.

## Usage
The script supports three actions: `install`, `deploy`, and `health`.

### 1. Install Helm and KEDA
```bash
python k8s_automation.py --action install --kubeconfig ~/.kube/config
```
- Installs Helm (if not present) and KEDA in the `keda` namespace.
- Verifies KEDA operator is running.

### 2. Create a Deployment
```bash
python k8s_automation.py --action deploy --config deployment_config.yaml --kubeconfig ~/.kube/config
```
- Uses a YAML config file (e.g., `deployment_config.yaml`) to create a deployment, service, and KEDA ScaledObject.
- Sample `deployment_config.yaml`:
  ```yaml
  deployment_name: my-app
  namespace: default
  image: nginxdemos/hello
  tag: latest
  cpu_request: "100m"
  cpu_limit: "200m"
  memory_request: "128Mi"
  memory_limit: "256Mi"
  port: 80
  min_replicas: 0
  max_replicas: 5
  scaler_type: rabbitmq
  scaler_config:
    queueName: my-queue
    queueLength: "5"
    host: "rabbitmq.default.svc.cluster.local"
  env_vars:
    APP_ENV: production
  ```
- Returns deployment details (endpoint, scaling config).

### 3. Check Deployment Health
```bash
python k8s_automation.py --action health --deployment my-app --namespace default --kubeconfig ~/.kube/config
```
- Displays health status (replicas, pod statuses).

## Security Measures
- **RBAC**: Uses Kubernetes RBAC via kubeconfig for access control.
- **Secrets**: Supports KEDA `TriggerAuthentication` for secure scaler credentials (configure separately).
- **Validation**: Input validation prevents invalid configurations.
- **Namespace Isolation**: Deployments are isolated in specified namespaces.

## Testing
1. **Setup**: Ensure a Kubernetes cluster (e.g., Minikube, AKS) is running and `kubectl` is configured.
2. **Install RabbitMQ** (for KEDA scaling):
   ```bash
   helm repo add bitnami https://charts.bitnami.com/bitnami
   helm install rabbitmq bitnami/rabbitmq --set auth.username=guest,auth.password=guest
   ```
3. **Run Install**:
   ```bash
   python k8s_automation.py --action install
   ```
   - Verify KEDA pods: `kubectl get pods -n keda`.
4. **Deploy Application**:
   ```bash
   python k8s_automation.py --action deploy --config deployment_config.yaml
   ```
   - Verify deployment: `kubectl get deployments -n default`.
   - Check ScaledObject: `kubectl get scaledobjects -n default`.
5. **Check Health**:
   ```bash
   python k8s_automation.py --action health --deployment my-app --namespace default
   ```
6. **Generate Load** (for RabbitMQ scaling):
   - Send messages to RabbitMQ queue (`my-queue`) to trigger scaling.
   - Monitor replicas: `kubectl get pods -n default -w`.

## Error Handling
- Validates configuration files for required fields.
- Checks for Helm and KEDA installation issues.
- Handles Kubernetes API errors with clear messages.
- Exits gracefully on failures with actionable feedback.

## Best Practices
- **Modular Design**: Functions are reusable for different configurations.
- **Resource Limits**: Enforces CPU/memory limits for efficiency.
- **KEDA Integration**: Supports scaling to zero for cost savings.
- **Documentation**: Inline comments and this README for clarity.

## Repository Structure
- `k8s_automation.py`: Main Python CLI script.
- `deployment_config.yaml`: Sample configuration for deployment.
- `README.md`: This documentation.
- `requirements.txt`: Python dependencies.

## Screenshots/Logs
- After running `install`, check KEDA pods:
  ```bash
  kubectl get pods -n keda
  ```
  Expected output:
  ```
  NAME                                    READY   STATUS    RESTARTS   AGE
  keda-operator-...                       1/1     Running   0          2m
  keda-operator-metrics-apiserver-...     1/1     Running   0          2m
  ```
- After `deploy`, check deployment and ScaledObject:
  ```bash
  kubectl get deployments,services,scaledobjects -n default
  ```
  Expected output:
  ```
  NAME                     READY   UP-TO-DATE   AVAILABLE   AGE
  deployment.apps/my-app   0/0     0            0           1m

  NAME                        TYPE        CLUSTER-IP     PORT(S)   AGE
  service/my-app-service      ClusterIP   10.96.123.45   80/TCP    1m

  NAME                             SCALE-TARGET   MIN   MAX   AGE
  scaledobject.keda.sh/my-app-scaler   my-app         0     5     1m
  ```
- Health check output (example):
  ```json
  {
    "deployment_name": "my-app",
    "namespace": "default",
    "replicas": 0,
    "available_replicas": 0,
    "ready_replicas": 0,
    "pod_statuses": []
  }
  ```

## Notes
- Replace `ACCOUNT_ID` in configurations with your AWS account ID if using AWS-specific scalers.
- For production, configure `TriggerAuthentication` for secure scaler credentials (see KEDA docs: https://keda.sh/docs/2.15/concepts/authentication/).
- Test thoroughly in a non-production environment first.

## GitHub Repository
Upload to a public GitHub repository with the above files. Ensure `requirements.txt` includes:
```
kubernetes==30.1.0
pyyaml==6.0.1
```

For further assistance, refer to:
- KEDA Documentation: https://keda.sh
- Kubernetes Python Client: https://github.com/kubernetes-client/python

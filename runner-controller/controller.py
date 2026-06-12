import os
import json
import logging
import subprocess
import hmac
import hashlib
import urllib.request, urllib.error
from http.server import HTTPServer, BaseHTTPRequestHandler

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("runner-controller")

NAMESPACE = os.environ.get("NAMESPACE", "arc-actions")
OWNER = os.environ.get("OWNER", "guilhermelinosp")
RUNNER_IMAGE = os.environ.get("RUNNER_IMAGE", "ghcr.io/guilhermelinosp/arc-runner:latest")
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "")

def has_workflows(full_name):
    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        return True
    req = urllib.request.Request(f"https://api.github.com/repos/{full_name}/contents/.github/workflows", headers={
        "Authorization": f"token {token}", "Accept": "application/vnd.github.v3+json", "User-Agent": "runner-controller",
    })
    try:
        urllib.request.urlopen(req, timeout=15)
        return True
    except urllib.error.HTTPError as e:
        if e.code == 404: return False
        log.warning(f"Error checking workflows for {full_name}: {e.code}")
        return False

def create_runner(full_name, repo_name):
    safe_name = repo_name.replace(".", "-").replace("_", "-").lower()
    manifest = f"""
apiVersion: actions.summerwind.dev/v1alpha1
kind: RunnerDeployment
metadata:
  name: runner-{safe_name}
  namespace: {NAMESPACE}
spec:
  replicas: 1
  template:
    spec:
      repository: {full_name}
      image: {RUNNER_IMAGE}
      dockerdWithinRunnerContainer: false
      resources:
        limits: {{ cpu: "1", memory: 2Gi }}
        requests: {{ cpu: 100m, memory: 256Mi }}
      nodeSelector:
        node-role.kubernetes.io/worker: ""
      tolerations:
        - key: "node-role.kubernetes.io/control-plane"
          operator: "Exists"
          effect: "NoSchedule"
---
apiVersion: actions.summerwind.dev/v1alpha1
kind: HorizontalRunnerAutoscaler
metadata:
  name: runner-{safe_name}-autoscaler
  namespace: {NAMESPACE}
spec:
  scaleTargetRef:
    name: runner-{safe_name}
  minReplicas: 0
  maxReplicas: 5
  metrics:
    - type: TotalNumberOfQueuedAndInProgressWorkflowRuns
      repositoryNames:
        - {full_name}
"""
    proc = subprocess.run(["kubectl", "apply", "-f", "-"], input=manifest.encode(), capture_output=True, timeout=30)
    if proc.returncode == 0:
        log.info(f"Runner created for {full_name}")
        return True
    log.error(f"Failed to create runner for {full_name}: {proc.stderr.decode()}")
    return False

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"runner-controller: ok")

    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        sig = self.headers.get("X-Hub-Signature-256", "")
        event = self.headers.get("X-GitHub-Event", "")

        if WEBHOOK_SECRET and sig:
            expected = "sha256=" + hmac.new(WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()
            if not hmac.compare_digest(expected, sig):
                log.warning("Invalid signature")
                self.send_response(401); self.end_headers(); return

        if event == "ping":
            self.send_response(200); self.end_headers(); self.wfile.write(json.dumps({"ok":True}).encode())
            return

        if event != "repository":
            self.send_response(200); self.end_headers(); return

        payload = json.loads(body)
        if payload.get("action") != "created":
            self.send_response(200); self.end_headers(); return

        repo = payload.get("repository", {})
        full_name = repo.get("full_name", "")
        owner_login = (repo.get("owner") or {}).get("login", "")
        repo_name = repo.get("name", "")

        if owner_login != OWNER:
            self.send_response(200); self.end_headers(); return

        log.info(f"Webhook: repo created → {full_name}")

        existing = subprocess.run(
            ["kubectl", "get", "runnerdeployment", "-n", NAMESPACE, "-o", "jsonpath={.items[*].spec.template.spec.repository}"],
            capture_output=True, timeout=15, text=True,
        )
        if full_name in (existing.stdout or ""):
            log.info(f"Runner already exists for {full_name}")
            self.send_response(200); self.end_headers(); self.wfile.write(json.dumps({"ok":True,"exists":full_name}).encode())
            return

        if not has_workflows(full_name):
            log.info(f"No workflows in {full_name}, skipping")
            self.send_response(200); self.end_headers(); self.wfile.write(json.dumps({"ok":True,"skipped":full_name}).encode())
            return

        if create_runner(full_name, repo_name):
            self.send_response(200); self.end_headers(); self.wfile.write(json.dumps({"ok":True,"runner":full_name}).encode())
        else:
            self.send_response(500); self.end_headers()

    def log_message(self, fmt, *args):
        log.info(f"{self.client_address[0]} - {fmt % args}")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(("0.0.0.0", port), Handler)
    log.info(f"Webhook-only controller on :{port}")
    server.serve_forever()

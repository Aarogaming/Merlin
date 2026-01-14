import grpc
import os
from loguru import logger
# Note: This requires the generated proto files to be available in the path
# In a real setup, we'd share the proto package or use a common library
try:
    import sys
    sys.path.append(os.path.abspath("../AaroneousAutomationSuite"))
    from proto import hub_pb2, hub_pb2_grpc
except ImportError:
    logger.error("Hub proto files not found. Ensure AaroneousAutomationSuite/proto is in path.")

class MerlinHubClient:
    def __init__(self):
        self.grpc_host = os.getenv("AAS_GRPC_HOST", "localhost")
        self.grpc_port = os.getenv("AAS_GRPC_PORT", "50052")
        self.channel = grpc.insecure_channel(f"{self.grpc_host}:{self.grpc_port}")
        self.stub = hub_pb2_grpc.HubServiceStub(self.channel)

    def create_aas_task(self, title, description, priority="Medium"):
        try:
            response = self.stub.CreateTask(hub_pb2.TaskRequest(
                title=title,
                description=description,
                priority=priority
            ))
            return response.task_id
        except Exception as e:
            logger.error(f"Failed to create AAS task: {e}")
            return None

    def get_task_status(self, task_id):
        try:
            response = self.stub.GetTaskStatus(hub_pb2.TaskId(id=task_id))
            return {
                "id": response.id,
                "status": response.status,
                "assignee": response.assignee
            }
        except Exception as e:
            logger.error(f"Failed to get task status: {e}")
            return None

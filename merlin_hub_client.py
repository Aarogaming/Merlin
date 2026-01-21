import grpc
import os
from loguru import logger

# Note: This requires the generated proto files to be available in the path
# In a real setup, we'd share the proto package or use a common library
try:
    import sys
    import grpc

    sys.path.append(os.path.abspath("../AaroneousAutomationSuite"))
    from proto import hub_pb2, hub_pb2_grpc  # type: ignore[import-not-found]

    _proto_loaded = True
    hub_pb2 = hub_pb2  # type: ignore[assignment]


except Exception:
    _proto_loaded = False
    grpc = None
    hub_pb2 = None
    hub_pb2_grpc = None
    logger.warning("Hub proto files not found. Merlin Hub integration disabled.")


class MerlinHubClient:
    def __init__(self):
        if not _proto_loaded or grpc is None or hub_pb2_grpc is None:
            self.channel = None
            self.stub = None
            return

        self.grpc_host = os.getenv("AAS_GRPC_HOST", "localhost")
        self.grpc_port = os.getenv("AAS_GRPC_PORT", "50052")
        self.channel = grpc.insecure_channel(f"{self.grpc_host}:{self.grpc_port}")
        self.stub = hub_pb2_grpc.HubServiceStub(self.channel)

    def create_aas_task(self, title, description, priority="Medium"):
        if not self.stub or hub_pb2 is None:
            return None
        try:
            response = self.stub.CreateTask(  # type: ignore[union-attr]
                hub_pb2.TaskRequest(  # type: ignore[union-attr]
                    title=title,
                    description=description,
                    priority=priority,
                )
            )
            return response.task_id
        except Exception as e:
            logger.error(f"Failed to create AAS task: {e}")
            return None

    def get_task_status(self, task_id):
        if not self.stub or hub_pb2 is None:
            return None
        try:
            response = self.stub.GetTaskStatus(  # type: ignore[union-attr]
                hub_pb2.TaskId(id=task_id)  # type: ignore[union-attr]
            )
            return {
                "id": response.id,
                "status": response.status,
                "assignee": response.assignee,
            }
        except Exception as e:
            logger.error(f"Failed to get task status: {e}")
            return None

from app.pipeline.feature_pipeline.models.raw import DocumentRawModel
import os
import uuid
from app.core.mq import publish_to_rabbitmq

path = "/data/liujl/projects/Bank-copilot/data/demo.md"
with open(os.path.join(os.path.dirname(__file__), path), "r") as f:
    demo_text = f.read()
    data = DocumentRawModel(
        knowledge_id="111",
        doc_id="222",
        path="file",
        filename="file",
        content=demo_text,
        type="documents",
        entry_id=str(uuid.uuid4()),
    ).model_dump_json()
    publish_to_rabbitmq(queue_name="test_files", data=data)

import requests
import os

token = os.getenv("MINERU_TOKEN")
url = "https://mineru.net/api/v4/extract/task"
header = {"Content-Type": "application/json", "Authorization": f"Bearer {token}"}
data = {"url": "https://cdn-mineru.openxlab.org.cn/demo/example.pdf", "model_version": "vlm"}

res = requests.post(url, headers=header, json=data)
print(res.status_code)
print(res.json())
print(res.json()["data"])

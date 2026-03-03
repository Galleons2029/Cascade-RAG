import requests

token = "eyJ0eXBlIjoiSldUIiwiYWxnIjoiSFM1MTIifQ.eyJqdGkiOiI1MDE0ODk4Iiwicm9sIjoiUk9MRV9SRUdJU1RFUiIsImlzcyI6Ik9wZW5YTGFiIiwiaWF0IjoxNzYzNTc3Mzk0LCJjbGllbnRJZCI6ImxremR4NTdudnkyMmprcHE5eDJ3IiwicGhvbmUiOiIiLCJvcGVuSWQiOm51bGwsInV1aWQiOiJjNWY5MjU5YS05OWUxLTRiOGUtOGM2Ny1mYmIwZjJlMDk0NjgiLCJlbWFpbCI6IiIsImV4cCI6MTc2NDc4Njk5NH0.vy1Eos9HtxKPthNTiMs0IFPcBORYd_Pm2x4jJjPD46CWEj0q01o7gs1L7l-yLWseKrP0F3akpDMysVE3UD5wyw"  # noqa: E501
url = "https://mineru.net/api/v4/extract/task"
header = {"Content-Type": "application/json", "Authorization": f"Bearer {token}"}
data = {"url": "/data/liujl/projects/Bank-copilot/data/Agent-Companion-CHN.pdf", "model_version": "vlm"}

res = requests.post(url, headers=header, json=data)
print(res.status_code)
print(res.json())
print(res.json()["data"])

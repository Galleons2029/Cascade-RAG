# -*- coding: utf-8 -*-
# @Time   : 2025/8/4 13:55
# @Author : Galleons
# @File   : main_client.py

"""
此处用于配置 MCP 服务端
"""

import asyncio
from fastmcp import Client

client = Client("../services/demo.py")


async def call_tool(name: str):
    async with client:
        result = await client.call_tool("greet", {"name": name})
        print(result)


asyncio.run(call_tool("Ford"))

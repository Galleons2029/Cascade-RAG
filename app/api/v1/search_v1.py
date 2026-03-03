# -*- coding: utf-8 -*-
# @Time   : 2025/8/13 14:40
# @Author : Galleons
# @File   : search_v1.py

"""
rag 向量检索
"""

from fastapi import APIRouter

router = APIRouter()


@router.get("/", summary="Search placeholder")
async def search_placeholder():
    """Placeholder search endpoint."""
    return {"message": "search service not yet implemented"}


# from PIL import Image
#
# find_image = model.get_query_embedding("Adventures on snow hills")
#
# ans1 = Image.open(client.query_points(
#     collection_name=COLLECTION_NAME,
#     query=find_image,
#     using="image",
#     with_payload=["image"],
#     limit=1
# ).points[0].payload['image'])
#
#
# ans2 = Image.open(client.query_points(
#     collection_name=COLLECTION_NAME,
#     query=model.get_query_embedding("Avventure sulle colline innevate"),
#     using="image",
#     with_payload=["image"],
#     limit=1
# ).points[0].payload['image'])
#
#
# ans3 = client.query_points(
#     collection_name=COLLECTION_NAME,
#     query=model.get_image_embedding("images/image-2.png"),
#     # Now we are searching only among text vectors with our image query
#     using="text",
#     with_payload=["caption"],
#     limit=1
# ).points[0].payload['caption']

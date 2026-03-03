# -*- coding: utf-8 -*-
# @Time   : 2025/8/13 14:52
# @Author : Galleons
# @File   : qdrant_search.py

"""
这里是文件说明
"""


def search(self, text: str):
    # Convert text query into vector
    vector = self.model.encode(text).tolist()

    # Use `vector` for search for closest vectors in the collection
    search_result = self.qdrant_client.query_points(
        collection_name=self.collection_name,
        query=vector,
        query_filter=None,  # If you don't want any filters for now
        limit=5,  # 5 the most closest results is enough
    ).points
    # `search_result` contains found vector ids with similarity scores along with the stored payload
    # In this function you are interested in payload only
    payloads = [hit.payload for hit in search_result]
    return payloads

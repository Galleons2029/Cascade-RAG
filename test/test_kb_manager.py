# -*- coding: utf-8 -*-
"""测试知识库管理 Agent"""

import sys
sys.path.insert(0, '/Users/apple/PycharmProjects/Bank-copilot')

from app.core.agent.graph.kb_manager import (
    create_collection, 
    get_collection_info, 
    delete_collection,
    add_documents,
    update_document,
    smart_upsert_document,
    check_document_exists,
    search_documents,
    scroll_documents,
    list_collections,
    kb_manager_graph,
)


def test_tools():
    """测试各个工具函数"""
    # 测试创建集合
    print('=' * 50)
    print('1. 测试创建集合')
    result = create_collection.invoke({'collection_name': 'test_kb_agent', 'vector_size': 1024})
    print(result)

    # 测试获取集合信息
    print('=' * 50)
    print('2. 测试获取集合信息')
    result = get_collection_info.invoke({'collection_name': 'test_kb_agent'})
    print(result)

    # 测试添加文档
    print('=' * 50)
    print('3. 测试添加文档')
    texts = [
        '人工智能是计算机科学的一个分支，致力于开发能够模拟人类智能的系统。',
        '机器学习是人工智能的子领域，通过数据训练模型来做出预测。',
        '深度学习使用神经网络来处理复杂的模式识别任务。',
    ]
    metadata = [
        {'source': 'AI基础', 'category': 'intro'},
        {'source': 'ML基础', 'category': 'ml'},
        {'source': 'DL基础', 'category': 'dl'},
    ]
    result = add_documents.invoke({
        'collection_name': 'test_kb_agent',
        'texts': texts,
        'metadata': metadata
    })
    print(result)

    # 测试搜索文档
    print('=' * 50)
    print('4. 测试搜索文档')
    result = search_documents.invoke({
        'collection_name': 'test_kb_agent',
        'query': '什么是机器学习？',
        'limit': 3
    })
    print(result)

    # 测试浏览文档
    print('=' * 50)
    print('5. 测试浏览文档')
    result = scroll_documents.invoke({
        'collection_name': 'test_kb_agent',
        'limit': 5
    })
    print(result)

    # 列出所有集合
    print('=' * 50)
    print('6. 列出所有集合')
    result = list_collections.invoke({})
    print(result)

    # 清理测试数据
    print('=' * 50)
    print('7. 清理测试数据')
    result = delete_collection.invoke({'collection_name': 'test_kb_agent'})
    print(result)

    print('=' * 50)
    print('所有测试完成!')


def test_smart_upsert():
    """测试智能添加/更新功能"""
    print('=' * 60)
    print('测试智能添加/更新文档功能')
    print('=' * 60)
    
    # 创建测试集合
    print('\n1. 创建测试集合')
    result = create_collection.invoke({'collection_name': 'test_smart_upsert'})
    print(result)
    
    # 添加初始文档
    print('\n2. 添加初始文档')
    result = add_documents.invoke({
        'collection_name': 'test_smart_upsert',
        'texts': ['人工智能是一种模拟人类智能的技术'],
        'metadata': [{'source': 'test'}]
    })
    print(result)
    
    # 检查相似文档是否存在
    print('\n3. 检查相似文档是否存在')
    result = check_document_exists.invoke({
        'collection_name': 'test_smart_upsert',
        'text': '人工智能技术是模拟人类智能的方法',
        'similarity_threshold': 0.7
    })
    print(result)
    
    # 智能添加/更新（应该更新）
    print('\n4. 智能添加/更新（相似文档应被更新）')
    result = smart_upsert_document.invoke({
        'collection_name': 'test_smart_upsert',
        'text': '人工智能(AI)是一种模拟和扩展人类智能的先进技术',
        'similarity_threshold': 0.7
    })
    print(result)
    
    # 智能添加/更新（应该添加新文档）
    print('\n5. 智能添加/更新（不相似，应添加新文档）')
    result = smart_upsert_document.invoke({
        'collection_name': 'test_smart_upsert',
        'text': '量子计算是利用量子力学原理进行计算的新型计算范式',
        'similarity_threshold': 0.85
    })
    print(result)
    
    # 查看最终结果
    print('\n6. 搜索验证')
    result = search_documents.invoke({
        'collection_name': 'test_smart_upsert',
        'query': '智能技术',
        'limit': 5
    })
    print(result)
    
    # 清理
    print('\n7. 清理测试数据')
    result = delete_collection.invoke({'collection_name': 'test_smart_upsert'})
    print(result)
    
    print('=' * 60)
    print('智能添加/更新测试完成!')


def visualize_graph():
    """可视化 Agent Graph"""
    try:
        # 获取 Graph 的 Mermaid 图
        mermaid_png = kb_manager_graph.get_graph().draw_mermaid_png()
        with open('kb_manager_graph.png', 'wb') as f:
            f.write(mermaid_png)
        print('✅ Graph 可视化已保存到 kb_manager_graph.png')
    except Exception as e:
        print(f'⚠️ 无法生成可视化: {e}')
        # 打印 ASCII 图
        print('\nGraph 结构:')
        print(kb_manager_graph.get_graph().draw_ascii())


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description='知识库管理 Agent 测试')
    parser.add_argument('--visualize', '-v', action='store_true', help='生成 Graph 可视化')
    parser.add_argument('--test', '-t', action='store_true', help='运行基础工具测试')
    parser.add_argument('--smart', '-s', action='store_true', help='运行智能添加/更新测试')
    args = parser.parse_args()
    
    if args.visualize:
        visualize_graph()
    elif args.test:
        test_tools()
    elif args.smart:
        test_smart_upsert()
    else:
        # 默认运行智能测试
        test_smart_upsert()


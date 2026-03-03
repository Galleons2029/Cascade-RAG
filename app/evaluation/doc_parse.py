# -*- coding: utf-8 -*-
# @Time   : 2025/8/26 16:46
# @Author : Galleons
# @File   : doc_parse.py

"""
文档上传
"""

import uuid

from app.core.mq import publish_to_rabbitmq
from app.configs import llm_config, qdrant_config
from app.core import logger_utils
from app.pipeline.feature_pipeline.models.raw import DocumentRawModel
from qdrant_client import QdrantClient, models

logger = logger_utils.get_logger(__name__)

# 使用配置中的 Qdrant 连接信息，兼容 Docker 和本地部署
client = QdrantClient(host=qdrant_config.QDRANT_DATABASE_HOST, port=qdrant_config.QDRANT_DATABASE_PORT)

collection_name = "test1"
try:
    client.get_collection(collection_name=collection_name)
except Exception:
    logger.warning(
        "无法访问集合。正在创建新集合...",
        collection_name=collection_name,
    )
    client.create_collection(
        collection_name=collection_name,
        vectors_config=models.VectorParams(size=llm_config.EMBEDDING_SIZE, distance=models.Distance.COSINE),
        quantization_config=models.ScalarQuantization(
            scalar=models.ScalarQuantizationConfig(
                type=models.ScalarType.INT8,
                quantile=0.99,
                always_ram=True,
            ),
        ),
    )


doc = """
Abstract
Large Language Models (LLMs) have revolutionized artificial intelligence (AI) by enabling human-like text generation and natural language understanding. However, their reliance on static training data limits their ability to respond to dynamic, real-time queries, resulting in outdated or inaccurate outputs. Retrieval-Augmented Generation (RAG) has emerged as a solution, enhancing LLMs by integrating real-time data retrieval to provide contextually relevant and up-to-date responses. Despite its promise, traditional RAG systems are constrained by static workflows and lack the adaptability required for multi-step reasoning and complex task management.

Agentic Retrieval-Augmented Generation (Agentic RAG) transcends these limitations by embedding autonomous AI agents into the RAG pipeline. These agents leverage agentic design patterns reflection, planning, tool use, and multi-agent collaboration to dynamically manage retrieval strategies, iteratively refine contextual understanding, and adapt workflows through clearly defined operational structures ranging from sequential steps to adaptive collaboration. This integration enables Agentic RAG systems to deliver unparalleled flexibility, scalability, and context-awareness across diverse applications.

This survey provides a comprehensive exploration of Agentic RAG, beginning with its foundational principles and the evolution of RAG paradigms. It presents a detailed taxonomy of Agentic RAG architectures, highlights key applications in industries such as healthcare, finance, and education, and examines practical implementation strategies. Additionally, it addresses challenges in scaling these systems, ensuring ethical decision-making, and optimizing performance for real-world applications, while providing detailed insights into frameworks and tools for implementing Agentic RAG 1. The GitHub link for this survey is available at: https://github.com/asinghcsu/AgenticRAG-Survey.

Keywords Large Language Models (LLMs)  
⋅
 Artificial Intelligence (AI)  
⋅
 Natural Language Understanding  
⋅
 Retrieval-Augmented Generation (RAG)  
⋅
 Agentic RAG  
⋅
 Autonomous AI Agents  
⋅
 Reflection  
⋅
 Planning  
⋅
 Tool Use  
⋅
 Multi-Agent Collaboration  
⋅
 Agentic Patterns  
⋅
 Contextual Understanding  
⋅
 Dynamic Adaptability  
⋅
 Scalability  
⋅
 Real-Time Data Retrieval  
⋅
 Taxonomy of Agentic RAG  
⋅
 Healthcare Applications  
⋅
 Finance Applications  
⋅
 Educational Applications  
⋅
 Ethical AI Decision-Making  
⋅
 Performance Optimization  
⋅
 Multi-Step Reasoning

1Introduction
Large Language Models (LLMs) [1, 2] [3], such as OpenAI’s GPT-4, Google’s PaLM, and Meta’s LLaMA, have significantly transformed artificial intelligence (AI) with their ability to generate human-like text and perform complex natural language processing tasks. These models have driven innovation across diverse domains, including conversational agents [4], automated content creation, and real-time translation. Recent advancements have extended their capabilities to multimodal tasks, such as text-to-image and text-to-video generation [5], enabling the creation and editing of videos and images from detailed prompts [6], which broadens the potential applications of generative AI.

Despite these advancements, LLMs face significant limitations due to their reliance on static pre-training data. This reliance often results in outdated information, hallucinated responses [7], and an inability to adapt to dynamic, real-world scenarios. These challenges emphasize the need for systems that can integrate real-time data and dynamically refine responses to maintain contextual relevance and accuracy.

Retrieval-Augmented Generation (RAG) [8, 9] emerged as a promising solution to these challenges. By combining the generative capabilities of LLMs with external retrieval mechanisms [10], RAG systems enhance the relevance and timeliness of responses. These systems retrieve real-time information from sources such as knowledge bases [11], APIs, or the web, effectively bridging the gap between static training data and the demands of dynamic applications. However, traditional RAG workflows remain limited by their linear and static design, which restricts their ability to perform complex multi-step reasoning, integrate deep contextual understanding, and iteratively refine responses.

The evolution of agents [12] has significantly enhanced the capabilities of AI systems. Modern agents, including LLM-powered and mobile agents [13], are intelligent entities capable of perceiving, reasoning, and autonomously executing tasks. These agents leverage agentic patterns, such as reflection [14], planning [15], tool use, and multi-agent collaboration [16], to enhance decision-making and adaptability.

Furthermore, these agents employ agentic workflow patterns [12, 13], such as prompt chaining, routing, parallelization, orchestrator-worker models, and evaluator-optimizer , to structure and optimize task execution. By integrating these patterns, Agentic RAG systems can efficiently manage dynamic workflows and address complex problem-solving scenarios. The convergence of RAG and agentic intelligence has given rise to Agentic Retrieval-Augmented Generation (Agentic RAG) [14], a paradigm that integrates agents into the RAG pipeline. Agentic RAG enables dynamic retrieval strategies, contextual understanding, and iterative refinement [15], allowing for adaptive and efficient information processing. Unlike traditional RAG, Agentic RAG employs autonomous agents to orchestrate retrieval, filter relevant information, and refine responses, excelling in scenarios requiring precision and adaptability. The overview of Agentic RAG is in figure 1.

This survey explores the foundational principles, taxonomy, and applications of Agentic RAG. It provides a comprehensive overview of RAG paradigms, such as Naïve RAG, Modular RAG, and Graph RAG [16], alongside their evolution into Agentic RAG systems. Key contributions include a detailed taxonomy of Agentic RAG frameworks, applications across domains such as healthcare [17, 18], finance, and education [19], and insights into implementation strategies, benchmarks, and ethical considerations.

The structure of this paper is as follows: Section 2 introduces RAG and its evolution, highlighting the limitations of traditional approaches. Section 3 elaborates on the principles of agentic intelligence and agentic patterns. Section 4 elaborates agentic workflow patterns. Section 5 provides a taxonomy of Agentic RAG systems, including single-agent, multi-agent, and graph-based frameworks. Section 6 provides comparative analysis of Agentic RAG frameworks. Section 7 examines applications of Agentic RAG, while Section 8 discusses implementation tools and frameworks. Section 9 focuses on benchmarks and dataset, and Section 10 concludes with future directions for Agentic RAG systems.

Refer to caption
Figure 1:An Overview of Agentic RAG
2Foundations of Retrieval-Augmented Generation
2.1Overview of Retrieval-Augmented Generation (RAG)
Retrieval-Augmented Generation (RAG) represents a significant advancement in the field of artificial intelligence, combining the generative capabilities of Large Language Models (LLMs) with real-time data retrieval. While LLMs have demonstrated remarkable capabilities in natural language processing, their reliance on static pre-trained data often results in outdated or incomplete responses. RAG addresses this limitation by dynamically retrieving relevant information from external sources and incorporating it into the generative process, enabling contextually accurate and up-to-date outputs.

2.2Core Components of RAG
The architecture of RAG systems integrates three primary components (Figure2):

• Retrieveal: Responsible for querying external data sources such as knowledge bases, APIs, or vector databases. Advanced retrievers leverage dense vector search and transformer-based models to improve retrieval precision and semantic relevance.
• Augmentation: Processes retrieved data, extracting and summarizing the most relevant information to align with the query context.
• Generation: Combines retrieved information with the LLM’s pre-trained knowledge to generate coherent, contextually appropriate responses.
Refer to caption
Figure 2:Core Components of RAG
2.3Evolution of RAG Paradigms
The field of Retrieval-Augmented Generation (RAG) has evolved significantly to address the increasing complexity of real-world applications, where contextual accuracy, scalability, and multi-step reasoning are critical. What began as simple keyword-based retrieval has transitioned into sophisticated, modular, and adaptive systems capable of integrating diverse data sources and autonomous decision-making processes. This evolution underscores the growing need for RAG systems to handle complex queries efficiently and effectively.

This section examines the progression of RAG paradigms, presenting key stages of development—Naïve RAG, Advanced RAG, Modular RAG, Graph RAG, and Agentic RAG alongside their defining characteristics, strengths, and limitations. By understanding the evolution of these paradigms, readers can appreciate the advancements made in retrieval and generative capabilities and their application in various domains

2.3.1Naïve RAG
Naïve RAG [20] represents the foundational implementation of retrieval-augmented generation. Figure 3 illustrates the simple retrieve-read workflow of Naive RAG, focusing on keyword-based retrieval and static datasets.. These systems rely on simple keyword-based retrieval techniques, such as TF-IDF and BM25, to fetch documents from static datasets. The retrieved documents are then used to augment the language model’s generative capabilities.

Refer to caption
Figure 3:An Overview of Naive RAG.
Naïve RAG is characterized by its simplicity and ease of implementation, making it suitable for tasks involving fact-based queries with minimal contextual complexity. However, it suffers from several limitations:

• Lack of Contextual Awareness: Retrieved documents often fail to capture the semantic nuances of the query due to reliance on lexical matching rather than semantic understanding.
• Fragmented Outputs: The absence of advanced preprocessing or contextual integration often leads to disjointed or overly generic responses.
• Scalability Issues: Keyword-based retrieval techniques struggle with large datasets, often failing to identify the most relevant information.
Despite these limitations, Naïve RAG systems provided a critical proof-of-concept for integrating retrieval with generation, laying the foundation for more sophisticated paradigms.

2.3.2Advanced RAG
Advanced RAG [20] systems build upon the limitations of Naïve RAG by incorporating semantic understanding and enhanced retrieval techniques. Figure 4 highlights the semantic enhancements in retrieval and the iterative, context-aware pipeline of Advanced RAG. These systems leverage dense retrieval models, such as Dense Passage Retrieval (DPR), and neural ranking algorithms to improve retrieval precision.

Refer to caption
Figure 4:Overview of Advanced RAG
Key features of Advanced RAG include:

• Dense Vector Search: Queries and documents are represented in high-dimensional vector spaces, enabling better semantic alignment between the user query and retrieved documents.
• Contextual Re-Ranking: Neural models re-rank retrieved documents to prioritize the most contextually relevant information.
• Iterative Retrieval: Advanced RAG introduces multi-hop retrieval mechanisms, enabling reasoning across multiple documents for complex queries.
These advancements make Advanced RAG suitable for applications requiring high precision and nuanced understanding, such as research synthesis and personalized recommendations. However, challenges such as computational overhead and limited scalability persist, particularly when dealing with large datasets or multi-step queries.

2.3.3Modular RAG
Modular RAG [20] represents the latest evolution in RAG paradigms, emphasizing flexibility and customization. These systems decompose the retrieval and generation pipeline into independent, reusable components, enabling domain-specific optimization and task adaptability. Figure 5 demonstrates the modular architecture, showcasing hybrid retrieval strategies, composable pipelines, and external tool integration.

Key innovations in Modular RAG include:

• Hybrid Retrieval Strategies: Combining sparse retrieval methods (e.g., a sparse encoder-BM25) with dense retrieval techniques [21] (e.g., DPR - Dense Passage Retrieval ) to maximize accuracy across diverse query types.
• Tool Integration: Incorporating external APIs, databases, or computational tools to handle specialized tasks, such as real-time data analysis or domain-specific computations.
• Composable Pipelines: Modular RAG enables retrievers, generators, and other components to be replaced, enhanced, or reconfigured independently, allowing high adaptability to specific use cases.
For instance, a Modular RAG system designed for financial analytics might retrieve live stock prices via APIs, analyze historical trends using dense retrieval, and generate actionable investment insights through a tailored language model. This modularity and customization make Modular RAG ideal for complex, multi-domain tasks, offering both scalability and precision.

Refer to caption
Figure 5:Overview of Modular RAG
2.3.4Graph RAG
Graph RAG [16] extends traditional Retrieval-Augmented Generation systems by integrating graph-based data structures as illustrated in Figure 6. These systems leverage the relationships and hierarchies within graph data to enhance multi-hop reasoning and contextual enrichment. By incorporating graph-based retrieval, Graph RAG enables richer and more accurate generative outputs, particularly for tasks requiring relational understanding.

Graph RAG is characterized by its ability to:

• Node Connectivity: Captures and reasons over relationships between entities.
• Hierarchical Knowledge Management: Handles structured and unstructured data through graph-based hierarchies.
• Context Enrichment: Adds relational understanding by leveraging graph-based pathways.
However, Graph RAG has some limitations:

• Limited Scalability: The reliance on graph structures can restrict scalability, especially with extensive data sources.
• Data Dependency: High-quality graph data is essential for meaningful outputs, limiting its applicability in unstructured or poorly annotated datasets.
• Complexity of Integration: Integrating graph data with unstructured retrieval systems increases design and implementation complexity.
Refer to caption
Figure 6:Overview of Graph RAG
Graph RAG is well-suited for applications such as healthcare diagnostics, legal research, and other domains where reasoning over structured relationships is crucial.

2.3.5Agentic RAG
Agentic RAG represents a paradigm shift by introducing autonomous agents capable of dynamic decision-making and workflow optimization. Unlike static systems, Agentic RAG employs iterative refinement and adaptive retrieval strategies to address complex, real-time, and multi-domain queries. This paradigm leverages the modularity of retrieval and generation processes while introducing agent-based autonomy.

Key characteristics of Agentic RAG include:

• Autonomous Decision-Making: Agents independently evaluate and manage retrieval strategies based on query complexity.
• Iterative Refinement: Incorporates feedback loops to improve retrieval accuracy and response relevance.
• Workflow Optimization: Dynamically orchestrates tasks, enabling efficiency in real-time applications.
Despite its advancements, Agentic RAG faces some challenges:

• Coordination Complexity: Managing interactions between agents requires sophisticated orchestration mechanisms.
• Computational Overhead: The use of multiple agents increases resource requirements for complex workflows.
• Scalability Limitations: While scalable, the dynamic nature of the system can strain computational resources for high query volumes.
Agentic RAG excels in domains like customer support, financial analytics, and adaptive learning platforms, where dynamic adaptability and contextual precision are paramount."""  # noqa: E501


data = DocumentRawModel(
    knowledge_id=collection_name,
    doc_id="222",
    path="file",
    filename="file",
    content=doc,
    type="documents",
    entry_id=str(uuid.uuid4()),
).model_dump_json()


publish_to_rabbitmq(queue_name="test_files", data=data)
logger.info(f"成功处理并发送文件：{data}")

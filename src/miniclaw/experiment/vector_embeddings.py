"""
使用 bge-m3
下载：https://huggingface.co/BAAI/bge-m3/tree/main 在 Files and versions 页面将所有的文件下载到指定文件夹 比如：D:\wormsleep\workspace\aigc\bge-m3
下面的示例使用的是官方的示例
"""

from sentence_transformers import SentenceTransformer

model = SentenceTransformer(r"D:\wormsleep\workspace\aigc\bge-m3")

sentences = [
    "That is a happy person",
    "That is a happy dog",
    "That is a very happy person",
    "Today is a sunny day"
]
embeddings = model.encode(sentences)

similarities = model.similarity(embeddings, embeddings)
print(similarities.shape)

"""
pip install pymilvus
"""
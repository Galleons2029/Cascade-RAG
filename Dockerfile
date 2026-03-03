# langgraph dockerfile -c langgraph.json Dockerfile

FROM langchain/langgraph-api:3.12

ARG DEBIAN_MIRROR=mirrors.tuna.tsinghua.edu.cn
ARG PYPI_MIRROR=https://pypi.tuna.tsinghua.edu.cn/simple
ARG PYPI_HOST=pypi.tuna.tsinghua.edu.cn

ENV PIP_INDEX_URL=${PYPI_MIRROR} \
    PIP_TRUSTED_HOST=${PYPI_HOST} \
    UV_INDEX_URL=${PYPI_MIRROR} \
    UV_EXTRA_INDEX_URL=${PYPI_MIRROR}

WORKDIR /deps/Bank-copilot

# -- Configure apt & pip to use domestic mirror --
RUN set -eux; \
    if [ -f /etc/apt/sources.list ]; then \
        sed -i "s@deb.debian.org@${DEBIAN_MIRROR}@g" /etc/apt/sources.list; \
        sed -i "s@security.debian.org@${DEBIAN_MIRROR}@g" /etc/apt/sources.list; \
    fi; \
    pip config set global.index-url "${PIP_INDEX_URL}"; \
    pip config set global.trusted-host "${PIP_TRUSTED_HOST}"; \
    rm -rf /var/lib/apt/lists/*
# -- End of apt mirror configuration --

# -- Adding local package . --
COPY pyproject.toml uv.lock README.md ./
COPY requirements-langgraph.txt ./
COPY app ./app
# -- End of local package . --

# -- Installing minimal dependencies for langgraph agent --
RUN PYTHONDONTWRITEBYTECODE=1 uv pip install \
    --system --no-cache-dir \
    -c /api/constraints.txt \
    -r requirements-langgraph.txt \
    --index-url "${PIP_INDEX_URL}"
# -- End of minimal dependencies install --

# -- Copy the rest of the source after dependency installation for better caching --
COPY . .
# -- End of copying remaining sources --

ENV LANGSERVE_GRAPHS='{"agent": "/deps/Bank-copilot/app/core/agent/graph/instructor_agent.py:instructor_agent"}'

# -- Ensure user deps didn't inadvertently overwrite langgraph-api
RUN mkdir -p /api/langgraph_api /api/langgraph_runtime /api/langgraph_license && touch /api/langgraph_api/__init__.py /api/langgraph_runtime/__init__.py /api/langgraph_license/__init__.py
RUN PYTHONDONTWRITEBYTECODE=1 uv pip install --system --no-cache-dir --no-deps -e /api
# -- End of ensuring user deps didn't inadvertently overwrite langgraph-api --
# -- Removing build deps from the final image ~<:===~~~ --
RUN pip uninstall -y pip setuptools wheel
RUN rm -rf /usr/local/lib/python*/site-packages/pip* /usr/local/lib/python*/site-packages/setuptools* /usr/local/lib/python*/site-packages/wheel* && find /usr/local/bin -name "pip*" -delete || true
RUN rm -rf /usr/lib/python*/site-packages/pip* /usr/lib/python*/site-packages/setuptools* /usr/lib/python*/site-packages/wheel* && find /usr/bin -name "pip*" -delete || true
RUN uv pip uninstall --system pip setuptools wheel && rm /usr/bin/uv /usr/bin/uvx

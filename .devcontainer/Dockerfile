# See here for image contents: https://github.com/microsoft/vscode-dev-containers/blob/v0.202.3/containers/python-3/.devcontainer/base.Dockerfile
# [Choice] Python version (use -bullseye variants on local arm64/Apple Silicon): 3, 3.9, 3.8, 3.7, 3.6, 3-bullseye, 3.9-bullseye, 3.8-bullseye, 3.7-bullseye, 3.6-bullseye, 3-buster, 3.9-buster, 3.8-buster, 3.7-buster, 3.6-buster
ARG VARIANT="3.10-bullseye"
FROM mcr.microsoft.com/vscode/devcontainers/python:0-${VARIANT}

# [Choice] Node.js version: none, lts/*, 16, 14, 12, 10
ARG NODE_VERSION="none"
RUN if [ "${NODE_VERSION}" != "none" ]; then su vscode -c "umask 0002 && . /usr/local/share/nvm/nvm.sh && nvm install ${NODE_VERSION} 2>&1"; fi

# install poetry - respects $POETRY_VERSION & $POETRY_HOME

RUN echo "export PROMPT_COMMAND='history -a'" >> /home/vscode/.bashrc \
    && echo "export HISTFILE=~/commandhistory/.bash_history" >> /home/vscode/.bashrc \
    && chown vscode:vscode -R /home/vscode/


ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=off \
    PIP_DISABLE_PIP_VERSION_CHECK=on \
    PIP_DEFAULT_TIMEOUT=100 \
    POETRY_HOME="/opt/poetry" \
    POETRY_VIRTUALENVS_CREATE=false

# prepend poetry and venv to path
ENV PATH="$POETRY_HOME/bin:$PATH"

RUN curl -sSL https://install.python-poetry.org | python -
# RUN poetry config virtualenvs.create false

RUN apt-get update \
    && apt-get install --no-install-recommends -y \
    curl \
    build-essential \
    gnupg gnupg2 gnupg1
#     && pip install -U --no-cache-dir pip

# AWS SAM CLI
RUN wget "https://github.com/aws/aws-sam-cli/releases/latest/download/aws-sam-cli-linux-x86_64.zip" -O "aws-sam-cli-linux-x86_64.zip"
RUN unzip aws-sam-cli-linux-x86_64.zip -d sam-installation
RUN sam-installation/install
